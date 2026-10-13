"""Checkout folders and machine-local settings.

Everything the workshop writes stays in the ignored `local/` folder:

    local/config.toml    settings: the BFME2 folder, the last opened map
    local/game/          the game's INI and map trees, extracted by `mw setup`
    local/build/<map>/   the latest build of each map project
    local/history/<map>/ earlier builds, one folder per build
    local/marks/         viewer marks, one file per map
    local/renders/       renders and viewer screenshots
    local/videos/        videos
    local/cache/         caches
"""
import os
from pathlib import Path
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
GAME_DATA = LOCAL/'game'
BUILD = LOCAL/'build'
HISTORY = LOCAL/'history'
MARKS = LOCAL/'marks'
RENDERS = LOCAL/'renders'
VIDEOS = LOCAL/'videos'
CACHE = LOCAL/'cache'
# Where BFME2 looks for its user's own maps.
USER_MAPS = Path(os.environ.get('APPDATA', '~')).expanduser()/'My Battle for Middle-earth(tm) II Files'/'Maps'


def settings():
    return tomllib.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {}


def setting(key, default=None):
    return settings().get(key, default)


def save_setting(key, value):
    """Set one string setting in local/config.toml, keeping the others."""
    values = settings()
    values[key] = str(value)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    lines = ['# bfme2-map-workshop settings; `mw config` changes them.']
    lines += [f'{name} = {_quote(entry)}' for name, entry in values.items() if isinstance(entry, str)]
    CONFIG.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _quote(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def game_dir():
    """The configured BFME2 installation (with lotrbfme2.exe and INI.big), or None."""
    value = setting('game')
    return Path(value).expanduser() if value else None


def local_path(name, default=None):
    """A configured path by name, or `default`."""
    value = game_dir() if name == 'game' else setting(name)
    if value:
        return Path(value).expanduser()
    return Path(default) if default else None
