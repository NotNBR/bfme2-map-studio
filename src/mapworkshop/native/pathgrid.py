"""Read BFME2's own pathfinding grid from a skirmish on a project.

From logic frame 10 of the skirmish, read() takes TheAI->m_pathfinder
(Open-BFME-2 PathfinderNewMap.cpp, PathfindLayerAllocateCells.cpp): the cell
flags of the ground grid and of each bridge layer, and the water depth
limits the cells were classified with. The game is ended as soon as they
are read.
"""
import struct
import time

import numpy as np

THE_AI = 0x9FF0F8               # RVA of TheAI
AI_PATHFINDER, AI_DATA = 0x10, 0x18
PF_READY, PF_BLOCK, PF_EXTENT, PF_LAYERS = 0x08, 0x0C, 0x14, 0x60
LAYER_SIZE, LAYERS = 0x40, 16
CELL = 16                       # sizeof(PathfindCell); flags at +0x0C
READ_FRAME = 10


def grid(game, block, width, height):
    total = width * height * CELL
    raw = b''
    for start in range(0, total, 1 << 22):                 # in 4 MB pieces
        part = game.read(block + start, min(1 << 22, total - start))
        if part is None or len(part) != min(1 << 22, total - start):
            raise RuntimeError('The pathfinder cell block is unreadable')
        raw += part
    cells = np.frombuffer(raw, '<u4').reshape(width, height, 4)    # column-major: [x][y]
    return cells[:, :, 3].T.copy()                                  # flags, as [y][x]


def read(game):
    """(arrays, info) of the running skirmish's pathfinder."""
    ai = game.u32(game.base + THE_AI)
    pf = game.u32(ai + AI_PATHFINDER) if ai else None
    if not pf:
        raise RuntimeError('The game has no pathfinder')
    ready = game.read(pf + PF_READY, 1)[0]
    lo_x, lo_y, hi_x, hi_y = struct.unpack('<4i', game.read(pf + PF_EXTENT, 16))
    if (lo_x, lo_y) != (0, 0) or not (0 < hi_x < 4096 and 0 < hi_y < 4096):
        raise RuntimeError(f'Implausible pathfinder extent {(lo_x, lo_y, hi_x, hi_y)}')
    ground = grid(game, game.u32(pf + PF_BLOCK), hi_x + 1, hi_y + 1)
    arrays, layers = dict(ground=ground), []
    for i in range(LAYERS):
        base = pf + PF_LAYERS + i*LAYER_SIZE
        block, _, width, height, x0, y0 = struct.unpack('<2I4i', game.read(base, 0x18))
        if not block or not (0 < width < 4096 and 0 < height < 4096):
            continue
        arrays[f'layer{i}'] = grid(game, block, width, height)
        layers.append(dict(index=i, x0=x0, y0=y0, width=width, height=height, bridge=bool(game.u32(base + 0x34))))
    data = game.u32(ai + AI_DATA)                # TheAI->m_aiData: the depth limits classifyMapCell uses
    water, deep = struct.unpack('<2f', game.read(data + 0x98, 8)) if data else (None, None)
    info = dict(ready=bool(ready), water_depth=water, deep_water_depth=deep, frame=game.logic()[0],
                read=time.strftime('%Y-%m-%d %H:%M'), extent=[lo_x, lo_y, hi_x, hi_y], cell_size=10, layers=layers,
                types={int(t): int(n) for t, n in zip(*np.unique(ground & 0xF, return_counts=True))})
    return arrays, info


def run(game, timeout=300):
    """Run a prepared skirmish (runtime.start) until the grid is read; returns
    (arrays, info). Raises RuntimeError when the game ends first."""
    from mapworkshop.native.debugger import SKIRMISH, describe
    found = {}

    def tick(game):
        frame, mode = game.logic()
        if mode == SKIRMISH and frame is not None and frame >= READ_FRAME:
            found['grid'] = read(game)
            return 'read'
        return None
    result = game.run(timeout, tick)
    if 'grid' not in found:
        raise RuntimeError(f'The game ended before its pathfinding grid was read: {describe(result)}')
    return found['grid']
