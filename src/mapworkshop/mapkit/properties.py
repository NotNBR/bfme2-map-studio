"""Map properties: the map-wide settings a map file and its map.ini carry.

Each property lives in one of three places:

- `world`: the WorldInfo dictionary of the .map (camera limits, map name,
  scenario flags). The names are the game's own dictionary keys.
- `environment`: the EnvironmentData chunk of the .map (water alpha, macro
  and cloud textures). The game reads its water depth and opacity into the
  terrain object that WaterShader's TransparentWaterDepth and
  MinWaterOpacity come from (WorldHeightMap::ParseEnvironmentDataChunk).
- `ini:<Block>`: a field of a top-level block of the map's map.ini, over the
  game's INI of the same name (Weather over weather.ini, WaterTransparency
  over water.ini).

A project keeps its own values in map.toml as overrides:

    [properties.world]
    cameraMaxHeight = 25000.0
    [properties.ini.WaterTransparency]
    ReflectionOn = true

and the build applies them over what map.py wrote (`apply`). Values are TOML
types: booleans, numbers, strings, [r, g, b] colours and [x, y] pairs.
"""

import re

from mapworkshop.formats import sections

# kind: real, int, bool, text, rgb (0-255 each), xy, choice (with `choices`:
# (value, label) pairs).
PROPERTIES = [
    # Camera ------------------------------------------------------------------
    dict(group='Camera', where='world', key='cameraMaxHeight', kind='real', label='Max height',
         help="The camera's zoom-out height (its offset z). Every stock map stores 300."),
    dict(group='Camera', where='world', key='cameraMinHeight', kind='real', label='Min height',
         help='How far in the camera zooms. Left out by most stock maps.'),
    dict(group='Camera', where='world', key='cameraPitchAngle', kind='real', label='Pitch angle',
         help='Degrees above the horizon the camera looks down from (37.5 on almost every stock map).'),
    dict(group='Camera', where='world', key='cameraYawAngle', kind='real', label='Yaw angle',
         help='Initial camera heading in degrees.'),
    dict(group='Camera', where='world', key='cameraScrollSpeedScalar', kind='real', label='Scroll speed',
         help='Multiplies the scroll speed.'),
    dict(group='Camera', where='world', key='cameraMapHeightSmoothnessScalar', kind='real', label='Height smoothing',
         help='How far the smoothed camera height field reaches up to its neighbours (0.75 typical).'),
    dict(group='Camera', where='world', key='cameraGroundMinHeight', kind='real', label='Ground min height',
         help='Lowest terrain height the camera allows for its ground level.'),
    dict(group='Camera', where='world', key='cameraGroundMaxHeight', kind='real', label='Ground max height',
         help='Highest terrain height the camera allows for its ground level.'),
    # Map -----------------------------------------------------------------------
    dict(group='Map', where='world', key='mapName', kind='text', label='Map name',
         help="WorldInfo's own name (the game lists maps by map.str and the folder name)."),
    dict(group='Map', where='world', key='mapDescription', kind='text', label='Map description',
         help="WorldInfo's own description."),
    dict(group='Map', where='world', key='weather', kind='choice', choices=[(0, 'Normal'), (1, 'Snowy')],
         label='Weather (WorldInfo)', help='The map\'s weather type: 1 on 14 of the 72 stock maps (the snowy ones).'),
    dict(group='Map', where='world', key='isScenarioMultiplayer', kind='bool', label='Scenario multiplayer',
         help='A scenario rather than a skirmish map.'),
    dict(group='Map', where='world', key='isLivingWorldScriptHolder', kind='bool', label='Living World script holder',
         help='Holds the War of the Ring scripts.'),
    dict(group='Map', where='world', key='compression', kind='int', label='Compression',
         help='The compression flag stock maps store (1); the file signature decides the actual compression.'),
    # Environment ------------------------------------------------------------
    dict(group='Environment', where='environment', key='water_max_alpha_depth', kind='real', label='Water opaque depth',
         help='Depth at which standing water becomes opaque (WaterShader MaxAlphaDepth). Stock maps use 3 to 25.'),
    dict(group='Environment', where='environment', key='deep_water_alpha', kind='real', label='Deep water alpha',
         help='Opacity of deep water, 0 to 1 (WaterShader DeepWaterAlpha).'),
    dict(group='Environment', where='environment', key='macro_texture_stretched', kind='bool', label='Stretch macro texture',
         help='Stretch the macro texture over the whole map instead of tiling it every 660 units.'),
    dict(group='Environment', where='environment', key='macro_texture', kind='text', label='Macro texture',
         help='Large-scale tint multiplied over the terrain.'),
    dict(group='Environment', where='environment', key='cloud_texture', kind='text', label='Cloud texture',
         help='Cloud shadows moving over the terrain.'),
    # Water (map.ini WaterTransparency over water.ini) -------------------------
    dict(group='Water', where='ini:WaterTransparency', key='ReflectionOn', kind='bool', label='Reflections',
         help='Draw water reflections at WaterLOD High and up. Every stock map with water turns them on; '
              'without them High water is nearly black.'),
    dict(group='Water', where='ini:WaterTransparency', key='ReflectionPlaneZ', kind='real', label='Reflection plane height',
         help='Height of the plane the scene is mirrored at: the water level.'),
    dict(group='Water', where='ini:WaterTransparency', key='ReflectionGuard', kind='xy', label='Reflection guard',
         help='Margin so big objects near the frustum edge do not pop in the reflection.'),
    dict(group='Water', where='ini:WaterTransparency', key='RiverTransparencyMultiplier', kind='real',
         label='River transparency', help="Multiplies the alpha of rivers' edge textures."),
    dict(group='Water', where='ini:WaterTransparency', key='RadarWaterColor', kind='rgb', label='Radar water colour',
         help='Colour of water on the minimap radar.'),
    # Weather (map.ini Weather over weather.ini) ------------------------------
    dict(group='Weather', where='ini:Weather', key='HardwareFogEnable', kind='bool', label='Fog',
         help='Distance fog.'),
    dict(group='Weather', where='ini:Weather', key='HardwareFogColor', kind='rgb', label='Fog colour'),
    dict(group='Weather', where='ini:Weather', key='HardwareFogStart', kind='real', label='Fog start',
         help='Distance from the camera where the fog starts.'),
    dict(group='Weather', where='ini:Weather', key='HardwareFogEnd', kind='real', label='Fog end',
         help='Distance where the fog is complete.'),
    dict(group='Weather', where='ini:Weather', key='CloudTextureSize', kind='xy', label='Cloud texture size',
         help='World units one cloud texture covers.'),
    dict(group='Weather', where='ini:Weather', key='CloudOffsetPerSecond', kind='xy', label='Cloud drift',
         help='Cloud texture movement per second, in texture units.'),
    dict(group='Weather', where='ini:Weather', key='SnowEnabled', kind='bool', label='Snow enabled',
         help='Allow falling rain or snow (with the Snow* settings of weather.ini or the map).'),
    dict(group='Weather', where='ini:Weather', key='IsSnowing', kind='bool', label='Snowing',
         help='Start with rain or snow falling.'),
    dict(group='Weather', where='ini:Weather', key='LightningEnabled', kind='bool', label='Lightning'),
]

