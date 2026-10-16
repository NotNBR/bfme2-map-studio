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
  Mordor in the arena. In the arena: a battle line with four heroes
  (HEROES), cavalry and beasts in the arena's mouth on the enemy's flank,
  siege behind the line, archers on the forward terrace above it. On a
  strip: a battle line in its basin lane, a vanguard at the strip's foot by
  its signal fire, guards at the lane's two outposts. At each base: a
  reserve. The lines, flanks, siege and vanguards advance at the clash; the
  archers on the heights, the outpost guards and the reserves hold. The
  armies are drawn up for players 1 and 2; 4 and 3 stand as their mirrors
  across the map's middle and the east players as the west's half-turn
  twins, so every pairing meets on the same ground.
- Neutral sites: each team holds its four basin outposts, the lane's
  players their own; the signal fires and the inn are still to fight for.
  The creep lairs are cleared.
- Scripts (on PlyrCivilian, the side a skirmish keeps): the map is revealed
  to you, every player gets START_MONEY, after CLASH seconds the advancing
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

    mw build nanduhirion-v1; mw build nanduhirion-battle; mw play nanduhirion-battle
"""
import math

import numpy as np
from PIL import Image

from mapworkshop import project
from mapworkshop.formats import sections
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.script_writer import Writer, arg
from maps.nanduhirion_v1.map import BORDER, CENTRE, SITES, STARTS, twin

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
# half) and player 2 (the north strip): per group its job, where the middle
# of its front row stands, its rows (an ARMY row and how many times over, or
# the heroes) and whether it advances at the clash or holds its ground. Every
# group faces its opponent's line and stands on its own spot's level.
# Players 4 and 3 stand as the mirrors of 1 and 2 across the map's middle,
# the east players as the half-turn twins of the west, facing them: 1 and 8,
# 4 and 5 in the arena, 2 and 7 on the north strip, 3 and 6 on the south one.
ARENA = [('line', (6350, 7550), [(0, 3), (1, 2), 'heroes', (2, 2)], True),
         ('flank', (6250, 8450), [(3, 2)], True),        # the arena's north-west mouth: on the enemy's flank
         ('siege', (5950, 7300), [(4, 2)], True),        # behind the line
         ('overwatch', (5350, 7600), [(2, 1)], False)]   # archers on the forward terrace above the arena
STRIP = [('line', (5900, 11400), [(0, 3), (1, 2), 'heroes', (2, 2)], True),
         ('vanguard', (6350, 10900), [(3, 2), (4, 1)], True),     # the strip's foot, by its signal fire
         ('inner outpost', (5650, 10050), [(0, 1), (2, 1)], False),
         ('corner outpost', (5150, 12450), [(1, 1), (2, 1)], False)]
RESERVE = [(0, 1), (1, 1), (2, 1)]   # at each base's rally point, holding
THEATRE = {1: ARENA, 4: ARENA, 2: STRIP, 3: STRIP}
MIRRORED = (3, 4)
OPPONENT = {1: 8, 8: 1, 4: 5, 5: 4, 2: 7, 7: 2, 3: 6, 6: 3}
ACROSS, BACK = 190, 175         # spacing of an army's units along a row, and between rows
RALLY = 650                     # the rally point (waves spawn there): this far from the start towards the line
LEVEL = 50                      # an army stands on its line's level, within this: not up a terrace behind it


def start(n):
    return SITES[STARTS[n - 1] - 1]


def bases(n):
    """Player n's two bases: its start, where the game puts its fortress, and
    its second site, where this map does."""
    return [start(n), SITES[SECOND_SITE[n] - 1]]


def at(n, p):
    """Where a point drawn up for player 1 or 2 is for player n."""
    west = n if n <= 4 else n - 4
    x, y = p
    if west in MIRRORED:
        y = 2*CENTRE[1] - y
    return (x, y) if n <= 4 else twin((x, y))


def groups(n):
    """Player n's army groups: (job, front middle, rows spec, advances)."""
    return [(job, at(n, p), rows, advances) for job, p, rows, advances in THEATRE[n if n <= 4 else n - 4]]


def line(n):
    return next(p for job, p, _, _ in groups(n) if job == 'line')


