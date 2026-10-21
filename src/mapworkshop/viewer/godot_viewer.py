"""The Godot viewer: `mw view MAP --godot` shows a map in the studio's own Godot
project (viewer/godot/, docs/godot-viewer/plan.md) on OpenBFME's library,
which draws the map as the game does, units animated.

Python prepares what the viewer needs and starts it:

- a project's build goes into OpenBFME's user maps folder
  (native/openbfme.py, install_user_map()), where the library opens it by
  name; a stock map opens from the game's archives;
- the scene, local/openbfme/scenes/<map>/: scene.json (the map, the camera,
  the marks as they are drawn, what to capture and check, the companion's
  port) and surface.f32, the visible surface as the studio's viewer has it
  (terrain raised to standing water, render.engine's surface_at) on the
  height map's samples, on which the viewer picks the ground;
- the assembled project, local/openbfme/viewer/ (openbfme.assemble()).

While the viewer is open, the companion (viewer/godot_link.py) keeps the
marks, the marks panel and Copy for agent, and reloads the map when it is
built again.

A view (`--view`, the key=value words of `mw render --view`) is resolved here
as mw render resolves it (on the terrain's own heights), and the viewer puts
its camera at the eye and target it gets, so the camera projects a map point
onto the pixel mw render does: `--probe X,Y[,Z]` prints it from each. The Edit
camera then orbits from that view (viewer.camera.Camera.aim's orbit).
"""

import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np

from mapworkshop import project
from mapworkshop.config import GAME_DATA, PROFILE, RENDERS
from mapworkshop.formats.map import Map
from mapworkshop.formats.terrain import height_at, playable_extent
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.mapkit.lines import inside
from mapworkshop.native import openbfme
from mapworkshop.render.camera import parse_view
from mapworkshop.render.photo import fov_from_focal
from mapworkshop.viewer import godot_link
from mapworkshop.viewer import marks as marklib

SCENES = openbfme.HOME/'scenes'
SIZE = (1600, 1000)
FOV = 50.0            # degrees across the width, as the studio viewer's Edit camera (viewer.camera.Camera)


class Heights:
    """A height map's samples in map units with `border` samples around the playable area (formats.terrain.height_at)."""

    def __init__(self, heights, border, playable):
        self.heights, self.border, self.playable = heights, border, playable

    def height_at(self, x, y):
        return height_at(self.heights, self.border, x, y)


class Surface(Heights):
    """The visible surface on the height map's samples: terrain heights, raised to each standing water area's level
    where the area covers a sample (render.engine's surface_at, sampled); `terrain` keeps the terrain's own, on which
    mw render resolves views."""

    def __init__(self, m):
        hm = m.heightmap()
        terrain = (hm['elevations']*0.0390625).astype(np.float32)
        super().__init__(terrain.copy(), hm['border'], playable_extent(hm))
        self.terrain = Heights(terrain, hm['border'], self.playable)
        ys, xs = np.indices(self.heights.shape)
        xs, ys = (xs - self.border)*10.0, (ys - self.border)*10.0
        for area in records(m, 'StandingWaterAreas'):
            level = float(area['water_height'])
            covered = inside(area['points'], xs, ys) & (self.heights < level)
            self.heights[covered] = level


def source(name):
    """(map file, the name the viewer opens it by, whether it is a user map, its project or None) for a project, a
    stock map or a .map file of either. A stock map opens from OpenBFME's RotWK archives, so its heights are those of
    the map drawn only under the RotWK profile."""
    path = project.map_path(name)
    owner = project.for_map_file(path)
    if owner is not None:
        return path, owner.native_name, True, owner
    if path.resolve().is_relative_to((GAME_DATA/'maps').resolve()):
        if PROFILE != 'rotwk':
            raise RuntimeError("the Godot viewer opens stock maps from RotWK's archives: use the RotWK profile "
                               "(mw --profile rotwk view ...)")
        return path, path.stem.lower(), False, None
    raise RuntimeError(f"{path} is neither a map project's build nor a stock map: the Godot viewer opens only those")


def resolve(view, terrain, size):
    """A view (key=value words or a render.camera view) resolved as mw render resolves it on the terrain's heights:
    eye, target, the field of view across the width, roll, near and far, the Edit camera's orbit around the target,
    and the view-projection matrix it projects with. The lens keys only frame it (a focal length's field of view):
    the Godot viewer has no depth of field yet."""
    view = parse_view(view.split()) if isinstance(view, str) else view
    if view.kind != 'orbit':
        raise RuntimeError('the Godot viewer takes orbit views (target=X,Y ...), not top views')
    camera = view.resolve(terrain, size[0]/size[1])
    eye, target = np.asarray(camera['eye'], float), np.asarray(camera['target'], float)
    offset = eye - target
    distance = float(np.linalg.norm(offset))
    return dict(eye=eye.tolist(), target=target.tolist(),
                fov=fov_from_focal(view.focal, camera['sensor']) if view.focal else float(view.fov),
                roll=float(view.roll or 0.0), near=float(camera['near']), far=float(camera['far']),
                # viewer.camera.Camera.aim: orbit the target from the eye
                orbit=dict(x=float(target[0]), y=float(target[1]), distance=distance,
                           heading=math.degrees(math.atan2(-offset[0], -offset[1])),
                           elevation=math.degrees(math.asin(max(-1.0, min(1.0, offset[2]/(distance or 1.0)))))),
                view_projection=camera['view_projection'])


