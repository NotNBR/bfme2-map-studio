"""The isolated game the native tools start, in local/runtime/:

    game/      a copy of the BFME2 install: the archives (.big) and movies are
               hard links (no extra disk; the game only reads them), everything
               else a real copy, so nothing a run writes reaches the install
    game-headless/  the same files as game/ (hard links to them), plus DXVK's
               d3d9.dll, for headless runs (below)
    dxvk/      the DXVK release headless runs use, downloaded on first use
    mod/maps/  the maps installed for test games, and their mapcache.ini
               entries (the game passes -mod with this folder)
    appdata/   the profile the game is given instead of the owner's: options,
               saves, replays (debugger.Game's appdata lie)
    logs/      launcher logs and run reports

prepare() builds or refreshes it from the configured install (`mw setup`),
which must be BFME2 1.06: the breakpoints are at its addresses. start()
starts a skirmish on an installed map, you against an easy AI.

Headless runs (start(..., headless=True): the pathfinding read and
screenshots) put the game on a hidden desktop of its own
(debugger.hidden_desktop), so no window appears and your focus stays where
it is. Direct3D 9 does not render on a desktop that is not shown, so they
start game-headless/, whose d3d9.dll is DXVK's (Direct3D 9 over Vulkan;
https://github.com/doitsujin/dxvk, zlib licence). Its frames match native
Direct3D 9 to about 2 levels in 255 on average (Brightwater Fold, Medium and
High with reflections, 14 October 2026). Test games keep game/ and native
Direct3D 9.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

from mapworkshop.config import RUNTIME, game_dir
from mapworkshop.native import debugger

GAME, MOD, APPDATA, LOGS = RUNTIME/'game', RUNTIME/'mod', RUNTIME/'appdata', RUNTIME/'logs'
HEADLESS_GAME = RUNTIME/'game-headless'
DXVK_VERSION = '3.1.1'
DXVK_URL = f'https://github.com/doitsujin/dxvk/releases/download/v{DXVK_VERSION}/dxvk-{DXVK_VERSION}.tar.gz'
DXVK_SHA256 = '40565b4a724aadc4433fa4e010b4b23916d9b1f1baeee64e17186db94f54e608'   # GitHub's digest of that file
SUPPORTED_SHA256 = 'f008b587570bad693981dc7218588c81d192a1e064b0f7f861539c51156a7640'   # game.dat 1.06
SKIPPED = re.compile(r'(?i)(^worldbuilder\.exe$|\.dmp$|\.log$|\.dbgcmd$|^dump_)')
PROFILE_LEAF = 'My Battle for Middle-earth II Files'
# Without Options.ini the game benchmarks the CPU on its first start, which
# faults under the debugger; start() sets the detail level and resolution.
OPTIONS = """AudioLOD = Low
FlashTutorial = 0
HasGotOnline = yes
HasSeenLogoMovies = yes
IsThreadedLoad = yes
TimesInGame = 1
"""
GRAPHICS = ('Low', 'Medium', 'High', 'UltraHigh')
WIDTH, HEIGHT = 1600, 1200

# Retail game.dat 1.06 (RVAs), from Open-BFME-2 / openbfme2's game_smoke.
FILE_SLOTS_SET = 0x2300DC       # GameEngine::init's -file branch, just after setSlot(0, "Test")
THE_GAME_INFO, THE_SKIRMISH_GAME_INFO = 0xA02EEC, 0xA02EF0
SLOTS_OFF, SLOT_STATE, SLOT_TEMPLATE = 0x18, 4, 0x18
TEMPLATE_RANDOM, EASY_AI = -1, 2


def linked(relative):
    """Files the runtime shares with the install by hard link."""
    parts = [p.lower() for p in relative.parts]
    return relative.suffix.lower() == '.big' or parts[:2] == ['data', 'movies']


def _same(source, target):
    try:
        a, b = source.stat(), target.stat()
    except OSError:
        return False
    return a.st_size == b.st_size and (os.path.samefile(source, target) or int(a.st_mtime) == int(b.st_mtime))


def prepare(progress=print):
    """Create or refresh the runtime from the installed game; returns the
    runtime's game folder. Only new or changed files are linked or copied."""
    source = game_dir()
    if not source or not (Path(source)/'game.dat').is_file():
        raise RuntimeError('BFME2 not found: run `mw setup`')
    source = Path(source)
    record = RUNTIME/'runtime.json'
    known = json.loads(record.read_text(encoding='utf-8')) if record.exists() else {}
    stat = (source/'game.dat').stat()
    if known.get('game_dat') != [stat.st_size, int(stat.st_mtime)]:
        if hashlib.sha256((source/'game.dat').read_bytes()).hexdigest() != SUPPORTED_SHA256:
            raise RuntimeError(f'{source/"game.dat"} is not BFME2 1.06, the version the launcher supports')
    made = 0
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if not path.is_file() or SKIPPED.search(path.name):
            continue
        target = GAME/relative
        if _same(path, target):
            continue
        if not made:
            progress(f'Preparing the game runtime in {RUNTIME} (archives are linked, not copied)...')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        if linked(relative):
            try:
                os.link(path, target)
            except OSError:               # another drive, or no hard links there: copy instead
                shutil.copy2(path, target)
        else:
            shutil.copy2(path, target)
        made += 1
    for folder in (MOD/'maps', LOGS):
        folder.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(dict(source=str(source), game_dat=[stat.st_size, int(stat.st_mtime)]), indent=2),
                      encoding='utf-8')
    return GAME