GROUPS = list(dict.fromkeys(p['group'] for p in PROPERTIES))
WORLD_KINDS = dict(bool=0, int=1, choice=1, real=2, text=3)   # WorldInfo property types


def find(where, key):
    return next((p for p in PROPERTIES if p['where'] == where and p['key'] == key), None)


# Values ----------------------------------------------------------------------
def coerce(prop, value):
    """A TOML or dialog value as the property's kind, or ValueError."""
    kind = prop['kind']
    if kind == 'bool':
        if isinstance(value, str):
            low = value.strip().lower()
            if low not in ('yes', 'no', 'true', 'false', '1', '0'):
                raise ValueError(f'{prop["key"]}: expected yes or no, not {value!r}')
            return low in ('yes', 'true', '1')
        return bool(value)
    if kind in ('int', 'choice'):
        return int(value)
    if kind == 'real':
        return float(value)
    if kind == 'text':
        return str(value)
    if kind == 'rgb':
        parts = _numbers(value) if isinstance(value, str) else list(value)
        if len(parts) != 3 or not all(0 <= float(v) <= 255 for v in parts):
            raise ValueError(f'{prop["key"]}: expected three numbers 0-255, not {value!r}')
        return [int(round(float(v))) for v in parts]
    if kind == 'xy':
        parts = _numbers(value) if isinstance(value, str) else list(value)
        if len(parts) != 2:
            raise ValueError(f'{prop["key"]}: expected two numbers, not {value!r}')
        return [float(v) for v in parts]
    raise ValueError(f'unknown kind {kind}')


