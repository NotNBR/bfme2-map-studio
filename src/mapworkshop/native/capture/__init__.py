"""Screenshots from the running game: camera views of a project's map, as
BFME2 renders them, HUD included.

capture() starts a skirmish on the map and loads capture.dll into the game
(debugger.Game.inject: LoadLibraryA on the game's main thread).
The DLL places the tactical camera and copies the D3D9 render target on
request (see capture.cpp). By default the game runs headless: on a hidden
desktop, rendering through DXVK (native.runtime). The launcher reveals the
map, then for each shot
(name, x, y, height) points the camera at the ground below x, y from that
height, waits `settle` rendered frames for the view to stream in, and saves
the frame. The game is ended after the last shot.

capture.dll is committed; `python -m mapworkshop.native.msvc` rebuilds it
from capture.cpp (native.msvc).
"""
import json
import struct
import time
from pathlib import Path

# Retail game.dat 1.06 (RVAs), from Open-BFME-2 and bfme-workshop.
GAME_ENGINE_UPDATE = 0x225DA9   # once per engine frame, on the main thread
REVEAL_MAP = 0x739790           # PartitionManager::revealMapForPlayer(player index), thiscall
THE_PARTITION_MANAGER = 0x9FE74C
THE_PLAYER_LIST = 0x9FEEE8      # PlayerList*: +0x10 local player; Player +0x54 its index


def capture(project, shots, out, graphics='Medium', settle=30, progress=print, timeout=240, headless=True):
    """Save each shot (name, x, y, height) of the project's current build as
    out/<name>.png; returns a report of the shots and the run. `headless`
    (the default) runs the game unseen, through DXVK (native.runtime); False
    shows its window and uses native Direct3D 9."""
    from PIL import Image, ImageStat
    from mapworkshop.native import debugger, msvc, runtime
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    game = runtime.start(project, graphics, headless=headless, progress=progress)
    state = dict(module=None, shot=0, step='load', done=[])

    def loaded(game, exports):
        if not game.u32(exports['mwInstalled']):
            raise RuntimeError('capture.dll did not install its hooks (not BFME2 1.06?)')
        state['module'] = exports
    game.inject(runtime.staged(msvc.dll('capture')), loaded)

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

    progress(f'Starting {project.title} at {graphics} detail' + (' (headless)' if headless else '')
             + f' for {len(shots)} screenshot(s)...')
    started = time.time()
    result = game.run(timeout, tick, tick_every=0.05)
    report = dict(map=project.id, graphics=graphics, headless=headless, shots=state['done'], seconds=round(time.time() - started, 1),
                  run=result)
    (out/'capture.json').write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8')
    if len(state['done']) != len(shots) and not result.get('injected', {}).get('capture.dll', True):
        raise RuntimeError('BFME2 could not load capture.dll')
    if len(state['done']) != len(shots):
        raise RuntimeError(f'The game ended after {len(state["done"])} of {len(shots)} shots: '
                           + debugger.describe(result))
    return report
