"""Screenshots from the running game: camera views of a project's map, as
BFME2 renders them, HUD included.

capture() starts a skirmish on the map and loads capture.dll into the game
(LoadLibraryA, called on the game's main thread from GameEngine::update).
The DLL places the tactical camera and copies the D3D9 render target on
request (see capture.cpp). The launcher reveals the map, then for each shot
(name, x, y, height) points the camera at the ground below x, y from that
height, waits `settle` rendered frames for the view to stream in, and saves
the frame. The game is ended after the last shot.

capture.dll is committed; `python -m mapworkshop.native.capture build`
rebuilds it from capture.cpp with Visual C++ .NET 2003 (setting `msvc71`,
default openbfme2-untouched's toolchain next to this checkout).
"""
import json
import shutil
import struct
import subprocess
import time
import os
from pathlib import Path

from mapworkshop.config import ROOT, setting

HERE = Path(__file__).parent
DLL = HERE/'capture.dll'
TOOLCHAIN = ROOT.parent/'openbfme2/openbfme2-untouched/reference/open-bfme-1/inputs/toolchains/vs2003' \
    / 'Program Files/Microsoft Visual Studio .NET 2003'

# Retail game.dat 1.06 (RVAs), from Open-BFME-2 and bfme-workshop.
GAME_ENGINE_UPDATE = 0x225DA9   # once per engine frame, on the main thread
LOAD_LIBRARY_SLOT = 0x7BA1F4    # game.dat's import slot of LoadLibraryA
REVEAL_MAP = 0x739790           # PartitionManager::revealMapForPlayer(player index), thiscall
THE_PARTITION_MANAGER = 0x9FE74C
THE_PLAYER_LIST = 0x9FEEE8      # PlayerList*: +0x10 local player; Player +0x54 its index


def build():
    """Compile capture.cpp into capture.dll (32-bit, MSVC 7.1, msvcr71 as the game uses)."""
    root = Path(setting('msvc71') or TOOLCHAIN)
    vc = root/'Vc7'
    if not (vc/'bin/cl.exe').is_file():
        raise RuntimeError(f'No Visual C++ .NET 2003 in {root}; set its folder with `mw config msvc71 <folder>`')
    # The compiler's own msvcr71.dll and msvcp71.dll sit two folders up.
    env = dict(os.environ, PATH=os.pathsep.join(map(str, [vc/'bin', root/'Common7/IDE', root.parents[1]]))
               + os.pathsep + os.environ['PATH'],
               INCLUDE=os.pathsep.join(map(str, [vc/'include', vc/'PlatformSDK/Include'])),
               LIB=os.pathsep.join(map(str, [vc/'lib', vc/'PlatformSDK/Lib'])))
    work = ROOT/'local/cache/capture-build'
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(vc/'bin/cl.exe'), '/nologo', '/O2', '/MD', '/LD', str(HERE/'capture.cpp'),
                    '/Fe' + str(work/'capture.dll'), '/Fo' + str(work/'capture.obj'),
                    '/link', '/MACHINE:X86', 'kernel32.lib'], env=env, cwd=work, check=True)
    shutil.copy2(work/'capture.dll', DLL)
    return DLL


def capture(project, shots, out, graphics='Medium', settle=30, progress=print, timeout=240):
    """Save each shot (name, x, y, height) of the project's current build as
    out/<name>.png; returns a report of the shots and the run."""
    from PIL import Image, ImageStat
    from mapworkshop.native import debugger, runtime
    from mapworkshop.native.pe import PE
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    game = runtime.start(project, graphics)
    dll = runtime.RUNTIME/'capture.dll'                    # a copy, so a rebuild never finds it in use
    if not dll.exists() or dll.read_bytes() != DLL.read_bytes():
        shutil.copy2(DLL, dll)
    exports = PE(dll).exports()
    state = dict(module=None, shot=0, step='load', done=[])

    def load(game, tid, ctx):
        path = str(dll.resolve()).encode('mbcs') + b'\0'
        memory = game.alloc(len(path))
        game.write(memory, path)

        def loaded(game, results):
            if not results[0]:
                raise RuntimeError('BFME2 could not load capture.dll')
            state['module'] = {name: results[0] + rva for name, rva in exports.items()}
            if not game.u32(state['module']['mwInstalled']):
                raise RuntimeError('capture.dll did not install its hooks (not BFME2 1.06?)')
        return {'call': game.u32(game.base + LOAD_LIBRARY_SLOT), 'args': [memory], 'done': loaded}
    game.on(GAME_ENGINE_UPDATE, load)

    def reveal(game, tid, ctx):
        player = game.u32(game.u32(game.base + THE_PLAYER_LIST) + 0x10)
        return {'call': game.base + REVEAL_MAP, 'ecx': game.u32(game.base + THE_PARTITION_MANAGER),
                'args': [game.u32(player + 0x54)]}

    def tick(game):
        frame, mode = game.logic()
        module = state['module']
        if not module or mode != debugger.SKIRMISH or frame is None or frame < 5:
            return None
        photo, cap = module['mwPhoto'], module['mwCapture']
        frames = game.u32(cap + 24)
        if state['step'] == 'load':
            game.arm(GAME_ENGINE_UPDATE, reveal)
            state['step'] = 'move'
        if state['step'] == 'move':
            name, x, y, height = shots[state['shot']]
            game.write(photo, struct.pack('<I3f', 1, x, y, height))
            state.update(step='settle', since=frames)
        elif state['step'] == 'settle' and frames >= state['since'] + settle:
            game.write(cap, struct.pack('<I', 1))
            state['step'] = 'read'
        elif state['step'] == 'read' and not game.u32(cap):
            status, w, h, pitch, pixels = struct.unpack('<5I', game.read(cap + 4, 20))
            name, x, y, height = shots[state['shot']]
            if status or not pixels or not (0 < w <= 8192 and 0 < h <= 8192):
                raise RuntimeError(f'The game could not copy its frame for {name} (status {status:#x}, '
                                   f'surface format {game.u32(cap + 28)})')
            picture = Image.frombytes('RGB', (w, h), game.read(pixels, pitch*h), 'raw', 'BGRX', pitch, 1)
            path = out/f'{name}.png'
            picture.save(path)
            stddev = sum(ImageStat.Stat(picture).stddev)/3
            state['done'].append(dict(name=name, x=x, y=y, height=height, path=str(path), width=w, height_px=h,
                                      frame=frame, seconds=game.seconds(), stddev=round(stddev, 1)))
            progress(f'  {name}: {path.name} ({w} x {h}, logic frame {frame})')
            state['shot'] += 1
            if state['shot'] == len(shots):
                return 'done'
            state['step'] = 'move'
        return None

    progress(f'Starting {project.title} at {graphics} detail for {len(shots)} screenshot(s)...')
    started = time.time()
    result = game.run(timeout, tick, tick_every=0.05)
    report = dict(map=project.id, graphics=graphics, shots=state['done'], seconds=round(time.time() - started, 1),
                  run=result)
    (out/'capture.json').write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8')
    if len(state['done']) != len(shots):
        raise RuntimeError(f'The game ended after {len(state["done"])} of {len(shots)} shots: '
                           + debugger.describe(result))
    return report
