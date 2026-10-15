"""Reuse the results of slow, repeatable calculations across builds.

Builds are deterministic, so a calculation given the same inputs by the same
code gives the same result; this keeps such results in local/cache/memo/ and
hands back a stored copy instead of calculating again. Nothing here changes
what a build makes: a result is found only under a key made of everything
it depends on.

    @pure                                  # toolkit functions of arrays
    def fbm(x, y, scale=900, seed=100, octaves=4): ...

    t = stage(terrain, root=project_folder)   # a project's build stage
                                              # (project.Build.cached)

`pure` is for functions whose result depends only on their arguments and on
their own module: the key is the arguments (arrays by their bytes), the
module's source and the numpy version. Results are arrays or tuples of
arrays, kept as .npz. Calls with small arrays are not worth a file and are
calculated as before.

`stage` is for a project's own build steps. Its key is the stage's
arguments, the code it reaches (the functions, module-level values and
project modules it names, followed through the project's own files), every
other file in the project folder (references, heightmaps), the source of the
toolkit it can call (formats, mapkit and what they import) and the numpy and
Pillow versions. A stage must not
read anything else: no game data, no files outside the project, nothing
reached through an object other than its arguments. A stage that assigns
module globals, or takes or names something the key cannot describe (an open
file, a Build, a random generator), is run every time, with a note.

MW_NO_CACHE=1 (`mw build --no-cache`) calculates everything again and stores
nothing. The cache keeps at most BUDGET bytes, dropping the least recently
used results first.
"""
import dis
import functools
import hashlib
import importlib.util
import inspect
import os
import pickle
import sys
import threading
import types
from pathlib import Path

import numpy as np

from mapworkshop.config import CACHE, ROOT

FOLDER = CACHE/'memo'
BUDGET = 3*1024**3          # bytes on disk
SMALLEST = 50_000           # array elements below which `pure` calls are calculated, not stored
VERSION = b'memo 1'         # change to set every stored result aside
# Where a build's code in src/mapworkshop starts; a stage's key holds these and
# every module they import (_toolkit_files), not the viewer, the game tools,
# video, the command line or the tests.
TOOLKIT = ('__init__.py', 'config.py', 'formats', 'mapkit')

stats = dict(reused=0, calculated=0)
_lock = threading.Lock()
_sizes = None               # {path: bytes} once the folder has been read
_sources = {}               # file -> sha256 of its bytes, for this process
_toolkit = None


class NotCacheable(Exception):
    """The key cannot describe this input: calculate without the cache."""


def enabled():
    return os.environ.get('MW_NO_CACHE', '') in ('', '0')


# Keys -------------------------------------------------------------------------
def _feed(h, value):
    """Feed a stable description of a value to a hash; NotCacheable for what
    has none."""
    if value is None or isinstance(value, (bool, int, float, complex, str)):
        h.update(f'{type(value).__name__}:{value!r};'.encode())
    elif isinstance(value, (bytes, bytearray)):
        h.update(f'bytes:{len(value)};'.encode()); h.update(value)
    elif isinstance(value, (np.ndarray, np.generic)):
        a = np.asarray(value)
        if a.dtype.hasobject:
            raise NotCacheable('an array of Python objects')
        h.update(f'nd:{a.dtype.str}:{a.shape};'.encode())
        h.update(np.ascontiguousarray(a).view(np.uint8).data if a.size else b'')
    elif isinstance(value, (tuple, list)):
        h.update(f'{type(value).__name__}:{len(value)}['.encode())
        for v in value:
            _feed(h, v)
        h.update(b']')
    elif isinstance(value, dict):
        # Insertion order is part of the value: code may iterate it.
        h.update(f'dict:{len(value)}{{'.encode())
        for k, v in value.items():
            _feed(h, k); _feed(h, v)
        h.update(b'}')
    elif isinstance(value, (set, frozenset)):
        parts = []
        for v in value:
            inner = hashlib.sha256(); _feed(inner, v); parts.append(inner.digest())
        h.update(f'{type(value).__name__}:{len(value)};'.encode()); h.update(b''.join(sorted(parts)))
    elif isinstance(value, Path):
        h.update(f'path:{value.as_posix()};'.encode())
    elif isinstance(value, (range, slice)):
        h.update(f'{value!r};'.encode())
    else:
        raise NotCacheable(f'a {type(value).__name__}')


