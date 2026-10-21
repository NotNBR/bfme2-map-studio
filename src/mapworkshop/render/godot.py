"""Pictures of a map by the viewer (viewer/godot/) on OpenBFME's library, and
the scene it reads: mw render's pictures (render), the build's minimap and
mw battle's plots (top_picture), mw item's (shoot), and what `mw view` opens.

- A project's build goes into OpenBFME's user maps folder
  (native/openbfme.py, install_user_map()), where the library opens it by
  name; a stock map opens from RotWK's archives; any other map is copied into
  the user maps folder for the viewer (loose_map), as a Preview is (preview_map:
  the map with a weather preset or a sun, which the library draws as its file
  and map.ini say). remove_copies takes the copies out again.
- The scene, local/openbfme/scenes/<map>/: scene.json (the map, the camera,
  the shots to take, the View switches, what to check) and surface.f32, the
  visible surface (terrain raised to standing water) on the height map's
  samples, on which the viewer picks the ground.
- Pictures are shots (shoot): the viewer opens the map once on a hidden desktop
  of its own (debugger.run_hidden), so no window shows, and saves each view in
  turn; the walkability and the river strips come worked out in the scene.

A view (`--view`, the key=value words of `mw render --view`) is resolved here
(resolve) on the terrain's own heights, and the viewer puts its camera at the
eye and target it gets, so pixel() says where a map point lands. A view with
an aperture or an exposure is taken in Photo mode with its lens.
"""

import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np

from mapworkshop import project
from mapworkshop.config import GAME_DATA, PROFILE, RENDERS
from mapworkshop.formats.map import Map
from mapworkshop.formats.terrain import Heights
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.mapkit.lines import inside
from mapworkshop.native import openbfme
from mapworkshop.render.camera import parse_view
from mapworkshop.render.photo import fov_from_focal

SCENES = openbfme.HOME/'scenes'
SIZE = (1600, 1000)
# Preview's choice when it shows the map as it is: the map's own weather and the weather's own sun, every object the
# map places drawn (not only what the game's tree and shrub buffers hold), the units too
OWN = dict(weather='map', sun='own', limits=False, units=True)
PREVIEW = ' studio preview'               # the name of a preview copy in the user maps folder: '<map> studio preview'
LOOSE = ' studio map'                     # and of a map that is neither a project's build nor in RotWK's archives
FOV = 50.0            # degrees across the width: the Edit camera's (orbit_camera.gd)


class Surface(Heights):
    """The visible surface on the height map's samples: terrain heights, raised to each standing water area's level
    where the area covers a sample; `terrain` keeps the terrain's own, on which
    mw render resolves views."""

    def __init__(self, m):
        self.terrain = Heights.of(m)
        super().__init__(self.terrain.heights.copy(), self.terrain.border, self.terrain.playable)
        ys, xs = np.indices(self.heights.shape)
        xs, ys = (xs - self.border)*10.0, (ys - self.border)*10.0
        for area in records(m, 'StandingWaterAreas'):
            level = float(area['water_height'])
            covered = inside(area['points'], xs, ys) & (self.heights < level)
            self.heights[covered] = level


def source(name):
    """(map file, the name the viewer opens it by, whether it is a user map, its project or None) for a project, a
    stock map or any .map file. A project's build is the user map its build installs; a stock map opens from
    OpenBFME's RotWK archives under the RotWK profile; any other map (a BFME2 stock map, a loose file) is copied
    into the user maps folder as '<map> studio map' (loose_map), removed again with the copies (remove_copies)."""
    path = project.map_path(name)
    owner = project.for_map_file(path)
    if owner is not None:
        return path, owner.native_name, True, owner
    if PROFILE == 'rotwk' and path.resolve().is_relative_to((GAME_DATA/'maps').resolve()):
        return path, path.stem.lower(), False, None
    return path, loose_map(path), True, None


