"""Headless battles: a project's map played without graphics, its units traced
(mw battle).

Two engines:

- OpenBFME (run()): openbfme_peer, the engine's headless game process, hosts a
  skirmish on the project's build with its line-up (openbfme.net_slots) and
  plays a number of logic frames (5 a second). Its battle log (--battle-log)
  has a line every EVERY frames: per player its troops, those raised (on a
  wall, a ramp or a ladder), battalions and heroes; the hurt gates and wall
  pieces; the siege engines by deploy phase; the map scripts' counters. Under
  each line every object of the watched templates (--battle-watch): its name,
  position, health, AI state, target and deploy phase. The battle log is the
  studio fork's (GameClient/BattleLog in native/openbfme-godot).
- RotWK 2.01 (rotwk()): the original game under the studio's debugger
  (native.debugger, native.runtime), with breakpoints that log each
  battalion's destination adjustment (Pathfinder::adjustDestination RW
  0x6FE456: the destination before and after), optionally every candidate
  cell its ring search tries (RW 0x6F83EB) with the box check's result
  (checkDestination RW 0x6F1584), and the goal reservations of every unit
  (the unit record's updateGoal RW 0x8E24D3). Addresses are the verified
  2.01 executable's (docs/game/runtime.md).

parse() reads a battle log, summary() sums up how each watched template moved,
plot() draws the tracks over a top render of the map (tracks.png, battle.gif).
"""
import json
import math
import re
import socket
import statistics
import struct
import subprocess
from collections import defaultdict
from pathlib import Path

from mapworkshop.native import openbfme

HEAD = re.compile(r'^frame (\d+) \|(.*)$')
OBJECT = re.compile(r'^  (\S+) (\S*) \((-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\) hp (-?[\d.]+)( dead)? state (\d+) victim (\S+) phase (-?\d+)')


def out_dir(project):
    return openbfme.HOME/'battles'/project.id


def default_watch(project):
    """The templates of the units a project's map places for its players (owned by Player_N)."""
    from mapworkshop.formats.map import Map
    m = Map(project.map_file.read_bytes())
    found = []
    for o in m.objects():
        owner = next((v for k, _, v in o['properties'] if k == 'originalOwner'), '') or ''
        if owner.startswith('Player_') and o['template'] not in found and not o['template'].startswith('*'):
            found.append(o['template'])
    return found


