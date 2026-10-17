"""Battle of Nanduhirion v2 (zoom): the v2 battle with the camera on the inn,
zooming in and out through the clash, a repeatable view for profiling
OpenBFME in a big fight.

The latest Battle of Nanduhirion v2 build (maps/nanduhirion_v2_battle/),
unchanged, with one shot over it (mapkit.cinematics): from ZOOM_START seconds,
just after the armies charge (the battle's CHARGE), the camera looks at
the inn in the middle of the arena from the south-west, PITCH degrees down,
and its distance swings smoothly between FAR and NEAR, a cosine of PERIOD
seconds, CYCLES times. Unlike the battle film, the interface, health bars and
icons stay on (UI), so a profile has the HUD's and the control bar's work as in
play; UI = False hides the interface as the film does.

    mw build nanduhirion-v2-battle; mw build nanduhirion-v2-battle-zoom; mw play nanduhirion-v2-battle-zoom --godot
"""
import json
import math

from PIL import Image

from mapworkshop import project
from mapworkshop.formats import sections
from mapworkshop.formats.map import Map
from mapworkshop.mapkit import cinematics
from mapworkshop.mapkit.script_writer import Writer
from maps.nanduhirion_v2.map import BORDER
from maps.nanduhirion_v2_battle.map import CHARGE

INN = (6922, 5593)              # the inn in the middle of the arena (mw where nanduhirion-v2-battle Inn)
LOOK = 40                       # the target stands this above the ground
ZOOM_START = CHARGE + 5         # seconds of game time: just after the armies charge
FAR, NEAR = 2800, 600           # the camera's distance from the target
PERIOD, CYCLES = 20, 3          # seconds per zoom in and out, and how many
PITCH, HEADING = 50, 225        # degrees down, and the direction the camera stands in (0 east, counter-clockwise: south-west)
CLEARANCE = 60                  # the camera stays at least this above the ground
UI = True                       # keep the interface (the control bar); False hides it as a film does


def zoom_keys(target):
    """A key a second: the camera on the line from `target` towards HEADING, PITCH down, its distance a cosine from FAR to NEAR and back."""
    tx, ty, tz = target
    pitch, heading = math.radians(PITCH), math.radians(HEADING)
    keys = []
    for second in range(PERIOD*CYCLES + 1):
        d = (FAR + NEAR)/2 + (FAR - NEAR)/2*math.cos(2*math.pi*second/PERIOD)
        flat = d*math.cos(pitch)
        keys.append((float(second), (tx + flat*math.cos(heading), ty + flat*math.sin(heading), tz + d*math.sin(pitch)), target))
    return keys


def build(b):
    battle = project.find('nanduhirion-v2-battle')
    if not battle.map_file.exists():
        raise RuntimeError('Build the battle first: mw build nanduhirion-v2-battle')
    m = Map(battle.map_file.read_bytes())
    z = m.heightmap()['elevations']*.0390625
    ground = lambda x, y: float(z[int(y//10) + BORDER, int(x//10) + BORDER])

    film = cinematics.Film(prefix='NBZ', icons=True, ui=UI)
    film.shot('Inn', zoom_keys((*INN, ground(*INN) + LOOK)), start=ZOOM_START)
    for name, _, keys, _ in film.shots:
        for t, (x, y, cz), _ in keys:
            if cz < ground(x, y) + CLEARANCE:
                raise ValueError(f'Shot {name} at {t:.1f} s: the camera is under {CLEARANCE} above the ground')
    w = Writer(m)
    sides = [dict((k, v) for k, _, v in p['properties']) for p in sections.read(m, 'SidesList')['players']]
    side = next(i for i, s in enumerate(sides) if s.get('playerName') == 'PlyrCreeps')
    w.install(film.install(m, w, start=ZOOM_START), side_index=side)
    b.report.update(shots=[dict(name=n, start=round(s, 1), end=round(e, 1)) for n, s, e in film.timeline(ZOOM_START)],
                    zoom=dict(target=INN, far=FAR, near=NEAR, period=PERIOD, cycles=CYCLES))
    ini = (battle.build_dir/'map.ini').read_text(encoding='ascii', errors='replace')
    b.save(m, ini=ini.split('\n', 1)[1] if ini.startswith(';') else ini, minimap=Image.open(battle.build_dir/'preview.png'))
