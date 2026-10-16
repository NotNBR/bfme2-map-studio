"""Glacial Crossroads: alpine terrain around a sixteen-site movement layout.

The user's SVG defines sixteen numbered sites and sixty connections. High
corner bases 1/4/7/10 overlook eight middle terraces; 13-16 stand just above
a broad central solid-ice field. Broken summit chains, descending buttresses,
snow-filled gullies and irregular cirques frame gently winding passes.
Two deep, impassable ruptures split the central sheet into connected fighting
spaces. Snowy woods, moraine boulders and ruined waystations frame the passes.
Eight marked locations carry four signal fires and four capturable inns.
One normal-scale fortress at site 13 provides a size reference; no economy
or combat balance is authored. The sixteen-site scaffold
is for terrain review; native sixteen-player support is not established.
The build checks final pad elevations and route clearance/connectivity.
"""
from copy import deepcopy
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from mapworkshop.formats import sections
from mapworkshop.formats.water import standing_water
from mapworkshop.mapkit.blank import add_object, create, set_heights, set_materials, starts, terrain_cell_sizes
from mapworkshop.mapkit.cliffs import steep_cells
from mapworkshop.mapkit.checks.strategy import at, distance_field
from mapworkshop.mapkit.pathing import compute as walking_grid
from mapworkshop.mapkit.lines import polyline_distance
from mapworkshop.mapkit.relief import distance_to
from mapworkshop.mapkit.walkable import PASSABLE, categories, flood
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block
from .design import (BASES, BORDER, CENTRE, EXTENT, HEIGHT, HIGH, ICE, LOW, MID,
                     PAD_HALF, RIDGES, ROUTES, SCALE, WIDTH)

from .terrain import landscape, PALETTE, CLIFF
from .features import CAPTURE_LINKS, CHECKPOINTS, CREVASSES
from .scenery import checkpoint_sites, populate


