"""Battle of Nanduhirion: Nanduhirion v1 in the thick of a 4 vs 4.

The latest Nanduhirion v1 build (maps/nanduhirion_v1/), seated by map.toml's
[play] line-up: the good factions west (starts 1-4: you with Men, Elves,
Dwarves, Men), the evil ones east (starts 5-8: Mordor, Isengard, the goblins,
Angmar), seven of them hard AI. The game is joined well on:

- Bases: two per player, so sixteen stand for sixteen players: its start,
  where the game puts the faction's fortress, and the other site of its base
  area in v1 (SECOND_SITE), where this map puts one (FORTRESS). Round each,
  its production and economy buildings stand built (BASES).
- Armies: each player's, both bases' together, stands by job (ARENA,
  STRIP, RESERVE): the Elves face the goblins on the north strip, the
  Dwarves Isengard on the south strip, your Men Angmar and the other Men
  Mordor in the arena. In the arena and in each strip's basin lane: a
  battle line (formation()) of battalions with lanes between them, the
  phalanx in front and the melee behind, four heroes (HEROES) behind the
  middle, the archers in a line behind the infantry, the riders and beasts
  in columns in the lanes and on both flanks, the siege at the back. Good
  armies stand in order, evil ones ragged (ORDER). In the arena also
  archers on the forward terrace above the line; on a strip guards at the
  lane's two outposts. At each base: a reserve. At the clash the lines
  advance, the riders charging through the lanes into the enemy's front,
  and the siege moves up to its battery (BATTERY short of the middle, in
  range of the clash); the archers on the heights, the outpost guards and
  the reserves hold. The
  armies are drawn up for players 1 and 2; 4 and 3 stand as their mirrors
  across the map's middle and the east players as the west's half-turn
  twins, so every pairing meets on the same ground.
- Neutral sites: each team holds its four basin outposts, the lane's
  players their own; the signal fires and the inn are still to fight for.
  The creep lairs are cleared.
- Scripts (on PlyrCivilian, the side a skirmish keeps): the map is revealed
  to you, every player gets START_MONEY, after CLASH seconds (a copy may set
  its own: Field's clash) the advancing
  groups attack-move on their opponent's line, and every WAVE seconds from
  FIRST_WAVE each player's reinforcements (WAVES) march from both its bases'
  rally points to the same line. You have no AI: your advancing groups and
  your waves follow the scripts, and the later waves drive them on (PUSH),
  into Angmar's base and then Mordor's, while your guards and reserves stay
  put. The AI players take over their own units, which stand on their
  default teams.

How a skirmish treats such a map (Open-BFME-2, BFME2 1.06's engine, which
ROTWK follows here): an object owned by "Player_N/teamPlayer_N" belongs to
whoever holds start N; the neutral side, PlyrCivilian and PlyrCreeps keep
their scripts; a script names a slot's team in full ("Player_3/teamPlayer_3");
a computer player's AI takes over the units on its default team. The map
also gets ROTWK's SkirmishAngmar side, which v1 (made from blank.create's
BFME2 sides) lacks: an AI takes its faction's AI scripts from that side.

The battle stands on any Nanduhirion copy laid out like v1 (the same
sixteen sites, starts and half-turn): stage_battle() takes the copy's layout
module and its scale over the original Nanduhirion, and the points drawn up
here (ARENA, STRIP) are in the original's map units, 5,500 x 4,500. Its
strength scales every army row and every wave to that share of its units,
the heroes kept; a row grown wider than WIDEST stands as two or more. Every
other row stands STAGGER of a unit's spacing aside, so each rank shows
between the units in front, and each unit stands a little off its place and
its facing (JITTER, the same every build): drawn up, not on a grid.
maps/nanduhirion_v2_battle/ stages it on Nanduhirion v2.

    mw build nanduhirion-v1; mw build nanduhirion-battle; mw play nanduhirion-battle

plan.py draws a build's battle plan: the armies as map symbols by role on
the map's top view, the routes and the timeline (python -m
maps.nanduhirion_battle.plan <project>).
"""
import math
import random

import numpy as np
from PIL import Image

from mapworkshop import project
from mapworkshop.formats import sections
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.script_writer import Writer, arg
import maps.nanduhirion_v1.map as v1

YOU = 1
START_MONEY = 4000
CLASH = 20                      # seconds before the armies advance
FIRST_WAVE, WAVE, WAVE_COUNT = 75, 150, 12
PUSH = {5: 'NB_Push_1', 9: 'NB_Push_2'}   # from this wave on, all your units attack-move here
SCENERY = ('Trees', 'Shrubs', 'Ruins', 'Life')   # v1's layers a base or an army clears
LAIRS = ('CaveTrollLair', 'FireDrakeLair', 'MoriarGoblinLair')

