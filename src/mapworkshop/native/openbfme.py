"""OpenBFME: The Rise of the Witch-king 2.01 rebuilt in Godot
(https://github.com/Open-BFME/openbfme-godot), started on a project's build
by `mw play --godot`: straight in a skirmish, through its LAN host, seated
by the project's line-up (play()). The studio's own Godot viewer runs on its
library (assemble()).

The engine's source is the submodule native/openbfme-godot, fetched on first
use (source(), not by `mw setup`) at the commit pinned here: a tag of the fork
NotNBR/openbfme-godot that is OpenBFME's official main with only what the
studio's commands need on top. Which tag, what it carries, how the pin moves
and what clean means (differences()): docs/guide/testing-in-game.md, "The pin
and a clean submodule". Of its studio commits, the code here uses
OPENBFME_EXTRA_ARCHIVES (.big files mounted over the retail archives),
game.gd's --no-shroud (the live game drawn without its shroud and fog, a view
setting: the logic keeps its shroud, as mw play reveals the map in BFME2) and
openbfme_peer's battle log (native/battle.py).
OpenBFME reads maps only from verified archives and ignores loose map files,
so each installed map goes into a .big of its own, and the skirmish list's
maps\\mapcache.ini (retail's, with the maps' entries added) into another.

Nothing is written into the submodule; everything else stays in local/openbfme/:

    tools/      llvm-mingw (the C++ toolchain upstream cross-builds Windows
                with) and Godot, downloaded once, checked against their
                releases' SHA-256
    build/      the engine's CMake build, and openbfme_peer (mw battle)
    project/    the Godot project Godot runs: a copy of the files the
                submodule tracks in godot/ (mirror(), on every build), the
                GDExtension in its bin/, where openbfme.gdextension loads it,
                and what Godot writes there (.godot/, the .uid and .import
                files)
    viewer/     the studio's viewer (assemble()): its Godot project, STUDIO
                (src/mapworkshop/viewer/godot/), with OpenBFME's library and
                the shaders that library loads (viewer_files()), and what Godot
                writes there
    assets/     rotwk/ and bfme2/: every archive OpenBFME's policies list
                (engine/data/retail-archives), hard links to your installs'
                files where their MD5 matches; OpenBFME refuses mod, patch
                2.02 and other-language archives, which those installs may
                hold. download=True fetches the rest from the service the
                OpenBFME launcher uses (its pinned owner, MD5-checked).
    maps/       <native name>.big and .ini (its map-cache entry) per map
    mapcache.big  the merged maps\\mapcache.ini, mounted last
    test/       the viewer's Test mode: a folder per viewer run, the map it
                shows packed with its map-cache entry (pack_for_test)
    appdata/    the APPDATA the game gets: its options, logs and saves stay here
    logs/       build, import and check logs, check-<map>.json;
                import-<project or viewer>.pending while an import is due

OpenBFME has eight player slots; a map lists its first eight starts. Windows
only: the toolchain is llvm-mingw's Windows-hosted build. CMake and Ninja
must be on PATH or in the studio's virtual environment.
"""
import filecmp
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from mapworkshop.config import LOCAL, ROOT, base_game_dir, setting

SOURCE = Path(__file__).resolve().parent/'openbfme-godot'
HOME = LOCAL/'openbfme'
TOOLS, BUILD, PROJECT, VIEWER, ASSETS, MAPS, APPDATA, LOGS = (HOME/n for n in ('tools', 'build', 'project', 'viewer', 'assets',
                                                                                'maps', 'appdata', 'logs'))
MAPCACHE = HOME/'mapcache.big'
TEST = HOME/'test'
STUDIO = Path(__file__).resolve().parents[1]/'viewer'/'godot'         # the studio's Godot project, assembled into VIEWER

LLVM_MINGW = 'llvm-mingw-20261006-ucrt-x86_64'
LLVM_MINGW_URL = f'https://github.com/mstorsjo/llvm-mingw/releases/download/20261006/{LLVM_MINGW}.zip'
LLVM_MINGW_SHA256 = '317492c456aa27ee607a5919f1d2d38dcdc1112516a24d0bf4b00d078f52d17a'   # GitHub's digest
GODOT = 'Godot_v4.7.2-stable_win64'
GODOT_URL = f'https://github.com/godotengine/godot/releases/download/4.7.2-stable/{GODOT}.exe.zip'
GODOT_SHA256 = '731980f9608d61333e5baf54a2ef17210acc7a538446c0cb9969f002aca1e953'          # GitHub's digest
DLL = 'bin/openbfme.windows.template_debug.x86_64.dll'      # in PROJECT and VIEWER: openbfme.gdextension's res://bin/...
GENERATED = ('.godot', 'bin')                                 # the folders Godot and the build write in PROJECT and VIEWER
SHADERS = ('terrain', 'water_standing', 'road', 'river')      # what OpenBFME's library loads by path: res://shaders/<name>.gdshader
LFS_OFF = ('-c', 'filter.lfs.process=', '-c', 'filter.lfs.clean=cat', '-c', 'filter.lfs.smudge=cat', '-c', 'filter.lfs.required=false')
FILES = 'https://workshop-files.bfmeladder.com'      # aio_install.gd's FILES: <owner>/<md5>
INSTALL = {'rotwk': 'ROTWK_INSTALL', 'bfme2': 'BFME2_INSTALL'}
POLICY = {'rotwk': 'rotwk-201', 'bfme2': 'bfme2-106'}