def dxvk(progress=print, download=None):
    """DXVK's 32-bit d3d9.dll, downloaded once into dxvk/<version>/ and
    checked against the release's SHA-256. `download(url) -> bytes` is for
    tests."""
    import io
    import tarfile
    target = RUNTIME/'dxvk'/DXVK_VERSION/'d3d9.dll'
    if target.exists():
        return target
    progress(f'Downloading DXVK {DXVK_VERSION} for headless runs (18 MB, once)...')
    if download is None:
        import urllib.request

        def download(url):
            with urllib.request.urlopen(url, timeout=120) as response:
                return response.read()
    data = download(DXVK_URL)
    if hashlib.sha256(data).hexdigest() != DXVK_SHA256:
        raise RuntimeError(f'The DXVK download does not match its published SHA-256: {DXVK_URL}')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        member = archive.getmember(f'dxvk-{DXVK_VERSION}/x32/d3d9.dll')
        dll = archive.extractfile(member).read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(dll)
    return target


def prepare_headless(progress=print, download=None):
    """game-headless/: game/'s files as hard links (refreshed like game/),
    plus DXVK's d3d9.dll. Returns the folder."""
    prepare(progress)
    dll = dxvk(progress, download)
    wanted = set()
    for path in GAME.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(GAME)
        wanted.add(relative)
        target = HEADLESS_GAME/relative
        if target.exists() and os.path.samefile(path, target):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        try:
            os.link(path, target)
        except OSError:
            shutil.copy2(path, target)
    for path in list(HEADLESS_GAME.rglob('*')):
        if path.is_file() and path.relative_to(HEADLESS_GAME) not in wanted and path.name.lower() != 'd3d9.dll':
            path.unlink()          # gone from game/ (or a log DXVK wrote before logging was off)
    target = HEADLESS_GAME/'d3d9.dll'
    if not target.exists() or target.read_bytes() != dll.read_bytes():
        shutil.copy2(dll, target)
    return HEADLESS_GAME


