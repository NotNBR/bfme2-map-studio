"""Cinematics: camera shots a map's own scripts play in the game, with the
interface hidden, so a scenario can be recorded as a film.

How ROTWK's cinematic maps do it (the game's `cin ...` maps and camera_demo,
read from local/profiles/rotwk/game/maps, 17 October 2026):

- A setup script hides the interface: HIDE_UI ("like letterbox mode, but
  with no border"), OPTIONS_SET_DRAWICON_UI_MODE(false) (no health bars or
  unit icons) and SET_CAMERA_CLIP_DEPTH_MULTIPLIER(10) (the far plane ten
  times out, so long shots draw their distance); some open
  CAMERA_LETTERBOX_BEGIN as well.
- A shot is a CameraAnimationList "look" animation: keys of the camera's
  position and, separately, of the point it looks at, in map units, each
  with Catmull-Rom interpolation (`catm`) and a field of view (0.8727 rad,
  50 degrees). MOVE_CAMERA_BY_ANIMATION plays one by name. Their keys step
  by 60 frames (59, 119, 179...) and a 329-frame animation gets a 12 s
  capture timer: FPS frames a second, which a ROTWK capture confirmed (a
  still 7.5 s into a 14 s orbit matched the renderer's view there, not the
  orbit's end; Battle of Nanduhirion (film), 17 October 2026).
- Timers (SET_MILLISECOND_TIMER, TIMER_EXPIRED) start the shots in turn.

    from mapworkshop.mapkit import cinematics
    film = cinematics.Film()
    film.shot('Opening', cinematics.move((0, 0, 2000), (3000, 0, 1200), target=(4000, 4000, 0), seconds=10))
    film.shot('Orbit', cinematics.orbit((4000, 4000, 0), 1200, 600, 200, 120, seconds=14))
    scripts = film.install(m, writer, start=0.5)     # the animations into m; the scripts to install

Shots follow each other back to back from `start` unless a shot names its
own start (seconds of game time). Scripts name timers unqualified, so they
are the running side's own (docs/game/scripts.md): install them on one side.
"""
import math

from mapworkshop.formats import sections

FPS = 30                        # camera animation frames per second
FOV = math.radians(50)          # the stock shots' field of view


def orbit(centre, radius, height, start, sweep, seconds, target=None, steps=None):
    """Keys circling `centre` (x, y, z) at `radius`, `height` above it, from
    `start` degrees (0 east, counter-clockwise) through `sweep` degrees,
    looking at `target` (the centre without one)."""
    steps = steps or max(2, int(abs(sweep)//15) + 1)
    cx, cy, cz = centre
    keys = []
    for i in range(steps + 1):
        a = math.radians(start + sweep*i/steps)
        keys.append((seconds*i/steps, (cx + radius*math.cos(a), cy + radius*math.sin(a), cz + height), target or centre))
    return keys


def move(camera, to, target, target_to=None, seconds=8, steps=4):
    """Keys gliding the camera along a straight line from `camera` to `to`
    (x, y, z), looking at `target`, which glides to `target_to` if given."""
    target_to = target_to or target
    lerp = lambda a, b, t: tuple(p + (q - p)*t for p, q in zip(a, b))
    return [(seconds*i/steps, lerp(camera, to, i/steps), lerp(target, target_to, i/steps)) for i in range(steps + 1)]


def animation(name, keys, fov=FOV):
    """A CameraAnimationList "look" animation from keys (seconds, camera
    (x, y, z), target (x, y, z))."""
    frames = [round(t*FPS) for t, _, _ in keys]
    if frames != sorted(set(frames)):
        raise ValueError(f'Shot {name}: its keys need rising times, at least 1/{FPS} s apart')
    return dict(type='look', name=name, num_frames=frames[-1] + 1, start_offset=0,
                camera_frames=[dict(frame=f, interpolation='catm', position=tuple(map(float, camera)), roll=0.0,
                                    fov_or_focal_parameter=float(fov)) for f, (_, camera, _) in zip(frames, keys)],
                target_frames=[dict(frame=f, interpolation='catm', look_at=tuple(map(float, target)))
                               for f, (_, _, target) in zip(frames, keys)])


class Film:
    """Shots and the interface settings of a film (see the module docstring)."""

    def __init__(self, prefix='Film', letterbox=False, icons=False, clip_depth=10.0, ui=False):
        """`ui`: keep the interface (no HIDE_UI), as for a test view of play rather than a film."""
        self.prefix, self.letterbox, self.icons, self.clip_depth, self.ui = prefix, letterbox, icons, clip_depth, ui
        self.shots = []                                   # (name, start or None, keys, fov)

    def shot(self, name, keys, start=None, fov=FOV):
        """Add a shot: keys (seconds from its start, camera, target); `start`
        in seconds of game time, else right after the shot before."""
        self.shots.append((name, start, keys, fov))
        return self

    def timeline(self, start=0.0):
        """(name, start, end) of each shot, in seconds of game time."""
        out, t = [], start
        for name, at, keys, _ in self.shots:
            t = t if at is None else at
            out.append((name, t, t + keys[-1][0]))
            t += keys[-1][0]
        return out

    def install(self, m, writer, start=0.0):
        """Add the shots to m's CameraAnimationList and return the scripts
        (script_writer) that hide the interface at once and play each shot
        at its time."""
        names = [f'{self.prefix}_{name}' for name, _, _, _ in self.shots]
        if len(set(names)) != len(names):
            raise ValueError('Shot names must be unique')
        anims = sections.read(m, 'CameraAnimationList')
        taken = {a['name'] for a in anims}
        if taken & set(names):
            raise ValueError(f'The map already has camera animations {sorted(taken & set(names))}')
        sections.write(m, 'CameraAnimationList', anims + [animation(n, keys, fov) for n, (_, _, keys, fov)
                                                          in zip(names, self.shots)])
        from mapworkshop.mapkit.script_writer import arg
        op = writer.operation
        text = lambda kind, value: arg(kind, text=value)
        setup = ([] if self.ui else [op('action', 'HIDE_UI')]) + [
            op('action', 'OPTIONS_SET_DRAWICON_UI_MODE', [arg(8, integer=int(self.icons))]),
            op('action', 'SET_CAMERA_CLIP_DEPTH_MULTIPLIER', [arg(1, real=float(self.clip_depth))])]
        if self.letterbox:
            setup.append(op('action', 'CAMERA_LETTERBOX_BEGIN'))
        scripts = []
        for k, (name, (_, t, _)) in enumerate(zip(names, self.timeline(start))):
            timer = f'{self.prefix}{k:02d}'
            setup.append(op('action', 'SET_MILLISECOND_TIMER', [text(4, timer), arg(1, real=max(float(t), .1))]))
            scripts.append(writer.script(name, [[op('condition', 'TIMER_EXPIRED', [text(4, timer)])]],
                                         [op('action', 'MOVE_CAMERA_BY_ANIMATION', [text(64, name)])]))
        return [writer.script(f'{self.prefix}_Setup', [[op('condition', 'CONDITION_TRUE')]], setup)] + scripts