def loose_map(path):
    """A copy of the map at `path` in the user maps folder, with the map.ini and map.str beside it; its name."""
    copy = path.stem.lower() + LOOSE
    folder = openbfme.user_maps()/copy
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, folder/f'{copy}.map')
    for other in ('map.ini', 'map.str'):
        if path.with_name(other).is_file():
            shutil.copyfile(path.with_name(other), folder/other)
    return copy


def resolve(view, terrain, size):
    """A view (key=value words or a render.camera view) resolved as mw render resolves it on the terrain's heights:
    eye, target, the field of view across the width, roll, near and far, the Edit camera's orbit around the target,
    the lens (render.photo's settings: focal, aperture, focus, ev; with an aperture or an exposure the viewer opens in
    Photo mode) and the view-projection matrix it projects with."""
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
                # orbit_camera.gd's aim: orbit the target from the eye
                orbit=dict(x=float(target[0]), y=float(target[1]), distance=distance,
                           heading=math.degrees(math.atan2(-offset[0], -offset[1])),
                           elevation=math.degrees(math.asin(max(-1.0, min(1.0, offset[2]/(distance or 1.0)))))),
                photo={k: (float(v) if v is not None else None) for k, v in camera['photo'].items()},
                view_projection=camera['view_projection'])


def pixel(view_projection, point, size):
    """Where a map point lands in a picture of `size` (pixels, origin top left), as mw render projects it."""
    clip = view_projection @ np.array([*point, 1.0])
    ndc = clip[:3]/clip[3]
    return float((ndc[0] + 1)/2*size[0]), float((1 - ndc[1])/2*size[1])


def preview_map(map_path, name, weather='map', sun='own', limits=False, units=True):
    """A copy of the map as Preview and the View switches show it, in the user maps folder (mapkit.weather): a
    weather preset's world weather and lighting, and its Weather block in place of the map's in map.ini; a sun's
    light rig over it, and its fog after; the sky they bring on the map's WaterReflectionSkydome objects (a copy can
    only change these templates). `limits`: without the trees and shrubs past the game's buffers
    (mapkit.vegetation.past_buffers); `units` False: without the units. The map's map.str and solo.ini go with it.
    Returns the copy's name."""
    from mapworkshop.mapkit import vegetation, weather as presets
    m = Map(map_path.read_bytes())
    weather, sun = (None if weather == 'map' else weather), (None if sun == 'own' else sun)
    if weather:
        presets.apply_weather(m, weather)
    if sun:
        presets.apply_sun_to_map(m, sun)
    sky = presets.sky(weather, sun)
    if sky or limits or not units:
        objects = m.objects()
        for o in objects:
            if sky and o['template'].lower().startswith('waterreflectionskydome_'):
                o['template'] = presets.skydome_template(sky)
        left_out = set()
        if limits or not units:
            from mapworkshop.assets.library import GameAssets
            assets = GameAssets.shared()
            if limits:
                left_out |= vegetation.past_buffers(objects, assets)
            if not units:
                left_out |= {o['index'] for o in objects
                             if (r := assets.template_model(o['template'])) and r['unit'] and not r['tree']}
        m.set_objects([o for o in objects if o['index'] not in left_out])
    ini = map_path.with_name('map.ini')
    text = ini.read_bytes().decode('latin-1') if ini.is_file() else ''      # byte for byte, whatever the code page
    if weather:
        text = presets.without_weather(text) + '\n' + presets.ini_block(weather)
    if sun:
        text += '\n' + presets.sun_ini(sun)                                # the last Weather block's keys win
    copy = name + PREVIEW
    folder = openbfme.user_maps()/copy
    folder.mkdir(parents=True, exist_ok=True)
    (folder/f'{copy}.map').write_bytes(m.encode())
    (folder/'map.ini').write_bytes(text.encode('latin-1'))
    for other in ('map.str', 'solo.ini'):
        if map_path.with_name(other).is_file():
            shutil.copyfile(map_path.with_name(other), folder/other)
    return copy