def profile_leaf():
    """The profile folder name the game uses: its registry's UserDataLeafName
    (a Rise of the Witch-king name on some installs), else BFME2's."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SOFTWARE\Electronic Arts\Electronic Arts\The Battle for Middle-earth II',
                            0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY) as key:
            leaf = winreg.QueryValueEx(key, 'UserDataLeafName')[0]
    except OSError:
        return PROFILE_LEAF
    if not isinstance(leaf, str) or Path(leaf).name != leaf or leaf in ('', '.', '..'):
        raise RuntimeError(f'Invalid BFME2 profile folder name in the registry: {leaf!r}')
    return leaf


def set_options(graphics):
    """The runtime profile's Options.ini at this detail level and 1600 x 1200."""
    if graphics not in GRAPHICS:
        raise ValueError(f'Detail level {graphics!r}: use one of {", ".join(GRAPHICS)}')
    real = Path(os.environ.get('APPDATA') or Path.home()/'AppData'/'Roaming').resolve()
    if APPDATA.resolve() == real or real in APPDATA.resolve().parents:
        raise RuntimeError(f'The runtime profile {APPDATA} is inside the real AppData')
    profile = APPDATA/profile_leaf()
    profile.mkdir(parents=True, exist_ok=True)
    path = profile/'Options.ini'
    text = path.read_text(encoding='latin1') if path.exists() else OPTIONS
    for key, value in [('Resolution', f'{WIDTH} {HEIGHT}'), ('StaticGameLOD', graphics),
                       ('FixedStaticGameLOD', graphics), ('IdealStaticGameLOD', graphics)]:
        text, found = re.subn(rf'(?m)^{key}\s*=.*$', f'{key} = {value}', text)
        if not found:
            text = text.rstrip('\n') + f'\n{key} = {value}\n'
    path.write_text(text, encoding='latin1')
    return path


def install(project):
    """Copy a project's build into the runtime's mod folder and enter it in
    the folder's map cache, which -file needs to find it. Returns the map's
    -file name."""
    from mapworkshop.formats.map import Map
    from mapworkshop.mapkit.cache import cache_entry
    if not project.map_file.exists():
        raise LookupError(f'{project.title} has not been built yet: run `mw build {project.id}`')
    target = MOD/'maps'/project.native_name
    target.mkdir(parents=True, exist_ok=True)
    for path in project.build_dir.iterdir():
        if path.suffix.lower() in ('.map', '.tga') or path.name == 'map.ini':
            shutil.copy2(path, target/path.name)
    path = target/(project.native_name + '.map')
    entry = cache_entry(path, Map(path.read_bytes()), project.native_name, project.title,
                        project.description or project.title)
    key = entry.split('\n', 1)[0]
    cache = MOD/'maps'/'mapcache.ini'
    text = cache.read_text(encoding='cp1252') if cache.exists() else ''
    text = re.sub(rf'(?ms)^{re.escape(key)}\s*\n.*?^END\s*\n?', '', text)
    cache.write_text((text.rstrip() + '\n\n' if text.strip() else '') + entry, encoding='cp1252')
    return f'maps\\{project.native_name}.map'


def skirmish_setup(game, tid, ctx):
    """At GameEngine::init's -file branch, after slot 0 became "Test", finish
    what the skirmish menu would do: TheGameInfo = TheSkirmishGameInfo
    (retail's -file path leaves it null and faults at 0x24578B), slot 0 (you)
    and slot 1 get random factions, and slot 1 becomes an easy AI."""
    info = game.u32(game.base + THE_SKIRMISH_GAME_INFO)
    if not info:
        return False
    game.write(game.base + THE_GAME_INFO, struct.pack('<I', info))
    slots = [game.u32(info + SLOTS_OFF + 4*i) for i in range(2)]
    for slot in slots:
        if slot:
            game.write(slot + SLOT_TEMPLATE, struct.pack('<i', TEMPLATE_RANDOM))
    if slots[1]:
        game.write(slots[1] + SLOT_STATE, struct.pack('<I', EASY_AI))
        game.write(slots[1] + 8, b'\x01\x01')          # accepted, has the map
    return False


def start(project, graphics='Medium', headless=False, progress=print):
    """A Game set up to start a skirmish on the project's current build at
    this detail level (not yet running: add breakpoints, then game.run()).
    `headless`: on a hidden desktop, with DXVK (see the module notes)."""
    running = debugger.running_games()
    if running:
        raise RuntimeError(f'BFME2 is already running ({running[0][1]}); close it first')
    folder = prepare_headless(progress) if headless else prepare(progress)
    map_name = install(project)
    set_options(graphics)
    args = subprocess.list2cmdline(['-mod', str(MOD.resolve()), '-win', '-xres', str(WIDTH), '-yres', str(HEIGHT),
                                    '-file', map_name])
    os.environ['DXVK_LOG_LEVEL'] = 'none'             # DXVK would write logs into the game folder
    game = debugger.Game(folder, args, APPDATA)
    game.headless = headless
    game.on(FILE_SLOTS_SET, skirmish_setup)
    return game