BASES = {
    'Men': ['GondorBarracks', 'GondorArcherRange', 'GondorStable', 'GondorWorkshop', 'GondorForge',
            'GondorFarm', 'GondorFarm', 'GondorFarm'],
    'Elves': ['ElvenBarracks', 'ElvenGreenPasture', 'ElvenEntMoot', 'EregionForge',
              'ElvenMallornTree', 'ElvenMallornTree', 'ElvenMallornTree'],
    'Dwarves': ['DwarfBarracks', 'DwarvenArcheryRange', 'DwarvenHearth',
                'DwarvenMineShaft', 'DwarvenMineShaft', 'DwarvenMineShaft'],
    'Mordor': ['MordorOrcPit', 'MordorHaradrimPalace', 'MordorTrollCage', 'MordorSiegeWorks',
               'MordorSlaughterHouse', 'MordorSlaughterHouse', 'MordorLumberMill'],
    'Isengard': ['IsengardUrukPit', 'IsengardWargPit', 'IsengardSiegeWorks', 'IsengardArmory',
                 'IsengardFurnace', 'IsengardFurnace', 'IsengardLumberMill'],
    'Wild': ['GoblinCave', 'GoblinFissure', 'WildSpiderPit', 'WildTreasureTrove',
             'WildMineShaft', 'WildMineShaft', 'WildMineShaft'],
    'Angmar': ['AngmarBarracks', 'AngmarDen', 'AngmarHallofTwilight', 'AngmarMill', 'AngmarMill', 'AngmarMill'],
}
# Each army in rows, the front row first; the heroes stand behind the second.
ARMY = {
    'Men': [['GondorTowerShieldGuardHorde']*3, ['GondorFighterHorde', 'GondorFighterHorde', 'RohanSpearmenHorde'],
            ['GondorArcherHorde', 'GondorArcherHorde', 'GondorRangerHorde'],
            ['GondorKnightHorde', 'RohanRohirrimHorde', 'RohanRohirrimHorde'], ['GondorTrebuchet']*2],
    'Elves': [['ElvenMithlondSentryHorde']*2 + ['ElvenLorienWarriorHorde'], ['ElvenLorienWarriorHorde']*3,
              ['ElvenLorienArcherHorde']*2 + ['ElvenMirkwoodArcherHorde'],
              ['ElvenRivendellLancerHorde']*2, ['RohanGenericEnt']*2],
    'Dwarves': [['DwarvenPhalanxHorde']*2 + ['DwarvenGuardianHorde'],
                ['DwarvenGuardianHorde', 'DwarvenZerkerHorde', 'DwarvenZerkerHorde'],
                ['DwarvenAxeThrowerHorde']*2 + ['DwarvenMenOfDaleHorde'],
                ['DwarvenMenOfDaleHorde', 'DwarvenBattleWagon', 'DwarvenCatapult']],
    'Mordor': [['MordorFighterHorde']*3, ['MordorBlackOrcHorde']*2 + ['MordorEasterlingHorde'],
               ['MordorArcherHorde']*2 + ['MordorHaradrimArcherHorde'],
               ['MordorMountainTroll']*2 + ['MordorHaradrimRiderHorde'],
               ['MordorCatapult', 'MordorMumakil', 'MordorCatapult']],
    'Isengard': [['IsengardPikemanHorde']*2 + ['IsengardFighterHorde'], ['IsengardFighterHorde']*2 + ['IsengardBeserker'],
                 ['IsengardUrukCrossbowHorde']*3, ['IsengardWargRiderHorde']*2 + ['IsengardBallista']],
    'Wild': [['GoblinFighterHorde']*3, ['WildMarauderHorde']*2 + ['GoblinFighterHorde'], ['GoblinArcherHorde']*3,
             ['GoblinSpiderRiderHorde']*2 + ['WildMountainGiant']],
    'Angmar': [['AngmarOrcWarriors_Placed']*3, ['AngmarHillTrollHorde']*2 + ['AngmarDarkDunedainHorde'],
               ['AngmarDarkRangerHorde']*2 + ['AngmarNecromancerHorde'],
               ['AngmarDireWolfHorde']*2 + ['AngmarSnowTrollHorde', 'AngmarThrallMaster']],
}
HEROES = {1: ['GondorAragornMP', 'GondorGandalf', 'GondorFaramir', 'RohanEomer'],
          2: ['ElvenLegolas', 'ElvenGlorfindel', 'ElvenHaldir', 'ElvenArwen'],
          3: ['DwarvenGimli', 'DwarvenDain', 'DwarvenGloin', 'DwarvenCaptainofDale'],
          4: ['GondorBoromir', 'RohanTheoden', 'RohanEowyn', 'GondorFaramir'],
          5: ['MordorGothmog', 'MordorMouthOfSauron', 'KhamulFellBeast', 'MorgomirFellBeast'],
          6: ['IsengardLurtz', 'IsengardSharku', 'IsengardWormTongue', 'IsengardSaruman'],
          7: ['WildGoblinKing', 'WildAzog', 'WildShelob', 'Drogoth'],
          8: ['AngmarRogash', 'AngmarHwaldar', 'AngmarKarsh', 'AngmarMorgramir']}
