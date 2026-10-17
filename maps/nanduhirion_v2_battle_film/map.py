"""Battle of Nanduhirion v2 (film): the v2 battle with a scripted camera, for
recording.

The latest Battle of Nanduhirion v2 build (maps/nanduhirion_v2_battle/),
unchanged, with a film over it (mapkit.cinematics): the interface hidden,
health bars and icons off, the far plane pushed out, and SHOTS played in turn
on the battle's own clock. They follow the battle in the arena, where four
battle lines fill the bowl, the Men (players 1 and 4) facing Angmar and
Mordor (8 and 5) across no-man's land until they charge (the battle's
CHARGE):

    the armies drawn up (a crane down over the bowl), all four fronts in one
    frame (a long lens from far beyond the map's north edge, down the
    no-man's land between them), a slide along your front through no-man's
    land, all three battlefronts in one frame (a longer lens from further
    out and higher: the north strip, the arena and the south strip one
    behind the other) held through the charge into the first of the fight,
    and then one slow flight along the whole battle line, from the south
    strip over the arena to the north strip (FLY).

The shots take the lines from the battle's report (NB_Line_n, the middle of
each line's front; maps/nanduhirion_battle/plan.py draws them), so they
follow the battle when it is drawn up anew.

Every move eases in and out (EASE). A shot's camera heights are above the
ground under it, or in the arena above its terraces (TOP), so that a camera
down in the bowl still sees over them; its targets stand LOOK above their
ground. The map gets a skybox as ROTWK's cinematic maps have one (SKYBOX: a
CINE_skybox_* model in the middle of the map at ground level, scaled with
objectPrototypeScale; the stock cin maps of 4,000 to 5,600 units use 0.2 to
0.64, this map is 13,750 wide). The build checks every key: the camera stays
CLEARANCE above the ground.

The scripts stand on PlyrCreeps, which a skirmish keeps and the battle leaves
empty (its own are on PlyrCivilian). Play it as the battle:

    mw build nanduhirion-v2-battle; mw build nanduhirion-v2-battle-film; mw play nanduhirion-v2-battle-film --godot

and record the game window (OBS, the Xbox Game Bar).
"""
import json
import math

from PIL import Image

from mapworkshop import project
from mapworkshop.formats import sections
from mapworkshop.formats.map import Map
from mapworkshop.mapkit import cinematics
from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.script_writer import Writer
from maps.nanduhirion_v2.map import BORDER, CENTRE

START = 0.5                     # seconds into the game the film starts
CLEARANCE = 60                  # the camera stays at least this above the ground
LOOK = 40                       # targets stand this above the ground
INN = (6922, 5593)              # the inn in the middle of the arena (mw where nanduhirion-v2-battle Inn)
FRONT = 770                     # half a line's front, across (nanduhirion_v2_battle ARENA: width 1540)
TOP = 160                       # the arena's highest ground near the bowl: its terraces (125, to 158 at their edges)
LONG = 12500, 1300, 13          # the long-lens shot's camera: this far north (1,250 beyond the map's edge), this high, this many degrees
                                # of view (vertical; the stock 50): its sight line clears the north strip's hills by about 370
WIDE = 19500, 4000, 17          # the three-fronts shot's camera, the same way: 8,250 beyond the edge; it sees every front over the
                                # walls between, the south strip's about 18,800 away (the far plane: 1,800 x CLIP_DEPTH)
SKYBOX, SKYBOX_SCALE ='CINE_skybox_day', 1.6  # the sky, as the cin maps place it (cin fornost, cin gundabad: CINE_skybox_day at 0.5 / 0.64)
FLY = 0, 7000, 1900, 2400, 1300, 45   # the flight: from y to y (the south edge to before the north strip), at this height (absolute), looking
                                      # this far ahead along the line, from this far west of it to this far east, over this many seconds
CLIP_DEPTH = 12                # the far plane, times the game's (the cinematics default 10 falls short of the three-fronts shot)
EASE = 3                        # keys per second of a move; their spacing eases in and out


def eased(t):
    """Smoothstep: 0 to 1 with no jolt at either end."""
    return t*t*(3 - 2*t)


def glide(camera, to, target, target_to=None, seconds=8):
    """Keys gliding camera and target along straight lines, easing in and out."""
    target_to = target_to or target
    steps = max(2, int(seconds*EASE))
    lerp = lambda a, b, t: tuple(p + (q - p)*t for p, q in zip(a, b))
    return [(seconds*i/steps, lerp(camera, to, eased(i/steps)), lerp(target, target_to, eased(i/steps))) for i in range(steps + 1)]


def circle(centre, radius, height, start, sweep, seconds, radius_to=None, height_to=None):
    """Keys circling `centre` from `start` through `sweep` degrees, easing in and out, looking at it; the radius and height may change on
    the way (to radius_to / height_to), a spiral."""
    radius_to, height_to = radius_to or radius, height_to or height
    steps = max(2, int(seconds*EASE))
    cx, cy, cz = centre
    keys = []
    for i in range(steps + 1):
        e = eased(i/steps)
        a = math.radians(start + sweep*e)
        r, h = radius + (radius_to - radius)*e, height + (height_to - height)*e
        keys.append((seconds*i/steps, (cx + r*math.cos(a), cy + r*math.sin(a), cz + h), centre))
    return keys


