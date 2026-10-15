"""Screenshots from the running game: camera views of a project's map, as
BFME2 renders them, HUD included.

capture() starts a skirmish on the map; like every game native.runtime
starts, it loads ingame.dll (native/ingame/ingame.cpp), which places the
tactical camera and copies the D3D9 render target on request. By default the game runs headless: on a hidden
desktop, rendering through DXVK (native.runtime). The launcher reveals the
map, then for each shot
(name, x, y, height) points the camera at the ground below x, y from that
height, waits `settle` rendered frames for the view to stream in, and saves
the frame. A shot (name, x, y, height, frame) waits until the game's logic
reaches that frame first, so a run can photograph a scripted scenario as it
plays out. A shot given as a dict may also set `pitch` (degrees below the
horizon), `heading` (degrees, 0 north, 90 east) and `distance` from the
point: ingame.dll then replaces the game's camera with that one, for low
cinematic views the game's own camera never takes. The game is ended after
the last shot.
"""
import json
import math
import struct
import time
from pathlib import Path

# Retail game.dat 1.06 (RVAs), from Open-BFME-2 and bfme-workshop.
GAME_ENGINE_UPDATE = 0x225DA9   # once per engine frame, on the main thread


def capture(project, shots, out, graphics='Medium', settle=30, progress=print, timeout=240, headless=True, delay=0):
    """Save each shot (name, x, y, height[, logic frame]) of the project's current build as
    out/<name>.png; returns a report of the shots and the run. `headless`
    (the default) runs the game unseen, through DXVK (native.runtime); False
    shows its window and uses native Direct3D 9."""
    from mapworkshop.config import PROFILE
    if PROFILE == 'rotwk':
        raise RuntimeError('Native screenshot capture currently supports BFME2 1.06 only')
    from PIL import Image, ImageStat
    from mapworkshop.native import debugger, runtime
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    def shot(s):
        if isinstance(s, dict):
            return dict(dict(frame=None, height=300., pitch=0., heading=0., distance=0.), **s)
        name, x, y, height, *at = s
        return dict(name=name, x=x, y=y, height=height, frame=at[0] if at else None, pitch=0., heading=0., distance=0.)
    shots = [shot(s) for s in shots]
    game = runtime.start(project, graphics, headless=headless, progress=progress)
    state = dict(shot=0, step='load', done=[])

    def tick(game):
        frame, mode = game.logic()
        module = game.ingame
        if not module or mode != debugger.SKIRMISH or frame is None or frame < 5:
            return None
        photo, cap = module['mwPhoto'], module['mwCapture']
        frames = game.u32(cap + 24)
        if state['step'] == 'load':
            game.arm(GAME_ENGINE_UPDATE, runtime.reveal_map)
            state['step'] = 'move'
        if state['step'] == 'move':
            s = shots[state['shot']]
            if s['frame'] is not None and frame < s['frame']:
                return None                       # not yet: the shot waits for its logic frame
            game.write(photo, struct.pack('<I6f', 1, s['x'], s['y'], s['height'], math.radians(s['pitch']),
                                          math.radians(s['heading']), s['distance']))
            state.update(step='settle', since=frames, moved=time.time())
        elif (state['step'] == 'settle' and frames >= state['since'] + settle
              and time.time() >= state['moved'] + delay/1000):   # `delay` ms at least
            game.write(cap, struct.pack('<I', 1))
            state['step'] = 'read'
        elif state['step'] == 'read' and not game.u32(cap):
            status, w, h, pitch, pixels = struct.unpack('<5I', game.read(cap + 4, 20))
            s = shots[state['shot']]
            name, x, y, height = s['name'], s['x'], s['y'], s['height']
            if (status or not pixels) and state.get('retries', 0) < 8:
                # Out of video memory for the copy (0x8876017C at High with
                # many units on screen) passes: ask again a few frames on.
                state['retries'] = state.get('retries', 0)+1
                state.update(step='settle', since=frames-settle+5)
                return None
            state['retries'] = 0
            if status or not pixels or not (0 < w <= 8192 and 0 < h <= 8192):
                raise RuntimeError(f'The game could not copy its frame for {name} (status {status:#x}, '
                                   f'surface format {game.u32(cap + 28)})')
            picture = Image.frombytes('RGB', (w, h), game.read(pixels, pitch*h), 'raw', 'BGRX', pitch, 1)
            path = out/f'{name}.png'
            picture.save(path)
            stddev = sum(ImageStat.Stat(picture).stddev)/3
            state['done'].append(dict(s, path=str(path), width=w, height_px=h, frame=frame, seconds=game.seconds(),
                                      stddev=round(stddev, 1)))
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
    if len(state['done']) != len(shots) and not game.ingame:
        raise RuntimeError('BFME2 could not load ingame.dll' + (f' ({result["ingame"]}; not BFME2 1.06?)'
                                                                 if 'ingame' in result else ''))
    if len(state['done']) != len(shots):
        raise RuntimeError(f'The game ended after {len(state["done"])} of {len(shots)} shots: '
                           + debugger.describe(result))
    return report
