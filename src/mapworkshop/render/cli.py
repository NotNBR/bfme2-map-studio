"""Render map views headlessly from the installed game assets.

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
10 units per terrain cell. Previews are not native game captures.
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--map', required=True, help='Map project, stock map or .map file')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--view', nargs='+', action='append', default=[], metavar=('NAME', 'KEY=VALUE'),
                        help='Named view followed by camera settings')
    parser.add_argument('--views', type=Path, help='JSON file with named views')
    parser.add_argument('--top', action='store_true', help='Add a top view of the whole map')
    parser.add_argument('--top-scale', type=float, default=2.0, help='Top-view pixels per terrain cell')
    parser.add_argument('--size', default='1600x1200', help='Orbit-view image size')
    parser.add_argument('--no-objects', action='store_true')
    parser.add_argument('--normal-maps', choices=['auto', 'on', 'off'], default='auto',
                        help='Terrain normal maps; auto follows --lod (on at high)')
    parser.add_argument('--no-clouds', action='store_true',
                        help='Disable the cloud texture (on in game: UseCloudMap; frozen at time 0 here)')
    parser.add_argument('--no-shadows', action='store_true', help='Disable shadows')
    parser.add_argument('--vegetation-limits', action='store_true',
                        help="Keep only the game's first 1,200 trees and 2,000 shrubs (default: draw every one)")
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
    parser.add_argument('--border', action='store_true',
                        help='Draw the non-playable border (hidden in game, black by default)')
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

    from mapworkshop.render.engine import MapRenderer
    source = resolve_map(args.map)
    width, height = (int(v) for v in args.size.lower().split('x'))
    started = time.time()
    renderer = MapRenderer(source, objects=not args.no_objects,
                           normal_maps={'auto': None, 'on': True, 'off': False}[args.normal_maps],
                           clouds=not args.no_clouds, shadows=not args.no_shadows, lod=args.lod,
                           vegetation_limits=args.vegetation_limits, weather=args.weather, sun=args.sun)
    renderer.visible['weather'] = not args.no_weather
    if args.walkable:
        renderer.walkable_overlay()
        renderer.visible['walkable'] = True
    args.out.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, view in views:
        if isinstance(view, TopView):
            view.border = args.border
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


if __name__ == '__main__':
    raise SystemExit(main())