def falling(map_path, preview, playable, folder):
    """The rain or snow the map's weather lets fall (render.weather: weather.ini's Weather under map.ini's, or under
    the Preview's weather and sun), for the viewer's falling.gd: its settings, the game's emitters as falling.f32 and
    the drop's texture as falling.png in `folder`. None when nothing falls."""
    from PIL import Image
    from mapworkshop.assets.library import GameAssets
    from mapworkshop.mapkit import weather as presets
    from mapworkshop.render import weather
    ini = map_path.with_name('map.ini')
    local = ini.read_text(encoding='cp1252', errors='replace') if ini.is_file() else ''
    if preview['weather'] != 'map':
        local = presets.ini_block(preview['weather'])
    sun = presets.sun_ini(preview['sun']) if preview['sun'] != 'own' else ''
    assets = GameAssets.shared()
    w = weather.parse(assets.ini_text('weather.ini'), local, sun)
    emitters = weather.emitters(w, *playable)
    image = assets.image(w['snowtexture']) if len(emitters) else None
    if image is None:
        return None
    Image.fromarray(weather.bleed_alpha(image), 'RGBA').save(folder/'falling.png')
    (folder/'falling.f32').write_bytes(emitters.astype('<f4').tobytes())
    box, speed = float(max(int(w['snowboxheight']), 1)), float(w['snowspeed'])
    return dict(emitters='falling.f32', texture='falling.png', count=len(emitters), size=w['snowquadsize'], box=box,
                speed=speed, amplitude=w['snowamplitude'],
                frequency=[w['snowfrequencyscalex'], w['snowfrequencyscaley']], xy_speed=list(w['snowxyspeed']),
                drift_per_cycle=[v*box/(speed or 1.0) for v in w['snowxyspeed']])


def remove_copies():
    """The preview copies and the loose maps' copies out of the user maps folder (they would show in OpenBFME's
    Skirmish list)."""
    for kind in (PREVIEW, LOOSE):
        for folder in openbfme.user_maps().glob('*' + kind):
            shutil.rmtree(folder, ignore_errors=True)


def scene(name, view=None, *, probes=(), shots=(), size=SIZE, check=False, port=None, drive=None, views=None,
          preview=None, fps='60', extra=None, m=None, marks=None):
    """Write the scene for map `name` (a project, stock map or .map file); (scene.json, its contents, the project or
    None, the Surface). A probe without a z stands on the terrain. `preview` ({weather, sun}, OWN's keys) opens a
    preview copy of the map (preview_map) instead of the map. `shots`: [{path, view (a render.camera view, None for
    the start's), size, or for a top view without one `scale` (pixels per cell)}], resolved here on the terrain.
    `extra` goes into the scene as it is (mw render's overlays); `m` is the map read already; `marks(map_path,
    surface)` gives the marks the viewer draws (viewer.godot_link.marks_state), none without it."""
    map_path, native, user_map, owner = source(name)
    surface = Surface(m or Map(map_path.read_bytes()))
    folder = SCENES/native
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'surface.f32').write_bytes(surface.heights.astype('<f4').tobytes())
    preview = dict(OWN, **(preview or {}))
    shown = native
    if preview != OWN:
        shown, user_map = preview_map(map_path, native, **preview), True
    data = dict(map=shown, user_map=user_map, title=owner.title if owner else native, map_path=str(map_path),
                preview=preview,
                user_map_folder=str(openbfme.user_maps()) if user_map else '', size=list(size),
                surface=dict(file='surface.f32', columns=surface.heights.shape[1], rows=surface.heights.shape[0],
                             border=surface.border, cell=10.0),
                playable=list(surface.playable), fov=FOV, check=check, screenshots=str(RENDERS/'godot'), port=port, drive=drive or [], views=views or {},
                fps=fps, **(extra or {}))
    data['falling'] = falling(map_path, preview, surface.playable, folder)
    if marks is not None:
        data['marks'] = marks(map_path, surface)
    if view:
        camera = resolve(view, surface.terrain, size)
        data['view'] = {k: v for k, v in camera.items() if k != 'view_projection'}
        points = [list(p) if len(p) == 3 else [*p, float(surface.terrain.height_at(*p))] for p in probes]
        data['probes'] = [dict(point=p, pixel=pixel(camera['view_projection'], p, size)) for p in points]
    data['shots'] = [shot_of(s, surface.terrain, data.get('view')) for s in shots]
    (folder/'scene.json').write_text(json.dumps(data, indent=1), encoding='utf-8')
    return folder/'scene.json', data, owner, surface