def build(b):
    battle = project.find('nanduhirion-v2-battle')
    if not battle.map_file.exists():
        raise RuntimeError('Build the battle first: mw build nanduhirion-v2-battle')
    m = Map(battle.map_file.read_bytes())
    wp = json.loads((battle.build_dir/'report.json').read_text(encoding='utf-8'))['waypoints']
    z = m.heightmap()['elevations']*.0390625
    rows, cols = z.shape
    ground = lambda x, y: float(z[min(rows - 1, max(0, int(y//10) + BORDER)), min(cols - 1, max(0, int(x//10) + BORDER))])
    up = lambda x, y, h: (x, y, ground(x, y) + h)        # a camera h above the ground
    over = lambda x, y, h: (x, y, max(ground(x, y), TOP) + h)   # a camera h above the arena's terraces, wherever it is
    on = lambda x, y: (x, y, ground(x, y) + LOOK)        # a target on the ground
    men, angmar = wp['NB_Line_1'], wp['NB_Line_8']       # the north pair's fronts (west, east)
    fight = ((men[0] + angmar[0])/2, men[1])             # no-man's land between them, where they meet
    south = ((wp['NB_Line_4'][0] + wp['NB_Line_5'][0])/2, wp['NB_Line_4'][1])   # the other Men against Mordor
    north_end, south_end = men[1] + FRONT + 200, men[1] - FRONT - 200   # just past each end of the north pair's fronts

    film = cinematics.Film(prefix='NBV', clip_depth=CLIP_DEPTH)
    # 1. The armies drawn up: high over the south-west, craning down over the bowl and its four lines.
    film.shot('Opening', glide(up(5000, 3100, 3000), up(5900, 4300, 1400), on(*CENTRE), on(*INN), seconds=8))
    # 2. All four fronts in one frame: a long lens from far beyond the map's north edge, down the no-man's land between the lines, the
    #    north pair's fronts in front of the south pair's, drifting a little sideways.
    ly, lz, lens = LONG
    film.shot('Lines', glide((fight[0] - 450, ly, lz), (fight[0] + 450, ly, lz), on(fight[0], (men[1] + south[1])/2 + 400),
                             seconds=7), fov=math.radians(lens))
    # 3. Your front: a slide through no-man's land along it, north to south, low, looking a little ahead at its phalanx.
    film.shot('Front', glide(over(fight[0] + 60, north_end, 40), over(fight[0] + 60, south_end, 40),
                             on(men[0] - 60, north_end - 450), on(men[0] - 60, south_end - 450), seconds=7))
    # 4. All three battlefronts in one frame: a longer lens from further out and higher, the north strip in front, the arena behind
    #    it and the south strip at the back, drifting a little sideways. It holds from 22.5 s to 53.5 s: the lines waiting, their
    #    charge (the battle's CHARGE, 39 s) across no-man's land, and the first of the fight on all three fronts.
    wy, wz, lens = WIDE
    film.shot('Fronts', glide((fight[0] + 500, wy, wz), (fight[0] - 500, wy, wz), on(fight[0], 6000), seconds=31), fov=math.radians(lens))
    # 5. The whole battle line, slowly: a flight from the map's south edge along the front, over the south strip, the arena and the north
    #    strip, at one height, drifting from the good side across the line to the evil side, looking ahead along the line.
    fy0, fy1, fz, ahead, drift, seconds = FLY
    film.shot('Flight', glide((fight[0] - drift, fy0, fz), (fight[0] + drift, fy1, fz), on(fight[0], fy0 + ahead), on(fight[0], fy1 + ahead),
                              seconds=seconds))

    # Every key: the camera clear of the ground.
    problems = []
    for name, _, keys, _ in film.shots:
        for t, (x, y, cz), (tx, ty, tz) in keys:
            if cz < ground(x, y) + CLEARANCE:
                problems.append(f'{name} at {t:.1f} s: the camera is under {CLEARANCE} above the ground')
    if problems:
        raise ValueError('Shots the game cannot draw: ' + '; '.join(problems))
    # The skybox, as ROTWK's cinematic maps place theirs: one model in the middle of the map at ground level, scaled.
    add_object(m, SKYBOX, *CENTRE, layer='Film', extra=[('objectPrototypeScale', 2, SKYBOX_SCALE), ('objectName', 3, 'NBV_Skybox')])
    w = Writer(m)
    sides = [dict((k, v) for k, _, v in p['properties']) for p in sections.read(m, 'SidesList')['players']]
    side = next(i for i, s in enumerate(sides) if s.get('playerName') == 'PlyrCreeps')
    w.install(film.install(m, w, start=START), side_index=side)
    b.report.update(shots=[dict(name=n, start=round(s, 1), end=round(e, 1)) for n, s, e in film.timeline(START)],
                    keys={n: [dict(t=round(t, 2), camera=[round(v) for v in c], target=[round(v) for v in g]) for t, c, g in keys]
                          for n, _, keys, _ in film.shots})
    ini = (battle.build_dir/'map.ini').read_text(encoding='ascii', errors='replace')
    b.save(m, ini=ini.split('\n', 1)[1] if ini.startswith(';') else ini, minimap=Image.open(battle.build_dir/'preview.png'))
