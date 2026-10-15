"""Glacial Crossroads: phase-one mountain landscape and movement draft.

The user's SVG defines sixteen numbered sites and sixty connections. High
corner bases 1/4/7/10 overlook eight middle terraces; 13-16 stand just above
a broad central solid-ice field. Mountain crowns and divides separate passes.
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
from mapworkshop.mapkit.blank import add_object, create, set_heights, set_materials, starts, terrain_cell_sizes
from mapworkshop.mapkit.cliffs import steep_cells
from mapworkshop.mapkit.earth import fbm, thermal_erosion
from mapworkshop.mapkit.lines import polyline_distance
from mapworkshop.mapkit.relief import distance_to, smooth
from mapworkshop.mapkit.walkable import flood
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block
from .design import (BASES, BORDER, CENTRE, EXTENT, HEIGHT, HIGH, ICE, LOW, MID,
                     PAD_HALF, RIDGES, ROUTES, SCALE, WIDTH, floor_height)

PALETTE = ['SnowType5', 'SnowCaradhras06', 'SnowCaradhras07', 'SnowCaradhras05',
           'SnowCaradhras08', 'SnowCaradhras09', 'CliffCaradhras03']
CLIFF = len(PALETTE)-1


def landscape():
    """Carve shared valley floors through broad angular mountain masses."""
    y, x = (np.mgrid[:HEIGHT+2*BORDER, :WIDTH+2*BORDER]-BORDER)*10.
    radius = np.hypot(x-CENTRE[0], y-CENTRE[1])
    floor = floor_height(radius)
    route_edge = np.full(x.shape, np.inf)
    main_edge = np.full(x.shape, np.inf)
    for route in ROUTES:
        d, _ = polyline_distance(route['points'], x, y, reach=1600)
        route_edge = np.minimum(route_edge, d-route['width']/2)
        if route['main']:
            main_edge = np.minimum(main_edge, d-route['width']/2)
    # Form one continuous playable floor first. Base aprons must not pull
    # mountain faces into a pass after its corridor has already been carved.
    pads = np.zeros(x.shape, bool)
    deployment = np.zeros(x.shape, bool)
    open_edge = route_edge.copy()
    lower = np.full(x.shape, ICE)
    upper = np.full(x.shape, 2550.)
    for base in BASES:
        dx, dy = np.abs(x-base['x']), np.abs(y-base['y'])
        d = np.hypot(np.maximum(dx-PAD_HALF, 0), np.maximum(dy-PAD_HALF, 0))
        # A bounded-grade apron grows out of the pad. Weighted flattening
        # made a steep lip where a high pad rejoined the descending floor.
        apron = d/SCALE
        allowance = np.where(apron < 600, .000375*apron*apron, 135+.45*(apron-600))
        lower = np.maximum(lower, base['height']-allowance)
        upper = np.minimum(upper, base['height']+allowance)
        pads |= (dx <= PAD_HALF) & (dy <= PAD_HALF)
        deployment |= d <= 100*SCALE
        open_edge = np.minimum(open_edge, d-100*SCALE)
    if np.any(lower > upper+.001):
        raise ValueError('Base approach envelopes need more horizontal space')
    floor = np.clip(floor, lower, upper)
    angle = np.arctan2(y-CENTRE[1], x-CENTRE[0])
    # The clean plan's inner toes reach near the centre. The former oversized
    # ice disk erased those ridges; the battlefield now fits between them.
    shore = radius-SCALE*(1390+60*np.cos(4*angle)+40*np.sin(7*angle))
    weight = 1-smooth(shore/(350*SCALE))
    floor = floor*(1-weight)+ICE*weight
    ice = shore <= 0
    open_edge = np.minimum(open_edge, shore)
    reserved = open_edge <= 0
    # A continuous bedrock landscape, excavated by the connected valleys.
    # The SVG crests guide the massifs; they are not isolated raised strips.
    # Geology at 30-unit spacing; final pads and movement at native 10 units.
    cx, cy = x[::3, ::3], y[::3, ::3]
    sx, sy = cx/SCALE, cy/SCALE
    noise = fbm(sx, sy, scale=1500, octaves=3, seed=1601)
    ribs = fbm(sx+210*noise, sy-170*noise, scale=430, octaves=4, seed=1631)
    crest = np.zeros(cx.shape)
    for i, ridge in enumerate(RIDGES):
        points = np.asarray(ridge['points'])
        d, along = polyline_distance(points, cx, cy, reach=ridge['spread']*3.5)
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
        end = np.minimum(along, arc[-1]-along)
        taper = .65+.35*smooth(end/(700*SCALE))
        profile = np.exp(-(d/(ridge['spread']*1.6))**1.4)
        crest = np.maximum(crest, taper*profile)
    # Broad shoulders occupy ALL land between the valleys. Variable carving
    # depth forms buttresses and cirques instead of little peaks on a plain.
    cfloor = floor[::3, ::3]
    cradius = radius[::3, ::3]/SCALE
    ceiling = np.minimum(cfloor+1450+400*smooth(cradius/10000), 2360+140*noise)
    depth = np.maximum(open_edge[::3, ::3]-20-50*(noise+.5), 0)
    shoulder = SCALE*(650-170*crest+260*noise+240*ribs)
    volume = 1-np.exp(-(depth/np.maximum(shoulder, 260*SCALE))**1.3)
    raw = cfloor+(ceiling-cfloor)*volume
    # Incised, branching surface relief has several scales. It is bedrock
    # height, not a field of placed stones or a noise texture on flat ground.
    detail = 370*ribs+120*fbm(sx, sy, scale=180, octaves=3, seed=1647)
    raw += detail*smooth(depth/(400*SCALE))*(1-.45*volume)
    raw = thermal_erosion(raw, iterations=14, spacing=30, talus=1.5)
    rows = np.array([np.interp(x[0], cx[0], row) for row in raw])
    mountains = np.array([np.interp(y[:, 0], cy[:, 0], col) for col in rows.T]).T
    # Restore the exact shared floor at native resolution after coarse
    # sculpting, so no erosion deposit closes a connection or a level pad.
    rise = np.maximum(mountains-floor, 0)
    z = floor+rise*smooth((open_edge-30)/100)
    slope = np.hypot(*np.gradient(z, 10))
    inside = (x >= 0) & (y >= 0) & (x < EXTENT) & (y < EXTENT)
    # Height alone does not stop units: closed mountain ground is explicit.
    candidate = (open_edge < 70) & (slope < .6) & inside
    origin = (round(CENTRE[1]/10)+BORDER, round(CENTRE[0]/10)+BORDER)
    walk = flood(candidate, [origin])
    materials = np.zeros(x.shape, np.uint16)
    drift = fbm(x/SCALE, y/SCALE, scale=1100, octaves=2, seed=1602)
    # Orange reference lines: wider, continuous packed-snow main ways.
    # Blue reference lines: narrower passages retaining softer white snow.
    # This hierarchy comes from the SVG groups, not guessed orientations.
    materials[main_edge < -25+20*drift] = 1
    materials[(slope > .8+.15*drift) & (open_edge > 140)] = 3
    # Snow remains in gullies and on shoulders; rock reads as coherent faces
    # instead of a dark band wherever the slope crosses one low threshold.
    materials[slope > 2.1+.4*drift] = CLIFF
    materials[pads] = 0
    materials[ice] = 2
    fractures = np.sin((x+.3*y)/(1100*SCALE)+drift)+.45*np.sin((y-.2*x)/(650*SCALE))
    materials[ice & (fractures > 1.05)] = 4
    materials[ice & (shore > SCALE*(-110-70*drift))] = 5
    return dict(z=z, blocked=~walk, slope=slope, materials=materials,
                pads=pads, reserved=reserved, ice=ice)


def validate(t):
    """Measure final terrain rather than merely connectivity of drawn axes."""
    cut = (slice(BORDER, BORDER+HEIGHT), slice(BORDER, BORDER+WIDTH))
    walk = ~t['blocked'][cut]
    centre = (round(CENTRE[1]/10), round(CENTRE[0]/10))
    clearance = distance_to(~walk)*10
    safe = flood(walk & (clearance >= 70) & (t['slope'][cut] <= .65), [centre])
    gy, gx = np.mgrid[:HEIGHT, :WIDTH]
    alternate = flood(walk & (np.hypot(gx*10-CENTRE[0], gy*10-CENTRE[1]) > 2850*SCALE),
                      [(round(BASES[0]['y']/10), round(BASES[0]['x']/10))])
    route_checks = []
    for route in ROUTES:
        # Check every cell in the swept width of THIS connection. Global
        # flood-fill alone can hide a severed route behind an alternate path.
        p = np.asarray(route['points'])
        margin = route['width']/2+20
        lo = np.maximum(np.floor((p.min(axis=0)-margin)/10).astype(int), 0)
        hi = np.minimum(np.ceil((p.max(axis=0)+margin)/10).astype(int)+1, [WIDTH, HEIGHT])
        ry, rx = np.mgrid[lo[1]:hi[1], lo[0]:hi[0]]
        d, _ = polyline_distance(p, rx*10., ry*10., reach=margin)
        core = d <= route['width']/2
        crop = (slice(lo[1], hi[1]), slice(lo[0], hi[0]))
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
    if float(t['z'].min()) < ICE-.001 or not np.allclose(t['z'][t['ice']], ICE):
        raise ValueError('Ice must be level and the lowest ground')
    return dict(stage='phase 1: layout and rough mountain terrain', bases=sites,
                horizontal_scale=SCALE, extent=[EXTENT, EXTENT],
                reference_routes=len(ROUTES), all_sites_connected=True,
                reference_ridges=len(RIDGES),
                every_route_clear_across_full_width=True, route_checks=route_checks,
                all_sites_connected_with_70_clearance_and_slope_065=True,
                all_sites_connected_without_central_ice=True,
                height_range=[float(t['z'].min()), float(t['z'].max())],
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
    draw.text((40, 18), 'GLACIAL CROSSROADS / PHASE 1', font=bold, fill='white')
    draw.text((40, 52), f'{EXTENT:,.0f} x {EXTENT:,.0f} units | 16 base sites | high mountain terrain | north up', font=font, fill='#bed4df')
    def point(x, y):
        return 40+x/EXTENT*1400, 85+(EXTENT-y)/EXTENT*1400
    for route in ROUTES:
        draw.line([point(*p) for p in route['points']], fill='#c98450' if route['main'] else '#567f8f', width=3 if route['main'] else 2)
    for base in BASES:
        px, py = point(base['x'], base['y'])
        color = '#5c466f' if base['height'] == HIGH else '#526c58' if base['height'] == MID else '#236c85'
        draw.rounded_rectangle((px-35, py-32, px+35, py+32), radius=10, fill=color, outline='white', width=2)
        draw.text((px, py-10), f'{base["number"]:02}', font=bold, fill='white', anchor='mm')
        draw.text((px, py+16), f'{base["height"]:g}', font=font, fill='white', anchor='mm')
    draw.text(point(*CENTRE), 'ICE FIELD\nz 120', font=bold, fill='#183f58', anchor='mm', align='center')
    draw.text((40, 1501), 'HIGH  1 / 4 / 7 / 10 : 1650       MID  outer bases : 850       LOW  13-16 : 220       ICE : 120', font=font, fill='white')
    draw.text((40, 1531), 'Solid ice terrain. Broad mountain passes. Terrain draft; native gameplay and balance not tested.', font=font, fill='#bed4df')
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


def build(b):
    print('Shaping 16 terraces, 60 connections and 68 ridges from the clean reference...', flush=True)
    t = b.cached(landscape)
    report = validate(t)
    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title,
               description=b.project.description, player_count=8, experimental_large=True)
    site_scaffold(m)
    set_heights(m, t['z'])
    set_materials(m, PALETTE, t['materials'], blocked=t['blocked'],
                  cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True,
                  cliffs=(t['materials'] == CLIFF) & steep_cells(t['z']), cliff_scale=3)
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
    b.image('layout.png', plan(t))
    (b.work/'layout.json').write_text(json.dumps(dict(bases=BASES, routes=ROUTES, ridges=RIDGES), indent=2), encoding='utf-8')
    b.report.update(report)
    b.save(m, ini=ini_block(b.project.weather))
    print('All 16 level sites connect through gentle passes and around the central ice.', flush=True)
