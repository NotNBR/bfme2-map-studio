"""Map projects: the registry of maps/*/map.toml and the build pipeline.

A project is a folder in maps/ with a map.toml and a map.py that describes
the map:

    def build(b):            # b: Build
        m = ...              # a formats.map.Map, e.g. from mapkit.blank.create
        b.save(m, ini=...)   # writes the .map, map.ini and minimap

The pipeline does the rest: it builds into a fresh history folder, swaps the
result into local/build/<id>/ only when the build succeeds (an open viewer
reloads it), then renders the minimap, compares with the previous build and
runs its checks, and keeps the last builds in local/history/<id>/. Slow
calculations are reused from earlier builds (mapkit.memo, Build.cached).

Older projects with a build.py and main() are run through the same pipeline;
their OUT, CHECK and TARGET globals are pointed at the run's folders.
"""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib

from mapworkshop.config import BUILD, HISTORY, MAPS, ROOT, PROFILE, save_setting, setting

KEEP_BUILDS = 5


@dataclass
class Project:
    folder: Path
    config: dict = field(repr=False)

    @property
    def id(self):
        return self.config['id']

    @property
    def title(self):
        return self.config.get('title', self.id)

    @property
    def native_name(self):
        return self.config['native_name']

    @property
    def players(self):
        return self.config.get('players')

    @property
    def description(self):
        return self.config.get('description', '')

    @property
    def weather(self):
        """The weather preset (mapkit.weather.PRESETS); 'clear' when map.toml names none."""
        from mapworkshop.mapkit.weather import PRESETS
        name = self.config.get('weather', 'clear')
        if name not in PRESETS:
            raise ValueError(f'{self.folder.name}/map.toml: unknown weather {name!r}; use one of {", ".join(PRESETS)}')
        return name

    @property
    def build_dir(self):
        return BUILD/self.id

    @property
    def map_file(self):
        """The latest build's .map file (may not exist yet)."""
        return self.build_dir/(self.native_name + '.map')

    @property
    def module_name(self):
        entry = 'map' if (self.folder/'map.py').exists() else 'build'
        return f'maps.{self.folder.name}.{entry}'

    def sources(self):
        return sorted(p for p in self.folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)


def projects():
    found = []
    for path in sorted(MAPS.glob('*/map.toml')):
        config = tomllib.loads(path.read_text(encoding='utf-8'))
        if 'id' in config and 'native_name' in config:
            found.append(Project(path.parent, config))
    return found