def _numbers(text):
    return [float(v) for v in re.findall(r'-?\d+(?:\.\d*)?(?:[eE]-?\d+)?|-?\.\d+', text)]


def ini_text(prop, value):
    """A value as map.ini writes it."""
    kind = prop['kind']
    if kind == 'bool':
        return 'Yes' if value else 'No'
    if kind == 'rgb':
        return 'R:{} G:{} B:{}'.format(*value)
    if kind == 'xy':
        return 'X:{:g} Y:{:g}'.format(*value)
    if kind == 'real':
        return f'{value:g}'
    return str(value)


def display(prop, value):
    """A value as the dialog shows it."""
    if value is None:
        return ''
    kind = prop['kind']
    if kind == 'bool':
        return 'Yes' if value else 'No'
    if kind == 'rgb':
        return '{} {} {}'.format(*value)
    if kind == 'xy':
        return '{:g} {:g}'.format(*value)
    if kind == 'real':
        return f'{value:g}'
    return str(value)


# map.ini blocks ------------------------------------------------------------
def _strip(line):
    return line.split(';', 1)[0].split('//', 1)[0].strip()


def _is_end(s):
    return s.lower() == 'end' or s.lower().startswith('end ')


def _blocks(lines, block):
    """(header, End) line indices of every `block` block. The blocks edited
    here (Weather, WaterTransparency) are flat, so each ends at the next End;
    nesting elsewhere is not tracked (an object's `Draw = ...` opens a block
    although it has an =)."""
    found, start = [], None
    for i, line in enumerate(lines):
        s = _strip(line)
        if not s:
            continue
        if start is None:
            if '=' not in s and s.split()[0].lower() == block.lower():
                start = i
        elif _is_end(s):
            found.append((start, i))
            start = None
    return found


def ini_fields(text, block):
    """The fields of the `block` blocks of an INI text, as {key: raw value};
    later blocks win, as the game reads them."""
    lines = text.splitlines()
    fields = {}
    for start, end in _blocks(lines, block):
        for line in lines[start+1:end]:
            s = _strip(line)
            if '=' in s:
                key, value = s.split('=', 1)
                fields[key.strip()] = value.strip()
    return fields


def parse_ini_value(prop, raw):
    """A raw map.ini value as the property's kind; None if it does not parse."""
    try:
        if prop['kind'] == 'rgb':
            parts = re.findall(r'[RGB]\s*:\s*(-?\d+(?:\.\d*)?)', raw, re.I)
            return coerce(prop, [float(v) for v in parts])
        if prop['kind'] == 'xy':
            return coerce(prop, raw)
        if prop['kind'] in ('real', 'int', 'choice'):
            return coerce(prop, _numbers(raw)[0])
        return coerce(prop, raw)
    except (ValueError, IndexError):
        return None


def set_ini_fields(text, block, values):
    """INI text with these fields ({key: text}) set in the last `block` block
    (lines replaced in place, new ones before its End), or in a new block at
    the end."""
    lines = text.splitlines()
    found = _blocks(lines, block)
    pending = dict(values)
    if not found:
        body = [f'  {k} = {v}' for k, v in pending.items()]
        tail = [''] if lines and lines[-1].strip() else []
        return '\n'.join(lines + tail + [block] + body + ['End']) + '\n'
    start, end = found[-1]
    for i in range(start+1, end):
        s = _strip(lines[i])
        if '=' not in s:
            continue
        key = s.split('=', 1)[0].strip()
        match = next((k for k in pending if k.lower() == key.lower()), None)
        if match:
            indent = lines[i][:len(lines[i])-len(lines[i].lstrip())] or '  '
            lines[i] = f'{indent}{match} = {pending.pop(match)}'
    lines[end:end] = [f'  {k} = {v}' for k, v in pending.items()]
    return '\n'.join(lines) + '\n'