TOOLCHAIN = """# mapworkshop.native.openbfme: llvm-mingw on a Windows host (upstream's
# engine/cmake/toolchains/windows-x64-llvm-mingw.cmake expects the Linux-hosted build's names).
set(LLVM_MINGW_ROOT "{root}" CACHE PATH "llvm-mingw install root")
set(CMAKE_C_COMPILER "${{LLVM_MINGW_ROOT}}/bin/x86_64-w64-mingw32-clang.exe")
set(CMAKE_CXX_COMPILER "${{LLVM_MINGW_ROOT}}/bin/x86_64-w64-mingw32-clang++.exe")
set(CMAKE_RC_COMPILER "${{LLVM_MINGW_ROOT}}/bin/x86_64-w64-mingw32-windres.exe")
set(CMAKE_AR "${{LLVM_MINGW_ROOT}}/bin/llvm-ar.exe")
set(CMAKE_RANLIB "${{LLVM_MINGW_ROOT}}/bin/llvm-ranlib.exe")
set(CMAKE_EXE_LINKER_FLAGS_INIT "-static")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "-static")
"""


# The engine -----------------------------------------------------------------------
def _git(*args, cwd=ROOT):
    result = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(f'git {" ".join(args)}: {(result.stderr or result.stdout).strip()[-400:]}')
    return result.stdout.rstrip()      # a status line's leading space is part of it


def recorded():
    """The commit the studio records for the submodule (its entry in the index), or None."""
    entry = _git('ls-files', '--stage', '--', SOURCE.relative_to(ROOT).as_posix())
    return entry.split()[1] if entry.startswith('160000 ') else None


def differences(path=None, commit=None):
    """How the submodule (or a clone of it at `path`) differs from `commit` (default: recorded()): [] when it is clean.
    Clean is checked out at that commit, every file as the commit has it, compared with Git LFS off (upstream stores four
    plain PNGs under its LFS rule, which Git with LFS reports changed), nothing untracked and nothing its .gitignore
    names (nothing is ever written there), and its own submodules (godot-cpp) the same."""
    path, commit = path or SOURCE, commit or recorded()
    if not (path/'.git').exists():
        return ['not checked out']
    found = []
    head = _git('rev-parse', 'HEAD', cwd=path)
    if commit and head != commit:
        found.append(f'at {head[:8]} instead of the recorded {commit[:8]}')
    found += _git('--no-optional-locks', *LFS_OFF, 'status', '--porcelain', '--ignored', cwd=path).splitlines()
    for entry in _git('ls-files', '--stage', cwd=path).splitlines():
        if entry.startswith('160000 '):                                 # a submodule: mode, commit, stage, path
            sha, name = entry.split()[1], entry.split('\t', 1)[1]
            found += [f'{name}: {d}' for d in differences(path/name, sha)]
    return found


def source(progress=print):
    """The submodule checked out at the commit recorded here (the pin), with its godot-cpp, and Git LFS off in its own
    config, so the studio's git status compares it as differences() does. A submodule at another commit moves to the
    pin, unless a file in it is changed or untracked: that may be someone's unfinished work, so this stops instead."""
    name = SOURCE.relative_to(ROOT).as_posix()
    if not (SOURCE/'engine'/'CMakeLists.txt').exists():
        progress('Fetching the OpenBFME submodule (about 90 MB, once)...')
        _git('submodule', 'update', '--init', '--checkout', '--', name)
    elif (pin := recorded()) and _git('rev-parse', 'HEAD', cwd=SOURCE) != pin:
        if changed := _git('--no-optional-locks', *LFS_OFF, 'status', '--porcelain', cwd=SOURCE).splitlines():
            raise RuntimeError(f'The OpenBFME submodule is not at the pinned {pin[:8]} and has changes ({changed[0].strip()}'
                               f'{" ..." if len(changed) > 1 else ""}): docs/guide/testing-in-game.md, "The pin and a clean '
                               f'submodule"')
        progress(f'Moving the OpenBFME submodule to the pinned {pin[:8]}...')
        _git('submodule', 'update', '--init', '--checkout', '--', name)
    cpp = 'engine/thirdparty/godot-cpp'
    pinned_cpp = _git('ls-files', '--stage', '--', cpp, cwd=SOURCE).split()[1]
    if not (SOURCE/cpp/'.git').exists() or _git('rev-parse', 'HEAD', cwd=SOURCE/cpp) != pinned_cpp:
        _git('submodule', 'update', '--init', cwd=SOURCE)               # godot-cpp at the commit the pin records
    for option in LFS_OFF[1::2]:
        key, value = option.split('=', 1)
        current = subprocess.run(['git', 'config', '--get', key], cwd=SOURCE, capture_output=True, text=True)
        if current.returncode or current.stdout.rstrip('\n') != value:     # unset, or another value ('' for process)
            _git('config', key, value, cwd=SOURCE)
    return SOURCE