def pixel(view_projection, point, size):
    """Where a map point lands in a picture of `size` (pixels, origin top left), as mw render projects it."""
    clip = view_projection @ np.array([*point, 1.0])
    ndc = clip[:3]/clip[3]
    return float((ndc[0] + 1)/2*size[0]), float((1 - ndc[1])/2*size[1])


def scene(name, view=None, probes=(), screenshot=None, size=SIZE, check=False, port=None, drive=None):
    """Write the scene for map `name` (a project, stock map or .map file); (scene.json, its contents, the project or
    None, the Surface). A probe without a z stands on the terrain."""
    map_path, native, user_map, owner = source(name)
    surface = Surface(Map(map_path.read_bytes()))
    folder = SCENES/native
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'surface.f32').write_bytes(surface.heights.astype('<f4').tobytes())
    data = dict(map=native, user_map=user_map, title=owner.title if owner else native, map_path=str(map_path),
                user_map_folder=str(openbfme.user_maps()) if user_map else '', size=list(size),
                surface=dict(file='surface.f32', columns=surface.heights.shape[1], rows=surface.heights.shape[0],
                             border=surface.border, cell=10.0),
                playable=list(surface.playable), fov=FOV, marks=godot_link.marks_state(marklib.Marks(map_path), surface),
                check=check, screenshot=str(Path(screenshot).resolve()) if screenshot else '',
                screenshots=str(RENDERS/'godot'), port=port, drive=drive or [])
    if view:
        camera = resolve(view, surface.terrain, size)
        data['view'] = {k: v for k, v in camera.items() if k != 'view_projection'}
        points = [list(p) if len(p) == 3 else [*p, float(surface.terrain.height_at(*p))] for p in probes]
        data['probes'] = [dict(point=p, pixel=pixel(camera['view_projection'], p, size)) for p in points]
    (folder/'scene.json').write_text(json.dumps(data, indent=1), encoding='utf-8')
    return folder/'scene.json', data, owner, surface


def run(name, view=None, probes=(), screenshot=None, size=SIZE, check=False, progress=print, timeout=None,
        drive=None):
    """Prepare and start the viewer on map `name`. With a screenshot or check, wait for it and return
    (exit code, the viewer's output lines); otherwise serve it as its companion until it closes and return its exit
    code. `drive` (tests): scripted input the viewer plays headless, with the companion, before it closes."""
    started = time.perf_counter()
    openbfme.assets(progress)
    gui, console = openbfme.assemble(progress)
    interactive = not (screenshot or check)
    link = godot_link.Link() if interactive else None
    path, data, owner, surface = scene(name, view, probes, screenshot, size, check, link.port if link else None, drive)
    if owner is not None:
        openbfme.install_user_map(owner)
    env = openbfme.environment([])
    headless = (check and not screenshot) or (drive and not any(step['do'] == 'screenshot' for step in drive))
    args = [str(gui if interactive and not drive else console), *(['--headless'] if headless else []),
            '--path', str(openbfme.VIEWER), '--', f'--scene={path}']
    progress(f'Opening {data["title"]} in the Godot viewer ({time.perf_counter() - started:.1f} s to prepare)...')
    if not interactive:
        result = subprocess.run(args, env=env, cwd=openbfme.HOME, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=timeout or 600)
        return result.returncode, (result.stdout + result.stderr).splitlines()

    def rescene():
        """The build changed: into the user maps folder again, and the scene (its surface) written again."""
        if owner is not None:
            openbfme.install_user_map(owner)
        return scene(name, size=size, port=link.port)[3]

    # driven (tests): the viewer's output kept out of the caller's, and a hung viewer stopped after `timeout`
    quiet = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) if drive else {}
    process = subprocess.Popen(args, env=env, cwd=openbfme.HOME, **quiet)
    companion = godot_link.Companion(Path(data['map_path']), surface, rescene if owner else None, progress)
    try:
        companion.serve(link, process)
        return process.wait(timeout=(timeout or 600) if drive else None)
    except subprocess.TimeoutExpired:
        process.kill()
        raise RuntimeError(f'the Godot viewer did not finish its scripted input within {timeout or 600} s')
    finally:
        link.close()


def main(args):
    """mw view MAP --godot [--view WORDS] [--probe X,Y[,Z] ...] [--screenshot PATH] [--size WxH]."""
    size = tuple(int(v) for v in args.size.lower().split('x'))
    probes = [tuple(float(v) for v in p.split(',')) for p in (args.probe or [])]
    if probes and not args.view:
        raise SystemExit('--probe needs --view: the points are projected through that view')
    name = args.map or args.map_option
    try:
        if not (args.screenshot or probes):
            return run(name, args.view, size=size)
        code, lines = run(name, args.view, probes, args.screenshot, size, check=not args.screenshot)
    except (LookupError, RuntimeError, ValueError) as error:
        raise SystemExit(f'mw view --godot: {error}')
    for line in lines:
        if line.startswith('VIEWER'):
            print(line)
    return code