def _file_digest(path):
    path = Path(path)
    key = str(path)
    if key not in _sources:
        _sources[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _sources[key]


def _toolkit_files():
    """The toolkit a build can run: TOOLKIT and every module of src/mapworkshop
    they import, anywhere in their code (read with ast, not run)."""
    import ast
    package = ROOT/'src'/'mapworkshop'

    def module_file(name):
        parts = name.split('.')[1:]
        for p in (package.joinpath(*parts).with_suffix('.py'), package.joinpath(*parts, '__init__.py')):
            if parts and p.is_file():
                return p
        return None

    todo = [p for p in package.rglob('*.py') if p.relative_to(package).parts[0] in TOOLKIT]
    found = set()
    while todo:
        p = todo.pop()
        if p in found or '__pycache__' in p.parts or 'tests' in p.relative_to(package).parts:
            continue
        found.add(p)
        for node in ast.walk(ast.parse(p.read_bytes())):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module] + [f'{node.module}.{a.name}' for a in node.names]
            else:
                continue
            todo += [f for f in map(module_file, (n for n in names if n.startswith('mapworkshop.'))) if f]
    return sorted(found)


def _toolkit_digest():
    """The source of the toolkit a build can run (_toolkit_files): any change
    to it sets stored stages aside."""
    global _toolkit
    if _toolkit is None:
        h = hashlib.sha256()
        package = ROOT/'src'/'mapworkshop'
        for p in _toolkit_files():
            h.update(p.relative_to(package).as_posix().encode()); h.update(p.read_bytes())
        _toolkit = h.hexdigest()
    return _toolkit


def _versions():
    import PIL
    return f'numpy {np.__version__}; Pillow {PIL.__version__}; python {sys.version_info[:2]}'


def _inside(path, root):
    try:
        Path(path).resolve().relative_to(root)
        return True
    except (TypeError, ValueError, OSError):
        return False


def _codes(code):
    """A code object and every code object nested in it."""
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from _codes(const)


def _feed_code(h, code):
    for c in _codes(code):
        h.update(c.co_code)
        h.update(repr(c.co_names).encode()); h.update(repr(c.co_varnames).encode())
        h.update(repr([k for k in c.co_consts if not isinstance(k, types.CodeType)]).encode())
        for ins in dis.get_instructions(c):
            if ins.opname in ('STORE_GLOBAL', 'DELETE_GLOBAL'):
                raise NotCacheable(f'{c.co_name} assigns the module global {ins.argval}')


def _feed_function(h, fn, root, seen):
    """Feed a function's code and everything it names, following functions
    and modules of the project (files under `root`)."""
    if fn in seen:
        h.update(f'seen:{fn.__module__}.{fn.__qualname__};'.encode())
        return
    seen.add(fn)
    h.update(f'function:{fn.__module__}.{fn.__qualname__};'.encode())
    _feed_code(h, fn.__code__)
    _feed(h, fn.__defaults__)
    _feed(h, fn.__kwdefaults__)
    for cell in fn.__closure__ or ():
        _feed_global(h, cell.cell_contents, root, seen)
    names = sorted({n for c in _codes(fn.__code__) for n in c.co_names})
    g = fn.__globals__
    for name in names:
        if name in g:
            h.update(f'global {name}='.encode())
            _feed_global(h, g[name], root, seen)
        elif name.startswith('maps.'):
            # A project module imported inside the function.
            spec = importlib.util.find_spec(name) if name not in sys.modules else None
            origin = getattr(sys.modules.get(name), '__file__', None) or (spec and spec.origin)
            if origin and _inside(origin, root):
                _feed_project(h, root)
            elif origin:
                raise NotCacheable(f'it imports {name}, outside the project')


def _feed_global(h, value, root, seen):
    if isinstance(value, types.FunctionType):
        source = inspect.getsourcefile(value)
        if source and _inside(source, root):
            _feed_function(h, value, root, seen)
        else:
            _feed_outside(h, value)
    elif isinstance(value, types.ModuleType):
        source = getattr(value, '__file__', None)
        if source and _inside(source, root):
            _feed_project(h, root)
        else:
            _feed_outside(h, value)
    elif isinstance(value, (type, types.BuiltinFunctionType, np.ufunc)):
        module = sys.modules.get(getattr(value, '__module__', None) or '')
        source = getattr(module, '__file__', None)
        if source and _inside(source, root):
            _feed_project(h, root)
        else:
            _feed_outside(h, value)
    else:
        _feed(h, value)


def _feed_project(h, root):
    """A project module or class, whose reach is not followed: every Python
    file of the project stands for it."""
    for p in sorted(root.rglob('*.py')):
        if '__pycache__' not in p.parts:
            h.update(f'source {p.relative_to(root).as_posix()}:{_file_digest(p)};'.encode())


def _feed_outside(h, value):
    """Code from the toolkit, the standard library or a package: the toolkit
    digest and the package versions in the key stand for it."""
    module = value.__name__ if isinstance(value, types.ModuleType) else getattr(value, '__module__', None) or ''
    name = getattr(value, '__qualname__', getattr(value, '__name__', ''))
    if not module or module == '__main__' or module.startswith('maps.'):
        raise NotCacheable(f'it names {name or value!r}, from outside the project')
    h.update(f'outside:{module}.{name};'.encode())


def _call_key(fn, args, kwargs):
    """Arguments as bound to fn's parameters, defaults filled in."""
    bound = inspect.signature(fn).bind(*args, **kwargs)
    bound.apply_defaults()
    return list(bound.arguments.items())