FORTRESS = dict(Men='MenFortress', Elves='ElvenFortress', Dwarves='DwarvenFortress', Isengard='IsengardFortress',
                Mordor='MordorFortress', Wild='WildFortress', Angmar='AngmarFortress')   # playertemplate.ini's StartingBuilding
# Each player's second base: the other site of its base area (v1's SITES), so
# sixteen bases stand for sixteen players.
SECOND_SITE = {1: 2, 2: 3, 3: 5, 4: 7, 5: 10, 6: 11, 7: 13, 8: 15}
# Each wave brings three units, the two lists in turn.
WAVES = {
    'Men': [['GondorFighterHorde', 'GondorArcherHorde', 'GondorKnightHorde'],
            ['GondorTowerShieldGuardHorde', 'GondorRangerHorde', 'RohanRohirrimHorde']],
    'Elves': [['ElvenLorienWarriorHorde', 'ElvenLorienArcherHorde', 'ElvenRivendellLancerHorde'],
              ['ElvenMithlondSentryHorde', 'ElvenMirkwoodArcherHorde', 'RohanGenericEnt']],
    'Dwarves': [['DwarvenGuardianHorde', 'DwarvenAxeThrowerHorde', 'DwarvenPhalanxHorde'],
                ['DwarvenZerkerHorde', 'DwarvenMenOfDaleHorde', 'DwarvenBattleWagon']],
    'Mordor': [['MordorFighterHorde', 'MordorArcherHorde', 'MordorBlackOrcHorde'],
               ['MordorEasterlingHorde', 'MordorHaradrimRiderHorde', 'MordorMountainTroll']],
    'Isengard': [['IsengardFighterHorde', 'IsengardUrukCrossbowHorde', 'IsengardPikemanHorde'],
                 ['IsengardFighterHorde', 'IsengardWargRiderHorde', 'IsengardBeserker']],
    'Wild': [['GoblinFighterHorde', 'GoblinArcherHorde', 'WildMarauderHorde'],
             ['GoblinFighterHorde', 'GoblinSpiderRiderHorde', 'WildMountainGiant']],
    'Angmar': [['AngmarOrcWarriors_Placed', 'AngmarDarkDunedainHorde', 'AngmarHillTrollHorde'],
               ['AngmarOrcWarriors_Placed', 'AngmarDarkRangerHorde', 'AngmarDireWolfHorde']],
}
# Where each army stands, by job, drawn up for player 1 (the arena's north
# half) and player 2 (the north strip), in the original Nanduhirion's map
# units: per group its job, where the middle of its front row stands, its
# rows (an ARMY row and how many times over, or the heroes) and when it
# advances: True at the clash, a number that many seconds into the game (0:
# at once), False never, holding its ground. Every group faces its
# opponent's line and stands on its own spot's level. Players 4 and 3 stand
# as the mirrors of 1 and 2 across the map's middle, the east players as the
# half-turn twins of the west, facing them: 1 and 8, 4 and 5 in the arena, 2
# and 7 on the north strip, 3 and 6 on the south one.
# A battle line's spec is a formation (formation()): per part the ARMY row
# and how many times over; the line's riders, beasts and siege come from rows
# 3 and 4, sorted by what they are (SIEGE).
LINE = dict(front=(0, 3), melee=(1, 2), archers=(2, 2), charge=(3, 2), siege=(4, 2))
ARENA = [('line', (2451, 2384), dict(LINE, width=900), True),   # two armies abreast in the arena: each this wide at most
         ('overwatch', (2065, 2400), [(2, 1)], False)]   # archers on the forward terrace above the arena
STRIP = [('line', (2277, 3600), dict(LINE, siege=(4, 1), width=1500), True),
         ('inner outpost', (2181, 3174), [(0, 1), (2, 1)], False),
         ('corner outpost', (1988, 3932), [(1, 1), (2, 1)], False)]
