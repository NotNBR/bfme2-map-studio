"""Dump BFME2's own pathfinding grid from a running skirmish.

Run by mapworkshop.native under bfme-workshop's Python, which provides the
isolated BFME2 1.06 runtime and its launch hooks; it imports bfme-workshop's
packages, never mapworkshop's:

  pathfind_dump.py MAP_ID OUT_DIR       e.g. 'maps\\map mp bridge lab.map'

Runs host.launch's standalone test path with a frame hook in place of the
script check: from frame 10 it reads TheAI->m_pathfinder (Open-BFME-2
PathfinderNewMap.cpp, PathfindLayerAllocateCells.cpp) and writes the cell
flags of the ground grid and of each bridge layer to OUT_DIR/pathfind.npz.
"""
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np

THE_AI = 0x9FF0F8               # RVA of TheAI (VA 0xDFF0F8)
AI_PATHFINDER = 0x10
PF_READY, PF_BLOCK, PF_EXTENT, PF_LAYERS = 0x08, 0x0C, 0x14, 0x60
LAYER_SIZE, LAYERS = 0x40, 16
CELL = 16                       # sizeof(PathfindCell); flags at +0x0C
READ_FRAME = 10

map_id, out = sys.argv[1], Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
state = dict(done=False)


def grid(game, block, width, height):
    raw = b''
    total = width * height * CELL
    for start in range(0, total, 1 << 22):                 # read in 4 MB pieces
        part = game.read(block + start, min(1 << 22, total - start))
        if part is None or len(part) != min(1 << 22, total - start):
            raise RuntimeError('Pathfinder cell block unreadable')
        raw += part
    cells = np.frombuffer(raw, '<u4').reshape(width, height, 4)  # column-major: [x][y]
    return cells[:, :, 3].T.copy()                                # flags, as [y][x]


def dump(game):
    ai = game.u32(game.base + THE_AI)
    pf = game.u32(ai + AI_PATHFINDER) if ai else None
    if not pf:
        raise RuntimeError('No pathfinder')
    ready = game.read(pf + PF_READY, 1)[0]
    lo_x, lo_y, hi_x, hi_y = struct.unpack('<4i', game.read(pf + PF_EXTENT, 16))
    if (lo_x, lo_y) != (0, 0) or not (0 < hi_x < 4096 and 0 < hi_y < 4096):
        raise RuntimeError(f'Implausible pathfinder extent {(lo_x, lo_y, hi_x, hi_y)}')
    ground = grid(game, game.u32(pf + PF_BLOCK), hi_x + 1, hi_y + 1)
    arrays = dict(ground=ground)
    layers = []
    for i in range(LAYERS):
        base = pf + PF_LAYERS + i * LAYER_SIZE
        block, _, width, height, x0, y0 = struct.unpack('<2I4i', game.read(base, 0x18))
        bridge = game.u32(base + 0x34)
        if not block or not (0 < width < 4096 and 0 < height < 4096):
            continue
        arrays[f'layer{i}'] = grid(game, block, width, height)
        layers.append(dict(index=i, x0=x0, y0=y0, width=width, height=height, bridge=bool(bridge)))
    np.savez_compressed(out / 'pathfind.npz', **arrays)
    data = game.u32(ai + 0x18)                   # TheAI->m_aiData: the depth limits classifyMapCell uses
    water_depth, deep_water_depth = struct.unpack('<2f', game.read(data + 0x98, 8)) if data else (None, None)
    info = dict(map=map_id, ready=bool(ready), water_depth=water_depth, deep_water_depth=deep_water_depth, frame=game.logic()[0], read=time.strftime('%Y-%m-%d %H:%M'), extent=[lo_x, lo_y, hi_x, hi_y], cell_size=10, layers=layers,
                types=dict((int(t), int(n)) for t, n in zip(*np.unique(ground & 0xF, return_counts=True))))
    (out / 'pathfind.json').write_text(json.dumps(info, indent=2) + '\n')
    return info


def register(smoke, _proof):
    original = smoke.skirmish_tick

    def factory(args, samples, mode):
        args.seconds = 15
        basic = original(args, samples, mode)

        def tick(game):
            result = basic(game)
            frame, current = game.logic()
            if not state['done'] and current == mode and frame is not None and frame >= READ_FRAME:
                state['done'] = True
                try:
                    state['info'] = dump(game)
                    state['frame'] = frame
                except Exception as error:      # reported by validate
                    state['error'] = repr(error)
            return result
        return tick
    smoke.skirmish_tick = factory


def preflight(mod, map_name, proof):
    from capture.screenshots import resolve_map
    return resolve_map(mod, map_name)[0]


def validate(output, proof, source=None):
    report = dict(frame=state.get('frame'), error=state.get('error'), info=state.get('info'))
    (out / 'native.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
    print(json.dumps(report, default=str)[:2000])
    return 0 if state.get('info') else 1


import mapkit.script_check as script_check
script_check.preflight, script_check.register, script_check.validate = preflight, register, validate
import host.launch
sys.argv = ['host.launch', '--script-check', str(out / 'unused.json'), '--map', map_id]
raise SystemExit(host.launch.main())