def _fetch(url, target, progress=print, sha256=None, md5=None):
    """Download url to target through target.part; the digest must match."""
    import urllib.request
    part = target.with_name(target.name + '.part')
    part.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256() if sha256 else hashlib.md5()
    request = urllib.request.Request(url, headers={'User-Agent': 'bfme2-map-workshop (+https://github.com/Open-BFME/openbfme-godot)'})
    with urllib.request.urlopen(request, timeout=120) as response, part.open('wb') as out:
        while block := response.read(1 << 20):
            digest.update(block)
            out.write(block)
    if digest.hexdigest() != (sha256 or md5):
        part.unlink()
        raise RuntimeError(f'{url} does not match its pinned {"SHA-256" if sha256 else "MD5"}')
    part.replace(target)
    return target


def toolchain(progress=print):
    """llvm-mingw's folder and Godot's (window, console) executables, downloaded once."""
    if os.name != 'nt':
        raise RuntimeError('OpenBFME from the studio needs Windows (llvm-mingw\'s Windows-hosted toolchain)')
    for name, url, sha256, size in ((LLVM_MINGW, LLVM_MINGW_URL, LLVM_MINGW_SHA256, '190 MB'),
                                    (GODOT, GODOT_URL, GODOT_SHA256, '86 MB')):
        done = TOOLS/name/'.complete'
        if done.exists():
            continue
        progress(f'Downloading {name} ({size}, once)...')
        archive = _fetch(url, TOOLS/(url.rsplit('/', 1)[1]), progress, sha256=sha256)
        shutil.rmtree(TOOLS/name, ignore_errors=True)
        with zipfile.ZipFile(archive) as z:
            z.extractall(TOOLS if name == LLVM_MINGW else TOOLS/name)    # llvm-mingw's zip has its own top folder
        archive.unlink()
        done.write_text(sha256, encoding='utf-8')
    return TOOLS/LLVM_MINGW, TOOLS/GODOT/f'{GODOT}.exe', TOOLS/GODOT/f'{GODOT}_console.exe'


def _program(name):
    found = shutil.which(name) or next((str(p) for p in [Path(sys.executable).parent/f'{name}.exe'] if p.exists()), None)
    if not found:
        raise RuntimeError(f'Building OpenBFME needs {name}: install it, or `pip install cmake ninja` into the studio\'s environment')
    return found


def is_built():
    """Whether the GDExtension in PROJECT is built for the submodule's commit (and its uncommitted engine changes) and
    the toolchain: build() then compiles nothing."""
    stamp = BUILD/'stamp.txt'
    return stamp.exists() and stamp.read_text(encoding='utf-8') == _stamp() and (PROJECT/DLL).exists()


def _stamp():
    """What the build depends on: the submodule's commit and any uncommitted change to its engine, the toolchain (godot/
    reaches PROJECT through mirror())."""
    head = _git('rev-parse', 'HEAD', cwd=SOURCE)
    local = _git('diff', 'HEAD', '--', 'engine', cwd=SOURCE)   # an engine edit not committed yet rebuilds too
    return hashlib.sha256(f'{head}\n{LLVM_MINGW}\n{GODOT}\n'.encode() + local.encode('utf-8')).hexdigest()


