"""Battle of Nanduhirion v2: the Battle of Nanduhirion on Nanduhirion v2.

The same battle as maps/nanduhirion_battle/ (its line-up, bases, armies by
job, outposts, scripts and waves), staged on the latest Nanduhirion v2
build: the original scaled 2.5 times each way to 13,750 x 11,250, with v1's
sixteen sites, starts and half-turn (maps/nanduhirion_v2/map.py). Its armies
and waves are two-thirds of the v1 battle's (STRENGTH), the heroes kept.

    mw build nanduhirion-v2; mw build nanduhirion-v2-battle; mw play nanduhirion-v2-battle
"""
import maps.nanduhirion_v2.map as v2
from maps.nanduhirion_battle.map import Field, stage_battle

V2 = Field(v2, (v2.SCALE, v2.SCALE))
STRENGTH = 2/3


def build(b):
    stage_battle(b, 'nanduhirion-v2', V2, STRENGTH)
