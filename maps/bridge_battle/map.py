"""Battle of the Sirannon Bridge: a film set on the Hollin Dales.

The latest Hollin Dales build, with two armies drawn up either side of the
bridge of Ost-in-Edhil, each in depth: shield walls on the bridge deck, foot
at the bridgehead, archers behind it, cavalry or trolls on the flanks and
siege engines at the back. Gondor (Player_1) holds the west bank, Mordor
(the creeps, hostile to everyone) the east.

Scripts at the start: every melee unit attack-moves across the bridge to the
far bridgehead, the archers attack-move up to their own bank, the siege
engines up to their quarter's square, and the flanks follow the foot across.

    mw build hollin-dales; mw build bridge-battle
    mw capture bridge-battle --view NAME X Y DISTANCE PITCH HEADING --at FRAME ...
"""
import math

from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.script_writer import Writer, arg

# Each army, in the bridge's frame: d out along the road from the bridge's
# middle (negative west, Gondor's side), c along the river; mirrored for
# Mordor. Template, d, c, and what it does: melee crosses, ranged comes up to
# the bank, flank crosses behind the melee, siege comes up to the square.
GONDOR = [('GondorTowerShieldGuardHorde', -170, -40, 'melee'), ('GondorTowerShieldGuardHorde', -170, 40, 'melee'),
          ('GondorFighterHorde', -330, -110, 'melee'), ('GondorFighterHorde', -330, 0, 'melee'),
          ('GondorFighterHorde', -330, 110, 'melee'),
          ('GondorArcherHorde', -520, -280, 'ranged'), ('GondorArcherHorde', -520, -100, 'ranged'),
          ('GondorArcherHorde', -520, 100, 'ranged'), ('GondorArcherHorde', -520, 280, 'ranged'),
          ('GondorKnightHorde', -650, -480, 'flank'), ('GondorKnightHorde', -650, 480, 'flank'),
          ('GondorTrebuchet', -950, -260, 'siege'), ('GondorTrebuchet', -950, 0, 'siege'), ('GondorTrebuchet', -950, 260, 'siege')]
MORDOR = [('MordorFighterHorde', 170, -40, 'melee'), ('MordorFighterHorde', 170, 40, 'melee'),
          ('MordorFighterHorde', 330, -120, 'melee'), ('MordorFighterHorde', 330, 0, 'melee'),
          ('MordorFighterHorde', 330, 120, 'melee'),
          ('MordorArcherHorde', 520, -280, 'ranged'), ('MordorArcherHorde', 520, -100, 'ranged'),
          ('MordorArcherHorde', 520, 100, 'ranged'), ('MordorArcherHorde', 520, 280, 'ranged'),
          ('MordorMountainTroll', 640, -430, 'flank'), ('MordorMountainTroll', 640, 430, 'flank'),
          ('MordorAttackTroll', 600, 0, 'flank'),
          ('MordorCatapult', 950, -260, 'siege'), ('MordorCatapult', 950, 0, 'siege'), ('MordorCatapult', 950, 260, 'siege')]
# Where each kind goes, as d (for Gondor; Mordor's the mirror).
GOAL = dict(melee=480, ranged=-300, flank=480, siege=-650)


def text(kind, value):
    return arg(kind, text=value)


def frame():
    """The bridge's middle, its road direction (towards Mordor) and the river's."""
    import maps.hollin_dales.map as hollin
    (bx, by), (ux, uy) = hollin.bridges()[0]
    return (bx, by), (ux, uy), (-uy, ux)


def at(d, c):
    (bx, by), (ux, uy), (rx, ry) = frame()
    return bx+ux*d+rx*c, by+uy*d+ry*c


def build(b):
    from mapworkshop.config import ROOT
    source = ROOT/'local/build/hollin-dales'/'map mp the hollin dales.map'
    if not source.exists():
        raise RuntimeError('Build the Hollin Dales first: mw build hollin-dales')
    m = Map(source.read_bytes())
    _, (ux, uy), _ = frame()
    east = math.atan2(uy, ux)
    w = Writer(m)
    first = max([v for o in m.objects() for k, _, v in o['properties'] if k == 'waypointID'], default=0)+1
    goals = {}
    for side, sign in (('W', -1), ('E', 1)):
        for kind, d in GOAL.items():
            name = f'BB_{side}_{kind}'
            x, y = at(sign*d if kind in ('ranged', 'siege') else -sign*d, 0)
            add_object(m, '*Waypoints/Waypoint', x, y, layer='Battle', extra=[
                ('originalOwner', 3, '/team'), ('uniqueID', 3, name), ('waypointID', 1, first+len(goals)),
                ('waypointName', 3, name), ('waypointTypeOption', 3, '')])
            goals[(side, kind)] = name
    orders = []
    for army, side, owner, facing in ((GONDOR, 'W', 'Player_1/teamPlayer_1', east),
                                      (MORDOR, 'E', 'PlyrCreeps/teamPlyrCreeps', east+math.pi)):
        for i, (template, d, c, kind) in enumerate(army):
            name = f'BB_{side}{i:02d}'
            add_object(m, template, *at(d, c), angle=facing, layer='Battle',
                       extra=[('originalOwner', 3, owner), ('objectName', 3, name)])
            orders.append(w.operation('action', 'ATTACK_MOVE_NAMED_UNIT_TO', [text(14, name), text(7, goals[(side, kind)])]))
    w.install([w.script('BB_Battle', [[w.operation('condition', 'CONDITION_TRUE')]], orders)], side_index=2)
    ini = (source.parent/'map.ini').read_text(encoding='ascii', errors='replace')
    from PIL import Image
    b.save(m, ini=ini.split('\n', 1)[1] if ini.startswith(';') else ini, minimap=Image.open(source.parent/'preview.png'))
    print(f'{len(GONDOR)} Gondor and {len(MORDOR)} Mordor units at the bridge {frame()[0]}')