def mirror(target, files):
    """Make `target` hold `files` ({path in target: the file it copies}; one whose file is missing counts as gone):
    delete every other file and the folders left empty, then copy those new or changed (by size and time, else content;
    copy2 keeps their times, so Godot re-imports only what changed). Deleting first lets a file become a folder, or its
    name change case. Kept: the GENERATED folders, and a .uid or .import file of one of `files`, which Godot writes
    beside the resource unless `files` has it already. Returns how many files it deleted or copied."""
    files, changed = {name: path for name, path in files.items() if path.is_file()}, 0
    folders = []
    for folder, subfolders, names in os.walk(target):
        here = Path(folder)
        if here == target:
            subfolders[:] = [s for s in subfolders if s not in GENERATED]
        else:
            folders.append(here)
        for name in names:
            path = here/name
            relative = path.relative_to(target).as_posix()
            if relative in files or (path.suffix in ('.uid', '.import') and relative.removesuffix(path.suffix) in files):
                continue
            path.unlink()
            changed += 1
    for folder in reversed(folders):                     # the deepest first
        if not any(folder.iterdir()):
            folder.rmdir()
    for name, a in sorted(files.items()):
        b = target/name
        if b.is_file() and filecmp.cmp(a, b):
            continue
        b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a, b)
        changed += 1
    return changed


def _import(project, console, changed, label, progress=print):
    """Godot's import of `project` (PROJECT or VIEWER) when it `changed`, and again while one is due (its marker in LOGS
    stays until an import succeeds, so one that failed or was cut short runs again)."""
    due = LOGS/f'import-{project.name}.pending'
    if changed:
        due.touch()
    if not due.exists():
        return
    listed = project/'.godot'/'extension_list.cfg'      # the library loaded at start, as every import after the first loads it:
    if not listed.exists():                             # loaded halfway through a first scan, it crashed the viewer's import
        listed.parent.mkdir(parents=True, exist_ok=True)    # on exit (0xC0000005), though not OpenBFME's
        listed.write_text('res://openbfme.gdextension\n', encoding='utf-8')
    progress(f'Importing {label}...')
    result = subprocess.run([str(console), '--headless', '--path', str(project), '--import'], env=environment([]),
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=1200)
    if result.returncode:
        log = LOGS/f'import-{project.name}.log'
        log.write_text(result.stdout + result.stderr, encoding='utf-8')
        raise RuntimeError(f'Godot could not import {label}; see {log}')
    due.unlink(missing_ok=True)


def build(progress=print):
    """Bring PROJECT up to date with the submodule's godot/ (mirror()), build the GDExtension into its bin/ and the
    headless openbfme_peer (mw battle), and import it, unless already done for this commit (and its uncommitted engine
    changes) and toolchain. Returns Godot's (window, console) executables."""
    source(progress)
    llvm, gui, console = toolchain(progress)
    BUILD.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    files = {name.removeprefix('godot/'): SOURCE/name for name in _git('ls-files', '-z', '--', 'godot', cwd=SOURCE).split('\0')
             if name}
    changed = mirror(PROJECT, files)
    stamp = BUILD/'stamp.txt'
    built = is_built()
    if not built:
        _compile(llvm, progress)
    _import(PROJECT, console, changed or not built, 'the Godot project', progress)
    if not built:
        stamp.write_text(_stamp(), encoding='utf-8')
    return gui, console


def viewer_files():
    """{path in VIEWER: the file it copies}: the studio's Godot project (STUDIO), and of OpenBFME its library (the
    .gdextension and the built DLL) and the SHADERS it loads by path, with the files they include."""
    files = {p.relative_to(STUDIO).as_posix(): p for p in sorted(STUDIO.rglob('*'))
             if p.is_file() and not set(GENERATED) & set(p.relative_to(STUDIO).parts)}
    library = {'openbfme.gdextension': SOURCE/'godot'/'openbfme.gdextension', DLL: PROJECT/DLL}
    shaders = [f'shaders/{name}.gdshader' for name in SHADERS]
    while shaders:
        name = shaders.pop()
        if name not in library:
            library[name] = SOURCE/'godot'/name
            shaders += re.findall(r'#include\s+"res://([^"]+)"', library[name].read_text(encoding='utf-8'))
    if clash := sorted(files.keys() & library.keys()):
        raise RuntimeError(f'The studio\'s Godot project has files of OpenBFME\'s: {", ".join(clash)}')
    return files | library


def assemble(progress=print):
    """The studio's viewer in VIEWER: OpenBFME built (build()), viewer_files() brought up to date there (mirror()) and
    imported when they changed. Returns Godot's (window, console) executables."""
    gui, console = build(progress)
    _import(VIEWER, console, mirror(VIEWER, viewer_files()), 'the studio\'s viewer', progress)
    return gui, console


