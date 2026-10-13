"""Strategic layout analysis for skirmish maps: walking distances and fairness.

    python -m mapworkshop.mapkit.checks.strategy --map <file.map> --out DIR [--teams 1,2,3/4,5,6]

Builds a walkability grid from the map's stored impassable plane plus the
decks of bridge objects, then measures walking distances (8-connected, 20-unit
cells) from every start and neutral site. Reports, per player:

- distances to every other start; nearest enemy (free-for-all and per team);
- the nearest and owned (closest-to-this-player) outposts and lairs, and how
  much closer they are to their owner than to anyone else (safety margin);
- the share of walkable land closest to each player (territory);
- for teams, the front: distances across the team boundary and which bridges
  carry the shortest routes.

Distances are terrain geometry only; unit speed, AI and pathfinder quirks are
not modelled. Writes strategy.json and strategy.png (territory overlay).
"""

import argparse
import heapq
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from mapworkshop.formats.map import Map

STEP = 20.0                       # world units per analysis cell
SITE_TEMPLATES = {'outpost': 'Outpost', 'warglair': 'WargLair', 'inn': 'Inn', 'signalfire': 'SignalFire'}
BRIDGE_HALF = (60.0, 285.0)       # deck half extents (across, along) of GondorIthilienBridge2


def walk_grid(m):
    hm = m.heightmap()
    w, h, border = hm['width'], hm['height'], hm['border']
    blocked = m.blend(inspection=True)['arrays']['impassable'].astype(bool)
    play = blocked[border:h-border, border:w-border]
    ph, pw = play.shape
    s = int(STEP/10)
    gh, gw = ph//s, pw//s
    # A coarse cell is walkable when most of its fine cells are.
    walk = (play[:gh*s, :gw*s].reshape(gh, s, gw, s).mean(axis=(1, 3)) < .5)
    bridges = []
    for o in m.objects():
        if 'bridge' not in o['template'].lower():
            continue
        a = o['angle'] + math.pi/2           # deck runs along the object's local Y
        ax, ay = math.cos(a), math.sin(a)
        yy, xx = np.indices(walk.shape)
        wx, wy = (xx+.5)*STEP - o['x'], (yy+.5)*STEP - o['y']
        along = wx*ax + wy*ay
        across = -wx*ay + wy*ax
        deck = (np.abs(along) <= BRIDGE_HALF[1]) & (np.abs(across) <= BRIDGE_HALF[0])
        walk |= deck
        name = next((v for k, _, v in o['properties'] if k == 'objectName'), o['template'])
        bridges.append(dict(name=name, position=(o['x'], o['y']), deck=deck))
    return walk, bridges


