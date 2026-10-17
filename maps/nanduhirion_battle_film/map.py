"""Battle of Nanduhirion (film): the battle with a scripted camera, for
recording.

The latest Battle of Nanduhirion build (maps/nanduhirion_battle/), unchanged,
with a film over it (mapkit.cinematics): the interface hidden, health bars
and icons off, the far plane pushed out, and SHOTS played in turn on the
battle's own clock: the armies drawn up, the lines before the clash, the
clash round the inn, both strip fronts, the heights over the arena, your
first wave appearing on the plateau, the whole field from above, and later
the arena, the north lane and Mordor's third wave. A shot's camera heights
are above the ground under it; the build refuses a key below CLEARANCE.
Shots look down at 35 degrees or more: the game draws no sky, and a level
view shows black beyond the map's edge.

The scripts stand on PlyrCreeps, which a skirmish keeps and the battle
leaves empty (its own are on PlyrCivilian). Play it as the battle:

    mw build nanduhirion-battle; mw build nanduhirion-battle-film; mw play nanduhirion-battle-film

and record the game window (OBS, the Xbox Game Bar).
"""
import json

from PIL import Image

from mapworkshop import project
from mapworkshop.formats import sections
from mapworkshop.formats.map import Map
from mapworkshop.mapkit import cinematics
from mapworkshop.mapkit.script_writer import Writer
from maps.nanduhirion_v1.map import BORDER, CENTRE, twin

START = 0.5                     # seconds into the game the film starts
CLEARANCE = 60                  # the camera stays at least this above the ground
INN = (7172, 7063)
LOOK = 40                       # targets stand this above the ground


def build(b):
    battle = project.find('nanduhirion-battle')
    if not battle.map_file.exists():
        raise RuntimeError('Build the battle first: mw build nanduhirion-battle')
    m = Map(battle.map_file.read_bytes())
    rally = json.loads((battle.build_dir/'report.json').read_text(encoding='utf-8'))['waypoints']
    z = m.heightmap()['elevations']*.0390625
    ground = lambda x, y: float(z[int(y//10) + BORDER, int(x//10) + BORDER])
    up = lambda x, y, h: (x, y, ground(x, y) + h)        # a camera h above the ground
    on = lambda x, y: (x, y, ground(x, y) + LOOK)        # a target on the ground

    film = cinematics.Film(prefix='NBF')
    # The armies drawn up, from high over the south-west, coming down.
    film.shot('Deploy', cinematics.move(up(4300, 4300, 2600), up(5300, 5400, 1500), on(*CENTRE), seconds=12))
    # Along the west lines, between the armies, as the clash is ordered.
    film.shot('Lines', cinematics.move(up(6950, 8500, 280), up(6950, 5450, 280), on(6250, 8300), on(6250, 5650), seconds=10))
    # The clash, round the inn.
    film.shot('Clash', cinematics.orbit(on(*INN), 1300, 750, 190, 100, seconds=14))
    # The north strip (the elves and the goblins), then its twin in the south (the dwarves and Isengard).
    film.shot('North', cinematics.move(up(7140, 9200, 1700), up(7140, 10200, 1300), on(7140, 10700), on(7140, 11500), seconds=12))
    film.shot('South', cinematics.move(up(*twin((7140, 9200)), 1700), up(*twin((7140, 10200)), 1300),
                                       on(*twin((7140, 10700))), on(*twin((7140, 11500))), seconds=12))
    # From above the archers on the west heights, across the arena.
    film.shot('Heights', cinematics.move(up(5000, 7900, 1100), up(5100, 6200, 1100), on(6700, 7300), on(6700, 6600), seconds=10))
    # Your first wave (at 75 s) appearing at your rally point on the plateau and marching off.
    rx, ry = rally['NB_Rally_1']
    film.shot('Wave', cinematics.move(up(rx - 600, ry - 700, 500), up(rx - 300, ry - 500, 400), on(rx + 150, ry),
                                      on(rx + 400, ry), seconds=10), start=74.5)
    # The whole field, from high above.
    film.shot('Field', cinematics.orbit(on(*CENTRE), 4200, 5200, 200, 70, seconds=20))
    # The arena again, lower, the other way round.
    film.shot('Melee', cinematics.orbit(on(*INN), 900, 450, 20, -90, seconds=14), start=120)
    # The north lane: the elves' line and their outposts.
    film.shot('Lane', cinematics.move(up(5000, 10600, 400), up(5300, 12000, 400), on(6400, 11000), on(6600, 11800), seconds=12))
    # Mordor's third wave (at 375 s) appearing at its rally point and marching off.
    ex, ey = rally['NB_Rally_5']
    film.shot('Mordor', cinematics.move(up(ex + 600, ey - 700, 500), up(ex + 300, ey - 500, 400), on(ex - 150, ey),
                                        on(ex - 400, ey), seconds=10), start=374.5)
    film.shot('End', cinematics.orbit(on(*CENTRE), 3600, 4400, 30, 90, seconds=24))

    for name, _, keys, _ in film.shots:
        for t, (x, y, cz), _ in keys:
            if cz < ground(x, y) + CLEARANCE:
                raise ValueError(f'Shot {name} at {t:.1f} s: the camera is under {CLEARANCE} above the ground')
    w = Writer(m)
    sides = [dict((k, v) for k, _, v in p['properties']) for p in sections.read(m, 'SidesList')['players']]
    side = next(i for i, s in enumerate(sides) if s.get('playerName') == 'PlyrCreeps')
    w.install(film.install(m, w, start=START), side_index=side)
    b.report.update(shots=[dict(name=n, start=round(s, 1), end=round(e, 1)) for n, s, e in film.timeline(START)])
    ini = (battle.build_dir/'map.ini').read_text(encoding='ascii', errors='replace')
    b.save(m, ini=ini.split('\n', 1)[1] if ini.startswith(';') else ini, minimap=Image.open(battle.build_dir/'preview.png'))