# Reading and applying --------------------------------------------------------
def read(m, ini=''):
    """The current value of every property of a map (formats.map.Map) and its
    map.ini text: {(where, key): value or None when the map leaves it out}."""
    world = {k: v for k, _, v in sections.read(m, 'WorldInfo')}
    try:
        environment = sections.read(m, 'EnvironmentData')
    except ValueError:
        environment = {}
    blocks = {}
    values = {}
    for p in PROPERTIES:
        where, key = p['where'], p['key']
        if where == 'world':
            value = world.get(key)
        elif where == 'environment':
            value = environment.get(key)
        else:
            block = where[4:]
            if block not in blocks:
                blocks[block] = {k.lower(): v for k, v in ini_fields(ini, block).items()}
            raw = blocks[block].get(key.lower())
            value = None if raw is None else parse_ini_value(p, raw)
        values[(where, key)] = None if value is None else coerce(p, value)
    return values


def defaults(ini_texts):
    """map.ini fields' game defaults from the game's INI texts
    ({'Weather': weather.ini text, 'WaterTransparency': water.ini text})."""
    out = {}
    for p in PROPERTIES:
        if p['where'].startswith('ini:'):
            block = p['where'][4:]
            raw = {k.lower(): v for k, v in ini_fields(ini_texts.get(block, ''), block).items()}.get(p['key'].lower())
            if raw is not None:
                out[(p['where'], p['key'])] = parse_ini_value(p, raw)
    return out


def flatten(config):
    """map.toml [properties] as {(where, key): value}, checked against the
    known properties."""
    out = {}
    for section, table in (config or {}).items():
        if section == 'ini':
            items = [(f'ini:{block}', fields) for block, fields in table.items()]
        else:
            items = [(section, table)]
        for where, fields in items:
            for key, value in fields.items():
                prop = find(where, key)
                if prop is None:
                    raise ValueError(f'map.toml [properties]: unknown property {where} {key}')
                out[(where, key)] = coerce(prop, value)
    return out


def nest(overrides):
    """{(where, key): value} as the map.toml [properties] tables."""
    out = {}
    for (where, key), value in overrides.items():
        if where.startswith('ini:'):
            out.setdefault('ini', {}).setdefault(where[4:], {})[key] = value
        else:
            out.setdefault(where, {})[key] = value
    return out


def apply(m, ini, overrides):
    """Set overrides ({(where, key): value}) on a map and its map.ini text.
    Returns the new ini text and what changed, as lines."""
    if not overrides:
        return ini, []
    before = read(m, ini)
    changes = []
    world_values = {k: v for (w, k), v in overrides.items() if w == 'world'}
    if world_values:
        fields = sections.read(m, 'WorldInfo')
        known = {k for k, _, _ in fields}
        fields = [(k, kind, world_values.get(k, v)) for k, kind, v in fields]
        fields += [(k, WORLD_KINDS[find('world', k)['kind']], v) for k, v in world_values.items() if k not in known]
        fields = [(k, kind, int(v) if kind in (0, 1) else v) for k, kind, v in fields]
        sections.write(m, 'WorldInfo', fields)
    env_values = {k: v for (w, k), v in overrides.items() if w == 'environment'}
    if env_values:
        environment = sections.read(m, 'EnvironmentData')
        if m.chunk('EnvironmentData').version < 3 and {'water_max_alpha_depth', 'deep_water_alpha'} & set(env_values):
            raise ValueError('EnvironmentData v2 has no water alpha settings')
        environment.update({k: int(v) if isinstance(v, bool) else v for k, v in env_values.items()})
        sections.write(m, 'EnvironmentData', environment)
    blocks = {}
    for (where, key), value in overrides.items():
        if where.startswith('ini:'):
            blocks.setdefault(where[4:], {})[key] = ini_text(find(where, key), value)
    for block, values in blocks.items():
        ini = set_ini_fields(ini, block, values)
    for (where, key), value in overrides.items():
        if before.get((where, key)) != value:
            prop = find(where, key)
            old = display(prop, before.get((where, key))) or '(unset)'
            changes.append(f'{prop["group"]}: {prop["label"]} {old} -> {display(prop, value)}')
    return ini, changes
