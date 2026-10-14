"""Walls: the game's chainable defensive walls laid along a path, and castle sites.

BFME2 has three kinds of wall object:

- Chain walls (WallHubBehavior): the segments, hubs, gates and towers players
  build from their fortress. In the game a player places hubs and the engine
  fills each span with segments. A map places them piece by piece, and
  `wall_line` does it the way the stock maps do: segments end to end along
  each straight run, a hub at every corner, and gates, towers and the like
  in place of segments. They are structures: they block paths, take damage,
  leave rubble and are rebuilt, and siege ladders scale them.
- Castles (CastleBehavior): a CastleFlag is a site that unpacks the faction
  castle of whoever captures it (bases/castle_<faction>[NE|NW|SE|SW].bse, its
  CastleTemplates chunk) within MaxCastleRadius 420: keep, walls, gates,
  elevators, tower nodes and props. `castle_site` places one; `castle_layout`
  reads a castle's buildings, e.g. to keep the ground clear. The castle only
  appears in the game: the renderer and viewer draw the flag alone.
- Decorative castle members (RohanEdorasWall, GondorCastleWall and the walls
  of the campaign maps' set pieces): ordinary objects for add_object.

Stock evidence (local/game/maps, measured): the advanced tutorial, Withered
Heath, Dol Guldur, Mirkwood and the Grey Havens place chain walls with
segments exactly one length (38) apart, turned to the run (angle = run + 90
degrees, or the run itself for a kit long along its local x) and a hub at each
end; a gate takes three segments' places, a tower, postern, trebuchet or
catapult one. Front and back of the pieces look alike, and the stock maps
turn them either way; `flip` turns a whole wall round. The castle kits marked
`stock=False` are built by fortresses in the game and are not seen placed in
any stock map. None of this is yet verified in a native capture.

    from mapworkshop.mapkit.walls import wall_line, place_wall
    pieces = wall_line([(1000, 1000), (1400, 1000), (1400, 1300)], kit='men',
                       at={'gate': [(1200, 1000)], 'tower': [(1400, 1150)]})
    place_wall(m, pieces, owner='PlyrCivilian')
"""
from dataclasses import dataclass, field
import math

CASTLE_RADIUS = 420.0           # CastleFlag's MaxCastleRadius (civilianbuildings.ini)
CASTLE_DIRECTIONS = ('', 'NE', 'NW', 'SE', 'SW')
CASTLE_FACTIONS = ('Men', 'Elves', 'Dwarves', 'Isengard', 'Mordor', 'Wild')


@dataclass(frozen=True)
class Kit:
    """One faction's chain wall: its segment and hub, the pieces that can take
    a segment's place, and their lengths along the wall (model bounds, `mw
    items`). `along` is the segment's local axis that runs along the wall."""
    segment: str
    hub: str
    length: float
    hub_size: float
    pieces: dict = field(default_factory=dict)     # kind: (template, length along the wall)
    along: str = 'y'
    stock: bool = True


KITS = {
    'men': Kit('MenWallSegmentSmall', 'MenWallHubSmall', 38, 41,
               dict(gate=('MenWallGateSmall', 128), postern=('MenWallPosternGateSmall', 38),
                    tower=('MenWallTowerSmall', 38), trebuchet=('MenWallTrebuchetSmall', 44))),
    'dwarves': Kit('DwarvenWallSegmentSmall', 'DwarvenWallHubSmall', 38, 45,
                   dict(gate=('DwarvenWallGateSmall', 122), postern=('DwarvenWallPosternGateSmall', 38),
                        tower=('DwarvenWallTowerSmall', 38), catapult=('DwarvenWallCatapultSmall', 45))),
    'dol_guldur': Kit('DolGoldurWallSegmentSmall', 'DoGoldurWallHubSmall', 38, 55,
                      dict(tower=('DoGoldurWallTowerSmall', 38), catapult=('DoGoldurWallCatapultSmall', 53)), along='x'),
    'elves': Kit('ElvenCastleWallSegment', 'ElvenCastleWallHub', 38, 46, dict(gate=('ElvenCastleWallGate', 120))),
    'isengard': Kit('IsengardCastleWallSegment', 'IsengardCastleWallHub', 38, 45,
                    dict(gate=('IsengardCastleWallGate', 118)), stock=False),
    'gondor_castle': Kit('GondorCastleWallSegment', 'GondorCastleWallHub', 78, 106, dict(gate=('MenWallGate', 282)),
                         stock=False),
    'dwarven_castle': Kit('DwarvenCastleWallSegment', 'DwarvenCastleWallHub', 126, 118,
                          dict(gate=('DwarvenCastleWallGate', 274)), stock=False),
    'mordor_castle': Kit('MordorCastleWallSegment', 'MordorCastleWallHub', 126, 118,
                         dict(gate=('MordorCastleWallGate', 282)), stock=False),
    'wild_castle': Kit('WildCastleWallSegment', 'WildCastleWallHub', 126, 118, dict(gate=('WildCastleWallGate', 282)),
                       stock=False),
}


