"""Rebuild Compact's texture transitions after importing its resized painting.

Viewer pin 1 at (4877.4, 3927.6) exposed grass/dirt boundaries with no blend
on either side. Keep the painted regions and regenerate native corner blends
across the map, including the intermediate textures already in its palette.
"""
import numpy as np

from mapworkshop.formats.terrain import decode_blend, encode_blend
from mapworkshop.mapkit.blank import corner_blend_records, fill_enclosed, tile_offset


def repair_transitions(m):
    """Replace stale imported blends; retain cliff mapping and base UV phases."""
    chunk = m.chunk('BlendTileData')
    blend = decode_blend(chunk.data, chunk.version, m)
    arrays = blend['arrays']
    arrays['tiles'] = arrays['tiles'].copy()
    textures = blend['textures']
    starts = np.array([4*t['cell_start'] for t in textures])
    sizes = np.array([t['cell_size'] for t in textures])
    assert np.all(sizes == 4), 'Compact uses four-cell terrain classes'
    labels = np.searchsorted(starts, arrays['tiles'], side='right')-1
    original = labels.copy()
    labels = fill_enclosed(labels)

    def tile_index(label, y, x):
        return starts[label] + tile_offset(x, y, sizes[label])

    primary, extra, records = corner_blend_records(labels, tile_index)
    mapped = arrays['cliffs'] != 0
    changed = (labels != original) & ~mapped
    yy, xx = np.nonzero(changed)
    arrays['tiles'][yy, xx] = tile_index(labels[yy, xx], yy, xx)
    primary[mapped] = extra[mapped] = 0
    report = dict(filled_cells=int(changed.sum()),
                  primary_cells_changed=int(np.count_nonzero(arrays['blends'] != primary)),
                  primary_cells=int(np.count_nonzero(primary)),
                  three_way_cells=int(np.count_nonzero(extra)))
    arrays['blends'], arrays['three_way'] = primary, extra
    blend['blend_records'] = records
    # decode retains the old declared count; the replacement table has a new size.
    blend['blend_count'] = len(records)+1
    chunk.data = encode_blend(blend, chunk.version, m)
    return report
