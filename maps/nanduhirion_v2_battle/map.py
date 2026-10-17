"""Battle of Nanduhirion v2: the Battle of Nanduhirion on Nanduhirion v2.

The same battle as maps/nanduhirion_battle/ (its line-up, bases, armies by
job, outposts, scripts and waves), staged on the latest Nanduhirion v2
build: the original scaled 2.5 times each way to 13,750 x 11,250, with v1's
sixteen sites, starts and half-turn (maps/nanduhirion_v2/map.py). Its armies
and waves are STRENGTH of the v1 battle's, the heroes kept, so that every
unit placed together costs about 25,000 command points.

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
them.

    mw build nanduhirion-v2; mw build nanduhirion-v2-battle; mw play nanduhirion-v2-battle
"""
import maps.nanduhirion_v2.map as v2
from maps.nanduhirion_battle.map import LINE, Field, stage_battle

CHARGE = 39                     # seconds into the game every line charges, the arena's and the strips' together (the film slides along them first)
ARENA = [('line', (6640, 6450), dict(LINE, width=1540), CHARGE)]   # the bowl's north half: three battalions abreast, 500 from Angmar's
# The north-west lowland, at the foot of the plateau's west ramps: one line holding what v1's strip line and its two outpost guards hold (STRIP:
# their front row, melee row and two archer rows added), so the whole army advances; 2,800 wide along the lowland (to y 10,800), so it
# stands five battalions abreast and three ranks deep
STRIP = [('line', (5800, 9400), dict(front=(0, 4), melee=(1, 3), archers=(2, 4), charge=(3, 2), siege=(4, 1), width=2800), CHARGE)]
V2 = Field(v2, (v2.SCALE, v2.SCALE), theatres=dict(arena=ARENA, strip=STRIP), reserve=None, clash=CHARGE)
STRENGTH = 1.5


def build(b):
    stage_battle(b, 'nanduhirion-v2', V2, STRENGTH)