def _compile(llvm, progress=print):
    """The engine's CMake build in BUILD, the GDExtension written to PROJECT's bin/."""
    cmake, ninja = _program('cmake'), _program('ninja')
    (BUILD/'toolchain.cmake').write_text(TOOLCHAIN.format(root=llvm.as_posix()), encoding='utf-8')
    env = dict(os.environ, PATH=os.pathsep.join([str(llvm/'bin'), str(Path(ninja).parent), os.environ.get('PATH', '')]),
               PYTHONDONTWRITEBYTECODE='1')     # godot-cpp's binding generator runs in the submodule: no __pycache__ there
    log = LOGS/'build.log'
    with log.open('w', encoding='utf-8') as out:
        steps = [[cmake, '-S', str(SOURCE/'engine'), '-B', str(BUILD), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                  '-DOPENBFME_LAME=OFF', '-DOPENBFME_BUILD_GODOT=ON', f'-DOPENBFME_GODOT_BIN={(PROJECT/"bin").as_posix()}',
                  f'-DCMAKE_MAKE_PROGRAM={ninja}', f'-DPython3_EXECUTABLE={sys.executable}',
                  f'-DCMAKE_TOOLCHAIN_FILE={(BUILD/"toolchain.cmake").as_posix()}'],
                 [cmake, '--build', str(BUILD), '--target', 'openbfme', 'openbfme_peer']]   # the peer: mw battle
        progress('Building the OpenBFME engine (the first build takes a few minutes)...')
        for command in steps:
            process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                       encoding='utf-8', errors='replace')
            shown = 0
            for line in process.stdout:
                out.write(line)
                if m := re.match(r'\[(\d+)/(\d+)\]', line):
                    percent = int(m[1])*100//int(m[2])
                    if percent >= shown + 10:
                        shown = percent - percent % 10
                        progress(f'  {shown}%')
            if process.wait():
                raise RuntimeError(f'The OpenBFME build failed (exit {process.returncode}); see {log}')


# The game's files -------------------------------------------------------------------
def required():
    """{game: [(path, md5, size)]}: every archive of OpenBFME's English policies,
    and RotWK's cursors (pinned in the launcher's download list)."""
    files = {}
    for game, name in POLICY.items():
        policy = json.loads((SOURCE/f'engine/data/retail-archives/{name}-english-archives.json').read_text(encoding='utf-8'))
        files[game] = [(a['path'], a['md5'], a['size']) for a in policy['archives']]
    _, pinned = pins()['rotwk']
    files['rotwk'] += [f for f in pinned if f[0].lower().startswith('data/cursors/')]
    return files


def pins(text=None):
    """{game: (owner, [(path, md5, size)])} from the launcher's aio_pins.gd."""
    text = text if text is not None else (SOURCE/'launcher/scripts/core/aio_pins.gd').read_text(encoding='utf-8')
    found = {}
    for block in text.split('{"key": "')[1:]:
        key = block.split('"', 1)[0]
        owner = re.search(r'"owner": "([0-9a-f-]+)"', block)[1]
        found[key] = owner, [(p, m, int(s)) for p, m, s in re.findall(r'\["([^"]+)", "([0-9a-f]{32})", (\d+)\]', block)]
    return found


class Hashes:
    """MD5s of files, kept in local/openbfme/md5.json by path, size and time."""
    def __init__(self, path):
        self.path = path
        try:
            self.known = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.known = {}

    def md5(self, path):
        stat = path.stat()
        key, seen = str(path.resolve()), self.known.get(str(path.resolve()))
        if seen and seen[:2] == [stat.st_size, stat.st_mtime_ns]:
            return seen[2]
        with path.open('rb') as f:
            digest = hashlib.file_digest(f, 'md5').hexdigest()
        self.known[key] = [stat.st_size, stat.st_mtime_ns, digest]
        return digest

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.known), encoding='utf-8')


def gather(files, target, roots, hashes, fetch=None, progress=print):
    """Put every (path, md5, size) of `files` into `target`: kept if already there,
    else a hard link (or copy) of the first root's file with that MD5, else
    fetch(path, md5, destination) when given. Returns the files still missing."""
    missing = []
    for path, md5, size in files:
        destination = target/path
        if destination.exists() and destination.stat().st_size == size and hashes.md5(destination) == md5:
            continue
        for root in roots:
            candidate = Path(root)/path
            if candidate.is_file() and candidate.stat().st_size == size and hashes.md5(candidate) == md5:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.unlink(missing_ok=True)
                try:
                    os.link(candidate, destination)
                except OSError:
                    shutil.copy2(candidate, destination)
                break
        else:
            if fetch is None:
                missing.append((path, md5, size))
            else:
                progress(f'  downloading {path} ({size/1e6:.1f} MB)')
                fetch(path, md5, destination)
    return missing