def cell_of(walk, p):
    gy, gx = int(p[1]//STEP), int(p[0]//STEP)
    gy = min(max(gy, 0), walk.shape[0]-1); gx = min(max(gx, 0), walk.shape[1]-1)
    if walk[gy, gx]:
        return gy, gx
    best = None
    for r in range(1, 40):
        ys, xs = np.nonzero(walk[max(0, gy-r):gy+r+1, max(0, gx-r):gx+r+1])
        if len(ys):
            k = np.argmin((ys+max(0, gy-r)-gy)**2+(xs+max(0, gx-r)-gx)**2)
            return ys[k]+max(0, gy-r), xs[k]+max(0, gx-r)
    return best


def distance_field(walk, source):
    """Dijkstra over walkable cells; distances in world units."""
    h, w = walk.shape
    dist = np.full((h, w), np.inf)
    sy, sx = cell_of(walk, source)
    dist[sy, sx] = 0
    queue = [(0.0, sy, sx)]
    moves = [(-1, 0, 1.), (1, 0, 1.), (0, -1, 1.), (0, 1, 1.),
             (-1, -1, 1.41421), (-1, 1, 1.41421), (1, -1, 1.41421), (1, 1, 1.41421)]
    flat_walk = walk
    while queue:
        d, y, x = heapq.heappop(queue)
        if d > dist[y, x]:
            continue
        for dy, dx, c in moves:
            ny, nx = y+dy, x+dx
            if 0 <= ny < h and 0 <= nx < w and flat_walk[ny, nx]:
                if dy and dx and not (flat_walk[y, nx] and flat_walk[ny, x]):
                    continue
                nd = d + c*STEP
                if nd < dist[ny, nx]:
                    dist[ny, nx] = nd
                    heapq.heappush(queue, (nd, ny, nx))
    return dist


def at(field, walk, p):
    c = cell_of(walk, p)
    return float(field[c]) if c else math.inf


def path_cells(field, walk, target):
    """Cells on the steepest-descent path from target back to the field's source."""
    y, x = cell_of(walk, target)
    cells = [(y, x)]
    for _ in range(100000):
        best = (field[y, x], y, x)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y+dy, x+dx
                if 0 <= ny < field.shape[0] and 0 <= nx < field.shape[1] and field[ny, nx] < best[0]:
                    best = (field[ny, nx], ny, nx)
        if best[1:] == (y, x):
            break
        _, y, x = best
        cells.append((y, x))
    return cells


def analyse(m, teams=None):
    walk, bridges = walk_grid(m)
    objects = m.objects()
    starts = sorted(((next(v for k, _, v in o['properties'] if k == 'waypointName'), (o['x'], o['y']))
                     for o in objects if o['template'] == '*Waypoints/Waypoint'
                     and any(k == 'waypointName' and str(v).startswith('Player_') for k, _, v in o['properties'])),
                    key=lambda s: s[0])
    names = [s[0] for s in starts]
    starts = [s[1] for s in starts]
    sites = [dict(kind=o['template'], position=(o['x'], o['y'])) for o in objects
             if o['template'].lower() in SITE_TEMPLATES]
    fields = [distance_field(walk, p) for p in starts]
    n = len(starts)
    matrix = [[at(fields[i], walk, starts[j]) for j in range(n)] for i in range(n)]
    owner = np.argmin(np.stack(fields), axis=0)
    reach = np.isfinite(np.min(np.stack(fields), axis=0)) & walk
    territory = [int(np.count_nonzero(reach & (owner == i))) for i in range(n)]
    for s in sites:
        d = [at(f, walk, s['position']) for f in fields]
        order = np.argsort(d)
        s['distances'] = [round(v) for v in d]
        s['owner'] = int(order[0]) + 1
        s['margin'] = round(d[order[1]] - d[order[0]])
    players = []
    for i in range(n):
        others = [matrix[i][j] for j in range(n) if j != i]
        entry = dict(player=i+1, name=names[i], position=starts[i],
                     nearest_opponent=round(min(others)), territory_cells=territory[i],
                     territory_share=round(territory[i]/max(1, sum(territory)), 4))
        for kind in sorted({s['kind'] for s in sites}):
            own = [s for s in sites if s['kind'] == kind and s['owner'] == i+1]
            nearest = min((s['distances'][i] for s in sites if s['kind'] == kind), default=None)
            entry[kind] = dict(owned=len(own), nearest=nearest,
                               owned_distances=[s['distances'][i] for s in own],
                               owned_margins=[s['margin'] for s in own])
        players.append(entry)
    report = dict(step=STEP, starts=n, base_distances=[[round(v) for v in row] for row in matrix],
                  players=players, sites=sites, bridges=[b['name'] for b in bridges])
    if teams:
        team_of = {p: t for t, members in enumerate(teams) for p in members}
        report['teams'] = []
        for t, members in enumerate(teams):
            enemies = [p for p in range(1, n+1) if team_of.get(p) != t]
            report['teams'].append(dict(team=t+1, members=members,
                nearest_enemy={p: round(min(matrix[p-1][e-1] for e in enemies)) for p in members},
                territory_share=round(sum(territory[p-1] for p in members)/max(1, sum(territory)), 4),
                outposts_owned=sum(1 for s in sites if s['kind'] == 'Outpost' and team_of.get(s['owner']) == t)))
        # Bridge use on the shortest routes between opposing starts.
        use = {b['name']: 0 for b in bridges}
        for a in range(1, n+1):
            for b in range(a+1, n+1):
                if team_of.get(a) == team_of.get(b):
                    continue
                cells = path_cells(fields[a-1], walk, starts[b-1])
                for br in bridges:
                    if any(br['deck'][c] for c in cells):
                        use[br['name']] += 1
        report['bridge_use_between_teams'] = use
    return report, walk, owner, reach, starts, sites, bridges


def draw(report, walk, owner, reach, starts, sites, bridges, path):
    colors = np.array([(227, 85, 72), (67, 143, 229), (85, 189, 86), (227, 203, 81), (181, 107, 234), (66, 198, 195),
                       (230, 140, 60), (200, 200, 200)], np.uint8)
    rgb = np.full(walk.shape+(3,), 30, np.uint8)
    rgb[walk] = 70
    rgb[reach] = (colors[owner[reach] % len(colors)] * .45 + 40).astype(np.uint8)
    im = Image.fromarray(np.flipud(rgb)).resize((walk.shape[1]*2, walk.shape[0]*2), Image.NEAREST)
    d = ImageDraw.Draw(im)
    H = walk.shape[0]*2
    px = lambda p: (p[0]/STEP*2, H - p[1]/STEP*2)
    for b in bridges:
        x, y = px(b['position']); d.rectangle((x-5, y-5, x+5, y+5), outline='white')
    for s in sites:
        x, y = px(s['position'])
        c = tuple(int(v) for v in colors[(s['owner']-1) % len(colors)])
        if s['kind'] == 'Outpost':
            d.ellipse((x-7, y-7, x+7, y+7), fill=c, outline='white', width=2)
        else:
            d.polygon([(x, y-8), (x+7, y+6), (x-7, y+6)], fill=(20, 20, 20), outline=c, width=2)
        d.text((x+9, y-6), str(s['margin']), fill='white')
    for i, p in enumerate(starts):
        x, y = px(p); c = tuple(int(v) for v in colors[i % len(colors)])
        d.rectangle((x-10, y-10, x+10, y+10), fill=c, outline='white', width=2)
        d.text((x-3, y-6), str(i+1), fill='black')
    im.save(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--map', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--teams', help='Player teams, e.g. 1,2,3/4,5,6')
    args = parser.parse_args(argv)
    teams = [[int(v) for v in t.split(',')] for t in args.teams.split('/')] if args.teams else None
    m = Map(args.map.read_bytes())
    report, walk, owner, reach, starts, sites, bridges = analyse(m, teams)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out/'strategy.json').write_text(json.dumps(report, indent=1, default=str)+'\n')
    draw(report, walk, owner, reach, starts, sites, bridges, args.out/'strategy.png')
    print(json.dumps(dict(players=[(p['player'], p['nearest_opponent'], p['territory_share']) for p in report['players']]), indent=None))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
