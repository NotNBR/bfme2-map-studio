"""Weather presets for BFME2 maps: map.ini Weather block, WorldInfo weather
and GlobalLighting adjustments.

What the game shows comes from three places:

- WorldInfo `weather` (NONE 0, CLOUDY 1, RAINY 2, CLOUDYRAINY 3, SUNNY 4) only
  picks the WeatherData entry in weather.ini: the ambient sound and whether
  lightning may flash. It does not change the picture.
- The map.ini Weather block: hardware fog (colour and start/end distance from
  the camera) and falling particles (the snow system; rain is the same system
  with EXRainDrop.tga, as weather.ini's defaults use).
- GlobalLighting: sun and fill colours for the mood.
- The sky: retail maps place one WaterReflectionSkydome object (KindOf
  SKYBOX) near the map centre, an unlit dome model (simple.fx, fog off) that
  fills the view beyond the map edges and mirrors in reflective water.

Fog distances are measured from the camera. Retail maps use 600..1800, made
for the default close camera; on a large map viewed from 1,300..1,800 units up
(2,000..3,000 to the ground) that fogs everything completely, and fully fogged
optimized trees turn into flat fog-coloured silhouettes. The presets start the
fog beyond the gameplay view so only the distance hazes. Particles fall from
SnowBoxHeight above the ground; a tall box keeps them near the camera.
"""

import re

WEATHER_CODES = dict(none=0, cloudy=1, rainy=2, cloudyrainy=3, sunny=4)
WEATHER_BLOCK = r'(?ims)^\s*Weather\s*$(.*?)^\s*End\b'    # an INI text's Weather blocks, their keys in group 1

# fog: (R, G, B), start, end. particles: snow-system settings. light: sun
# diffuse multipliers (R, G, B) and an ambient multiplier; fill: new colour of
# light 1; low_sun: flatten the sun direction for long evening shadows.
PRESETS = {
    'clear': dict(weather='none', sky='GapOfRohan'),
    'haze': dict(weather='cloudy', sky='Celduin', fog=((150, 160, 175), 3200, 11000), light=(.92, .95, 1.0, 1.05)),
    'rain': dict(weather='cloudyrainy', sky='DolGul', fog=((92, 99, 110), 2400, 8000), light=(.55, .62, .72, .85),
                 particles=dict(texture='EXRainDrop.tga', box=1600, spacing=14, amplitude=0, quad=16,
                                speed=900.0, point=(8, 40)), lightning=0.15),
    'snow': dict(weather='cloudy', sky='DolGul', fog=((178, 185, 198), 2600, 9000), light=(.85, .93, 1.05, 1.15),
                 particles=dict(texture='EXSnowFlake2.tga', box=1600, spacing=30, amplitude=3, quad=5,
                                speed=160.0, point=(4, 12))),
    'dusk': dict(weather='sunny', sky='Celduin', fog=((150, 110, 86), 4200, 14000), light=(1.15, .78, .52, .95),
                 fill=(.16, .20, .34), low_sun=True),
}


def _fog_lines(fog):
    if not fog:
        return ['  HardwareFogEnable = No']
    (r, g, b), start, end = fog
    return ['  HardwareFogEnable = Yes', f'  HardwareFogColor = R:{r} G:{g} B:{b}',
            f'  HardwareFogStart = {start}', f'  HardwareFogEnd = {end}']