def assets(progress=print, download=False, roots=None):
    """local/openbfme/assets/{rotwk,bfme2}, complete and verified. `roots`
    ({game: [folders]}) are searched before the configured installs."""
    roots = roots or {}
    installs = {'rotwk': setting('rotwk'), 'bfme2': base_game_dir()}
    hashes = Hashes(HOME/'md5.json')
    owners = {game: owner for game, (owner, _) in pins().items()}
    missing = {}
    try:
        for game, files in required().items():
            folders = [*roots.get(game, []), *([installs[game]] if installs[game] else [])]
            fetch = None
            if download:
                def fetch(path, md5, destination, game=game):
                    _fetch(f'{FILES}/{owners[game]}/{md5}', destination, md5=md5)
            missing[game] = gather(files, ASSETS/game, folders, hashes, fetch, progress)
    finally:
        hashes.save()
    gi = ASSETS/'rotwk'/'gi.dat'                # UserDataLeafName: the profile folder's name
    if not gi.exists() and installs['rotwk'] and (Path(installs['rotwk'])/'gi.dat').exists():
        shutil.copy2(Path(installs['rotwk'])/'gi.dat', gi)
    lacking = [(game, *f) for game, files in missing.items() for f in files]
    if lacking:
        size = sum(f[3] for f in lacking)
        raise RuntimeError(f'OpenBFME needs {len(lacking)} unmodified English game files your installs lack '
                           f'({", ".join(f"{g}/{p}" for g, p, _, _ in lacking[:4])}{", ..." if len(lacking) > 4 else ""}; '
                           f'{size/1e6:.0f} MB). Add --download to fetch them from the service the OpenBFME launcher uses.')
    return ASSETS


# Maps ---------------------------------------------------------------------------------
def write_big(path, files):
    """A BIG4 archive of (name, bytes or Path): little-endian size, big-endian
    count and end of directory; entries big-endian offset, size, then the path."""
    names = [name.replace('/', '\\').encode('cp1252') + b'\0' for name, _ in files]
    sizes = [len(data) if isinstance(data, bytes) else Path(data).stat().st_size for _, data in files]
    end = 16 + sum(8 + len(n) for n in names) + 8               # + retail's 'L253' tail
    offset, table = end, b''
    for name, size in zip(names, sizes):
        table += struct.pack('>II', offset, size) + name
        offset += size
    part = path.with_name(path.name + '.part')
    with part.open('wb') as out:
        out.write(b'BIG4' + struct.pack('<I', offset) + struct.pack('>II', len(files), end) + table + b'L253\0\0\0\0')
        for _, data in files:
            if isinstance(data, bytes):
                out.write(data)
            else:
                with Path(data).open('rb') as f:
                    shutil.copyfileobj(f, out, 1 << 22)
    part.replace(path)
    return path


def merged_cache(retail, entries):
    """Retail's mapcache.ini with each entry added (replacing one with its key)."""
    for entry in entries:
        key = entry.split('\n', 1)[0]
        retail = re.sub(rf'(?ms)^{re.escape(key)}\s*\n.*?^END\s*\n?', '', retail)
    return (retail.rstrip() + '\n\n' + '\n'.join(e.rstrip() + '\n' for e in entries)).replace('\r\n', '\n')


def install(project, progress=print):
    """Pack the project's build for OpenBFME and refresh the merged map cache.
    Returns the archives to mount, the map cache last."""
    from mapworkshop.formats.map import Map
    from mapworkshop.mapkit.cache import cache_entry
    name = project.native_name
    files = [p for p in sorted(project.build_dir.iterdir()) if p.suffix.lower() in ('.map', '.tga') or p.name == 'map.ini']
    archive, entry = MAPS/f'{name}.big', MAPS/f'{name}.ini'
    MAPS.mkdir(parents=True, exist_ok=True)
    if not (archive.exists() and entry.exists()) or archive.stat().st_mtime_ns < max(p.stat().st_mtime_ns for p in files):
        progress(f'Packing {project.title} for OpenBFME...')
        entry.write_text(cache_entry(project.map_file, Map(project.map_file.read_bytes()), name, project.title,
                                     project.description or project.title, max_players=16), encoding='cp1252')
        write_big(archive, [(f'maps/{name}/{p.name}', p) for p in files])
    return archives()


def user_maps():
    """OpenBFME's user maps folder, where RotWK keeps WorldBuilder maps: APPDATA (the one OpenBFME gets here), the
    leaf name the RotWK files' gi.dat holds (OpenBFME reads it there, not in the registry), then "Maps"
    (UserDataFolder::userMapFolder, Open-BFME/openbfme-godot#76). A build installed there opens by name with the map
    builders' user_map option."""
    data = (ASSETS/'rotwk'/'gi.dat').read_bytes()
    if data[:4] != b'GI  ':
        raise RuntimeError(f'{ASSETS/"rotwk"/"gi.dat"} is not a gi.dat file')
    parts = data[8:].split(b'\0')
    values = {parts[2*i].decode('cp1252').lower(): parts[2*i+1].decode('cp1252')
              for i in range(int.from_bytes(data[4:8], 'little'))}
    if not values.get('userdataleafname'):
        raise RuntimeError(f'{ASSETS/"rotwk"/"gi.dat"} names no UserDataLeafName')
    return APPDATA/values['userdataleafname']/'Maps'