def find(name=None):
    """The project for an id, folder name, title or unique prefix of one; with
    no name, the last opened or built project."""
    every = projects()
    if not every:
        raise LookupError('No map projects in maps/; create one with `mw new "<title>"`')
    if not name:
        name = setting('last_map')
        if not name:
            if len(every) == 1:
                return every[0]
            raise LookupError('Which map? ' + ', '.join(p.id for p in every))
    key = name.lower().replace('_', '-').replace(' ', '-')
    for p in every:
        if key in (p.id, p.folder.name.replace('_', '-'), p.native_name.replace(' ', '-'),
                   p.title.lower().replace(' ', '-')):
            return p
    matches = [p for p in every if p.id.startswith(key) or p.title.lower().replace('the ', '', 1).replace(' ', '-').startswith(key)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise LookupError(f'"{name}" matches ' + ', '.join(p.id for p in matches) + '; be more specific')
    raise LookupError(f'No map project "{name}". Projects: ' + ', '.join(p.id for p in every))


def here(source):
    """The project a map's own source file belongs to, for code that runs
    without a Build: `PROJECT = here(__file__)` in an older build.py."""
    folder = Path(source).resolve().parent
    for p in projects():
        if p.folder.resolve() == folder:
            return p
    raise LookupError(f'No map project with a map.toml in {folder}')


def for_map_file(path):
    """The project whose build is this .map file, or None."""
    path = Path(path).resolve()
    for p in projects():
        if p.map_file.resolve() == path:
            return p
    return None


def remember(project):
    save_setting('last_map', project.id)


class Build:
    """What a project's build(b) works with."""

    def __init__(self, project, work, out, args=()):
        self.project = project
        self.work = work          # this run's folder: previews, reports, checkpoints
        self.out = out            # the map folder being built
        self.args = list(args)    # extra command-line arguments for the project
        self._assets = None
        self.report = {}
        self.minimap_due = None   # what save() left for the pipeline: True (render), or a fallback image

    @property
    def assets(self):
        if self._assets is None:
            from mapworkshop.assets.library import GameAssets
            self._assets = GameAssets.shared()
        return self._assets

    @property
    def map_file(self):
        return self.out/(self.project.native_name + '.map')

    def image(self, name, image):
        """Save a preview image of this build (e.g. a layout plan)."""
        image.save(self.work/name)

    def save(self, m, ini='', minimap=None, fallback=None):
        """Write the map, its map.ini and the in-game minimap (_art/_pic.tga).
        Without a `minimap` image, the pipeline renders it from the map from
        above once the build is published (the viewer reloads meanwhile), or
        uses `fallback` (an image, e.g. a layout plan) where it cannot render
        one (no GPU)."""
        data = m.encode() if hasattr(m, 'encode') else bytes(m)
        self.map_file.write_bytes(data)
        title = self.project.title
        (self.out/'map.ini').write_text((f'; {title}\n' + ini) if ini else f'; {title}\n', encoding='ascii')
        if minimap is None:
            self.minimap_due = fallback if fallback is not None else True
        else:
            self.minimap_due = None
            _write_minimap(self.out, self.project.native_name, minimap)
        return self.map_file

    def cached(self, fn, *args, **kwargs):
        """fn(*args, **kwargs), or a copy of its result from an earlier build
        when the call, the code it reaches in the project, the project's other
        files and the toolkit are all unchanged (mapkit.memo.stage). For
        slow stages that depend on nothing else: `t = b.cached(terrain)`."""
        from mapworkshop.mapkit.memo import stage
        return stage(fn, *args, root=self.project.folder, **kwargs)


def _write_minimap(folder, name, image):
    from PIL import Image
    image = image.resize((256, 256), Image.Resampling.LANCZOS) if image.size != (256, 256) else image
    for suffix in ('_art.tga', '_pic.tga'):
        image.save(folder/(name + suffix))


def render_minimap(path):
    """A top-down render of the map for its minimap, or None without a GPU."""
    try:
        import numpy as np
        from PIL import Image
        from mapworkshop.render.camera import TopView
        from mapworkshop.render.engine import MapRenderer
        from mapworkshop.assets.library import GameAssets
        renderer = MapRenderer(path, assets=GameAssets.shared(), objects=True, clouds=False)
        width, height = renderer.playable
        top = renderer.render(TopView(), (1350, max(1, round(1350*height/width))))
        image = Image.fromarray(top).resize((256, 256), Image.Resampling.LANCZOS)
        return Image.fromarray(np.clip(np.asarray(image, float)*1.35 + 8, 0, 255).astype('uint8'))
    except Exception as error:
        print('Minimap render unavailable:', error)
        return None


def _git(*args):
    try:
        return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _digest(paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(p.relative_to(ROOT).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _legacy(module, b):
    """Run an older build.py main() inside the pipeline's folders."""
    module.OUT = b.work
    module.CHECK = b.work/'checkpoints'
    module.TARGET = b.out
    previous = sys.argv
    sys.argv = [f'mw build {b.project.id}', *b.args]
    try:
        code = module.main()
    finally:
        sys.argv = previous
    if code:
        raise RuntimeError(f'{b.project.id}: build returned {code}')
    # These builds write their report as build.json, which the pipeline's own
    # build record uses; keep it as the report instead.
    if (b.work/'build.json').exists():
        (b.work/'build.json').replace(b.work/'report.json')


def build(project, args=(), progress=print):
    """Build a project; returns the folder of the new build in local/build."""
    started = time.time()
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    work = HISTORY/project.id/stamp
    work.mkdir(parents=True, exist_ok=False)
    out = work/'map'
    out.mkdir()
    b = Build(project, work, out, args)
    record = dict(project=project.id, profile=PROFILE, started=stamp, commit=_git('rev-parse', 'HEAD'),
                  dirty=bool(_git('status', '--porcelain', '--', 'maps', 'src')), sources_sha256=_digest(project.sources()))
    try:
        for name in [n for n in sys.modules if n == f'maps.{project.folder.name}' or n.startswith(f'maps.{project.folder.name}.')]:
            del sys.modules[name]   # pick up edits when `mw dev` rebuilds in one process
        module = importlib.import_module(project.module_name)
        if hasattr(module, 'build'):
            module.build(b)
        else:
            _legacy(module, b)
        if not b.map_file.exists():
            raise RuntimeError(f'{project.id}: the build wrote no {b.map_file.name}')
        set_properties = _apply_properties(project, b)
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}', seconds=round(time.time() - started, 1))
        (work/'build.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        raise
    data = b.map_file.read_bytes()
    record.update(status='built', seconds=round(time.time() - started, 1), map_sha256=hashlib.sha256(data).hexdigest(),
                  map_bytes=len(data))
    if b.report:
        (work/'report.json').write_text(json.dumps(b.report, indent=2, default=str) + '\n', encoding='utf-8')
    (work/'build.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    # Publish first: an open viewer reloads the map while the minimap, the
    # comparison and the checks below run.
    _publish(project, work)
    remember(project)
    progress(f'Built {project.title} in {record["seconds"]:.0f} s: {project.build_dir}')
    if set_properties:
        progress('Map properties from map.toml over the build\'s own:')
        for line in set_properties:
            progress('  ' + line)
    try:
        _minimap(project, b, work, stamp)
    except Exception as error:   # the map is out: a minimap never fails the build
        progress(f'(No minimap: {error})')
    since, changes = _changes(project, work)
    if changes is not None:
        record.update(changes_since=since, changes=changes)
    concerns = _template_concerns(b)
    if concerns:
        record['template_concerns'] = concerns
    ini_concerns = _ini_concerns(b)
    if ini_concerns:
        record['ini_concerns'] = ini_concerns
    record['seconds_with_checks'] = round(time.time() - started, 1)
    _update_record(project, work, record, stamp)
    _prune(project)
    from mapworkshop.mapkit import memo
    if memo.stats['reused']:
        progress(f'Reused {memo.stats["reused"]} of {memo.stats["reused"] + memo.stats["calculated"]} '
                 'calculations from earlier builds (`--no-cache` makes them again)')
    if since:
        progress(f'Changes since the build of {since} (`mw diff {project.id}`):')
    for line in changes or ():
        progress('  ' + line)
    if concerns:
        progress('Placed templates to know about (`mw item NAME --info`):')
        for line in concerns:
            progress('  ' + line)
    if ini_concerns:
        progress('map.ini definitions the game will not take:')
        for line in ini_concerns:
            progress('  ' + line)
    return project.build_dir


def _ours(project, stamp):
    """Whether local/build/<id>/ still holds the build started at `stamp`."""
    try:
        return json.loads((project.build_dir/'build.json').read_text(encoding='utf-8')).get('started') == stamp
    except (OSError, ValueError):
        return False


def _minimap(project, b, work, stamp):
    """The minimap save() left to the pipeline, after publishing: the
    previous build's when the map and map.ini are unchanged, else rendered
    (or the build's fallback image without a GPU). Written to this run's
    folder and, while it is still the latest, to local/build/<id>/."""
    if b.minimap_due is None:
        return
    name = project.native_name
    image = None
    try:
        previous = previous_build(project, latest=work)
        if previous is not None and previous.read_bytes() == b.map_file.read_bytes() \
                and (previous.parent/'map.ini').read_bytes() == (b.out/'map.ini').read_bytes() \
                and all((previous.parent/(name + s)).exists() for s in ('_art.tga', '_pic.tga')):
            for suffix in ('_art.tga', '_pic.tga'):
                shutil.copy2(previous.parent/(name + suffix), b.out/(name + suffix))
            image = True
    except OSError:
        pass
    if image is None:
        image = render_minimap(b.map_file)
        if image is None and b.minimap_due is not True:
            image = b.minimap_due
        if image is None:
            return
        _write_minimap(b.out, name, image)
    if _ours(project, stamp):
        from PIL import Image
        for suffix in ('_art.tga', '_pic.tga'):
            shutil.copy2(b.out/(name + suffix), project.build_dir/(name + suffix))
        Image.open(b.out/(name + '_art.tga')).convert('RGB').save(project.build_dir/'preview.png')


def _update_record(project, work, record, stamp):
    """build.json again, with what was worked out after publishing."""
    text = json.dumps(record, indent=2) + '\n'
    (work/'build.json').write_text(text, encoding='utf-8')
    if _ours(project, stamp):
        (project.build_dir/'build.json').write_text(text, encoding='utf-8')


def _template_concerns(b):
    """Objects of the built map whose templates the game doesn't define, or
    that are obsolete, cinematic, spawned-only or unowned faction gameplay
    buildings (render.catalog.check_map), as lines. They inform; the build
    still succeeds."""
    try:
        from mapworkshop.formats.map import Map
        from mapworkshop.render import catalog
        ini = b.out/'map.ini'
        return catalog.check_map(b.assets, Map(b.map_file.read_bytes()),
                                   ini.read_text(encoding='ascii', errors='replace') if ini.exists() else '')
    except Exception as error:   # a check never fails the build
        return [f'(No template check: {error})']


def _ini_concerns(b):
    """What the build's map.ini defines that the game will not take
    (render.catalog.check_ini), as lines."""
    try:
        from mapworkshop.render import catalog
        ini = b.out/'map.ini'
        return catalog.check_ini(b.assets, ini.read_text(encoding='ascii', errors='replace')) if ini.exists() else []
    except Exception as error:   # a check never fails the build
        return [f'(No map.ini check: {error})']


def _apply_properties(project, b):
    """Set map.toml's [properties] (mapkit.properties) on the built map and its
    map.ini; returns what they changed, as lines."""
    from mapworkshop.formats.map import Map
    from mapworkshop.mapkit import properties
    overrides = properties.flatten(project.config.get('properties'))
    if not overrides:
        return []
    m = Map(b.map_file.read_bytes())
    ini_path = b.out/'map.ini'
    ini = ini_path.read_text(encoding='ascii') if ini_path.exists() else ''
    ini, changes = properties.apply(m, ini, overrides)
    b.map_file.write_bytes(m.encode())
    ini_path.write_text(ini, encoding='ascii')
    return changes


PROPERTIES_NOTE = "# Map properties set in the viewer's Properties dialog; the build applies them over the map's own."


def _toml(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_toml(v) for v in value) + ']'
    if isinstance(value, float):
        text = repr(value)
        return text if any(c in text for c in '.en') else text + '.0'
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def save_properties(project, overrides, settings=None):
    """Write map-property overrides ({(where, key): value}, mapkit.properties)
    as map.toml's [properties] tables, at its end, and top-level settings
    ({'title': ...}) in place, keeping the rest of the file and its comments.
    Returns the project as read back from the new file."""
    import re
    from mapworkshop.mapkit import properties
    path = project.folder/'map.toml'
    kept, skip = [], False
    for line in path.read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if s.startswith('['):
            skip = s.strip('[]').split('.')[0].strip().strip('"') == 'properties'
        if not skip and s != PROPERTIES_NOTE:
            kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    first_table = next((i for i, line in enumerate(kept) if line.strip().startswith('[')), len(kept))
    for key, value in (settings or {}).items():
        pattern = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*)("(?:[^"\\]|\\.)*"|\'[^\']*\'|[^#\s]+)(.*)$')
        for i in range(first_table):
            found = pattern.match(kept[i])
            if found:
                kept[i] = found.group(1) + _toml(value) + found.group(3)
                break
        else:
            kept.insert(first_table, f'{key} = {_toml(value)}')
            first_table += 1
    tables = properties.nest(overrides)
    if tables:
        kept += ['', PROPERTIES_NOTE]
        for section in [s for s in tables if s != 'ini'] + (['ini'] if 'ini' in tables else []):
            groups = [(f'ini.{block}', fields) for block, fields in tables['ini'].items()] if section == 'ini' \
                else [(section, tables[section])]
            for name, fields in groups:
                kept.append(f'[properties.{name}]')
                kept += [f'{key} = {_toml(value)}' for key, value in fields.items()]
    text = '\n'.join(kept) + '\n'
    config = tomllib.loads(text)
    properties.flatten(config.get('properties'))      # refuse anything the build would refuse
    path.write_text(text, encoding='utf-8', newline='\n')
    return Project(project.folder, config)


def _changes(project, work):
    """What this build changed against the previous successful one, as short
    lines (mapkit.mapdiff), and that build's folder name; (None, None) for a
    first build or when the comparison fails."""
    try:
        from mapworkshop.mapkit import mapdiff
        previous = previous_build(project, latest=work)
        if previous is None:
            return None, None
        result = mapdiff.compare_files(previous, work/'map'/(project.native_name + '.map'))
        return previous.parent.parent.name, mapdiff.lines(result, limit=8)
    except Exception as error:   # a comparison never fails the build
        return None, [f'(No comparison with the previous build: {error})']


def _publish(project, work):
    """Make this run the latest build: local/build/<id>/ gets the map folder,
    build.json, report.json and a preview.png."""
    staging = BUILD/(project.id + '.partial')
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(work/'map', staging)
    for name in ('build.json', 'report.json', 'build-report.json'):
        if (work/name).exists():
            shutil.copy2(work/name, staging/name)
    art = staging/(project.native_name + '_art.tga')
    if art.exists():
        from PIL import Image
        Image.open(art).convert('RGB').save(staging/'preview.png')
    target = project.build_dir
    # The game's pathfinding grid (mw walkable --native) stays while the map is unchanged.
    grid = target/'pathfind.json'
    if grid.exists() and (target/'pathfind.npz').exists():
        map_hash = hashlib.sha256((staging/(project.native_name + '.map')).read_bytes()).hexdigest()
        if json.loads(grid.read_text(encoding='utf-8')).get('map_sha256') == map_hash:
            for name in ('pathfind.json', 'pathfind.npz'):
                shutil.copy2(target/name, staging/name)
    old = BUILD/(project.id + '.old')
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.replace(old)
    try:
        staging.replace(target)
    except OSError:
        # Never leave no build at all: the previous one goes back in place.
        if old.exists() and not target.exists():
            old.replace(target)
        raise
    shutil.rmtree(old, ignore_errors=True)


def _prune(project):
    """Keep the newest KEEP_BUILDS runs, and the two newest successful ones
    however many failed runs came between: the build and the one `mw diff`
    and the next build's changes compare it with (previous_build)."""
    runs = history(project)
    built = [folder for folder, record in runs if record.get('status') == 'built']
    keep = {folder for folder, _ in runs[:KEEP_BUILDS]} | set(built[:2])
    for folder, _ in runs:
        if folder not in keep:
            shutil.rmtree(folder, ignore_errors=True)


def previous_build(project, latest=None):
    """The .map file of the newest successful build before `latest` (a build
    folder), or before the newest one; None if there is none."""
    built = [folder for folder, record in history(project)
             if record.get('status') == 'built' and (folder/'map'/(project.native_name + '.map')).exists()]
    built = [f for f in built if f.name < Path(latest).name] if latest is not None else built[1:]
    return built[0]/'map'/(project.native_name + '.map') if built else None


def history(project):
    """Earlier builds, newest first, as (folder, build.json contents)."""
    folder = HISTORY/project.id
    runs = sorted((p for p in folder.iterdir() if p.is_dir()), reverse=True) if folder.exists() else []
    return [(r, json.loads((r/'build.json').read_text(encoding='utf-8')) if (r/'build.json').exists() else {}) for r in runs]


def run(project, args=(), on_line=None):
    """Build a project in a fresh Python process and return its exit code.

    The process gets a fixed PYTHONHASHSEED: some builds iterate sets of
    template names, and Python randomises string hashing per process, which
    would otherwise make two builds of the same source differ."""
    import os
    env = dict(os.environ, PYTHONHASHSEED='0', PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
    command = [sys.executable, '-m', 'mapworkshop.project', 'build', project.id, *args]
    if on_line is None:
        return subprocess.run(command, cwd=ROOT, env=env).returncode
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace')
    for line in process.stdout:
        on_line(line.rstrip('\n'))
    return process.wait()


class _Output:
    """stdout of a build run by run(): when its reader goes away (the viewer
    closed mid-build), every print would raise OSError (Errno 22 on Windows)
    and fail the build; the output goes to nowhere instead and the build
    finishes and publishes."""

    def __init__(self, stream):
        self.stream = stream

    def _detach(self):
        import os
        self.stream = open(os.devnull, 'w', encoding='utf-8')

    def write(self, text):
        try:
            return self.stream.write(text)
        except OSError:
            self._detach()
            return len(text)

    def flush(self):
        try:
            self.stream.flush()
        except OSError:
            self._detach()

    def __getattr__(self, name):
        return getattr(self.stream, name)


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] != 'build':
        raise SystemExit('usage: python -m mapworkshop.project build <map> [project arguments]')
    sys.stdout = _Output(sys.stdout)
    try:
        build(find(sys.argv[2]), sys.argv[3:])
    except LookupError as error:
        raise SystemExit(str(error))


def map_path(name=None):
    """The .map file for a name: a .map file, a project (id, title or prefix;
    its latest build), or a stock map ("map mp fords of isen"). With no name,
    the last opened or built project."""
    if name and Path(name).is_file():
        return Path(name)
    try:
        p = find(name)
    except LookupError as error:
        if not name:
            raise
        from mapworkshop.config import GAME_DATA
        stem = Path(name.replace('\\', '/')).stem.lower()
        stock = GAME_DATA/'maps'/stem/(stem + '.map')
        if stock.is_file():
            return stock
        matches = sorted((GAME_DATA/'maps').glob(f'*{stem}*/*.map'))
        if len(matches) == 1:
            return matches[0]
        raise LookupError(f'{error}; no stock map "{name}" either') from None
    if not p.map_file.exists():
        raise LookupError(f'{p.title} has not been built yet: run `mw build {p.id}`')
    return p.map_file