def validate(t):
    """Measure final terrain rather than merely connectivity of drawn axes."""
    if not np.isfinite(t['z']).all() or t['z'].max() > 65535*.0390625:
        raise ValueError('Terrain exceeds the native finite height range')
    cut = (slice(BORDER, BORDER+HEIGHT), slice(BORDER, BORDER+WIDTH))
    walk = ~t['blocked'][cut]
    centre = (round(CENTRE[1]/10), round(CENTRE[0]/10))
    clearance = distance_to(~walk)*10
    safe = flood(walk & (clearance >= 70) & (t['slope'][cut] <= .65), [centre])
    gy, gx = np.mgrid[:HEIGHT, :WIDTH]
    alternate = flood(walk & (np.hypot(gx*10-CENTRE[0], gy*10-CENTRE[1]) > 2850*SCALE),
                      [(round(BASES[0]['y']/10), round(BASES[0]['x']/10))])
    route_checks = []
    for route in ROUTES+CAPTURE_LINKS:
        # Check every cell in the swept width of THIS connection. Global
        # flood-fill alone can hide a severed route behind an alternate path.
        p = np.asarray(route['points'])
        margin = route['width']/2+20
        lo = np.maximum(np.floor((p.min(axis=0)-margin)/10).astype(int), 0)
        hi = np.minimum(np.ceil((p.max(axis=0)+margin)/10).astype(int)+1, [WIDTH, HEIGHT])
        ry, rx = np.mgrid[lo[1]:hi[1], lo[0]:hi[0]]
        d, _ = polyline_distance(p, rx*10., ry*10., reach=margin)
        # Inside the ice basin these are entry routes into an open field.
        # Armies skirt the two authored ruptures rather than following the
        # old conceptual straight rays through them. The whole approach
        # width outside the ice remains protected; entrances are checked below.
        crop = (slice(lo[1], hi[1]), slice(lo[0], hi[0]))
        core = (d <= route['width']/2) & ~t['ice'][cut][crop]
        grade = t['slope'][cut][crop]
        bad = core & (~walk[crop] | (grade > .65))
        if np.any(bad):
            row, col = np.argwhere(bad)[0]
            raise ValueError(f'{route["name"]}: blocked/steep ground at '
                             f'{(col+lo[0])*10},{(row+lo[1])*10}; '
                             f'grade {grade[row,col]:.3f}; maximum {grade[core].max():.3f}')
        route_checks.append(dict(name=route['name'], clear_width=route['width'],
                                 max_slope=round(float(grade[core].max()), 3)))
    sites = []
    for base in BASES:
        row, col = round(base['y']/10), round(base['x']/10)
        half = round(PAD_HALF/10)
        pad = t['z'][row+BORDER-half:row+BORDER+half+1, col+BORDER-half:col+BORDER+half+1]
        if not np.allclose(pad, base['height'], atol=.001):
            raise ValueError(f'Base {base["number"]} is not level at its authored elevation')
        if not safe[row, col]:
            raise ValueError(f'Base {base["number"]} has no gentle route with 70-unit clearance')
        if not alternate[row, col]:
            raise ValueError(f'Base {base["number"]} loses its route around the ice field')
        sites.append(dict(**base, pad_size=[2*PAD_HALF, 2*PAD_HALF], connected=True))
    ice_heights = t['z'][t['ice']]
    sheet = t['ice'] & (t['rupture'] == 0)
    ice_slopes = t['slope'][sheet]
    if float(t['z'].min()) < 0 or ice_heights.max() >= LOW:
        raise ValueError('The glacier must stay in the native range below the inner bases')
    if t['blocked'][sheet].any() or ice_slopes.max() > .60:
        raise ValueError('Solid ice outside the two ruptures must remain gently traversable')
    # Check each mouth into the ice, including the full route width. Merely
    # reaching the centre by a different mountain route would hide a dead end.
    entrances = t['route_core'][cut] & t['ice'][cut] & (distance_to(~t['ice'][cut])*10 < 110)
    if not np.all(safe[entrances]):
        raise ValueError('An ice-field entrance has lost its gentle route around the ruptures')
    ruptures = []
    for index, feature in enumerate(CREVASSES, 1):
        mask = t['rupture'] == index
        if not mask.any() or not t['blocked'][mask].all():
            raise ValueError(f'{feature["name"]} is not an explicitly blocked obstacle')
        rows, cols = np.nonzero(mask)
        crop = (slice(rows.min(), rows.max()+1), slice(cols.min(), cols.max()+1))
        seed = (int(rows[0]-rows.min()), int(cols[0]-cols.min()))
        if flood(mask[crop], [seed]).sum() != mask.sum():
            raise ValueError(f'{feature["name"]} has detached blocked fragments')
        bed = float(t['z'][mask].min())
        rim = float(t['z'][mask].max())
        if ICE-bed < 95 or rim-bed < 135:
            raise ValueError(f'{feature["name"]} is too shallow')
        ruptures.append(dict(**feature, measured_floor=bed, measured_rim=rim,
                             depth_below_sheet=ICE-bed, rim_to_floor=rim-bed))
    return dict(stage='alpine landscape with twin ruptures and scenery', bases=sites,
                horizontal_scale=SCALE, extent=[EXTENT, EXTENT],
                reference_routes=len(ROUTES), all_sites_connected=True,
                capture_approach_links=len(CAPTURE_LINKS),
                reference_ridges=len(RIDGES),
                every_approach_clear_across_full_width=True, route_checks=route_checks,
                all_ice_entrances_connected_with_70_clearance=True,
                all_sites_connected_with_70_clearance_and_slope_065=True,
                all_sites_connected_without_central_ice=True,
                height_range=[float(t['z'].min()), float(t['z'].max())],
                glacier=dict(height_range=[float(ice_heights.min()), float(ice_heights.max())],
                             solid_sheet_maximum_slope=float(ice_slopes.max()),
                             solid_sheet_walkable=True, crevasses=ruptures),
                walkable_percent=round(float(walk.mean()*100), 1),
                native_gameplay_tested=False, sixteen_player_support_verified=False)