# The store --------------------------------------------------------------------
def _path(key, suffix):
    return FOLDER/key[:2]/(key + suffix)


def _load(path, reader):
    try:
        result = reader(path)
    except Exception:            # unreadable, or written by older code: calculate again
        return None
    try:
        os.utime(path)          # recently used: kept longest
    except OSError:
        pass
    return result


def _store(path, writer):
    global _sizes
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
    try:
        writer(temporary)
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        print(f'(Could not keep a calculation in the cache: {error})')
        return
    with _lock:
        if _sizes is None:
            _sizes = {p: p.stat().st_size for p in FOLDER.glob('*/*') if p.suffix in ('.npz', '.pickle')}
        _sizes[path] = path.stat().st_size
        if sum(_sizes.values()) > BUDGET:
            _prune()


def _prune():
    """Drop the least recently used results until the cache fits its budget."""
    entries = []
    for p in list(_sizes):
        try:
            entries.append((p.stat().st_mtime, p))
        except OSError:
            _sizes.pop(p, None)
    total = sum(_sizes.values())
    for _, p in sorted(entries):
        if total <= BUDGET*.8:
            break
        p.unlink(missing_ok=True)
        total -= _sizes.pop(p, 0)


def _read_npz(path):
    with np.load(path, allow_pickle=False) as data:
        kind = str(data['kind'])
        parts = [data[f'r{i}'] for i in range(int(data['count']))]
    return parts[0] if kind == 'array' else tuple(parts)


def _write_npz(result):
    parts = [result] if isinstance(result, np.ndarray) else list(result)
    kind = 'array' if isinstance(result, np.ndarray) else 'tuple'

    def write(path):
        with open(path, 'wb') as f:
            np.savez(f, kind=kind, count=len(parts), **{f'r{i}': p for i, p in enumerate(parts)})
    return write


# The two uses -----------------------------------------------------------------
def pure(fn):
    """Keep fn's results, keyed by its arguments and its module's source.
    fn must return an array or a tuple of arrays, and not change its arguments."""
    source = inspect.getsourcefile(fn)
    name = f'{fn.__module__}.{fn.__qualname__}'

    @functools.wraps(fn)
    def cached(*args, **kwargs):
        if not enabled() or not any(isinstance(a, np.ndarray) and a.size >= SMALLEST
                                    for a in (*args, *kwargs.values())):
            return fn(*args, **kwargs)
        h = hashlib.sha256(VERSION)
        try:
            h.update(f'{name};{_file_digest(source)};numpy {np.__version__};'.encode())
            _feed(h, _call_key(fn, args, kwargs))
        except NotCacheable:
            return fn(*args, **kwargs)
        path = _path(h.hexdigest(), '.npz')
        result = _load(path, _read_npz) if path.exists() else None
        if result is not None:
            stats['reused'] += 1
            return result
        result = fn(*args, **kwargs)
        stats['calculated'] += 1
        if isinstance(result, np.ndarray) or isinstance(result, tuple) and all(isinstance(r, np.ndarray) for r in result):
            _store(path, _write_npz(result))
        return result
    return cached


def stage_key(fn, args=(), kwargs=None, root=None):
    """The key of a stage call (see the module notes); raises NotCacheable."""
    root = Path(root or Path(inspect.getsourcefile(fn)).parent).resolve()
    h = hashlib.sha256(VERSION + b' stage')
    h.update(f'{_versions()};toolkit {_toolkit_digest()};'.encode())
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.suffix not in ('.py', '.pyc', '.md') and '__pycache__' not in p.parts:
            h.update(f'file {p.relative_to(root).as_posix()}:{_file_digest(p)};'.encode())
    _feed_function(h, fn, root, set())
    _feed(h, _call_key(fn, args, kwargs or {}))
    return h.hexdigest()


def stage(fn, *args, root=None, note=print, **kwargs):
    """fn(*args, **kwargs), or the stored result of the same call by the same
    code. Each call returns its own copy, so a build may change it."""
    name = getattr(fn, '__qualname__', repr(fn))
    if not enabled():
        return fn(*args, **kwargs)
    try:
        key = stage_key(fn, args, kwargs, root)
    except NotCacheable as error:
        note(f'(Stage {name} runs every build: {error})')
        return fn(*args, **kwargs)
    path = _path(key, '.pickle')
    if path.exists():
        def read(p):
            with open(p, 'rb') as f:
                return pickle.load(f)
        result = _load(path, read)
        if result is not None:
            note(f'Reused {name}() from an earlier build (`mw build --no-cache` runs it again)')
            return result
    result = fn(*args, **kwargs)
    try:
        data = pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as error:
        note(f'(Stage {name} could not be kept: {error})')
        return result
    _store(path, lambda p: p.write_bytes(data))
    # The caller keeps working on this result; later builds load their own copy.
    return result