def shot_of(shot, terrain, start):
    """A shot as the viewer takes it: {path, size} and its resolved view, or a top view's region (centre, width,
    height) seen from above the highest ground, as render.camera.TopView resolves it; its background colour, another
    map to show and the time it is taken at (seconds after the map was built), when it has them."""
    from mapworkshop.render.camera import TopView
    view, out = shot.get('view'), dict(path=str(Path(shot['path']).resolve()))
    out.update({k: shot[k] for k in ('background', 'map', 'time') if shot.get(k) is not None})
    if isinstance(view, TopView):
        x0, y0, x1, y1 = view.bounds(terrain)
        out['size'] = list(shot.get('size') or (round((x1-x0)/10*shot['scale']), round((y1-y0)/10*shot['scale'])))
        out['top'] = dict(center=[(x0+x1)/2, (y0+y1)/2], width=x1-x0, height=y1-y0,
                          z=float(view.resolve(terrain)['eye'][2]))
        return out
    out['size'] = list(shot['size'])
    if view is not None:
        camera = resolve(view, terrain, shot['size'])
        out['view'] = {k: v for k, v in camera.items() if k != 'view_projection'}
    elif start is not None:
        out['view'] = start
    return out


def prepare(name, view=None, **options):
    """A map ready for the viewer: its build in the user maps folder (a project's) and its scene written (scene()'s
    options); what scene() returns. The companion prepares the map again for a new build, another map or another
    preview."""
    prepared = scene(name, view, **options)
    if prepared[2] is not None:
        openbfme.install_user_map(prepared[2])
    return prepared


def unseen(args, folder, headless, timeout=None):
    """Run the viewer without showing it: headless (it draws nothing), or on a hidden desktop when it draws
    pictures. Returns (exit code, its output lines)."""
    from mapworkshop.native.debugger import run_hidden
    env = openbfme.environment([])
    if headless:
        result = subprocess.run(args, env=env, cwd=openbfme.HOME, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=timeout or 600)
        return result.returncode, (result.stdout + result.stderr).splitlines()
    log = folder/'viewer.log'
    log.unlink(missing_ok=True)
    code = run_hidden([args[0], '--log-file', str(log), *args[1:]], env, openbfme.HOME, timeout or 600)
    return code, log.read_text(encoding='utf-8', errors='replace').splitlines() if log.is_file() else []


def shoot(name, shots, size=SIZE, switches=None, preview=None, extra=None, m=None, progress=print):
    """Take `shots` of map `name` (as shot_of takes them) in one run of the viewer on a hidden desktop, the marks
    left out; the shots as the scene resolved them. The caller removes any copies it made (remove_copies)."""
    switches = dict(dict(marks=False), **(switches or {}))      # the marks are the viewer's, not the map's
    openbfme.assets(progress)
    gui, console = openbfme.assemble(progress)
    path, data = prepare(name, shots=shots, size=size, views=switches, preview=preview, extra=extra, m=m)[:2]
    progress(f'Rendering {len(shots)} picture(s) of {data["title"]} in the Godot viewer...')
    code, lines = unseen([str(console), '--path', str(openbfme.VIEWER), '--', f'--scene={path}'], path.parent, False)
    failed = [line for line in lines if line.startswith('VIEWER failed')]
    if code != 0 or failed:
        raise RuntimeError('; '.join(failed) or f'the Godot viewer ended with {code}: see {path.parent/"viewer.log"}')
    return data['shots']