RESERVE = [(0, 1), (1, 1), (2, 1)]   # at each base's rally point, holding
THEATRE = {1: ARENA, 4: ARENA, 2: STRIP, 3: STRIP}
THEATRE_NAME = {1: 'arena', 4: 'arena', 2: 'strip', 3: 'strip'}   # Field anchors name a theatre's groups by these
MIRRORED = (3, 4)
OPPONENT = {1: 8, 8: 1, 4: 5, 5: 4, 2: 7, 7: 2, 3: 6, 6: 3}
ACROSS, BACK = 190, 175         # spacing of an army's units along a row, and between rows
WIDEST = 9                      # units in a row at most: a wider one splits into rows behind each other
STAGGER = .5                    # every other row stands this share of ACROSS aside: each rank shows between the units in front
JITTER = 22, 16, 6              # each unit off its place by up to this along the row, back and in facing (degrees), by its name
# A battle line (formation()): battalions FILE abreast, their phalanx in front and their melee in ranks behind, with LANEs between
# them through which the riders and beasts, waiting in columns there and on both flanks, charge into the enemy's front; the heroes
# behind the middle, the archers in a line behind the infantry (open where the lanes run), the siege at the back.
GOOD = ('Men', 'Elves', 'Dwarves')
SIEGE = ('Trebuchet', 'Catapult', 'Ballista')   # in a template's name: a siege engine (it fires from the back, not in the lanes)
FILE, FILE_GAP, RANK_GAP = 3, 150, 150          # a battalion's front, the spacing along it and between its ranks
LANE, COLUMN_GAP = 320, 170                     # a lane's width, and the spacing of the riders down it
HEROES_BACK, ARCHERS_BACK, SIEGE_BACK = 2.4, 3.6, 5.8   # in RANK_GAPs behind the front
BATTERY = 420                   # at the clash the siege moves up to this short of the middle between the lines (their range: 300 to 500)
# Good armies stand in order, evil ones in a horde: each unit off its place by up to (along, back, facing in degrees), a battalion's
# own step forward or back, and how much the spacing varies
ORDER = {True: dict(jitter=(4, 4, 1.5), step=0, spread=0),
         False: dict(jitter=(45, 35, 14), step=80, spread=.18)}
RALLY = 650                     # the rally point (waves spawn there): this far from the start towards the line
LEVEL = 50                      # an army stands on its line's level, within this: not up a terrace behind it


class Field:
    """The Nanduhirion copy the battle stands on: its layout module (SITES,
    STARTS, CENTRE, twin and BORDER, as maps/nanduhirion_v1/map.py has them)
    and its scale over the original Nanduhirion, east and north. `anchors`
    places groups where this copy's ground wants them instead: per
    (theatre, job) the point for player 1 or 2 in this copy's map units
    (THEATRE_NAME; the other players mirror and turn it as at() does).
    `theatres` replaces a theatre's groups altogether: per theatre name its
    groups as THEATRE has them, their points in this copy's map units.
    `reserve` is when the bases' reserves (RESERVE) advance, as a group's
    advances (False: they hold; None: there are none). `clash` is the
    seconds into the game a group that advances at the clash (True) goes."""
    def __init__(self, layout, scale, anchors=None, theatres=None, reserve=False, clash=CLASH):
        self.layout, self.scale, self.anchors, self.theatres = layout, scale, anchors or {}, theatres or {}
        self.reserve, self.clash = reserve, clash

    def start(self, n):
        return self.layout.SITES[self.layout.STARTS[n - 1] - 1]

    def bases(self, n):
        """Player n's two bases: its start, where the game puts its fortress,
        and its second site, where this map does."""
        return [self.start(n), self.layout.SITES[SECOND_SITE[n] - 1]]

    def at(self, n, p, anchor=None):
        """Where a point drawn up for player 1 or 2, in the original's map
        units (or `anchor`, in this copy's), is for player n on this copy."""
        west = n if n <= 4 else n - 4
        x, y = anchor if anchor else (p[0]*self.scale[0], p[1]*self.scale[1])
        if west in MIRRORED:
            y = 2*self.layout.CENTRE[1] - y
        return (x, y) if n <= 4 else self.layout.twin((x, y))

    def groups(self, n):
        """Player n's army groups: (job, front middle, rows spec, advances)."""
        west = n if n <= 4 else n - 4
        if THEATRE_NAME[west] in self.theatres:
            return [(job, self.at(n, None, p), rows, advances) for job, p, rows, advances in self.theatres[THEATRE_NAME[west]]]
        return [(job, self.at(n, p, self.anchors.get((THEATRE_NAME[west], job))), rows, advances)
                for job, p, rows, advances in THEATRE[west]]

    def line(self, n):
        return next(p for job, p, _, _ in self.groups(n) if job == 'line')

    def lane(self, x, y):
        """The player whose basin lane holds x, y."""
        cx, cy = self.layout.CENTRE
        return (2 if y > cy else 3) if x < cx else (7 if y > cy else 6)


# Nanduhirion v1: the original stretched to 14,250 x 14,250.
V1 = Field(v1, (14250/5500, 14250/4500))