def ini_block(name, fog='preset'):
    """The map.ini Weather block for a preset; `fog` ((R, G, B), start, end,
    or None for none) in place of the preset's."""
    p = PRESETS[name]
    lines = ['Weather']
    lines += _fog_lines(p.get('fog') if fog == 'preset' else fog)
    s = p.get('particles')
    if s:
        lines += ['  SnowEnabled = yes', '  IsSnowing = yes', f'  SnowTexture = {s["texture"]}',
                  f'  SnowBoxHeight = {s["box"]}', f'  SnowSpacing = {s["spacing"]}', '  NumberTiles = 4',
                  f'  SnowAmplitude = {s["amplitude"]}', '  SnowFrequencyScaleX = 0.02', '  SnowFrequencyScaleY = 0.02',
                  '  SnowPointSize = 2', f'  SnowMinPointSize = {s["point"][0]}', f'  SnowMaxPointSize = {s["point"][1]}',
                  '  SnowPointSprites = no', f'  SnowQuadSize = {s["quad"]}', f'  SnowSpeed = {s["speed"]}']
    if p.get('lightning'):
        lines += ['  LightningEnabled = yes', f'  LightningChance = {p["lightning"]}']
    lines.append('End')
    return '\n'.join(lines) + '\n'


# Suns: a light rig over any weather (the same keys as a preset's light,
# fill and low_sun), optionally with its own sky dome and fog tint.
SUNS = {
    'ember': dict(label='Mordor: Ember', light=(1.2, .55, .38, .75), fill=(.22, .07, .05), low_sun=True,
                  sky='MinasMorgul', fog=((48, 20, 14), 5000, 17000)),
    'copper': dict(label='Mordor: Copper', light=(1.45, .82, .56, 1.0), fill=(.28, .12, .08), low_sun=True,
                   sky='MinasMorgul', fog=((70, 34, 22), 5000, 17000)),
    'blood': dict(label='Mordor: Blood red', light=(1.55, .42, .28, .85), fill=(.30, .05, .04), low_sun=True,
                  sky='MinasMorgul', fog=((60, 14, 10), 5000, 17000)),
    'sulphur': dict(label='Mordor: Sulphur glow', light=(1.45, 1.0, .42, .9), fill=(.22, .10, .04), low_sun=True,
                    sky='MinasMorgul', fog=((72, 46, 18), 5000, 17000)),
    'ash': dict(label='Mordor: High sun through ash', light=(1.15, .80, .62, 1.05), fill=(.18, .12, .10),
                sky='MinasMorgul', fog=((62, 40, 32), 5000, 17000)),
    'violet': dict(label='Mordor: Dusk violet', light=(1.05, .52, .58, .85), fill=(.16, .08, .20), low_sun=True,
                   sky='MinasMorgul', fog=((44, 22, 34), 5000, 17000)),
}


def apply_sun(lighting, name):
    """Adjust decoded GlobalLighting in place for a sun (see SUNS)."""
    return _apply_light(lighting, SUNS[name])


def apply_sun_to_map(m, name):
    """Adjust a map's GlobalLighting for a sun (apply_sun on the decoded chunk)."""
    from mapworkshop.formats.lighting import decode, encode
    chunk = m.chunk('GlobalLighting')
    lighting = decode(chunk.data, chunk.version)
    apply_sun(lighting, name)
    chunk.data = encode(lighting, chunk.version)


def sun_ini(name):
    """A Weather block with only the sun's fog, to override the weather's."""
    fog = SUNS[name].get('fog')
    return 'Weather\n' + '\n'.join(_fog_lines(fog)) + '\nEnd\n' if fog else ''


def without_weather(text):
    """An INI text without its Weather blocks (a preset's ini_block stands in their place)."""
    return re.sub(WEATHER_BLOCK, '', text)


def sky(weather=None, sun=None):
    """The sky a weather preset and a sun bring: the sun's, else the preset's; None for the map's own (no
    preset and no sun, or neither brings one)."""
    return (SUNS[sun].get('sky') if sun in SUNS else None) or (PRESETS[weather].get('sky') if weather in PRESETS else None)


def preview_choices():
    """The viewers' Preview choices, {'weather': [(value, label)], 'sun': [...]}: 'map' and 'own' are the map's
    own weather and the weather's own sun."""
    return dict(weather=[('map', "Map's own")] + [(k, k.title()) for k in PRESETS],
                sun=[('own', "Weather's own")] + [(k, v['label']) for k, v in SUNS.items()])