# OpenBFME ------------------------------------------------------------------------------
def run(project, frames=300, every=5, watch=None, uber=True, out=None, progress=print):
    """Play `frames` logic frames of the project's map headless in OpenBFME and write battle.log
    (a line every `every` frames, the `watch` templates traced; default: the map's own units),
    report.json and peer.log into `out`. Returns the folder."""
    out = Path(out or out_dir(project))
    out.mkdir(parents=True, exist_ok=True)
    _, _, env, key = openbfme.prepare(project, progress)
    watch = list(watch) if watch else default_watch(project)
    slots = []
    for spec in openbfme.net_slots(project).split(';'):     # kind:Faction:start:team, as the peer's kind,Faction,start,team
        slots += ['--slot', ','.join(spec.split(':'))]
    peer = openbfme.peer()
    if not peer.exists():
        raise RuntimeError(f'{peer} is missing: delete {openbfme.BUILD/"stamp.txt"} so the next run builds it')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    args = [str(peer), '--host', str(port), '--bind', '127.0.0.1', '--map', key, '--seed', '1',
            *slots, *(['--uber'] if uber else []), '--frames', str(frames), '--battle-log', str(out/'battle.log'),
            '--battle-every', str(every), '--report', str(out/'report.json')]
    if watch:
        args += ['--battle-watch', ','.join(watch)]
    progress(f'Playing {frames} logic frames ({frames/5:.0f} s) of {project.title} headless in OpenBFME'
             f' ({"Uber" if uber else "Faithful"} profile), {len(watch)} template(s) traced...')
    with open(out/'peer.log', 'w', encoding='utf-8') as log:
        result = subprocess.run(args, env=env, cwd=openbfme.HOME, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode or not (out/'battle.log').exists():
        raise RuntimeError(f'openbfme_peer ended with exit {result.returncode}; see {out/"peer.log"}')
    (out/'battle.json').write_text(json.dumps(dict(map=project.id, frames=frames, every=every, watch=watch, uber=uber), indent=1),
                                   encoding='utf-8')
    return out


def parse(text):
    """A battle log's text: {'frames': [(frame, summary)], 'objects': {name: {'template', 'track':
    [(frame, x, y, z, health, dead, state, victim, phase)]}}}. Unnamed objects are keyed by template#n."""
    frames, objects, frame, unnamed = [], {}, None, defaultdict(int)
    for line in text.splitlines():
        if m := HEAD.match(line):
            frame = int(m[1])
            frames.append((frame, m[2].strip()))
            unnamed.clear()
        elif (m := OBJECT.match(line)) and frame is not None:
            template, name = m[1], m[2]
            if not name:
                unnamed[template] += 1
                name = f'{template}#{unnamed[template]}'
            entry = objects.setdefault(name, dict(template=template, track=[]))
            entry['track'].append((frame, float(m[3]), float(m[4]), float(m[5]), float(m[6]), bool(m[7]), int(m[8]), m[9], int(m[10])))
    return dict(frames=frames, objects=objects)


def summary(log, moved=5.0):
    """Per watched template: how many, how many never moved (no step over `moved` between two
    lines), when they started and stopped moving (median frames), how far they went on average
    (x east, y north) and how much longer their paths were than their displacements."""
    groups = defaultdict(list)
    for o in log['objects'].values():
        groups[o['template']].append(o['track'])
    rows = []
    for template, tracks in groups.items():
        starts, stops, dx, dy, paths, disps, still = [], [], [], [], 0.0, 0.0, 0
        for t in tracks:
            steps = [(b[0], math.hypot(b[1] - a[1], b[2] - a[2])) for a, b in zip(t, t[1:])]
            moving = [f for f, d in steps if d > moved]
            if not moving:
                still += 1
                continue
            starts.append(moving[0])
            stops.append(moving[-1])
            dx.append(t[-1][1] - t[0][1])
            dy.append(t[-1][2] - t[0][2])
            paths += sum(d for _, d in steps)
            disps += math.hypot(dx[-1], dy[-1])
        rows.append(dict(template=template, count=len(tracks), never_moved=still,
                         start=statistics.median(starts) if starts else None, stop=statistics.median(stops) if stops else None,
                         dx=statistics.mean(dx) if dx else 0.0, dy=statistics.mean(dy) if dy else 0.0,
                         backwards=sum(1 for v in dy if v < -50), detour=paths / disps if disps else None))
    return sorted(rows, key=lambda r: r['template'])


def plot(project, log, out, size=1100, gif=True):
    """tracks.png (every track, an x where it ended dead) and battle.gif (the positions line by line)
    over a top render of the project's map; one colour per template. Returns the paths."""
    from PIL import Image, ImageDraw
    from mapworkshop.formats.map import Map
    from mapworkshop.formats.terrain import playable_extent
    from mapworkshop.render.godot import top_picture
    bg = top_picture(project.map_file, size)
    width, height = playable_extent(Map(project.map_file.read_bytes()).heightmap())
    scale = bg.width / width
    bg = Image.blend(bg.convert('RGB'), Image.new('RGB', bg.size, (0, 0, 0)), 0.35)
    W, H = bg.size
    px = lambda x, y: (x*scale, H - y*scale)
    palette = [(230, 40, 40), (60, 140, 255), (255, 200, 0), (255, 0, 255), (0, 220, 120), (255, 140, 0), (160, 100, 255), (255, 255, 255)]
    colour = {t: palette[i % len(palette)] for i, t in enumerate(sorted({o['template'] for o in log['objects'].values()}))}

    def legend(d):
        for i, (t, c) in enumerate(colour.items()):
            d.rectangle([10, 10 + 16*i, 22, 22 + 16*i], fill=c)
            d.text((28, 9 + 16*i), t, fill=(255, 255, 255))

    out = Path(out)
    img = bg.copy()
    d = ImageDraw.Draw(img)
    for o in log['objects'].values():
        c, xy = colour[o['template']], [px(p[1], p[2]) for p in o['track']]
        if len(xy) > 1:
            d.line(xy, fill=c, width=1)
        ex, ey = xy[-1]
        if o['track'][-1][5]:
            d.line([ex - 3, ey - 3, ex + 3, ey + 3], fill=c, width=2)
            d.line([ex - 3, ey + 3, ex + 3, ey - 3], fill=c, width=2)
        else:
            d.ellipse([ex - 2, ey - 2, ex + 2, ey + 2], fill=c)
    legend(d)
    img.save(out/'tracks.png')
    paths = [out/'tracks.png']
    if gif and log['frames']:
        at = defaultdict(list)
        for o in log['objects'].values():
            for p in o['track']:
                at[p[0]].append((o['template'], p[1], p[2], p[5]))
        frames = []
        for frame, text in log['frames']:
            img = bg.copy()
            d = ImageDraw.Draw(img)
            for t, x, y, dead in at[frame]:
                X, Y = px(x, y)
                d.ellipse([X - 2, Y - 2, X + 2, Y + 2], fill=(110, 110, 110) if dead else colour[t])
            legend(d)
            d.rectangle([0, H - 18, W, H], fill=(0, 0, 0))
            d.text((8, H - 16), f'frame {frame}  {frame/5:5.1f} s   {text[:150]}', fill=(255, 255, 255))
            frames.append(img.quantize(colors=128))
        frames[0].save(out/'battle.gif', save_all=True, append_images=frames[1:], duration=150, loop=0, optimize=True)
        paths.append(out/'battle.gif')
    return paths


# RotWK 2.01 ----------------------------------------------------------------------------
BASE = 0x400000
ADJUST_DESTINATION, ADJUST_CELL, CHECK_DESTINATION, UPDATE_GOAL = 0x6FE456, 0x6F83EB, 0x6F1584, 0x8E24D3


def rotwk(project, frames=5, cells=False, progress=print):
    """Start the project's map in RotWK 2.01 (headless, under the debugger) and log until logic frame
    `frames`: every battalion's destination adjustment {'frame', 'id', 'at', 'before', 'after'} (with
    `cells`: the candidate cells [x, y, result] and box checks [x, y, result] of its ring search), and
    every goal reservation {'frame', 'id', 'horde', 'at', 'goal', 'angle'}. Object ids are the game's."""
    from mapworkshop.config import PROFILE
    from mapworkshop.native import debugger, runtime
    if PROFILE != 'rotwk':
        raise RuntimeError('mw battle --rotwk needs the ROTWK profile (mw config profile rotwk)')
    game = runtime.start(project, 'Low', headless=True, progress=progress)
    adjustments, goals, state = [], [], dict(armed=False, current=None)
    f3 = lambda va: struct.unpack('<3f', game.read(va, 12))
    horde = lambda obj: bool((t := game.u32(obj + 4)) and game.read(t + 0x115, 1)[0] & 0x20)   # KindOf HORDE, as updateGoal RW 0x8E257A tests it

    def returned(record, read):
        def done(game, tid, ctx):
            read(record, ctx)
            return False
        return done

    def on_adjust(game, tid, ctx):
        ret, obj, _loco, dest = struct.unpack('<4I', game.read(ctx.esp, 16))   # thiscall: the object, the locomotor set, Coord3D *dest
        if not horde(obj):
            return True
        entry = dict(frame=game.logic()[0], id=game.u32(obj + 0x74), at=f3(obj + 0x38)[:2], before=f3(dest)[:2], cells=[], checks=[])
        state['current'] = entry

        def finish(e, ctx):
            e.update(after=f3(dest)[:2], result=ctx.eax & 0xFF)
            adjustments.append(e)
            state['current'] = None
        game.arm(ret - game.base, returned(entry, finish))
        return True

    def on_candidate(kind):
        def handler(game, tid, ctx):
            entry = state['current']
            if entry is not None:
                words = struct.unpack('<4I', game.read(ctx.esp, 16))
                record = list(words[1:3] if kind == 'cells' else words[2:4])            # (x, y): RW 0x6F83EB's arguments; RW 0x6F1584's after the object
                entry[kind].append(record)
                game.arm(words[0] - game.base, returned(record, lambda r, ctx: r.append(ctx.eax & 0xFF)))
            return True
        return handler

    def on_goal(game, tid, ctx):
        _ret, pos, angle, _layer = struct.unpack('<4I', game.read(ctx.esp, 16))     # thiscall on the unit record ([ecx] the object): goal, angle, layer
        obj = game.u32(ctx.ecx)
        goals.append(dict(frame=game.logic()[0], id=game.u32(obj + 0x74), horde=horde(obj), at=f3(obj + 0x38)[:2], goal=f3(pos)[:2],
                          angle=struct.unpack('<f', struct.pack('<I', angle))[0]))
        return True

    def tick(game):
        frame, mode = game.logic()
        if mode != debugger.SKIRMISH or frame is None:
            return None
        if not state['armed']:
            game.arm(ADJUST_DESTINATION - BASE, on_adjust)
            game.arm(UPDATE_GOAL - BASE, on_goal)
            if cells:
                game.arm(ADJUST_CELL - BASE, on_candidate('cells'))
                game.arm(CHECK_DESTINATION - BASE, on_candidate('checks'))
            state['armed'] = True
        return 'done' if frame >= frames else None

    progress(f'Tracing RotWK on {project.title} until logic frame {frames}...')
    result = game.run(600, tick, tick_every=0.05)
    if not state['armed']:
        raise RuntimeError('RotWK did not reach its skirmish: ' + debugger.describe(result))
    return dict(adjustments=adjustments, goals=goals)


def formations(trace, reach=150.0):
    """Per battalion of a RotWK trace: its first goal reservation and its members' goals relative to it
    (the members are the non-battalion ids between it and the next battalion, as the game creates them,
    that stood within `reach` of it)."""
    first = {}
    for g in trace['goals']:
        first.setdefault(g['id'], g)
    hordes = sorted(i for i, g in first.items() if g['horde'])
    out = []
    for h, nxt in zip(hordes, hordes[1:] + [None]):
        gx, gy = first[h]['goal']
        hx, hy = first[h]['at']
        members = [first[i] for i in sorted(first) if not first[i]['horde'] and i > h and (nxt is None or i < nxt)
                   and math.hypot(first[i]['at'][0] - hx, first[i]['at'][1] - hy) <= reach]
        out.append(dict(id=h, at=first[h]['at'], goal=(gx, gy),
                        members=[(round(m['goal'][0] - gx, 2), round(m['goal'][1] - gy, 2)) for m in members]))
    return out