class Ground:
    """The terrain's heights and passability, for finding level, open spots."""
    def __init__(self, m, border):
        self.border = border
        hm = m.heightmap()
        self.z = hm['elevations']*.0390625
        self.blocked = m.blend(inspection=True)['arrays']['impassable'].astype(bool)
        self.taken = []                                   # (x, y, radius) of what this build placed

    def height(self, x, y):
        return float(self.z[int(y//10) + self.border, int(x//10) + self.border])

    def fits(self, x, y, radius, relief, level=None):
        """Open, walkable ground within `relief` of level over `radius`, clear
        of what was taken, and at `level` (within LEVEL) when given."""
        i, j, r = int(y//10) + self.border, int(x//10) + self.border, max(1, int(radius//10))
        box = (slice(i - r, i + r + 1), slice(j - r, j + r + 1))
        return (0 <= i - r and i + r < self.z.shape[0] and 0 <= j - r and j + r < self.z.shape[1]
                and not self.blocked[box].any() and np.ptp(self.z[box]) <= relief
                and (level is None or abs(self.z[i, j] - level) <= LEVEL)
                and all(math.dist((x, y), (tx, ty)) >= radius + tr for tx, ty, tr in self.taken))

    def spot(self, x, y, radius, relief, reach=400, level=None):
        """The nearest spot to x, y that fits, searched outwards; taken."""
        for r in range(0, reach + 1, 20):
            for k in range(max(1, int(2*math.pi*r/20))):
                a = 2*math.pi*k/max(1, int(2*math.pi*r/20))
                p = (x + r*math.cos(a), y + r*math.sin(a))
                if self.fits(*p, radius, relief, level):
                    self.taken.append((*p, radius))
                    return p
        raise ValueError(f'No room for a radius {radius} object near ({x:.0f}, {y:.0f})')


def scaled(units, strength, turn=0):
    """`strength` times units (at least one), taken round them from `turn`
    places in, so scaled waves leave out or add a different unit in turn."""
    keep = max(1, round(len(units)*strength))
    return units if keep == len(units) else [units[(turn + i) % len(units)] for i in range(keep)]


def split(row):
    """A row as rows of at most WIDEST units, as even as they come."""
    n = -(-len(row)//WIDEST)
    return [row[len(row)*k//n:len(row)*(k + 1)//n] for k in range(n)]


def formation(faction, spec, strength, heroes, rnd):
    """A battle line's units as (template, forward, across, role) from the
    middle of its front, forward towards the enemy (see LANE): `spec` names
    per part (front, melee, archers, charge, siege) an ARMY row and how many
    times over, each scaled to `strength`, and its `width` at most (as many
    battalions as fit, deeper the more they hold); the role is line,
    archers or siege; the riders, beasts and siege of
    the charge and siege rows are sorted by what they are (SIEGE). A good
    faction (GOOD) stands in order, an evil one ragged (ORDER)."""
    order = ORDER[faction in GOOD]
    rows = ARMY[faction]
    take = lambda part: (scaled(rows[spec[part][0]]*spec[part][1], strength)
                         if part in spec and spec[part][0] < len(rows) else [])
    front, melee, archers = take('front'), take('melee'), take('archers')
    pool = take('charge') + take('siege')
    siege = [t for t in pool if any(w in t for w in SIEGE)]
    charge = [t for t in pool if not any(w in t for w in SIEGE)]
    spread = lambda: 1 + rnd.uniform(-order['spread'], order['spread'])
    width = (FILE - 1)*FILE_GAP
    # battalions: as many as the line's width takes (at least two, a lane between them), deeper the more they hold
    count = max(2, min(-(-len(front)//FILE), int((spec.get('width', 10**6) + LANE)//(width + LANE))))
    fronts = [front[len(front)*k//count:len(front)*(k + 1)//count] for k in range(count)]
    melees = [melee[len(melee)*k//count:len(melee)*(k + 1)//count] for k in range(count)]
    total = count*width + (count - 1)*LANE
    middles = [-total/2 + width/2 + k*(width + LANE) for k in range(count)]
    out = []
    for k in range(count):
        step = rnd.uniform(-order['step'], order['step'])
        ranks = [part[i:i + FILE] for part in (fronts[k], melees[k]) for i in range(0, len(part), FILE)]   # the phalanx's ranks first
        for r, rank in enumerate(ranks):
            for i, t in enumerate(rank):
                out.append((t, step - r*RANK_GAP*spread(), middles[k] + (i - (len(rank) - 1)/2)*FILE_GAP*spread(), 'line'))
    deepest = max(-(-len(fronts[k])//FILE) - (-len(melees[k])//FILE) for k in range(count))   # a battalion's ranks
    for i, t in enumerate(heroes):
        out.append((t, -max(HEROES_BACK, deepest + .4)*RANK_GAP, (i - (len(heroes) - 1)/2)*110*spread(), 'line'))
    # the lanes between the battalions and on both flanks: the riders' and beasts' columns
    lanes = [m + width/2 + LANE/2 for m in middles[:-1]] + [-total/2 - LANE/2, total/2 + LANE/2]
    for i, t in enumerate(charge):
        out.append((t, -.6*RANK_GAP - (i//len(lanes))*COLUMN_GAP*spread(), lanes[i % len(lanes)], 'line'))
    # the archers in a line behind the infantry, open where the lanes run; a second line behind if they are more
    slots = [x for x in (-total/2 + j*FILE_GAP for j in range(int(total//FILE_GAP) + 1))
             if all(abs(x - lane) > LANE*.4 for lane in lanes)]
    for i, t in enumerate(archers):
        r = i//len(slots)
        out.append((t, -(max(ARCHERS_BACK, deepest + 1.6) + r*.9)*RANK_GAP, slots[i % len(slots)] + (FILE_GAP/2 if r % 2 else 0), 'archers'))
    for i, t in enumerate(siege):
        out.append((t, -max(SIEGE_BACK, deepest + 3.8)*RANK_GAP*spread(), (i - (len(siege) - 1)/2)*total*.8/max(1, len(siege) - 1), 'siege'))
    return out


def owner(n):
    return ('originalOwner', 3, f'Player_{n}/teamPlayer_{n}')


def check_templates(assets, names):
    """Every template the scenario places exists in the selected game."""
    missing = sorted({t for t in names if t.lower() not in assets.templates})
    if missing:
        raise ValueError(f'Templates the game lacks: {", ".join(missing)}')


def add_angmar_side(m):
    """ROTWK's SkirmishAngmar side, with its team, script list and library list."""
    sides = sections.read(m, 'SidesList')
    sides['players'].append(dict(build_list=[], properties=[
        ('playerName', 3, 'SkirmishAngmar'), ('playerIsHuman', 0, 0), ('playerDisplayName', 4, 'SkirmishAngmar'),
        ('playerFaction', 3, 'FactionAngmar'), ('playerAllies', 3, ''), ('playerEnemies', 3, '')]))
    sections.write(m, 'SidesList', sides)
    sections.write(m, 'Teams', sections.read(m, 'Teams') + [[('teamName', 3, 'teamSkirmishAngmar'),
                                                            ('teamOwner', 3, 'SkirmishAngmar'), ('teamIsSingleton', 0, 1)]])
    sections.write(m, 'PlayerScriptsList', sections.read(m, 'PlayerScriptsList')
                   + [dict(chunk='ScriptList', version=1, children=[])])
    sections.write(m, 'LibraryMapLists', sections.read(m, 'LibraryMapLists')
                   + [dict(chunk='LibraryMaps', version=1, maps=[])])


def stage(m, factions, ground, field, strength=1):
    """Clear the lairs, give the basin outposts to their lanes' players, and
    lay out bases, armies (each row scaled to `strength`) and waypoints on
    `field`. Returns the armies' units
    by player (name, template, role, advances, job), the waypoints by name and
    what was placed."""
    objs = []
    for o in m.objects():
        if o['template'] in LAIRS:
            continue
        objs.append(o)
    # The basin outposts and their flags: each to its lane's player.
    for o in objs:
        if o['template'] in ('Outpost', 'CaptureFlag'):
            near = min((p for p in objs if p['template'] == 'Outpost'), key=lambda p: math.dist((p['x'], p['y']), (o['x'], o['y'])))
            if o['template'] == 'Outpost' or math.dist((near['x'], near['y']), (o['x'], o['y'])) < 200:
                n = field.lane(near['x'], near['y'])
                o['properties'] = [p for p in o['properties'] if p[0] != 'originalOwner'] + [owner(n)]
    # Everything already standing keeps its room (outposts, inns, columns...).
    for o in objs:
        layer = next((v for k, _, v in o['properties'] if k == 'objectLayer'), '')
        if layer not in SCENERY and not o['template'].startswith(('*', 'Amb', 'FarmTemplate')):
            ground.taken.append((o['x'], o['y'], 80))
    placed, armies, waypoints = [], {}, {}

    def put(template, x, y, angle, n, name, layer):
        placed.append((template, x, y, angle, [owner(n), ('uniqueID', 3, name), ('objectName', 3, name)], layer))

    for n in range(1, 9):                                  # the fortresses' ground first
        for x, y in field.bases(n):
            ground.taken.append((x, y, 330))
    for n in range(1, 9):
        faction = factions[n - 1]
        lx, ly = field.line(n)
        ox, oy = field.line(OPPONENT[n])
        for b, (sx, sy) in enumerate(field.bases(n)):
            tag = '' if b == 0 else 'b'
            if b:                                          # the game builds the start's fortress; this map the second
                put(FORTRESS[faction], sx, sy, math.atan2(ly - sy, lx - sx), n, f'NB_B{n}b_F', 'Bases')
            # The rally point, towards the line.
            d = math.dist((sx, sy), (lx, ly))
            waypoints[f'NB_Rally_{n}{tag}'] = ground.spot(sx + (lx - sx)*RALLY/d, sy + (ly - sy)*RALLY/d, 60, 40)
            # The buildings, on rings round the fortress, nearest first, spread round it.
            rings = [(r, a) for r in range(450, 1100, 75) for a in range(0, 360, 15)]
            for k, template in enumerate(BASES[faction]):
                for r, a in sorted(rings, key=lambda ra: (ra[0], (ra[1] - 137*k) % 360)):
                    p = (sx + r*math.cos(math.radians(a)), sy + r*math.sin(math.radians(a)))
                    if ground.fits(*p, 120, 25):
                        ground.taken.append((*p, 120))
                        put(template, *p, math.atan2(ly - p[1], lx - p[0]), n, f'NB_B{n}{tag}_{k:02d}', 'Bases')
                        break
                else:
                    raise ValueError(f'No room for {template} in player {n}\'s base {b + 1}')
        # The army, by group (groups(), RESERVE at each base's rally point):
        # rows back from the group's front, facing the opponent's line, on
        # the group's own level.
        army = field.groups(n) + [('reserve', waypoints[f'NB_Rally_{n}{tag}'], RESERVE, field.reserve) for tag in ('', 'b')
                                  if field.reserve is not None]
        armies[n] = []
        for job, (gx, gy), spec, advances in army:
            d = math.dist((gx, gy), (ox, oy))
            fx, fy = (ox - gx)/d, (oy - gy)/d
            level = ground.height(gx, gy)
            if isinstance(spec, dict):                     # a battle line: its formation (the heroes with the line)
                spots = formation(faction, spec, strength, HEROES[n] if job == 'line' else [], random.Random(f'NB_P{n}_{job}'))
                jitter = ORDER[faction in GOOD]['jitter']
            else:                                          # rows, the front row first, every other one staggered
                rows = [r for s in spec if s[0] < len(ARMY[faction]) for r in split(scaled(ARMY[faction][s[0]]*s[1], strength))]
                spots = [(t, -r*BACK, (c - (len(row) - 1)/2 + (STAGGER if r % 2 else 0))*ACROSS, job)
                         for r, row in enumerate(rows) for c, t in enumerate(row)]
                jitter = JITTER
            for template, forward, across, role in spots:
                name = f'NB_P{n}_A{len(armies[n]):02d}'
                rnd = random.Random(name)                  # the same small offsets every build
                forward += rnd.uniform(-1, 1)*jitter[1]
                across += rnd.uniform(-1, 1)*jitter[0]
                x, y = gx + fx*forward - fy*across, gy + fy*forward + fx*across
                # the archers and the siege may stand on higher ground behind the line (a terrace above an arena); the rest on its level
                x, y = ground.spot(x, y, 70, 60, reach=1200, level=None if role in ('archers', 'siege') else level)
                put(template, x, y, math.atan2(fy, fx) + math.radians(rnd.uniform(-1, 1)*jitter[2]), n, name, 'Armies')
                armies[n].append((name, template, role, field.clash if advances is True else advances, job))
        waypoints[f'NB_Line_{n}'] = (lx, ly)
        # the siege's firing position: BATTERY short of the middle between the two lines (in range of the clash, behind it;
        # behind its own line when the lines stand closer)
        d = math.dist((lx, ly), (ox, oy))
        waypoints[f'NB_Battery_{n}'] = (lx + (ox - lx)*(d/2 - BATTERY)/d, ly + (oy - ly)*(d/2 - BATTERY)/d)
    waypoints['NB_Push_1'] = field.start(8)
    waypoints['NB_Push_2'] = field.start(5)
    # Clear the scenery under what was placed.
    keep = []
    for o in objs:
        layer = next((v for k, _, v in o['properties'] if k == 'objectLayer'), '')
        if layer in SCENERY and any(math.dist((o['x'], o['y']), (x, y)) < (140 if l == 'Bases' else 80)
                                    for _, x, y, _, _, l in placed):
            continue
        keep.append(o)
    m.set_objects(keep)
    for template, x, y, angle, extra, layer in placed:
        add_object(m, template, x, y, angle, layer=layer, extra=extra)
    first = max([v for o in keep for k, _, v in o['properties'] if k == 'waypointID'], default=0) + 1
    for i, (name, (x, y)) in enumerate(waypoints.items()):
        add_object(m, '*Waypoints/Waypoint', x, y, layer='Battle', extra=[
            ('originalOwner', 3, '/team'), ('uniqueID', 3, name), ('waypointID', 1, first + i),
            ('waypointName', 3, name), ('waypointTypeOption', 3, '')])
    return armies, waypoints, placed


def scripts(m, factions, armies, strength=1):
    """The scenario's scripts, on PlyrCivilian (see the module docstring),
    each wave scaled to `strength`."""
    w = Writer(m)
    text = lambda kind, value: arg(kind, text=value)
    team = lambda n: text(3, f'Player_{n}/teamPlayer_{n}')
    move = lambda unit, waypoint: w.operation('action', 'ATTACK_MOVE_NAMED_UNIT_TO', [text(14, unit), text(7, waypoint)])
    timer = lambda name, seconds: w.operation('action', 'SET_MILLISECOND_TIMER', [text(4, name), arg(1, real=float(seconds))])
    expired = lambda name: [[w.operation('condition', 'TIMER_EXPIRED', [text(4, name)])]]
    setup = [w.operation('action', 'MAP_REVEAL_ALL_PERM', [text(11, f'Player_{YOU}')])]
    setup += [w.operation('action', 'PLAYER_GIVE_MONEY', [text(11, f'Player_{n}'), arg(0, integer=START_MONEY)])
              for n in range(1, 9)]
    # the advancing groups, by when they go (THEATRE): the siege to its battery, the rest on the opponent's line
    moves = {}
    for n in range(1, 9):
        for name, _, role, advances, _ in armies[n]:
            if advances is not False:
                moves.setdefault(advances, []).append(
                    move(name, f'NB_Battery_{n}' if role == 'siege' else f'NB_Line_{OPPONENT[n]}'))
    timers = {t: 'NB_Clash' if t == CLASH else f'NB_Advance_{t:g}' for t in moves}
    setup += [timer(timers[t], t) for t in sorted(moves)] + [timer(f'NB_Wave{k:02d}', FIRST_WAVE + (k - 1)*WAVE)
                                                             for k in range(1, WAVE_COUNT + 1)]
    out = [w.script('NB_Setup', [[w.operation('condition', 'CONDITION_TRUE')]], setup)]
    out += [w.script(timers[t], expired(timers[t]), moves[t]) for t in sorted(moves)]
    yours = [name for name, _, _, advances, _ in armies[YOU] if advances is not False]    # the guards and reserves stay put
    target = f'NB_Line_{OPPONENT[YOU]}'
    for k in range(1, WAVE_COUNT + 1):
        target = PUSH.get(k, target)
        actions, new = [], set()
        for n in range(1, 9):
            goal = target if n == YOU else f'NB_Line_{OPPONENT[n]}'
            for tag in ('', 'b'):                          # a wave from each of the player's bases
                for i, template in enumerate(scaled(WAVES[factions[n - 1]][k % 2], strength, k//2)):
                    name = f'NB_P{n}{tag}_W{k:02d}_{i}'
                    actions.append(w.operation('action', 'CREATE_NAMED_ON_TEAM_AT_WAYPOINT',
                                               [text(14, name), text(15, template), team(n), text(7, f'NB_Rally_{n}{tag}')]))
                    actions.append(move(name, goal))
                    new.add(name)
                    if n == YOU:
                        yours.append(name)
        actions += [move(name, target) for name in yours if name not in new]
        out.append(w.script(f'NB_Wave{k:02d}', expired(f'NB_Wave{k:02d}'), actions))
    side = [p['properties'] for p in sections.read(m, 'SidesList')['players']].index(
        next(p['properties'] for p in sections.read(m, 'SidesList')['players']
             if dict((k, v) for k, _, v in p['properties']).get('playerName') == 'PlyrCivilian'))
    w.install(out, side_index=side)
    return len(out), sum(len(s) for s in [setup])


def build(b):
    stage_battle(b, 'nanduhirion-v1', V1)


def stage_battle(b, source, field, strength=1):
    """The battle on the latest build of the project `source`, a Nanduhirion
    copy laid out as `field` describes it, seated by b.project's line-up,
    its armies and waves at `strength` (1: in full)."""
    base = project.find(source)
    if not base.map_file.exists():
        raise RuntimeError(f'Build {base.title} first: mw build {base.id}')
    factions = [slot['faction'] for slot in b.project.config['play']['slots']]
    names = [t for f in factions for t in BASES[f] + [u for row in ARMY[f] for u in row] + [u for w in WAVES[f] for u in w]]
    check_templates(b.assets, names + [FORTRESS[f] for f in factions] + [h for hs in HEROES.values() for h in hs])
    m = Map(base.map_file.read_bytes())
    add_angmar_side(m)
    ground = Ground(m, field.layout.BORDER)
    armies, waypoints, placed = stage(m, factions, ground, field, strength)
    count, _ = scripts(m, factions, armies, strength)
    b.report.update(players={n: dict(faction=factions[n - 1], start=field.start(n), line=field.line(n), opponent=OPPONENT[n],
                                     army=len(armies[n]), groups={job: sum(1 for u in armies[n] if u[2] == job)
                                                                   for job in dict.fromkeys(u[2] for u in armies[n])},
                                     buildings=sum(1 for p in placed if p[5] == 'Bases' and
                                                                        p[4][0][2].startswith(f'Player_{n}/')))
                             for n in range(1, 9)},
                    units={name: dict(job=job, advances=advances)
                           for n in range(1, 9) for name, _, _, advances, job in armies[n]},
                    waypoints={k: [round(v) for v in p] for k, p in waypoints.items()}, scripts=count,
                    waves=dict(first=FIRST_WAVE, every=WAVE, count=WAVE_COUNT))
    ini = (base.build_dir/'map.ini').read_text(encoding='ascii', errors='replace')
    b.save(m, ini=ini.split('\n', 1)[1] if ini.startswith(';') else ini, minimap=Image.open(base.build_dir/'preview.png'))
