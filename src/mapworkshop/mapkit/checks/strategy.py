"""Strategic layout analysis for skirmish maps: walking distances and fairness.

    mw sites MAP [--teams 1-4/5-8] [--bases X,Y ...] [--image FILE] [--json]
    python -m mapworkshop.mapkit.checks.strategy --map <file.map> --out DIR [--teams 1,2,3/4,5,6]

Builds a walkability grid from the map's stored impassable plane plus the
decks of bridge objects, then measures walking distances (8-connected, 20-unit
cells) from every base (the starts, or `bases`) to the others and to every
neutral site: the capturable buildings (outposts, inns, signal fires,
shipwrights) and the creep lairs. Reports, per player:

- distances to every other start; nearest enemy (free-for-all and per team);
- the nearest and owned (closest-to-this-player) sites of each kind, and how
  much closer they are to their owner than to anyone else (safety margin);
- the share of walkable land closest to each player (territory);
- for teams, the front: distances across the team boundary and which bridges
  carry the shortest routes.

lines() puts the report as text: each site with the nearest base of each team
(or the nearest two bases) and the margin, each base with its nearest enemy
and its nearest site of each kind, and per kind how far the bases walk to
their nearest one.

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
from mapworkshop.mapkit.memo import pure
from mapworkshop.mapkit.sites import LAIRS, LINKED

STEP = 20.0                       # world units per analysis cell
SITE_TEMPLATES = (*LINKED, *LAIRS)   # the capturable buildings and the creep lairs
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


@pure
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


def parse_teams(text):
    """Teams written 1-4/5-8 or 1,2,3/4,5,6: lists of base numbers."""
    teams = []
    for part in text.split('/'):
        members = []
        for item in part.split(','):
            first, _, last = item.partition('-')
            members += range(int(first), int(last or first) + 1)
        teams.append(members)
    return teams


def analyse(m, teams=None, bases=None):
    """The report (see the module docstring) and what draw() needs. `bases`:
    points to measure from instead of the starts, for a map laid out for more
    players than it seats; `teams`: lists of base numbers."""
    walk, bridges = walk_grid(m)
    objects = m.objects()
    if bases:
        starts = [(f'Base {i}', tuple(p)) for i, p in enumerate(bases, 1)]
    else:
        starts = sorted(((next(v for k, _, v in o['properties'] if k == 'waypointName'), (o['x'], o['y']))
                         for o in objects if o['template'] == '*Waypoints/Waypoint'
                         and any(k == 'waypointName' and str(v).startswith('Player_') for k, _, v in o['properties'])),
                        key=lambda s: s[0])
    names = [s[0] for s in starts]
    starts = [s[1] for s in starts]
    sites = [dict(kind=o['template'], position=(o['x'], o['y'])) for o in objects
             if o['template'] in SITE_TEMPLATES]
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
    report = dict(step=STEP, starts=n, bases='given' if bases else 'starts',
                  base_distances=[[round(v) for v in row] for row in matrix], players=players, sites=sites, bridges=[b['name'] for b in bridges])
    if teams:
        team_of = {p: t for t, members in enumerate(teams) for p in members}
        for s in sites:                  # the nearest team, and how much nearer than the next
            near = sorted((min(s['distances'][p-1] for p in members), t+1) for t, members in enumerate(teams))
            s['team'], s['team_margin'] = near[0][1], (near[1][0] - near[0][0] if len(near) > 1 else None)
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


def lines(report, title):
    """The report as text: sites, bases and a summary per kind of site."""
    n, sites, teams = report['starts'], report['sites'], report.get('teams')
    matrix = report['base_distances']
    who = 'the given points' if report.get('bases') == 'given' else 'the starts'
    split = ' / '.join(_span(t['members']) for t in teams) if teams else 'every base for itself'
    out = [f'{title}: {n} bases ({who}); teams {split}. Walking distances in map units, over '
           f'{report["step"]:g}-unit cells of the stored impassable plane and bridge decks.', '']
    kinds = sorted({s['kind'] for s in sites}, key=lambda k: (k not in LINKED, k))
    if sites:
        out.append('Sites: the nearest base of each team, and how much nearer the nearer team is.' if teams else
                   'Sites: the nearest base, the next nearest, and how much nearer the first is.')
        for s in sorted(sites, key=lambda s: (kinds.index(s['kind']), -s['position'][1], s['position'][0])):
            d = s['distances']
            if teams:
                near = sorted(min((d[p-1], p) for p in t['members']) + (t['team'],) for t in teams)
                parts = [f'team {team}: #{p} {v:,.0f}' for v, p, team in near]
                lead = f'team {near[0][2]} by {near[1][0] - near[0][0]:,.0f}' if len(near) > 1 else ''
            else:
                near = sorted((v, i + 1) for i, v in enumerate(d))[:2]
                parts = [f'#{p} {v:,.0f}' for v, p in near]
                lead = f'by {near[1][0] - near[0][0]:,.0f}' if len(near) > 1 else ''
            x, y = s['position']
            out.append(f'  {s["kind"]:<17} ({x:6.0f}, {y:6.0f})  ' + '   '.join(parts) + f'   {lead}')
        out.append('')
    out.append('Bases: the nearest enemy' + (' (on another team)' if teams else '')
               + ', and the nearest site of each kind.')
    team_of = {p: t['team'] for t in teams for p in t['members']} if teams else {}
    widths = [max(len(k), 7) for k in kinds]
    out.append(f'  {"base":<20} {"enemy":>7}  ' + '  '.join(f'{k:>{w}}' for k, w in zip(kinds, widths)))
    for i, p in enumerate(report['players']):
        enemies = [matrix[i][j] for j in range(n)
                   if j != i and (not teams or team_of.get(j + 1) != team_of.get(i + 1))]
        x, y = p['position']
        cells = [f'{p[k]["nearest"]:>{w},}' if p[k]['nearest'] is not None else f'{"-":>{w}}'
                 for k, w in zip(kinds, widths)]
        out.append(f'  {f"#{i+1} ({x:.0f}, {y:.0f})":<20} {min(enemies, default=0):>7,}  ' + '  '.join(cells))
    if sites:
        out += ['', 'Per kind: how far the bases walk to their nearest one (least, median, most).']
        for k in kinds:
            walks = sorted(p[k]['nearest'] for p in report['players'] if p[k]['nearest'] is not None)
            count = sum(s['kind'] == k for s in sites)
            if walks:
                sites_ = 'sites' if count != 1 else 'site '
                out.append(f'  {k:<17} {count:>3} {sites_}   {walks[0]:,} / {walks[len(walks)//2]:,} / {walks[-1]:,}')
    return out


def _span(members):
    """1-4 for 1,2,3,4; else the numbers."""
    if len(members) > 2 and members == list(range(members[0], members[-1] + 1)):
        return f'{members[0]}-{members[-1]}'
    return ','.join(map(str, members))


def draw(report, walk, owner, reach, starts, sites, bridges, path):
    """Each base's territory (the ground nearest it), coloured by team when
    the report has teams, every other base a shade darker; the sites with
    their margins (over the next team, with teams); the bases."""
    colors = np.array([(227, 85, 72), (67, 143, 229), (85, 189, 86), (227, 203, 81), (181, 107, 234), (66, 198, 195),
                       (230, 140, 60), (200, 200, 200)], np.uint8)
    team_of = {p - 1: t['team'] - 1 for t in report.get('teams', ()) for p in t['members']}
    tint = np.array([team_of.get(i, i) for i in range(len(starts))])
    shade = np.array([1. - .25*(i % 2) if team_of else 1. for i in range(len(starts))])
    rgb = np.full(walk.shape+(3,), 30, np.uint8)
    rgb[walk] = 70
    rgb[reach] = (colors[tint[owner[reach]] % len(colors)] * .45 * shade[owner[reach], None] + 40).astype(np.uint8)
    im = Image.fromarray(np.flipud(rgb)).resize((walk.shape[1]*2, walk.shape[0]*2), Image.NEAREST)
    d = ImageDraw.Draw(im)
    H = walk.shape[0]*2
    px = lambda p: (p[0]/STEP*2, H - p[1]/STEP*2)
    for b in bridges:
        x, y = px(b['position']); d.rectangle((x-5, y-5, x+5, y+5), outline='white')
    for s in sites:
        x, y = px(s['position'])
        c = tuple(int(v) for v in colors[tint[s['owner']-1] % len(colors)])
        if s['kind'] in LINKED:
            d.ellipse((x-7, y-7, x+7, y+7), fill=c, outline='white', width=2)
        else:
            d.polygon([(x, y-8), (x+7, y+6), (x-7, y+6)], fill=(20, 20, 20), outline=c, width=2)
        name = s['kind'].replace('Lair', '').replace('Moriar', '').replace('Cave', '')
        d.text((x+9, y-6), f"{name} {s.get('team_margin', s['margin'])}", fill='white')
    for i, p in enumerate(starts):
        x, y = px(p); c = tuple(int(v) for v in colors[tint[i] % len(colors)])
        d.rectangle((x-10, y-10, x+10, y+10), fill=c, outline='white', width=2)
        d.text((x-3 - 3*(i >= 9), y-6), str(i+1), fill='black')
    im.save(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--map', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--teams', help='Player teams, e.g. 1,2,3/4,5,6')
    args = parser.parse_args(argv)
    teams = parse_teams(args.teams) if args.teams else None
    m = Map(args.map.read_bytes())
    report, walk, owner, reach, starts, sites, bridges = analyse(m, teams)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out/'strategy.json').write_text(json.dumps(report, indent=1, default=str)+'\n')
    draw(report, walk, owner, reach, starts, sites, bridges, args.out/'strategy.png')
    print(json.dumps(dict(players=[(p['player'], p['nearest_opponent'], p['territory_share']) for p in report['players']]), indent=None))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