def install_user_map(project):
    """The project's build in OpenBFME's user maps folder (user_maps()/<native name>/), as game.install puts it in
    the game's: the .map, map.ini and the preview images, copied when they changed. Returns the folder."""
    name = project.native_name
    files = {p.name: p for p in sorted(project.build_dir.iterdir())
             if p.is_file() and (p.name.startswith(name) or p.name == 'map.ini')}
    if not any(name.lower().endswith('.map') for name in files):
        raise RuntimeError(f'{project.title} has no build yet: run `mw build {project.id}`')
    target = user_maps()/name
    target.mkdir(parents=True, exist_ok=True)
    mirror(target, files)
    return target


def archives():
    """Every packed map's archive and the merged map cache, written again from
    them; the archives to mount, the map cache last."""
    from mapworkshop.formats.big import BigArchive
    maps = [p for p in sorted(MAPS.glob('*.big')) if p.with_suffix('.ini').exists()]
    retail = BigArchive(ASSETS/'rotwk'/'_patch201maps.big').read('maps/mapcache.ini')
    cache = merged_cache(retail, [p.with_suffix('.ini').read_text(encoding='cp1252') for p in maps])
    write_big(MAPCACHE, [('maps/mapcache.ini', cache.replace('\n', '\r\n').encode('cp1252'))])
    return [*maps, MAPCACHE]


def pack_for_test(map_file, name, title):
    """The map at `map_file` (with the map.ini, map.str and .tga files beside it) packed as maps/<name>/ for a live
    game in the viewer's Test mode, with a map cache that names it: the archives to mount. OpenBFME's GameWorld
    finds a map only in its archives (a game on a user map is not ported yet: its stop S-5160), and they are mounted
    when the viewer starts (OPENBFME_EXTRA_ARCHIVES, read once) and stay open while it runs, so each run packs into a
    folder of its own under TEST; the folders no viewer holds any more go."""
    from mapworkshop.formats.big import BigArchive
    from mapworkshop.formats.map import Map
    from mapworkshop.mapkit.cache import cache_entry
    TEST.mkdir(parents=True, exist_ok=True)
    for old in TEST.iterdir():
        shutil.rmtree(old, ignore_errors=True)               # a running viewer's archives stay: they are open
    folder = TEST/f'{time.time_ns()}'
    folder.mkdir()
    files = [p for p in sorted(map_file.parent.iterdir())
             if p == map_file or p.suffix.lower() in ('.tga', '.str') or p.name.lower() == 'map.ini']
    archive = folder/f'{name}.big'
    write_big(archive, [(f'maps/{name}/{name}.map' if p == map_file else f'maps/{name}/{p.name}', p) for p in files])
    entry = cache_entry(map_file, Map(map_file.read_bytes()), name, title, title, max_players=16)
    cache = merged_cache(BigArchive(ASSETS/'rotwk'/'_patch201maps.big').read('maps/mapcache.ini'), [entry])
    write_big(folder/'mapcache.big', [('maps/mapcache.ini', cache.replace('\n', '\r\n').encode('cp1252'))])
    return [archive, folder/'mapcache.big']


def world_slots(project):
    """GameWorld's slots for a live game in the viewer's Test mode: map.toml's [play] line-up (runtime.lineup), each
    slot's Player_<n> with its faction and team, every slot human, so that no skirmish AI moves an army (an order goes
    out as whoever owns the units ordered); without a line-up, or a faction, Men against Mordor."""
    from mapworkshop.native import runtime
    try:
        seats = runtime.lineup(project) if project is not None else None
    except ValueError:
        seats = None
    seats = seats or [dict(faction=None, team=-1), dict(faction=None, team=-1)]
    defaults = ('Men', 'Mordor')
    return [dict(player=f'Player_{i + 1}', faction='Faction' + (s['faction'] or defaults[i % 2]), human=True,
                 team=s['team'] if s['team'] >= 0 else i, start_index=i) for i, s in enumerate(seats)]


# Running it ---------------------------------------------------------------------------
def environment(archives):
    env = dict(os.environ, APPDATA=str(APPDATA), OPENBFME_EXTRA_ARCHIVES=';'.join(str(a) for a in archives))
    env.update({variable: str(ASSETS/game) for game, variable in INSTALL.items()})
    APPDATA.mkdir(parents=True, exist_ok=True)
    return env