def plan(t):
    """Numbered height-and-route plan sampled from the actual terrain."""
    cut = (slice(BORDER, BORDER+HEIGHT), slice(BORDER, BORDER+WIDTH))
    z = t['z'][cut]
    colors = np.array([(99, 176, 215), (156, 197, 204), (186, 198, 193),
                       (207, 210, 217), (247, 248, 249)])
    pixels = np.stack([np.interp(z, [ICE, LOW, MID, HIGH, 2500], colors[:, k]) for k in range(3)], -1)
    dy, dx = np.gradient(z, 10)
    light = np.clip((.94+.34*(-dx+dy))/np.sqrt(1+.35*(dx*dx+dy*dy)), .38, 1.15)
    pixels *= light[..., None]
    image = Image.fromarray(np.uint8(np.clip(pixels[::-1], 0, 255))).resize((1400, 1400))
    sheet = Image.new('RGB', (1480, 1570), '#172633')
    sheet.paste(image, (40, 85))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 19)
    bold = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 26)
    draw.text((40, 18), 'GLACIAL CROSSROADS / ALPINE TERRAIN', font=bold, fill='white')
    draw.text((40, 52), f'{EXTENT:,.0f} x {EXTENT:,.0f} units | 16 base sites | high mountain terrain | north up', font=font, fill='#bed4df')
    def point(x, y):
        return 40+x/EXTENT*1400, 85+(EXTENT-y)/EXTENT*1400
    for route in ROUTES:
        draw.line([point(*p) for p in route['points']], fill='#c98450' if route['main'] else '#567f8f', width=3 if route['main'] else 2)
    for feature in CREVASSES:
        draw.line([point(*p) for p in feature['points']], fill='#18303b', width=8)
    for site in CHECKPOINTS:
        px, py = point(*site['position'])
        color = '#e5b975' if site['template'] == 'Inn' else '#b44c38'
        draw.ellipse((px-9, py-9, px+9, py+9), fill=color, outline='white', width=2)
        draw.text((px+14, py), site['name'], font=font, fill='white', anchor='lm')
    for base in BASES:
        px, py = point(base['x'], base['y'])
        color = '#5c466f' if base['height'] == HIGH else '#526c58' if base['height'] == MID else '#236c85'
        draw.rounded_rectangle((px-35, py-32, px+35, py+32), radius=10, fill=color, outline='white', width=2)
        draw.text((px, py-10), f'{base["number"]:02}', font=bold, fill='white', anchor='mm')
        draw.text((px, py+16), f'{base["height"]:g}', font=font, fill='white', anchor='mm')
    draw.text(point(*CENTRE), 'TWIN RUPTURES\nopen ice crossing', font=font, fill='#183f58', anchor='mm', align='center')
    draw.text((40, 1501), 'HIGH  1 / 4 / 7 / 10 : 1650       MID  outer bases : 850       LOW  13-16 : 220       ICE : 120', font=font, fill='white')
    draw.text((40, 1531), 'Solid ice terrain. Narrow main and side passes. Terrain draft; native gameplay and balance not tested.', font=font, fill='#bed4df')
    return sheet


def site_scaffold(m):
    """Local sixteen-site preview scaffold, not an extension of native play."""
    sides = sections.read(m, 'SidesList')
    template = sides['players'][-1]
    for i in range(9, 17):
        side = deepcopy(template)
        side['properties'] = [(k, t, f'Player_{i}' if k in ('playerName', 'playerDisplayName') else v)
                              for k, t, v in side['properties']]
        sides['players'].append(side)
    sections.write(m, 'SidesList', sides)
    teams = sections.read(m, 'Teams')
    for i in range(9, 17):
        teams.append([('teamName', 3, f'teamPlayer_{i}'), ('teamOwner', 3, f'Player_{i}'), ('teamIsSingleton', 0, 1)])
    sections.write(m, 'Teams', teams)
    for name in ('MPPositionList', 'LibraryMapLists', 'PlayerScriptsList'):
        records = sections.read(m, name)
        records.extend(deepcopy(records[-1]) for _ in range(8))
        sections.write(m, name, records)


def rupture_water(m, t):
    """Still meltwater below the ice; dry banks clip each buried polygon."""
    level = 35  # 85 units below the solid sheet, just above the uneven beds.
    areas, measurements = [], []
    for index, feature in enumerate(CREVASSES, 1):
        rows, cols = np.nonzero(t['rupture'] == index)
        r0, r1 = int(rows.min())-2, int(rows.max())+3
        c0, c1 = int(cols.min())-2, int(cols.max())+3
        crop = (slice(r0, r1), slice(c0, c1))
        wet = t['z'][crop] < level
        if not wet.any() or np.any(wet & (t['rupture'][crop] != index)):
            raise ValueError(f'{feature["name"]}: meltwater escapes its rupture')
        x0, x1 = (c0-BORDER)*10, (c1-1-BORDER)*10
        y0, y1 = (r0-BORDER)*10, (r1-1-BORDER)*10
        areas.append(dict(id=index, name=f'{feature["name"]} meltwater',
                          layer='RuptureWater', uv_speed=.008, additive=0,
                          bump_texture='WaterRippleBump.tga', sky_texture='SkyEnv.tga',
                          points=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                          water_height=level, shader='wtr_Riv_pond.W3D',
                          depth_colors='LUTDepthTint.tga'))
        measurements.append(dict(name=feature['name'], water_height=level,
                                 below_sheet=ICE-level,
                                 maximum_depth=float(level-t['z'][crop][wet].min()),
                                 wet_samples=int(wet.sum()), confined_to_rupture=True))
    m.chunk('StandingWaterAreas').data = standing_water(areas)
    return measurements