@dataclass
class Piece:
    template: str
    x: float
    y: float
    angle: float                # map angle, radians
    kind: str                   # 'segment', 'hub' or a Kit.pieces kind
    run: int                    # the run (path edge) it stands on; hubs: the corner's index
    length: float = 0.0         # along the wall
    heading: float = 0.0        # the wall's direction there, radians


def slots(length, size):
    """How many segment places a piece of `length` takes in a wall of `size` segments."""
    return max(1, round(length/size))


def wall_line(points, kit='men', closed=False, at=None, flip=False, ends=True):
    """The pieces of a chain wall along `points` (x, y in map units), as Piece
    records; place them with place_wall.

    Each straight run between two points is filled with segments end to end,
    spaced evenly so that they reach from hub to hub without gaps (never more
    than one length apart). A hub stands on every point (on the end points of
    an open wall only with `ends`). `at` maps a kind of the kit's pieces
    ('gate', 'tower', ...) to points: each takes the places of the segments
    nearest it on its nearest run. `closed` joins the last point to the first."""
    k = KITS[kit] if isinstance(kit, str) else kit
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2 or (closed and len(pts) < 3):
        raise ValueError('A wall needs at least two points (three when closed)')
    runs = list(zip(pts, pts[1:]+pts[:1])) if closed else list(zip(pts, pts[1:]))
    turn = math.pi if flip else 0.0
    face = (math.pi/2 if k.along == 'y' else 0.0)+turn

    # Segment places along every run, between the hubs at its ends.
    places = []                 # (run, x, y, run angle, spacing)
    for r, ((ax, ay), (bx, by)) in enumerate(runs):
        length = math.hypot(bx-ax, by-ay)
        if length < 1:
            raise ValueError(f'Run {r} has no length')
        clear = .75*k.hub_size/2
        usable = length-2*clear
        if usable < k.length*.5:
            raise ValueError(f'Run {r} is too short ({length:.0f}) for a {kit} wall between its hubs')
        n = max(1, math.ceil(usable/k.length))
        step = usable/n
        dx, dy = (bx-ax)/length, (by-ay)/length
        for i in range(n):
            s = clear+step*(i+.5)
            places.append([r, ax+dx*s, ay+dy*s, math.atan2(dy, dx), step, None])

    # Pieces in place of segments: each takes the nearest places on one run.
    for kind, where in (at or {}).items():
        if kind not in k.pieces:
            raise ValueError(f'The {kit} wall has no {kind!r}; it has {", ".join(k.pieces) or "no pieces"}')
        template, length = k.pieces[kind]
        for px, py in where:
            first = min(range(len(places)), key=lambda i: math.dist(places[i][1:3], (px, py)))
            r = places[first][0]
            run = [i for i in range(len(places)) if places[i][0] == r]
            need = slots(length, places[first][4])
            if need > len(run):
                raise ValueError(f'No room for a {kind} on run {r}: it takes {need} places, the run has {len(run)}')
            # The window of `need` places on this run whose middle is nearest the point.
            starts = range(run[0], run[-1]-need+2)
            start = min(starts, key=lambda s: math.dist(_middle(places, s, need), (px, py)))
            if any(places[i][5] is not None for i in range(start, start+need)):
                raise ValueError(f'The {kind} at ({px:.0f}, {py:.0f}) overlaps another piece')
            for i in range(start, start+need):
                places[i][5] = (kind, template, length, start, need)

    pieces, done = [], set()
    for i, (r, x, y, angle, step, taken) in enumerate(places):
        if taken is None:
            pieces.append(Piece(k.segment, x, y, angle+face, 'segment', r, k.length, angle))
        elif taken[3] not in done:
            kind, template, length, start, need = taken
            mx, my = _middle(places, start, need)
            pieces.append(Piece(template, mx, my, angle+face, kind, r, length, angle))
            done.add(start)
    corners = range(len(pts)) if closed or ends else range(1, len(pts)-1)
    for c in corners:
        here = pts[c]
        before = pts[c-1] if (closed or c > 0) else None
        after = pts[(c+1) % len(pts)] if (closed or c < len(pts)-1) else None
        dirs = [math.atan2(b[1]-a[1], b[0]-a[0]) for a, b in ((before, here), (here, after)) if a and b]
        angle = math.atan2(sum(math.sin(d) for d in dirs), sum(math.cos(d) for d in dirs))
        pieces.append(Piece(k.hub, here[0], here[1], angle+face, 'hub', c, k.hub_size, angle))
    return pieces