class Ground:
    """The terrain's heights and passability, for finding level, open spots."""
    def __init__(self, m):
        hm = m.heightmap()
        self.z = hm['elevations']*.0390625
        self.blocked = m.blend(inspection=True)['arrays']['impassable'].astype(bool)
        self.taken = []                                   # (x, y, radius) of what this build placed

    def height(self, x, y):
        return float(self.z[int(y//10) + BORDER, int(x//10) + BORDER])

    def fits(self, x, y, radius, relief, level=None):
        """Open, walkable ground within `relief` of level over `radius`, clear
        of what was taken, and at `level` (within LEVEL) when given."""
        i, j, r = int(y//10) + BORDER, int(x//10) + BORDER, max(1, int(radius//10))
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


def stage(m, factions, ground):
    """Clear the lairs, give the basin outposts to their lanes' players, and
    lay out bases, armies and waypoints. Returns the armies' units by player
    (name, template) and the waypoints by name."""
    objs = []
    for o in m.objects():
        if o['template'] in LAIRS:
            continue
        objs.append(o)
    # The basin outposts and their flags: each to its lane's player.
    lane = lambda x, y: (2 if y > 6975 else 3) if x < 7140 else (7 if y > 6975 else 6)
    for o in objs:
        if o['template'] in ('Outpost', 'CaptureFlag'):
            near = min((p for p in objs if p['template'] == 'Outpost'), key=lambda p: math.dist((p['x'], p['y']), (o['x'], o['y'])))
            if o['template'] == 'Outpost' or math.dist((near['x'], near['y']), (o['x'], o['y'])) < 200:
                n = lane(near['x'], near['y'])
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
        for x, y in bases(n):
            ground.taken.append((x, y, 330))
    for n in range(1, 9):
        faction = factions[n - 1]
        lx, ly = line(n)
        ox, oy = line(OPPONENT[n])
        for b, (sx, sy) in enumerate(bases(n)):
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
        army = groups(n) + [('reserve', waypoints[f'NB_Rally_{n}{tag}'], RESERVE, False) for tag in ('', 'b')]
        armies[n] = []
        for job, (gx, gy), spec, advances in army:
            d = math.dist((gx, gy), (ox, oy))
            fx, fy = (ox - gx)/d, (oy - gy)/d
            rows = [HEROES[n] if s == 'heroes' else ARMY[faction][s[0]]*s[1] for s in spec
                    if s == 'heroes' or s[0] < len(ARMY[faction])]
            level = ground.height(gx, gy)
            for r, row in enumerate(rows):
                for c, template in enumerate(row):
                    across = (c - (len(row) - 1)/2)*ACROSS
                    x, y = gx - fx*r*BACK - fy*across, gy - fy*r*BACK + fx*across
                    x, y = ground.spot(x, y, 70, 60, reach=1200, level=level)
                    name = f'NB_P{n}_A{len(armies[n]):02d}'
                    put(template, x, y, math.atan2(fy, fx), n, name, 'Armies')
                    armies[n].append((name, template, job, advances))
        waypoints[f'NB_Line_{n}'] = (lx, ly)
    waypoints['NB_Push_1'] = start(8)
    waypoints['NB_Push_2'] = start(5)
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


def scripts(m, factions, armies):
    """The scenario's scripts, on PlyrCivilian (see the module docstring)."""
    w = Writer(m)
    text = lambda kind, value: arg(kind, text=value)
    team = lambda n: text(3, f'Player_{n}/teamPlayer_{n}')
    move = lambda unit, waypoint: w.operation('action', 'ATTACK_MOVE_NAMED_UNIT_TO', [text(14, unit), text(7, waypoint)])
    timer = lambda name, seconds: w.operation('action', 'SET_MILLISECOND_TIMER', [text(4, name), arg(1, real=float(seconds))])
    expired = lambda name: [[w.operation('condition', 'TIMER_EXPIRED', [text(4, name)])]]
    setup = [w.operation('action', 'MAP_REVEAL_ALL_PERM', [text(11, f'Player_{YOU}')])]
    setup += [w.operation('action', 'PLAYER_GIVE_MONEY', [text(11, f'Player_{n}'), arg(0, integer=START_MONEY)])
              for n in range(1, 9)]
    setup += [timer('NB_Clash', CLASH)] + [timer(f'NB_Wave{k:02d}', FIRST_WAVE + (k - 1)*WAVE)
                                           for k in range(1, WAVE_COUNT + 1)]
    out = [w.script('NB_Setup', [[w.operation('condition', 'CONDITION_TRUE')]], setup)]
    out.append(w.script('NB_Clash', expired('NB_Clash'),
                        [move(name, f'NB_Line_{OPPONENT[n]}') for n in range(1, 9)
                         for name, _, _, advances in armies[n] if advances]))
    yours = [name for name, _, _, advances in armies[YOU] if advances]    # the guards and reserves stay put
    target = f'NB_Line_{OPPONENT[YOU]}'
    for k in range(1, WAVE_COUNT + 1):
        target = PUSH.get(k, target)
        actions, new = [], set()
        for n in range(1, 9):
            goal = target if n == YOU else f'NB_Line_{OPPONENT[n]}'
            for tag in ('', 'b'):                          # a wave from each of the player's bases
                for i, template in enumerate(WAVES[factions[n - 1]][k % 2]):
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
    v1 = project.find('nanduhirion-v1')
    if not v1.map_file.exists():
        raise RuntimeError('Build Nanduhirion v1 first: mw build nanduhirion-v1')
    factions = [slot['faction'] for slot in b.project.config['play']['slots']]
    names = [t for f in factions for t in BASES[f] + [u for row in ARMY[f] for u in row] + [u for w in WAVES[f] for u in w]]
    check_templates(b.assets, names + [FORTRESS[f] for f in factions] + [h for hs in HEROES.values() for h in hs])
    m = Map(v1.map_file.read_bytes())
    add_angmar_side(m)
    ground = Ground(m)
    armies, waypoints, placed = stage(m, factions, ground)
    count, _ = scripts(m, factions, armies)
    b.report.update(players={n: dict(faction=factions[n - 1], start=start(n), line=line(n), opponent=OPPONENT[n],
                                     army=len(armies[n]), groups={job: sum(1 for u in armies[n] if u[2] == job)
                                                                   for job in dict.fromkeys(u[2] for u in armies[n])},
                                     buildings=sum(1 for p in placed if p[5] == 'Bases' and
                                                                        p[4][0][2].startswith(f'Player_{n}/')))
                             for n in range(1, 9)},
                    waypoints={k: [round(v) for v in p] for k, p in waypoints.items()}, scripts=count,
                    waves=dict(first=FIRST_WAVE, every=WAVE, count=WAVE_COUNT))
    ini = (v1.build_dir/'map.ini').read_text(encoding='ascii', errors='replace')
    b.save(m, ini=ini.split('\n', 1)[1] if ini.startswith(';') else ini, minimap=Image.open(v1.build_dir/'preview.png'))