def build(b):
    print('Shaping alpine ranges, 16 cirques and 60 connected mountain passages...', flush=True)
    t = b.cached(landscape)
    report = validate(t)
    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title,
               description=b.project.description, player_count=8, experimental_large=True)
    site_scaffold(m)
    set_heights(m, t['z'])
    report['scenery'] = populate(m, t)
    report['checkpoints'] = checkpoint_sites(m, t)
    set_materials(m, PALETTE, t['materials'], blocked=t['blocked'],
                  cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True,
                  cliffs=(t['materials'] == CLIFF) & steep_cells(t['z']), cliff_scale=3)
    report['glacier']['meltwater'] = rupture_water(m, t)
    starts(m, [(base['x'], base['y']) for base in BASES])
    # The four asset views show the entrance ramp on local +x. Rotate it
    # south toward the ice. Keep the game's default scale for comparison.
    reference_base = next(base for base in BASES if base['number'] == 13)
    add_object(m, 'DwarvenFortressCitadel', reference_base['x'], reference_base['y'],
               angle=-np.pi/2, layer='ScaleReference',
               extra=[('objectName', 3, 'Base13_ScaleReference')])
    report['scale_reference'] = dict(base=13, template='DwarvenFortressCitadel',
                                     scale=1., x=reference_base['x'], y=reference_base['y'])
    add_sky(m, b.project.weather, EXTENT, EXTENT, BORDER*10)
    apply_weather(m, b.project.weather,
                  sun=dict(ambient=(.30, .34, .40), diffuse=(.92, .91, .87), direction=(.55, -.62, -.56)),
                  fill=dict(ambient=(0, 0, 0), diffuse=(.17, .20, .26), direction=(-.6, .4, -.6)))
    report['capture_access'] = capture_access(m, b.assets, report['checkpoints'])
    b.image('layout.png', plan(t))
    (b.work/'layout.json').write_text(json.dumps(dict(bases=BASES, routes=ROUTES, ridges=RIDGES,
                                                   crevasses=CREVASSES, captures=CHECKPOINTS,
                                                   capture_links=CAPTURE_LINKS), indent=2), encoding='utf-8')
    b.report.update(report)
    b.save(m, ini=ini_block(b.project.weather))
    print(f'All 16 sites and ice entrances connect around two deep ruptures; '
          f'{report["scenery"]["total_scenery"]} scenery objects, '
          f'{report["scenery"]["trees"]} trees, '
          f'{len(report["scenery"]["waystations"])} ruined waystations.', flush=True)


def capture_access(m, assets, sites):
    """Check the authored base groups against local, object-aware walking paths."""
    fine = np.isin(categories(walking_grid(m, assets=assets)), PASSABLE)
    # Conservative 20-unit cells: all four native terrain cells must be
    # passable. Dijkstra disallows diagonal corner cutting around obstacles.
    walk = fine.reshape(HEIGHT//2, 2, WIDTH//2, 2).all(axis=(1, 3))
    results = []
    failures = []
    for site in sites:
        field = distance_field(walk, site['flag'])
        all_distances = {base['number']: at(field, walk, (base['x'], base['y'])) for base in BASES}
        distances = [all_distances[i] for i in site['surrounding_bases']]
        if not np.isfinite(distances).all():
            raise ValueError(f'{site["name"]}: a surrounding base cannot reach the flag')
        spread = (max(distances)-min(distances))/np.mean(distances)
        limit = .06 if site['template'] == 'Inn' else .07
        if spread > limit:
            failures.append(f'{site["name"]}: walking-distance spread {spread:.1%} exceeds {limit:.0%}')
        others = [v for k, v in all_distances.items() if k not in site['surrounding_bases']]
        if min(others) < max(distances):
            raise ValueError(f'{site["name"]}: another base is closer than its intended neighbours')
        results.append(dict(name=site['name'], template=site['template'],
                            walking_distances={i: round(all_distances[i]) for i in site['surrounding_bases']},
                            spread_percent=round(spread*100, 2)))
        print(f'{site["name"]}: {results[-1]["walking_distances"]}, spread {spread:.1%}', flush=True)
    if failures:
        raise ValueError('; '.join(failures))
    return dict(method='local object-aware shortest paths, 20-unit grid',
                native_verified=False, sites=results)