def _middle(places, start, need):
    xs = [places[i][1] for i in range(start, start+need)]
    ys = [places[i][2] for i in range(start, start+need)]
    return sum(xs)/need, sum(ys)/need


def owner_property(owner):
    """originalOwner for a player or side name ('PlyrCivilian', 'Player_1',
    'PlyrCreeps'), as `<name>/team<name>`; a value with a slash is kept."""
    return owner if '/' in owner else f'{owner}/team{owner}'


def place_wall(m, pieces, owner='PlyrCivilian', layer='Walls'):
    """Add the pieces to the map, owned by `owner` (owner_property)."""
    from mapworkshop.mapkit.blank import add_object
    extra = [('originalOwner', 3, owner_property(owner))]
    for p in pieces:
        add_object(m, p.template, p.x, p.y, p.angle, layer=layer, extra=extra)
    return len(pieces)


def ground_rise(pieces, height_at):
    """For every piece, how much the ground rises and falls along it (max -
    min of `height_at` over its length): walls want level ground, so a project
    can level under them or move them where this is large."""
    out = []
    for p in pieces:
        dx, dy = math.cos(p.heading), math.sin(p.heading)
        heights = [float(height_at(p.x+dx*t, p.y+dy*t)) for t in (-p.length/2, -p.length/4, 0, p.length/4, p.length/2)]
        out.append(max(heights)-min(heights))
    return out


def castle_site(m, x, y, direction='', owner='PlyrNeutral', layer='Castles'):
    """A CastleFlag at (x, y): the player who captures it gets their faction's
    castle unpacked round it (CASTLE_RADIUS), laid out for `direction` ('',
    'NE', 'NW', 'SE' or 'SW': the castle_<faction><direction> variant, whose
    gate faces that way). Keep the ground within CASTLE_RADIUS level and clear."""
    from mapworkshop.mapkit.blank import add_object
    if direction not in CASTLE_DIRECTIONS:
        raise ValueError(f'Castle direction {direction!r}: use one of {CASTLE_DIRECTIONS}')
    add_object(m, 'CastleFlag'+direction, x, y, 0.0, layer=layer, extra=[('originalOwner', 3, owner_property(owner))])


def castle_layout(faction='Men', direction='', assets=None):
    """The buildings of a faction's castle (bases/castle_<faction><direction>.bse):
    dict(name, buildings=[dict(template, x, y, z, angle)], radius), positions
    relative to the castle's flag."""
    from mapworkshop.formats.castles import decode
    from mapworkshop.formats.map import Map
    from mapworkshop.formats.map_archive import unpack
    if assets is None:
        from mapworkshop.render.assets import GameAssets
        assets = GameAssets()
    name = f'castle_{faction}{direction}'.lower()
    data = assets.read(f'bases/{name}/{name}.bse')
    if data[:4] != b'CkMp':
        data = unpack(data)
    m = Map(data)
    chunk = m.chunk('CastleTemplates')
    value = decode(chunk.data, m.names, chunk.version)
    buildings = [dict(template=b['template'], x=b['position'][0], y=b['position'][1], z=b['position'][2],
                      angle=b['angle']) for b in value['buildings'] if b['template']]
    radius = max((math.hypot(b['x'], b['y']) for b in buildings), default=0.0)
    return dict(name=value['faction'], buildings=buildings, radius=radius)
