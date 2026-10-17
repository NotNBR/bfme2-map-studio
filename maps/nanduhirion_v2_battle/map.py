"""Battle of Nanduhirion v2: the Battle of Nanduhirion on Nanduhirion v2.

The same battle as maps/nanduhirion_battle/ (its line-up, bases, armies by
job, outposts, scripts and waves), staged on the latest Nanduhirion v2
build: the original scaled 2.5 times each way to 13,750 x 11,250, with v1's
sixteen sites, starts and half-turn (maps/nanduhirion_v2/map.py). Its armies
and waves are STRENGTH of the v1 battle's, the heroes kept, so that every
unit placed together costs about 30,000 command points (about 25,900 at the
first STRENGTH, 1.5).

Its ground differs from v1's, so the armies stand where v2's terrain wants
them, not at v1's points scaled. Every army stands at the front, in one
battle line (formation(): the phalanx in front, the melee behind, the riders
in the lanes between the battalions, the heroes, the archers, the siege at
the back); the bases keep no reserves. In the arena (ARENA) the four lines
fill the bowl (height 0), each pair facing across a few hundred units of
no-man's land; on a strip (STRIP) each army stands in its lowland basin at
the foot of the north (or south) plateau's ramps, its outposts' guards in
its line, meeting on the plateau. Every line charges at once, at CHARGE, and
nothing holds back. Points for players 1 and 2; the others mirror and turn
them. Every unit has LIFE times its health (tougher.py), so the fight lasts.
The film (maps/nanduhirion_v2_battle_film/) stages the same battle with a
later charge (staged()).

    mw build nanduhirion-v2; mw build nanduhirion-v2-battle; mw play nanduhirion-v2-battle
"""
import maps.nanduhirion_v2.map as v2
from maps.nanduhirion_battle.map import ARMY, HEROES, LINE, WAVES, Field, battle_map
from maps.nanduhirion_v2_battle import tougher

CHARGE = 6                      # seconds into the game every line charges, the arena's and the strips' together (the film stages its own)
# The bowl's north half, 500 from Angmar's: four battalions of three abreast with narrow lanes, its riders' flank columns included as
# wide as the half takes (the south pair's line meets it by the inn), so the line stands wide and shallow
ARENA_LINE = (6640, 6450), dict(LINE, width=1700, lane=160)
# The north-west lowland, at the foot of the plateau's west ramps: one line holding what v1's strip line and its two outpost guards hold (STRIP:
# their front row, melee row and two archer rows added), so the whole army advances; 2,800 wide along the lowland (to y 10,800), so it
# stands six battalions abreast with narrow lanes, wide and shallow
STRIP_LINE = (5800, 9400), dict(front=(0, 4), melee=(1, 3), archers=(2, 4), charge=(3, 2), siege=(4, 1), width=2900, lane=200)
STRENGTH = 1.77                 # about 30,000 command points (18 October 2026)
LIFE = 5                        # its units have this many times their health, so the fight lasts (tougher.py)


def field(charge):
    """The battle's Field, every line charging `charge` seconds into the game."""
    theatres = dict(arena=[('line', *ARENA_LINE, charge)], strip=[('line', *STRIP_LINE, charge)])
    return Field(v2, (v2.SCALE, v2.SCALE), theatres=theatres, reserve=None, clash=charge)


V2 = field(CHARGE)


def staged(b, charge=CHARGE):
    """The battle, its lines charging at `charge`, unsaved (battle_map()): (map, map.ini, minimap). Its map.ini gives every unit it places
    (its armies, heroes and waves, and the soldiers in its hordes) LIFE times its health (tougher.py)."""
    m, ini, minimap = battle_map(b, 'nanduhirion-v2', field(charge), STRENGTH)
    factions = {slot['faction'] for slot in b.project.config['play']['slots']}
    names = [t for f in factions for row in ARMY[f] + WAVES[f] for t in row] + [h for hs in HEROES.values() for h in hs]
    units, overrides = tougher.map_ini(b.assets, names, LIFE)
    b.report.update(charge=charge, life=LIFE, units_tougher=units)
    return m, ini.rstrip() + '\n\n' + overrides, minimap


def build(b):
    m, ini, minimap = staged(b)
    b.save(m, ini=ini, minimap=minimap)
