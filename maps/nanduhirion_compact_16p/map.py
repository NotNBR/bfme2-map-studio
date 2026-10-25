"""Nanduhirion Compact: the authored 9,000 x 6,000 map with all sixteen starts.

This imports the validated compact map from the bundled references, so building
and opening it needs no external share ZIP or machine-specific source path.
Compared with Medium (9,900 x 8,100), X is reduced by 9% and Y by 26%.
Terrain heights follow the Y scale; gameplay objects keep their normal size.
All farm sites and objectives remain. Static terrain and footprint checks
found all starts walkable and connected to the centre; a full match remains
unverified. Requires OpenBFME's sixteen-player support for play.

Derived from the community Nanduhirion map and the locally authored v2 layout.
Original assets remain credited to their respective creators.
"""
from PIL import Image

from mapworkshop.formats.map import Map
from mapworkshop.formats import sections


def build(b):
    source = b.project.folder / 'references'
    m = Map((source / 'compact.map').read_bytes())
    terrain = m.heightmap()
    border = terrain['border']
    assert (terrain['width'] - 2 * border, terrain['height'] - 2 * border) == (900, 600)
    assert len(sections.read(m, 'MPPositionList')) == b.project.players == 16
    with Image.open(source / 'minimap.tga') as minimap:
        b.save(m, ini=(source / 'map.ini').read_text(encoding='ascii'), minimap=minimap)
