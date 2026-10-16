"""Nanduhirion: the map from the community 2.02 patch, unchanged, to look at
beside Nanduhirion Enlarged (maps/nanduhirion_enlarged/), which stretches its
terrain.

The build reads `map mp nanduhirion` from `__patch202.big` in the ROTWK
folder (`mw config rotwk`): the ROTWK profile's extracted data leaves that
archive out. It keeps everything: terrain, the 1,883 objects, lighting,
camera settings, map.ini and minimap. Only the WorldInfo name and
description, which the original leaves empty, are set from map.toml. Its game
folder name, `map mp nanduhirion original`, keeps it apart from the patch's
own copy.
"""
import io
from pathlib import Path

from PIL import Image

from mapworkshop.config import setting
from mapworkshop.formats.big import BigArchive
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import set_world

ARCHIVE = '__patch202.big'      # in the ROTWK folder
FOLDER = 'maps/map mp nanduhirion/'


def build(b):
    folder = setting('rotwk')
    if not folder:
        raise RuntimeError('The map is in the ROTWK folder: mw config rotwk DIR')
    archive = BigArchive(Path(folder)/ARCHIVE)
    m = Map(archive.read_bytes(FOLDER + 'map mp nanduhirion.map'))
    set_world(m, mapName=b.project.title, mapDescription=b.project.description)
    minimap = Image.open(io.BytesIO(archive.read_bytes(FOLDER + 'map mp nanduhirion_art.tga')))
    b.save(m, ini=archive.read(FOLDER + 'map.ini').replace('\r\n', '\n'), minimap=minimap)
