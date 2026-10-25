"""Checkout folders and machine-local settings.

Everything the workshop writes stays in the ignored `local/` folder:

    local/config.toml    settings: game folders, active profile, last opened map
    local/game/          the game's INI and map trees, extracted by `mw setup`
    local/build/<map>/   the latest build of each map project
    local/history/<map>/ earlier builds, one folder per build
    local/marks/         viewer marks, one file per map
    local/renders/       renders and viewer screenshots
    local/cache/         caches
    local/openbfme/      OpenBFME for `mw play --godot` (native.openbfme)

ROTWK keeps the same layout under local/profiles/rotwk/, except for the
shared config.toml. Map sources are shared; generated output is isolated.
"""
import os
from pathlib import Path
import tempfile
import threading
import tomllib

PROJECT = 'bfme2-map-workshop'


def find_root(start=None):
    override = os.environ.get('MAP_WORKSHOP_ROOT')
    start = Path(start or __file__).resolve()
    candidates = [Path(override).expanduser().resolve()] if override else [start, *start.parents]
    for candidate in candidates:
        project = candidate/'pyproject.toml'
        if project.is_file() and tomllib.loads(project.read_text(encoding='utf-8')).get('project', {}).get('name') == PROJECT:
            return candidate
    raise RuntimeError(f'Not inside a {PROJECT} checkout; set MAP_WORKSHOP_ROOT to one')


ROOT = find_root()
MAPS = ROOT/'maps'
LOCAL = ROOT/'local'
CONFIG = LOCAL/'config.toml'
_CONFIG_LOCK = threading.RLock()


def settings():
    with _CONFIG_LOCK:
        return tomllib.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {}


def setting(key, default=None):
    return settings().get(key, default)


def save_setting(key, value):
    """Set one setting in local/config.toml, preserving TOML values and nested
    tables. Other objects (such as paths) are written as text by _toml_value."""
    if key == 'profile' and value not in ('bfme2', 'rotwk'):
        raise ValueError('Profile must be bfme2 or rotwk')
    with _CONFIG_LOCK:
        values = settings()
        values[key] = value
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        lines = ['# bfme2-map-workshop settings; `mw config` changes them.']
        lines += _toml_table(values)
        # Background asset loading reads this file too. Publish the complete
        # settings at once so readers never see a truncated, empty config.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=CONFIG.parent,
                                         prefix='config-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write('\n'.join(lines) + '\n')
            except BaseException:
                stream.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(CONFIG)
        finally:
            temporary.unlink(missing_ok=True)


def _toml_table(values, prefix=''):
    """TOML lines for a dict as tomllib reads it: its values, then its tables."""
    lines = [f'{_toml_key(k)} = {_toml_value(v)}' for k, v in values.items() if not isinstance(v, dict)]
    for k, v in values.items():
        if isinstance(v, dict):
            name = prefix + _toml_key(k)
            lines += ['', f'[{name}]'] + _toml_table(v, name + '.')
    return lines


def _toml_key(key):
    return key if key and all(c.isalnum() or c in '-_' for c in key) else _quote(key)


def _toml_value(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_toml_value(v) for v in value) + ']'
    if isinstance(value, dict):
        return '{' + ', '.join(f'{_toml_key(k)} = {_toml_value(v)}' for k, v in value.items()) + '}'
    if hasattr(value, 'isoformat'):         # dates and times
        return value.isoformat()
    return _quote(str(value))


def _quote(text):
    escaped = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')
    return '"' + escaped + '"'


def game_dir():
    """The active profile's installation, or None."""
    value = setting('rotwk' if PROFILE == 'rotwk' else 'game')
    return Path(value).expanduser() if value else None


def base_game_dir():
    """BFME2 supplies shared assets to both profiles."""
    value = setting('game')
    return Path(value).expanduser() if value else None


def archive_paths(game=None, expansion=None):
    """Assets in override order, BFME2 first and ROTWK last.

    Explicit folders are independent of the active profile. The ROTWK profile
    uses retail archives plus official 2.01 patches, excluding community mods.
    BFME2 keeps the studio's existing archive order.
    """
    if game is None:
        game = base_game_dir()
        expansion = game_dir() if PROFILE == 'rotwk' else None
        if PROFILE == 'rotwk' and expansion is None:
            raise RuntimeError('ROTWK not configured: run `mw --profile rotwk setup --rotwk DIR`')
    if game is None:
        raise RuntimeError('BFME2 not configured: run `mw setup --game DIR`')
    for folder in (game, expansion):
        if folder is not None and not Path(folder).is_dir():
            raise RuntimeError(f'Game asset folder does not exist: {folder}; run `mw setup`')
    paths = sorted(Path(game).glob('*.big'), key=lambda p: (p.name.lower().startswith('_patch'), p.name.lower()))
    if expansion is not None:
        paths += sorted((p for p in Path(expansion).glob('*.big') if p.name.lower() in ROTWK_ARCHIVES),
                        key=lambda p: p.name.lower(), reverse=True)
    return paths


# Retail root archives from the disc's file list, plus official patch 2.01.
# An allowlist also excludes mods with ordinary filenames, not just __patch202.
ROTWK_ARCHIVES = frozenset(('ambientstreams.big', 'audio.big', 'bases.big', 'data1.big', 'data2.big',
    'ini.big', 'libraries.big', 'lotrsec.big', 'maps.big', 'music.big', 'shaders.big', 'terrain.big',
    'textures0.big', 'textures1.big', 'textures2.big', 'textures3.big', 'textures4.big', 'w3d.big', 'window.big',
    '_patch201.big', '_patch201ini.big', '_patch201maps.big'))


# Select once per process. Children inherit this choice even if another studio
# changes the saved default while a build or viewer is running.
PROFILE = os.environ.get('MW_GAME_PROFILE') or setting('profile', 'bfme2')
if PROFILE not in ('bfme2', 'rotwk'):
    raise RuntimeError(f'Unknown game profile {PROFILE!r}; use bfme2 or rotwk')
os.environ['MW_GAME_PROFILE'] = PROFILE
PROFILE_ROOT = LOCAL if PROFILE == 'bfme2' else LOCAL/'profiles'/PROFILE
GAME_DATA = PROFILE_ROOT/'game'
BUILD = PROFILE_ROOT/'build'
HISTORY = PROFILE_ROOT/'history'
MARKS = PROFILE_ROOT/'marks'
VIEWS = PROFILE_ROOT/'views'
RENDERS = PROFILE_ROOT/'renders'
CACHE = PROFILE_ROOT/'cache'
RUNTIME = PROFILE_ROOT/'runtime'
GAME_LABEL = 'ROTWK 2.01' if PROFILE == 'rotwk' else 'BFME2'
GAME_EXE = 'lotrbfme2ep1.exe' if PROFILE == 'rotwk' else 'lotrbfme2.exe'
USER_MAPS = Path(os.environ.get('APPDATA', '~')).expanduser()/(
    'My The Lord of the Rings, The Rise of the Witch-king Files' if PROFILE == 'rotwk'
    else 'My Battle for Middle-earth(tm) II Files')/'Maps'