def render(name, views, out, size=(1600, 1200), top_scale=2.0, switches=None, preview=None, time=0.0,
           progress=print):
    """mw render on the Godot viewer: each (name, view) as out/<name>.png (shoot), `time` seconds after the map was
    built (the units' animations, the overlays, the falling weather). `switches`: the View switches mw render has
    (objects, fog, grid, border, walkable, flow, and terrain); the walkability and the river strips are worked out
    here. Returns [{name, file, size, view}]."""
    from mapworkshop.assets.library import GameAssets
    from mapworkshop.render.camera import TopView
    switches = dict(switches or {})
    remove_copies()
    out = Path(out).resolve()                     # the viewer runs elsewhere
    out.mkdir(parents=True, exist_ok=True)
    try:
        map_path, native = source(name)[:2]
        m = Map(map_path.read_bytes())
        extra = {}
        if switches.get('walkable'):
            progress('Computing walkability...')
            (SCENES/native).mkdir(parents=True, exist_ok=True)
            extra['walkable'] = walkability(m, GameAssets(), map_path.with_name('map.ini'), SCENES/native/'walkable.png')
        if switches.get('flow'):
            extra['flow'] = flow_strips(m)
        shots = [dict(path=out/f'{n}.png', view=v, size=None if isinstance(v, TopView) else size, scale=top_scale,
                      time=time) for n, v in views]
        resolved = shoot(name, shots, size, switches, preview, extra, m, progress)
    finally:
        remove_copies()
    return [dict(name=n, file=f'{n}.png', size=shot['size'], view=v.describe()) for (n, v), shot in zip(views, resolved)]


def top_picture(name, size):
    """The whole map seen from above, `size` pixels along its longer side (the build's minimap, mw battle's plots):
    a PIL image, from one shot of the viewer."""
    import tempfile
    from PIL import Image
    from mapworkshop.render.camera import TopView
    width, height = Surface(Map(project.map_path(name).read_bytes())).playable
    scale = size / max(width, height) * 10                     # pixels per cell
    with tempfile.TemporaryDirectory(dir=SCENES.parent) as folder:
        render(name, [('top', TopView())], folder, top_scale=scale, progress=lambda line: None)
        with Image.open(Path(folder)/'top.png') as picture:
            return picture.convert('RGB')


def walkability(m, assets, map_ini, path):
    """The walkability estimate of map `m` (mapkit.pathing, mapkit.walkable), its image saved at `path`: the viewer's
    walkable message {image, size, cut_off}."""
    from PIL import Image
    from mapworkshop.assets.models import ModelCache
    from mapworkshop.mapkit import pathing, walkable
    text = map_ini.read_text(encoding='cp1252', errors='replace') if map_ini.is_file() else ''
    grid = pathing.compute(m, assets=getattr(assets, '_base', assets), map_ini=text, models=ModelCache(assets))
    result = walkable.analyse(grid, m)
    rgba = np.ascontiguousarray(walkable.overlay(result))
    Image.fromarray(rgba, 'RGBA').save(path)
    h, w = rgba.shape[:2]
    return dict(type='walkable', image=str(path), size=[w*walkable.CELL, h*walkable.CELL],
                cut_off=len(result['cut_off']))


def flow_strips(m):
    """The map's river strips for the flow arrows, every one as OpenBFME draws them: vertices [x, y, z, u, v] flat
    (u across the strip from 0 to 1, v along it), triangles flat, length in v (render.rivers.strips)."""
    from mapworkshop.render import rivers
    return [dict(vertices=vertices[:, [0, 1, 2, 4, 5]].round(2).ravel().tolist(),
                 triangles=triangles.ravel().tolist(), length=float(vertices[-1, 5]))
            for _, (vertices, triangles) in rivers.strips(m)]
