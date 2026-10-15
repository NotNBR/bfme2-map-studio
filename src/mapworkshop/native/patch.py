"""Faster map loading in the normal game: mw patch install / remove / status.

Installs native/loading/bin/dinput8.dll into the selected game's folder: the player
build of bfme2-map-quickload (the native/loading submodule,
https://github.com/NotNBR/bfme2-map-quickload; loading.cpp built with
MW_STANDALONE). The game imports DirectInput8Create from dinput8.dll and finds
this copy before the system's, which it forwards to. In BFME2 1.06 or the
verified ROTWK 2.01 engine, the DLL builds terrain textures on worker threads
while a map loads and skips the five-second title logo afterward. Removing it puts
the folder back as it was. A dinput8.dll that is not ours is never replaced
or removed.
"""
import hashlib
from pathlib import Path

from mapworkshop.config import game_dir
from mapworkshop.native import msvc
from mapworkshop.native.pe import PE
from mapworkshop.native.runtime import SUPPORTED_SHA256
from mapworkshop.native.rotwk import SUPPORTED_SHA256 as SUPPORTED_ROTWK_SHA256

NAME = 'dinput8.dll'


def is_ours(path):
    """Whether a dinput8.dll is this patch (any version of it)."""
    try:
        return 'mwLoading' in PE(path).exports()
    except (OSError, ValueError):
        return False


def folder(game=None):
    game = Path(game or game_dir() or '')
    if not (game/'game.dat').is_file():
        raise RuntimeError('Game not found: run `mw setup` for the selected profile')
    return game


def status(game=None):
    """'not installed', 'installed', 'outdated' (an older build of ours) or
    'foreign' (another program's dinput8.dll)."""
    target = folder(game)/NAME
    if not target.exists():
        return 'not installed'
    if not is_ours(target):
        return 'foreign'
    return 'installed' if target.read_bytes() == msvc.dll('dinput8').read_bytes() else 'outdated'


def install(game=None):
    game = folder(game)
    if not msvc.dll('dinput8').exists():
        raise RuntimeError('The bfme2-map-quickload submodule is missing: run `git submodule update --init`, '
                           'or get dinput8.dll from github.com/NotNBR/bfme2-map-quickload/releases')
    if hashlib.sha256((game/'game.dat').read_bytes()).hexdigest() not in (SUPPORTED_SHA256, SUPPORTED_ROTWK_SHA256):
        raise RuntimeError(f'{game/"game.dat"} is not a verified BFME2 1.06 or ROTWK 2.01 engine')
    if status(game) == 'foreign':
        raise RuntimeError(f'{game/NAME} belongs to another program; remove it first if you want this patch')
    try:
        (game/NAME).write_bytes(msvc.dll('dinput8').read_bytes())
    except PermissionError:
        raise RuntimeError(f'No permission to write to {game}: run the command as administrator') from None
    return game/NAME


def remove(game=None):
    game = folder(game)
    if status(game) == 'foreign':
        raise RuntimeError(f'{game/NAME} belongs to another program; it was left alone')
    try:
        (game/NAME).unlink(missing_ok=True)
    except PermissionError:
        raise RuntimeError(f'No permission to change {game}: run the command as administrator') from None
    return game/NAME
