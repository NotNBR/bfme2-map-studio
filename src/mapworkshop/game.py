"""The BFME2 installation: find it, extract its data, install maps, launch it.

Nothing here writes to the game folder. `extract` copies the game's INI and
map trees into local/game, which the builds and the renderer read; `install`
copies a built map into the game's user maps folder.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess

from mapworkshop.config import GAME_DATA, ROOT, USER_MAPS, game_dir, save_setting
from mapworkshop.formats.big import BigArchive

REGISTRY_KEYS = [r'SOFTWARE\WOW6432Node\Electronic Arts\Electronic Arts\The Battle for Middle-earth II',
                 r'SOFTWARE\Electronic Arts\Electronic Arts\The Battle for Middle-earth II']
COMMON_FOLDERS = [r'EA Games\The Battle for Middle-earth (tm) II', r'Electronic Arts\The Battle for Middle-earth (tm) II',
                  r'EA Games\The Battle for Middle-earth II', 'The Battle for Middle-earth II']


def is_game(path):
    path = Path(path)
    return (path/'INI.big').is_file() and ((path/'lotrbfme2.exe').is_file() or (path/'game.dat').is_file())


def _registry():
    try:
        import winreg
    except ImportError:
        return []
    found = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key in REGISTRY_KEYS:
            try:
                with winreg.OpenKey(hive, key) as handle:
                    found.append(Path(winreg.QueryValueEx(handle, 'InstallPath')[0]))
            except OSError:
                pass
    return found


def _nearby(base, depth=3):
    """Game folders up to `depth` levels below `base` (e.g. next to this checkout)."""
    found, level = [], [Path(base)]
    for _ in range(depth):
        following = []
        for folder in level:
            try:
                children = [c for c in folder.iterdir() if c.is_dir() and not c.name.startswith('.')]
            except OSError:
                continue
            for child in children:
                if child.resolve() == ROOT.resolve():
                    continue
                (found if is_game(child) else following).append(child)
        level = following[:400]
    return found


def find():
    """The BFME2 folder: the configured one, the registry's, a usual install
    folder, or one near this checkout. None when there is none."""
    configured = game_dir()
    if configured and is_game(configured):
        return configured
    candidates = _registry()
    for variable in ('ProgramFiles(x86)', 'ProgramFiles'):
        if os.environ.get(variable):
            candidates += [Path(os.environ[variable])/folder for folder in COMMON_FOLDERS]
    candidates += [Path(f'{drive}:/Games')/folder for drive in 'CD' for folder in COMMON_FOLDERS]
    for candidate in candidates:
        if is_game(candidate):
            return candidate.resolve()
    nearby = _nearby(ROOT.parent)
    return nearby[0].resolve() if nearby else None


def archives(game):
    """The archives the game reads INIs and maps from, in override order."""
    game = Path(game)
    found = [game/'INI.big', game/'Maps.big']
    found += sorted(p for p in game.glob('*.big') if p.name.lower().startswith('data'))
    found += sorted(game.glob('_patch*.big'))
    return [p for p in found if p.is_file()]


def _signature(game):
    return [[p.name, p.stat().st_size, int(p.stat().st_mtime)] for p in archives(game)]


def extracted(game=None):
    """True when local/game holds the data of this game folder."""
    game = game or game_dir()
    manifest = GAME_DATA/'manifest.json'
    if not game or not manifest.exists():
        return False
    data = json.loads(manifest.read_text(encoding='utf-8'))
    return data.get('game') == str(Path(game)) and data.get('archives') == _signature(game)


def extract(game, progress=print):
    """Copy the effective data/ini and maps trees of `game` into local/game."""
    game = Path(game)
    effective = {}
    for path in archives(game):
        archive = BigArchive(path)
        for key in archive.entries:
            effective[key] = archive
    keys = sorted(k for k in effective if k.startswith(('data/ini/', 'maps/')))
    staging = GAME_DATA.with_name(GAME_DATA.name + '.partial')
    shutil.rmtree(staging, ignore_errors=True)
    for i, key in enumerate(keys):
        relative = PurePosixPath(key)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError(f'Unsafe archive path: {key}')
        target = staging/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(effective[key].read_bytes(key))
        if progress and (i + 1) % 2000 == 0:
            progress(f'  {i + 1:,} of {len(keys):,} files')
    (staging/'manifest.json').write_text(json.dumps(dict(
        game=str(game), archives=_signature(game), files=len(keys),
        game_dat_sha256=hashlib.sha256((game/'game.dat').read_bytes()).hexdigest() if (game/'game.dat').exists() else None),
        indent=2), encoding='utf-8')
    shutil.rmtree(GAME_DATA, ignore_errors=True)
    staging.replace(GAME_DATA)
    return len(keys)


def setup(game=None, force=False, progress=print):
    """Find (or take) the game folder, remember it, extract its data. Returns the folder."""
    game = Path(game).expanduser().resolve() if game else find()
    if game is None:
        raise RuntimeError('BFME2 not found. Run `mw setup --game "<BFME2 folder>"` with the folder '
                           'that holds lotrbfme2.exe and INI.big.')
    if not is_game(game):
        raise RuntimeError(f'{game} is not a BFME2 folder (no INI.big next to lotrbfme2.exe).')
    save_setting('game', game)
    if force or not extracted(game):
        progress(f'Extracting the game data from {game} ...')
        count = extract(game, progress)
        progress(f'{count:,} INI and map files in {GAME_DATA}')
    else:
        progress(f'Game data is up to date ({GAME_DATA}).')
    return game


def stock_maps():
    """The game's own maps, from local/game/maps."""
    return sorted((GAME_DATA/'maps').glob('*/*.map'))


def install(build_folder, native_name):
    """Copy a built map into the game's user maps folder; returns the target."""
    target = USER_MAPS/native_name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for path in Path(build_folder).iterdir():
        if path.is_file() and (path.name.startswith(native_name) or path.name == 'map.ini'):
            shutil.copy2(path, target/path.name)
    return target


def launch():
    game = game_dir()
    if not game or not is_game(game):
        raise RuntimeError('BFME2 not found: run `mw setup`')
    exe = game/'lotrbfme2.exe'
    if not exe.exists():
        raise RuntimeError(f'No lotrbfme2.exe in {game}')
    return subprocess.Popen([str(exe)], cwd=game)
