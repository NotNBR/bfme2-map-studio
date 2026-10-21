"""Render map views without starting the game (docs/guide/rendering.md).

Each --view is a name followed by key=value camera settings:

  mw render --map greywater-marches --out DIR \\
      --view base5  target=5500,1090 distance=1800 elevation=40 heading=0 \\
      --view bridge target=11900,3850 distance=900 elevation=30 heading=300 \\
      --view sw     region=0,0,4000,3000 \\
      --top

Orbit view keys (only target is required):
  target=X,Y[,Z]   point to look at; Z defaults to the terrain height there
  distance=1500    camera distance from the target, world units
  elevation=45     degrees above the horizon (90 = straight down)
  heading=0        direction the camera faces: 0 N, 90 E, 180 S, 270 W
  fov=50           horizontal field of view, degrees
  eye=X,Y,Z        explicit camera position (replaces distance/elevation/heading)

Top view keys:
  region=X0,Y0,X1,Y1   orthographic, north up; rendered at --top-scale px/cell

--top adds a top view of the whole map. The non-playable border is black,
as in game; --border draws it. A --views JSON file holds
{"views": {"name": {"target": [x, y], "distance": 1500, ...}, ...}}.
World units: X east, Y north, origin at the playable south-west corner,
10 units per terrain cell.

--engine picks what draws the pictures (the guide says what each does):
  godot   the Godot viewer on OpenBFME's library, unseen (the default; godot())
  studio  the studio's Python renderer (render.engine)
  game    the game itself, through mw capture (game())
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

from mapworkshop.render.camera import TopView, parse_view, view_from_dict


def resolve_map(name):
    """A .map file, a map project or a stock map (see mapworkshop.project.map_path)."""
    from mapworkshop.project import map_path
    try:
        return map_path(name)
    except LookupError as error:
        raise SystemExit(str(error))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='mw render', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--map', required=True, help='Map project, stock map or .map file')
    parser.add_argument('--out', required=True, type=Path, help='Folder for the PNGs and render.json (created if missing)')
    parser.add_argument('--view', nargs='+', action='append', default=[], metavar=('NAME', 'KEY=VALUE'),
                        help='Named view followed by camera settings')
    parser.add_argument('--views', type=Path, help='JSON file with named views')
    parser.add_argument('--top', action='store_true', help='Add a top view of the whole map')
    parser.add_argument('--top-scale', type=float, default=2.0, help='Top-view pixels per terrain cell')
    parser.add_argument('--size', default='1600x1200', help='Orbit-view image size')
    parser.add_argument('--no-objects', action='store_true', help='Leave out every placed object: terrain and water alone')
    parser.add_argument('--normal-maps', choices=['auto', 'on', 'off'], default='auto',
                        help='Terrain normal maps; auto follows --lod (on at high)')
    parser.add_argument('--no-clouds', action='store_true',
                        help='Disable the cloud texture (on in game: UseCloudMap; frozen at time 0 here)')
    parser.add_argument('--no-shadows', action='store_true', help='Disable shadows')
    parser.add_argument('--vegetation-limits', action='store_true',
                        help="Keep only the game's first 1,200 trees and 2,000 shrubs (default: draw every one)")
    parser.add_argument('--editor-markers', action='store_true',
                        help='Also draw the WorldBuilder-only models the game never shows, such as the AI farm sites')
    parser.add_argument('--no-units', action='store_true',
                        help='Leave out the units (default: hordes as their members, each unit in its idle pose)')
    parser.add_argument('--time', type=float, default=0.0,
                        help='Animation time in seconds (water ripples, clouds, falling rain and snow)')
    parser.add_argument('--weather', default=None,
                        help="Weather preset over the map's own: clear, haze, rain, snow, dusk")
    parser.add_argument('--sun', default=None,
                        help='Sun over the weather: ember, copper, blood, sulphur, ash, violet (mapkit.weather.SUNS)')
    parser.add_argument('--no-weather', action='store_true',
                        help="Ignore map.ini Weather (fog, falling rain or snow)")
    parser.add_argument('--lod', choices=['low', 'medium', 'high'], default='medium',
                        help='Game detail level to imitate (GameLOD.ini); default medium, the launcher default')
    parser.add_argument('--grid', action='store_true', help='Overlay a 100-unit world grid')
    parser.add_argument('--walkable', action='store_true',
                        help='Overlay locally computed walkability (no game launch)')
    parser.add_argument('--flow', action='store_true',
                        help='Draw arrows along each river strip pointing downstream; its first cross-section '
                             'green, its last red')
    parser.add_argument('--border', action='store_true',
                        help='Draw the non-playable border (hidden in game, black by default)')
    parser.add_argument('--engine', choices=['godot', 'studio', 'game'], default='godot',
                        help='What draws the pictures: the Godot viewer (default), the studio renderer or the game')
    args = parser.parse_args(argv)

    views = []
    try:
        for name, *words in args.view:
            views.append((name, parse_view(words)))
        if args.views:
            data = json.loads(args.views.read_text())
            views += [(name, view_from_dict(spec)) for name, spec in data['views'].items()]
    except ValueError as error:
        parser.error(str(error))
    if args.top:
        views.append(('top', TopView(border=args.border)))
    if not views:
        parser.error('Request at least one --view, --views file or --top')
    names = [n for n, _ in views]
    if len(set(names)) != len(names):
        parser.error('View names must be unique')
    for _, view in views:
        if isinstance(view, TopView):
            view.border = args.border
    width, height = (int(v) for v in args.size.lower().split('x'))
    if args.engine == 'godot':
        return godot(parser, args, views, (width, height))
    if args.engine == 'game':
        return game(parser, args, views)

    from mapworkshop.render.engine import MapRenderer
    source = resolve_map(args.map)
    started = time.time()
    renderer = MapRenderer(source, objects=not args.no_objects,
                           normal_maps={'auto': None, 'on': True, 'off': False}[args.normal_maps],
                           clouds=not args.no_clouds, shadows=not args.no_shadows, lod=args.lod,
                           vegetation_limits=args.vegetation_limits, weather=args.weather, sun=args.sun,
                           editor_markers=args.editor_markers, units=not args.no_units)
    renderer.visible['weather'] = not args.no_weather
    if args.walkable:
        renderer.walkable_overlay()
        renderer.visible['walkable'] = True
    renderer.visible['flow'] = args.flow
    args.out.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, view in views:
        if isinstance(view, TopView):
            size = renderer.top_size(view, args.top_scale)
        else:
            size = (width, height)
        path = renderer.save(renderer.render(view, size, grid=args.grid, border=args.border, time=args.time), args.out/(name+'.png'))
        outputs.append(dict(name=name, file=path.name, size=list(size), view=view.describe()))
    report = dict(map=str(source), map_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  renderer='bfme2-map-workshop headless preview (not a native capture)',
                  options=renderer.options,
                  assets=dict(missing_textures=sorted(set(renderer.report['missing_textures'])),
                              missing_models=renderer.report['missing_models'],
                              unreadable_models=renderer.report.get('unreadable_models', {}),
                              objects_drawn=renderer.report['objects_drawn'],
                              texture_size_errors=renderer.report.get('texture_size_errors', [])),
                  vegetation=renderer.report.get('vegetation'), fx_materials=renderer.report.get('fx_materials'),
                  effects=renderer.report.get('effects'),
                  shadows=dict(volumes=renderer.report.get('shadow_volumes'), tree_decals=renderer.report.get('shadow_decals', 0)),
                  water=renderer.report.get('water'), weather=renderer.report.get('weather') if renderer.visible['weather'] else None,
                  outputs=outputs, seconds=round(time.time()-started, 2))
    (args.out/'render.json').write_text(json.dumps(report, indent=2)+'\n')
    for error in report['assets']['texture_size_errors']:
        print(f"WARNING: {error['name']} is {error['pixels'][1]}px but declared as {error['declared_cells']} "
              f"cells ({error['declared_cells']*64}px); the game will not load it correctly")
    print(json.dumps(dict(out=str(args.out), images=[o['file'] for o in outputs], seconds=report['seconds'])))
    return 0


# Options the Godot viewer cannot honour: (option, whether it is set, why).
STUDIO_ONLY = (('--lod', lambda a: a.lod != 'medium', 'OpenBFME has no detail levels'),
               ('--normal-maps', lambda a: a.normal_maps != 'auto', 'OpenBFME has no switch for them'),
               ('--editor-markers', lambda a: a.editor_markers, 'OpenBFME does not draw them'))


def godot(parser, args, views, size):
    """The pictures from the Godot viewer (render.godot.render), with render.json beside them. It needs
    OpenBFME built (the first run builds it) and the game files it plays from (English RotWK 2.01, BFME2 1.06)."""
    import sys
    from mapworkshop.render.godot import render
    for option, used, why in STUDIO_ONLY:
        if used(args):
            parser.error(f'{option} needs --engine studio: {why}')
    source = resolve_map(args.map)
    started = time.time()
    switches = dict(objects=not args.no_objects, fog=not args.no_weather, clouds=not args.no_clouds, grid=args.grid,
                    border=args.border, walkable=args.walkable, flow=args.flow)
    preview = {k: v for k, v in dict(weather=args.weather, sun=args.sun).items() if v}
    if args.vegetation_limits:
        preview['limits'] = True
    if args.no_units:
        preview['units'] = False
    try:
        outputs = render(args.map, views, args.out, size, args.top_scale, switches, preview, args.time,
                         progress=lambda line: print(line, file=sys.stderr))
    except (LookupError, RuntimeError, ValueError, OSError) as error:
        raise SystemExit(f'mw render: {error} (--engine studio renders without OpenBFME)')
    report = dict(map=str(source), map_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  renderer='OpenBFME (Godot viewer), not a native capture', engine='godot',
                  options=dict(switches, **preview, time=args.time), outputs=outputs, seconds=round(time.time()-started, 2))
    (args.out/'render.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(out=str(args.out), images=[o['file'] for o in outputs], seconds=report['seconds'])))
    return 0


# What the game draws as it is: options --engine game cannot honour, as for STUDIO_ONLY.
GAME_FIXED = (('--size', lambda a: a.size != '1600x1200', 'the game draws at its own resolution'),
              ('--grid, --border, --walkable, --flow', lambda a: a.grid or a.border or a.walkable or a.flow,
               'the game draws no overlays'),
              ('--weather, --sun, --no-weather', lambda a: a.weather or a.sun or a.no_weather,
               'the game shows the map\'s own weather'),
              ('--no-objects, --no-units, --no-shadows, --no-clouds', lambda a: a.no_objects or a.no_units
               or a.no_shadows or a.no_clouds, 'the game draws everything'),
              ('--lod, --normal-maps, --time', lambda a: a.lod != 'medium' or a.normal_maps != 'auto' or a.time,
               'the game runs at Medium from its start'))


def game_shot(name, view, terrain):
    """An orbit view as mw capture's cinematic shot: the ground point it looks at, its distance, its pitch below
    the horizon and the heading it faces."""
    import math
    camera = view.resolve(terrain, 16/9)               # the eye and target, as the other engines place them
    offset = camera['eye'] - camera['target']
    distance = float(math.sqrt((offset**2).sum()))
    return dict(name=name, x=float(camera['target'][0]), y=float(camera['target'][1]), distance=distance,
                pitch=math.degrees(math.asin(offset[2]/distance)),
                heading=math.degrees(math.atan2(-offset[0], -offset[1])) % 360)


def game(parser, args, views):
    """The pictures from the game itself (native.capture): each orbit view as a cinematic shot of the project's
    build, at the game's own resolution and field of view, HUD included."""
    from mapworkshop import project
    from mapworkshop.formats.map import Map
    from mapworkshop.native.capture import capture
    from mapworkshop.render.godot import Surface
    for option, used, why in GAME_FIXED:
        if used(args):
            parser.error(f'{option}: not with --engine game: {why}')
    try:
        owner = project.for_map_file(project.map_path(args.map))
    except LookupError as error:
        raise SystemExit(f'mw render: {error}')
    if owner is None:
        parser.error('--engine game renders a map project\'s build (mw capture)')
    terrain = Surface(Map(owner.map_file.read_bytes())).terrain
    shots = []
    for name, view in views:
        if isinstance(view, TopView):
            parser.error(f'{name}: --engine game has no top views')
        shot = game_shot(name, view, terrain)
        if shot['pitch'] <= 0:
            parser.error(f'{name}: --engine game needs a view from above the target (the game\'s camera)')
        shots.append(shot)
    started = time.time()
    report = capture(owner, shots, args.out, progress=lambda line: None)
    report.update(engine='game', seconds=round(time.time()-started, 2))
    (args.out/'render.json').write_text(json.dumps(report, indent=2, default=str)+'\n')
    print(json.dumps(dict(out=str(args.out), images=[f'{name}.png' for name, _ in views], seconds=report['seconds'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
