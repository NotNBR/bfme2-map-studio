"""Battle plan sheets of a Battle of Nanduhirion build: the map's top view with
every army drawn as map symbols by role, the routes of the plan (the advance,
the riders' charge through the lanes, the siege to its battery with its
range, the waves from the bases) and its timeline.

    local/venv/Scripts/python -m maps.nanduhirion_battle.plan nanduhirion-v2-battle

writes overview.png, arena.png and north.png (the south strip mirrors the
north) to local/renders/<project>-plan/. The roles come from the battle's
tables (ARMY rows, HEROES, SIEGE), the positions from the built map, the
routes from its report's waypoints and units (each advancing group's job and
when it goes) plus ROUTES, the ramps v2's armies take (Nanduhirion v2's
terrain: maps/nanduhirion_v2_battle/map.py), and the timeline from when the
groups go.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from mapworkshop import project
from mapworkshop.config import LOCAL, ROOT
from mapworkshop.formats.map import Map
from maps.nanduhirion_battle.map import ARMY, FIRST_WAVE, GOOD, HEROES, OPPONENT, SIEGE

UNITS_PER_PX = 5                 # the top view's scale
RANGE = 500                      # the siege's reach from its battery (SIEGE weapons: 300 to 500)
# The ramps v2's armies take, for players 1 and 2 (the others mirror / turn them): in the arena from the high ground down to the
# terrace and from the terrace down into the bowl; on the north strip up onto the plateau. A group takes those nearer the fight than it.
ROUTES = {1: [(3200, 5450), (5450, 6330), (5850, 6280)], 2: [(6200, 9100)]}
COLOURS = {1: (90, 150, 255), 2: (110, 220, 200), 3: (150, 200, 120), 4: (140, 120, 255),
           5: (255, 110, 60), 6: (240, 200, 60), 7: (220, 120, 220), 8: (255, 60, 80)}


def font(size):
    for name in ('arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def role(template, faction, n):
    if template in HEROES.get(n, []):
        return 'hero'
    if any(w in template for w in SIEGE):
        return 'siege'
    rows = ARMY[faction]
    for k, name in ((0, 'front'), (1, 'melee'), (2, 'archers')):
        if k < len(rows) and template in rows[k]:
            return name
    return 'charge'


class Sheet:
    def __init__(self, top, box, scale):
        """`box` (x0, y0, x1, y1) of the map shown, `scale` px per top-view px."""
        x0, y0, x1, y1 = box
        h = top.height
        crop = top.crop((x0//UNITS_PER_PX, h - y1//UNITS_PER_PX, x1//UNITS_PER_PX, h - y0//UNITS_PER_PX))
        crop = crop.resize((int(crop.width*scale), int(crop.height*scale)), Image.LANCZOS)
        dark = Image.new('RGBA', crop.size, (10, 12, 18, 120))
        self.im = Image.alpha_composite(crop.convert('RGBA'), dark)
        self.box, self.k = box, scale/UNITS_PER_PX
        self.layer = Image.new('RGBA', self.im.size, (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.layer)

    def px(self, x, y):
        return ((x - self.box[0])*self.k, (self.box[3] - y)*self.k)

    def arrow(self, points, colour, width, alpha=210, dashed=False, head=True):
        pts = [self.px(*p) for p in points]
        c = colour + (alpha,)
        for a, b in zip(pts, pts[1:]):
            if dashed:
                L = math.dist(a, b)
                steps = max(1, int(L//(width*4)))
                for i in range(0, steps, 2):
                    p = (a[0] + (b[0] - a[0])*i/steps, a[1] + (b[1] - a[1])*i/steps)
                    q = (a[0] + (b[0] - a[0])*min(steps, i + 1)/steps, a[1] + (b[1] - a[1])*min(steps, i + 1)/steps)
                    self.d.line([p, q], fill=c, width=width)
            else:
                self.d.line([a, b], fill=c, width=width, joint='curve')
        if head and len(pts) > 1:
            (ax, ay), (bx, by) = pts[-2], pts[-1]
            ang = math.atan2(by - ay, bx - ax)
            s = width*3.2
            tri = [(bx + math.cos(ang)*s*.6, by + math.sin(ang)*s*.6),
                   (bx + math.cos(ang + 2.5)*s, by + math.sin(ang + 2.5)*s),
                   (bx + math.cos(ang - 2.5)*s, by + math.sin(ang - 2.5)*s)]
            self.d.polygon(tri, fill=c)

    def unit(self, x, y, angle, kind, colour, size):
        cx, cy = self.px(x, y)
        a = -angle                                       # map angle: counter-clockwise from east; the image's y points down
        fwd, side = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        at = lambda f, s: (cx + fwd[0]*f + side[0]*s, cy + fwd[1]*f + side[1]*s)
        c, edge = colour + (255,), (0, 0, 0, 255)
        if kind in ('front', 'melee'):
            poly = [at(size*.35, -size), at(size*.35, size), at(-size*.35, size), at(-size*.35, -size)]
            self.d.polygon(poly, fill=c if kind == 'front' else (0, 0, 0, 120), outline=c if kind == 'melee' else edge)
            if kind == 'melee':
                self.d.line(poly + [poly[0]], fill=c, width=2)
        elif kind == 'archers':
            r = size*.42
            self.d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c, outline=edge)
        elif kind == 'charge':
            self.d.polygon([at(size*.9, 0), at(-size*.5, size*.7), at(-size*.15, 0), at(-size*.5, -size*.7)], fill=c, outline=edge)
        elif kind == 'siege':
            r = size*.55
            self.d.rectangle((cx - r, cy - r, cx + r, cy + r), outline=c, width=2)
            self.d.line((cx - r, cy - r, cx + r, cy + r), fill=c, width=2)
            self.d.line((cx - r, cy + r, cx + r, cy - r), fill=c, width=2)
        elif kind == 'hero':
            pts = []
            for i in range(10):
                rr = size*(.75 if i % 2 == 0 else .32)
                t = -math.pi/2 + i*math.pi/5
                pts.append((cx + math.cos(t)*rr, cy + math.sin(t)*rr))
            self.d.polygon(pts, fill=(255, 230, 120, 255), outline=edge)

    def ring(self, x, y, r, colour, alpha=150):
        cx, cy = self.px(x, y)
        rr = r*self.k
        self.d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=colour + (alpha,), width=2)
        self.d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=colour + (28,))

    def label(self, x, y, text, size=18, fill=(255, 255, 255), anchor='mm'):
        self.d.text(self.px(x, y), text, font=font(size), fill=fill + (255,), anchor=anchor, stroke_width=3, stroke_fill=(0, 0, 0, 255))

    def finish(self, title, lines, legend=True):
        im = Image.alpha_composite(self.im, self.layer)
        pad = 360 if legend else 0
        out = Image.new('RGBA', (im.width + pad, im.height + 70), (18, 20, 26, 255))
        out.paste(im, (0, 70))
        d = ImageDraw.Draw(out)
        d.text((16, 18), title, font=font(30), fill=(255, 255, 255))
        if legend:
            x, y = im.width + 18, 90
            sample = Sheet.__new__(Sheet)
            sample.layer, sample.d, sample.k, sample.box = out, d, 1, (0, 0, 0, 0)
            sample.px = lambda a, b: (a, b)
            for kind, text in (('front', 'phalanx / front line'), ('melee', 'melee battalion'), ('archers', 'archers'),
                               ('charge', 'riders and beasts'), ('siege', 'siege engine'), ('hero', 'hero')):
                Sheet.unit(sample, x + 14, y + 12, math.pi/2, kind, (210, 210, 210), 12)
                d.text((x + 40, y + 2), text, font=font(17), fill=(230, 230, 230))
                y += 34
            y += 10
            for colour, text, dashed in (((200, 200, 200), 'advance', False), ((200, 200, 200), 'riders\' charge', True)):
                Sheet.arrow(sample, [(x + 2, y + 12), (x + 32, y + 12)], colour, 4, dashed=dashed)
                d.text((x + 40, y + 2), text, font=font(17), fill=(230, 230, 230))
                y += 34
            d.ellipse((x + 4, y + 2, x + 26, y + 24), outline=(240, 180, 90), width=2)
            d.text((x + 40, y + 2), f'siege range {RANGE}', font=font(17), fill=(230, 230, 230))
            y += 50
            for line in lines:
                d.text((x, y), line, font=font(17), fill=(240, 220, 160) if line[:1].isdigit() else (220, 220, 220))
                y += 26
        return out.convert('RGB')


def main(project_id):
    p = project.find(project_id)
    report = json.loads((p.build_dir/'report.json').read_text(encoding='utf-8'))
    out = LOCAL/'renders'/f'{p.id}-plan'
    out.mkdir(parents=True, exist_ok=True)
    width, height = 13750, 11250
    top_png = out/'top'/'whole.png'
    if not top_png.exists() or top_png.stat().st_mtime < p.map_file.stat().st_mtime:
        subprocess.run([str(ROOT/'local/venv/Scripts/mw.exe'), 'render', '--map', p.id, '--out', str(out/'top'),
                        '--size', f'{width//UNITS_PER_PX}x{height//UNITS_PER_PX}', '--view', 'whole', f'region=0,0,{width},{height}'],
                       check=True, capture_output=True)
    top = Image.open(top_png).convert('RGB')
    factions = {int(n): v['faction'] for n, v in report['players'].items()}
    wp = report['waypoints']
    m = Map(p.map_file.read_bytes())
    units = []
    for o in m.objects():
        props = {k: v for k, _, v in o['properties']}
        if props.get('objectLayer') != 'Armies':
            continue
        n = int(props['originalOwner'].split('/')[0].split('_')[1])
        units.append((n, o['template'], o['x'], o['y'], o['angle'], role(o['template'], factions[n], n), props['objectName']))
    jobs = report['units']
    import maps.nanduhirion_v2.map as layout                     # the half-turn and the mirror of the routes
    cx, cy = layout.CENTRE

    def route(n):
        west = n if n <= 4 else n - 4
        base = ROUTES.get(1 if west in (1, 4) else 2, [])
        pts = [(x, 2*cy - y) if west in (3, 4) else (x, y) for x, y in base]
        return [layout.twin(q) for q in pts] if n > 4 else pts

    def clash(n):
        a, b = wp[f'NB_Line_{n}'], wp[f'NB_Line_{OPPONENT[n]}']
        return ((a[0] + b[0])/2, (a[1] + b[1])/2)

    middle = lambda pts: (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))

    def path(n, frm, to):
        """From `frm` to `to` by the ramps between them (the ROUTES nearer `to`)."""
        return [frm] + [q for q in route(n) if math.dist(q, to) < math.dist(frm, to)] + [to]

    def draw(sheet, size, players, charge_arrows=True):
        for n in players:
            col = COLOURS[n]
            meet = clash(n)
            groups = {}                                            # the advancing groups: each to the fight by its ramps
            for m_, t, x, y, a, r, name in units:
                if m_ == n and jobs[name]['advances'] is not False:
                    groups.setdefault(jobs[name]['job'], []).append((x, y, r))
            for job, members in groups.items():
                foot = [(x, y) for x, y, r in members if r not in ('siege', 'charge')]
                if foot:
                    sheet.arrow(path(n, middle(foot), meet), col, max(5, int(size*.6)), alpha=150)
                riders = [(x, y) for x, y, r in members if r == 'charge']
                if charge_arrows and riders:                       # the riders: out of their lanes into the enemy's front
                    frm = middle(riders)
                    beyond = (meet[0] + (meet[0] - frm[0])*.25, meet[1] + (meet[1] - frm[1])*.25)
                    sheet.arrow(path(n, frm, beyond), col, 4, alpha=230, dashed=True)
                engines = [(x, y) for x, y, r in members if r == 'siege']
                if engines:                                        # the siege: to its battery, its range round it
                    bx, by = wp[f'NB_Battery_{n}']
                    sheet.ring(bx, by, RANGE, (240, 180, 90))
                    sheet.arrow(path(n, middle(engines), (bx, by)), (240, 180, 90), 3, alpha=200, dashed=True)
        for n, t, x, y, a, r, _ in units:
            if n in players:
                sheet.unit(x, y, a, r, COLOURS[n], size)

    # The timeline: when each job's groups go, then the waves.
    going = {}
    for u in jobs.values():
        if u['advances'] is not False and u['job'] != 'reserve':
            going.setdefault(u['advances'], {})[u['job']] = None
    clock = lambda t: f'{int(t)//60}:{int(t) % 60:02d}'
    timeline = ['0:00  armies drawn up'] + [f'{clock(t)}  {", ".join(going[t])} go' for t in sorted(going)]
    timeline += [f'{clock(FIRST_WAVE)}  first reinforcement waves']
    # Overview: the whole field, every army, the routes and the waves.
    s = Sheet(top, (0, 0, width, height), .5)
    draw(s, 7, range(1, 9), charge_arrows=False)
    for n in range(1, 9):
        for tag in ('', 'b'):
            rx, ry = wp[f'NB_Rally_{n}{tag}']
            s.arrow([(rx, ry), tuple(wp[f'NB_Line_{n}'])], COLOURS[n], 2, alpha=110, dashed=True)
    s.label(cx, cy - 300, 'ARENA', 26)
    s.label(cx, cy + 3500, 'NORTH PLATEAU', 22)
    s.label(cx, cy - 3500, 'SOUTH PLATEAU', 22)
    for n in range(1, 9):
        x, y = wp[f'NB_Line_{n}']
        s.label(x, y + (420 if y > cy else -420), f'{factions[n]} ({n})', 15)
    s.finish(f'{p.title}: the plan', timeline + ['', 'good (west): Men, Elves, Dwarves', 'evil (east): Mordor, Isengard,',
                                                 '  goblins, Angmar']).save(out/'overview.png')
    # The arena: the four armies, the ramps, the batteries.
    s = Sheet(top, (2500, 3700, 11300, 7400), 1.1)
    draw(s, 9, (1, 4, 5, 8))
    s.label(cx, cy - 60, 'INN', 18, (255, 230, 150))
    for n in (1, 4):
        r = route(n)[0]
        s.label(r[0] - 250, r[1] + (230 if r[1] > cy else -230), 'ramp', 15, (210, 170, 255))
    s.label(5300, 5650 + 260, 'balcony', 15, (210, 170, 255))
    s.finish('The arena: terraces, ramps and the bowl', timeline + ['', 'Men (1, 4) west, Angmar (8) and', 'Mordor (5) east: four battle',
             'lines filling the bowl, each', 'pair facing across no-man\'s', 'land, until they charge.']).save(out/'arena.png')
    # The north strip: the Elves and the goblins meet on the plateau.
    s = Sheet(top, (4300, 7400, 9500, 10900), 1.6)
    draw(s, 9, (2, 7))
    s.label(cx, 9100 + 900, 'NORTH PLATEAU', 20)
    s.finish('The north strip: Elves against the goblins', timeline + ['', 'Each army in its lowland at the', 'foot of the plateau\'s ramps;',
             'they climb and meet on top.', 'The south strip (Dwarves against', 'Isengard) mirrors it.']).save(out/'north.png')
    print(f'Plan sheets in {out}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'nanduhirion-v2-battle')