def preview_labels(weather, sun):
    """What a Preview choice shows on its button: the weather's label, and the sun's unless it is the weather's own."""
    choices = {option: dict(entries) for option, entries in preview_choices().items()}
    return [choices['weather'][weather]] + ([choices['sun'][sun]] if sun != 'own' else [])


def sky_texture(sky):
    """Texture of a WaterReflectionSkydome variant ('GapOfRohan', ...)."""
    return f'WtrSkydome_{sky}.tga'


# WtrSky_* models: a dome 3,835 x 3,934 units in radius, 68..2,639 high.
SKYDOME_RADIUS, SKYDOME_BASE = 3835.0, 68.0


def skydome_template(sky):
    """The retail sky dome template of a sky ('GapOfRohan', ...)."""
    return 'WaterReflectionSkydome_' + sky


def sky_template(name):
    """The retail sky dome template for a preset."""
    return skydome_template(PRESETS[name].get('sky', 'GapOfRohan'))


def add_sky(m, name, width, height, border=0.0, drop=0.0):
    """Place the preset's sky dome at the centre of a width x height map
    (object coordinates, playable area) and scale it with
    objectPrototypeScale (Object::updateObjValuesFromMapProperties
    multiplies the drawable's scale by it) so that it encloses the whole
    terrain, border included, with 10% to spare. `drop` is how far the
    lowest terrain lies below the ground at the centre: the dome is lowered
    so that its rim (68 units up, scaled) meets it, leaving no gap under the
    sky at the horizon."""
    import math
    from mapworkshop.mapkit.blank import add_object
    reach = math.hypot(width/2 + border, height/2 + border)*1.1
    scale = max(1.0, math.ceil(reach/SKYDOME_RADIUS*20)/20)
    template = sky_template(name)
    z = -(SKYDOME_BASE*scale + max(drop, 0.0) + 10.0)
    add_object(m, template, width/2, height/2, 0.0, layer='Sky', extra=[('objectPrototypeScale', 2, scale)], z=z)
    return dict(template=template, scale=scale, radius=round(SKYDOME_RADIUS*scale), z=round(z, 1))


def weather_code(name):
    return WEATHER_CODES[PRESETS[name]['weather']]


def apply_lighting(lighting, name):
    """Adjust decoded GlobalLighting (formats.lighting) in place for a preset."""
    return _apply_light(lighting, PRESETS[name])


def apply_weather(m, name, sun=None, fill=None):
    """Set a map's WorldInfo weather and GlobalLighting for a preset. `sun` and
    `fill` first set fields (ambient, diffuse, direction) of lights 0 and 1 in
    every time of day: the map's own light rig, which the preset then adjusts.
    The sky (add_sky) and the map.ini block (ini_block) are separate."""
    from mapworkshop.formats.lighting import decode, encode
    from mapworkshop.mapkit.blank import set_world
    set_world(m, weather=weather_code(name))
    chunk = m.chunk('GlobalLighting')
    lighting = decode(chunk.data, chunk.version)
    rig = {0: sun or {}, 1: fill or {}}
    for configuration in lighting['configurations']:
        for light in configuration:
            light.update(rig.get(light['light_index'], {}))
    apply_lighting(lighting, name)
    chunk.data = encode(lighting, chunk.version)


def _apply_light(lighting, p):
    if 'light' not in p and 'fill' not in p:
        return lighting
    r, g, b, ambient = p.get('light', (1, 1, 1, 1))
    for configuration in lighting['configurations']:
        for light in configuration:
            if light['light_index'] == 0:
                light['diffuse'] = tuple(x*k for x, k in zip(light['diffuse'], (r, g, b)))
                light['ambient'] = tuple(x*ambient for x in light['ambient'])
                if p.get('low_sun'):
                    x, y, z = light['direction']
                    light['direction'] = (x*1.3, y*1.3, z*.7)
            elif light['light_index'] == 1 and p.get('fill'):
                light['diffuse'] = p['fill']
    return lighting
