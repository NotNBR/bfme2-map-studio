"""ROTWK 2.01 test runtime and direct -file skirmish startup.

Addresses are RVAs in the hash-pinned local 2.01 engine, not generic version
numbers. Derived from its GameEngine::init at VA 0x63ad4f, setSlot at
0x8016c3, and GameSlot at 0x8014f1. This binary has pre-existing scheduling
differences; matching its version resource alone is insufficient.

The runtime mounts retail and official 2.01 archives only. Community patch,
HD and timer packs from the source install are excluded. BFME2 archives are
mounted at lower priority under distinct names; originals remain read-only.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

from mapworkshop.config import ROTWK_ARCHIVES, base_game_dir, game_dir, archive_paths

SUPPORTED_SHA256 = '5481de75b63e22483660ea8097478faef594f90b9ade7de893e092256ba68a26'
FILE_SLOTS_SET = 0x23CB7B
GAME_INFO, SKIRMISH_INFO = 0x9E892C, 0x9E8930
GAME_LOGIC, ENGINE_UPDATE, LOAD_LIBRARY_SLOT = 0x9E412C, 0x2325A0, 0x7D0188
CLOSE_ARM = 0x18EB
LOAD_SCREEN_DESTROY = 0x225524   # GameLogic deletes LoadScreen (+0x120), before the map draws


def runtime_files(source, base):
    """Destination-relative paths and sources for a clean 2.01 runtime."""
    source, base = Path(source), Path(base)
    wanted = {}
    filelist = source/'filelist.txt'
    listed = set()
    if filelist.exists():
        for line in filelist.read_text(encoding='cp1252').splitlines():
            parts = line.split(',', 2)
            if len(parts) == 3:
                listed.add(parts[2].replace('\\', '/').lower())
    for path in source.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        key = relative.as_posix().lower()
        if len(relative.parts) == 1:
            allowed = path.name.lower() in ROTWK_ARCHIVES if path.suffix.lower() == '.big' else (
                key in listed or key in ('game.dat', 'lotrbfme2ep1.exe', 'lotrbfme2ep1.lcf', 'gi.dat'))
            allowed = allowed and key != 'worldbuilder.exe'
        elif relative.parts[0].lower() == 'lang':
            allowed = bool(re.fullmatch(r'[a-z]+(?:audio|music|patch201)?\.big', path.name.lower()))
        else:
            allowed = key in listed and relative.parts[0].lower() in ('apt', 'mss', 'data')
            # Movies and cursors are also distributed as loose disc files.
            allowed |= key.startswith(('data/movies/', 'data/cursors/'))
        if allowed:
            wanted[relative] = path
    for i, path in enumerate(archive_paths(base)):
        wanted[Path(f'zz_bfme2_{9999-i:04d}_{path.name}')] = path
    return wanted


def prepare(progress=print):
    """An isolated runtime; exact engine hash checked before any hooks run."""
    from mapworkshop.native import runtime
    source, base = game_dir(), base_game_dir()
    if source is None or base is None or not (source/'game.dat').is_file():
        raise RuntimeError('Configure BFME2 and ROTWK with `mw --profile rotwk setup` first')
    if hashlib.sha256((source/'game.dat').read_bytes()).hexdigest() != SUPPORTED_SHA256:
        raise RuntimeError('This ROTWK executable has no verified studio launch hooks; '
                           'its version number alone does not identify a supported binary')
    wanted = runtime_files(source, base)
    record = runtime.RUNTIME/'runtime.json'
    known = json.loads(record.read_text()) if record.exists() else {}
    made = 0
    for relative, original in wanted.items():
        target = runtime.GAME/relative
        if runtime._same(original, target):
            continue
        if made == 0:
            progress(f'Preparing isolated ROTWK 2.01 in {runtime.RUNTIME}...')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        if runtime.linked(relative):
            try:
                os.link(original, target)
            except OSError:
                shutil.copy2(original, target)
        else:
            shutil.copy2(original, target)
        made += 1
    # Remove only files recorded by our earlier runtime preparation.
    for old in known.get('files', []):
        relative = Path(old)
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Unsafe path in ROTWK runtime manifest')
        if relative not in wanted:
            (runtime.GAME/relative).unlink(missing_ok=True)
    for folder in (runtime.MOD/'maps', runtime.LOGS):
        folder.mkdir(parents=True, exist_ok=True)
    runtime.skip_title_logo()
    record.write_text(json.dumps(dict(source=str(source), profile='rotwk-2.01',
                                     engine_sha256=SUPPORTED_SHA256,
                                     files=[str(p) for p in wanted]), indent=2), encoding='utf-8')
    return runtime.GAME


def skirmish_setup(game, tid, ctx):
    """Complete the -file slot setup as the skirmish menu would."""
    info = game.u32(game.base + SKIRMISH_INFO)
    if not info:
        game.stop('missing-skirmish-info')
        return False
    game.write(game.base + GAME_INFO, struct.pack('<I', info))
    slots = [game.u32(info + 0x18 + 4*i) for i in range(2)]
    if not all(slots):
        game.stop('missing-skirmish-slots')
        return False
    for slot in slots:
        game.write(slot + 0x18, struct.pack('<i', -1))  # random faction
    game.write(slots[1] + 4, struct.pack('<I', 2))     # easy AI
    game.write(slots[1] + 8, b'\x01\x01')           # accepted, has map
    game.res['skirmish_setup'] = True
    return False


def configure(game, skirmish=True):
    """Use ROTWK addresses only; camera/capture DLLs remain BFME2-specific."""
    # This hash-pinned engine supports direct invocation, as the local runtime
    # harness established. Its retail launcher stalls before GameEngine::init.
    game.executable = 'game.dat'
    game.game_logic, game.engine_update = GAME_LOGIC, ENGINE_UPDATE
    game.load_library_slot, game.debug_exits = LOAD_LIBRARY_SLOT, ()
    if skirmish:
        game.on(FILE_SLOTS_SET, skirmish_setup)
    game.ingame = {}
    return game


def launch_menu():
    """Open the clean runtime's menu using the same profile redirection."""
    from mapworkshop.config import ROOT
    from mapworkshop.native import debugger, runtime
    if debugger.running_games():
        raise RuntimeError('A game is already running; close it before starting another test')
    prepare()
    log = open(runtime.LOGS/'menu.log', 'w', encoding='utf-8')
    try:
        return subprocess.Popen([sys.executable, '-m', 'mapworkshop.native.rotwk'], cwd=ROOT,
                                stdout=log, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    finally:
        log.close()


def main():
    """Menu supervisor; the game runs until its window or menu closes it."""
    from mapworkshop.native import debugger, msvc, runtime
    folder = prepare()
    runtime.set_options('Medium')
    args = subprocess.list2cmdline(['-win', '-xres', str(runtime.WIDTH), '-yres', str(runtime.HEIGHT)])
    game = configure(debugger.Game(folder, args, runtime.APPDATA), skirmish=False)
    # The menu can load several maps in one process. The standalone build
    # detects each loading screen and flushes before the tactical view draws.
    if msvc.dll('dinput8').exists():
        game.inject(runtime.staged(msvc.dll('dinput8')))
    def close(game, tid, ctx):
        if ctx.ebx == 0x10:
            game.stop('closed')
        return True
    game.on(CLOSE_ARM, close)
    result = game.run(7*24*3600)
    print(json.dumps(result), flush=True)
    return 0 if result['stopped'] in ('closed', 'exit') else 1


if __name__ == '__main__':
    raise SystemExit(main())