def prepare(project, progress=print, download=False):
    """Engine, game files and the project's archive ready: (gui, console,
    environment, map key). Without a project, only the maps packed before."""
    gui, console = build(progress)
    assets(progress, download)
    if project is None:
        return gui, console, environment(archives()), None
    return gui, console, environment(install(project, progress)), f'maps/{project.native_name}/{project.native_name}.map'


def net_slots(project):
    """OpenBFME's --net-slots for the project's line-up (runtime.lineup):
    kind:faction:start:team per slot, the first you; without one, you against
    an easy AI, factions and starts random."""
    from mapworkshop.native import runtime
    seats = runtime.lineup(project) or [dict(state=None, faction=None, start=-1, team=-1),
                                        dict(state=runtime.EASY_AI, faction=None, start=-1, team=-1)]
    kinds = {v: k for k, v in runtime.AI_LEVELS.items()}
    return ';'.join(f'{kinds.get(s["state"], "human")}:{"Faction" + s["faction"] if s["faction"] else ""}:'
                    f'{s["start"]}:{s["team"]}' for s in seats)


def play(project, progress=print, download=False, fog=False, record=False):
    """Start OpenBFME straight in a skirmish on the project's map, as mw play
    starts the game: its line-up (net_slots()). OpenBFME's LAN host
    (--net-host) seats the slots without the lobby screens and, every slot
    but yours a computer, starts at once. The game is drawn without its
    shroud and fog (--no-shroud) unless `fog`. It is not recorded
    (--no-record) unless `record`: OpenBFME records every LAN game, and a
    replay keeps the whole game state's hash of every logic frame, which in a
    big battle was a third of the simulation's time. With no project: its
    main menu, with the maps packed before. Returns the process."""
    gui, _, env, key = prepare(project, progress, download)
    args = [str(gui), '--path', str(PROJECT), '--', '--no-intro', '--no-update-check', '--free-camera']
    if project is not None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:   # a free port for the host
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        args += [f'--net-host={port}', f'--map={key}', f'--net-slots={net_slots(project)}'] + ([] if fog else ['--no-shroud'])
        args += [] if record else ['--no-record']
    return subprocess.Popen(args, env=env, cwd=HOME, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def check(project, progress=print, download=False, seconds=5, timeout=600):
    """A headless scripted skirmish on the map (OpenBFME's --auto: the menus are
    clicked, you against an AI) for `seconds` of game time; saves
    logs/check-<map>.json and raises RuntimeError unless the game ran."""
    _, console, env, key = prepare(project, progress, download)
    progress(f'Starting a headless OpenBFME skirmish on {project.title}...')
    started = time.time()
    result = subprocess.run([str(console), '--headless', '--path', str(PROJECT), '--', '--auto', f'--map={key}',
                             f'--advance={seconds}', '--no-intro', '--no-update-check'], env=env, cwd=HOME,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    log = LOGS/f'check-{project.id}.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(result.stdout + result.stderr, encoding='utf-8')
    report = dict(map=key, map_sha256=hashlib.sha256(project.map_file.read_bytes()).hexdigest(), exit=result.returncode,
                  seconds=round(time.time() - started, 1), log=str(log),
                  failures=re.findall(r'^GAME FAIL.*$', result.stdout, re.M))
    if m := re.search(r'^GAME load: (\d+) ms', result.stdout, re.M):
        report['load_ms'] = int(m[1])
    if m := re.search(r'^GAME ran ([\d.]+) s: logic frame (\d+), (\d+) objects', result.stdout, re.M):
        report.update(game_seconds=float(m[1]), frame=int(m[2]), objects=int(m[3]))
    (LOGS/f'check-{project.id}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if result.returncode or report['failures'] or 'frame' not in report:
        raise RuntimeError(f'OpenBFME did not play {project.title}: '
                           f'{(report["failures"] or ["exit " + str(result.returncode)])[0][:300]}; see {log}')
    return report


def status():
    """(ready, text) for `mw doctor`."""
    if not (SOURCE/'engine').exists():
        return False, 'not set up: the first `mw play --godot` fetches and builds it'
    if not (PROJECT/DLL).exists():
        return False, 'submodule present, engine not built yet: `mw play --godot` builds it'
    if not (ASSETS/'rotwk'/'_patch201maps.big').exists():
        return False, 'engine built, game files not gathered yet: `mw play --godot` gathers them'
    return True, f'built ({_git("rev-parse", "--short", "HEAD", cwd=SOURCE)}), game files in {ASSETS}'
