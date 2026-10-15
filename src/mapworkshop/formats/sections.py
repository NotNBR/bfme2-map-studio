"""Typed reading and writing of every map section, from one layout per section.

A layout lists a section's fields in file order. The same layout reads a
payload (`decode`) and writes one (`encode`), so the two directions cannot
drift apart: `encode(name, version, decode(name, version, data, m), m) == data`
for every stock map, base and library (see tests/test_sections.py and
`mw test --corpus`). Field meanings and evidence are in
docs/format/.

    areas = read(m, 'StandingWaterAreas')        # a list of dicts
    areas[0]['water_height'] = 140
    write(m, 'StandingWaterAreas', areas)

Field kinds:
- a struct format ('I', 'f', 'B', 'i', '2f', '4B', ...): one value, or a
  tuple when the format has several;
- STR: a u16 length and that many cp1252 bytes;
- PROPS: a property dictionary, as (name, type, value) triples in order;
- NAME: a 3-byte index into the map's name table, read as the name;
- FOURCC: four ASCII bytes stored reversed ('free', 'catm');
- items(kind, count='I'): a count, then that many values of `kind`;
- chunks(children): child chunks up to the end of the payload, each a dict
  with its `chunk` name, `version` and fields; children without a layout (or
  that do not parse) stay as `raw` bytes;
- record(...): (name, kind) fields in order; since(version, ...) for fields
  that only later versions store, when(key, values, ...) and
  unless(key, values, ...) for fields that depend on an earlier field.

Five sections have their own codecs, registered in CODECS: objects and the
terrain (formats.map, formats.terrain), lighting and castle templates.
PROPS, NAME and chunks need the map `m` for its name table.
"""
from functools import lru_cache
import struct

from mapworkshop.formats.map import Chunk, Reader, chunks as split_chunks, string

STR = 'str'
PROPS = 'props'
NAME = 'name'
FOURCC = 'fourcc'
MAX_ITEMS = 100000


def record(*fields):
    return ('record', fields)


def items(kind, count='I'):
    return ('items', kind, count)


def chunks(children):
    """children: {chunk name: {version: record}}."""
    return ('chunks', children)


def since(version, *fields):
    return ('if', lambda v, rec: v >= version, fields)


def when(key, values, *fields):
    return ('if', lambda v, rec: rec[key] in values, fields)


def unless(key, values, *fields):
    return ('if', lambda v, rec: rec[key] not in values, fields)


# Shared parts ---------------------------------------------------------------
_AREA = (('id', 'I'), ('name', STR), ('layer', STR), ('uv_speed', 'f'), ('additive', 'B'))
_VIEW = (('pitch', 'f'), ('roll', 'f'), ('yaw', 'f'), ('zoom', 'f'), ('field_of_view', 'f'), ('unknown', 'f'))
# A BFME build-list entry (not the larger runtime/savegame BuildListInfo).
_BUILD_ITEM = record(('building_name', STR), ('template', STR), ('position', '3f'), ('angle', 'f'),
                     ('initially_built', 'B'), ('rebuilds', 'I'), ('script', STR), ('health', 'i'),
                     ('whiner', 'B'), ('unsellable', 'B'), ('repairable', 'B'))
_FRAME = (('frame', 'I'), ('interpolation', FOURCC))

# Scripts: lists hold scripts and groups; scripts hold OR-groups of conditions
# and the actions taken when they are true or false. Arguments store an int, a
# float and a string side by side (not a union), or one position (type 16).
_ARGUMENT = record(('type_id', 'I'), when('type_id', (16,), ('position', '3f')),
                   unless('type_id', (16,), ('int_value', 'i'), ('float_value', 'f'), ('string_value', STR)))
_OPERATION = (('opcode_raw', 'I'), ('internal_name_kind', 'B'), ('internal_name', NAME),
              ('arguments', items(_ARGUMENT)))
_CONDITION = {v: record(*_OPERATION, since(5, ('enabled_raw', 'I'), ('condition_flag_4d_raw', 'I'))) for v in (4, 5, 6)}
_ACTION = {v: record(*_OPERATION, since(3, ('enabled_raw', 'I'))) for v in (2, 3)}
_OR = {1: record(('children', chunks({'Condition': _CONDITION})))}
_SCRIPT = {v: record(
    ('name', STR), ('comment', STR), ('conditions_comment', STR), ('actions_comment', STR),
    ('active_raw', 'B'), ('deactivate_on_success_raw', 'B'), ('easy_raw', 'B'), ('medium_raw', 'B'),
    ('hard_raw', 'B'), ('subroutine_raw', 'B'),
    since(2, ('evaluation_interval_raw', 'I')),
    since(3, ('sequential_raw', 'B'), ('loop_raw', 'B'), ('loop_count', 'i'), ('target_type_raw', 'B'),
          ('target_name', STR)),
    since(4, ('player_mask_text', STR)),
    ('children', chunks({'OrCondition': _OR, 'ScriptAction': _ACTION, 'ScriptActionFalse': _ACTION}))) for v in (1, 2, 3, 4)}
_GROUP = {}   # filled below: from version 3 a group may hold groups
for _v in (1, 2, 3):
    _GROUP[_v] = record(('name', STR), ('active_raw', 'B'), ('subroutine_raw', 'B'),
                        ('children', chunks({'Script': _SCRIPT, **({'ScriptGroup': _GROUP} if _v >= 3 else {})})))
_SCRIPT_LIST = {1: record(('children', chunks({'Script': _SCRIPT, 'ScriptGroup': _GROUP})))}

# name: (versions, layout)
LAYOUTS = {
    'WorldInfo': ((1,), PROPS),
    'MPPositionList': ((0,), chunks({'MPPositionInfo': {v: record(
        ('human', 'B'), ('computer', 'B'), since(1, ('load_ai_script', 'B')), ('team', 'I'),
        since(1, ('side_restrictions', items(STR)))) for v in (0, 1)}})),
    'SidesList': ((5, 6), record(
        since(6, ('unknown_boolean', 'B')),
        ('players', items(record(('properties', PROPS), ('build_list', items(_BUILD_ITEM))))))),
    'LibraryMapLists': ((1,), chunks({'LibraryMaps': {1: record(('maps', items(STR)))}})),
    'Teams': ((1,), items(PROPS)),
    'PlayerScriptsList': ((1, 5, 6), chunks({'ScriptList': _SCRIPT_LIST})),
    'BuildLists': ((1,), items(record(('property_kind', 'B'), ('faction', NAME), ('items', items(_BUILD_ITEM))))),
    'PolygonTriggers': ((4, 5), items(record(
        ('name', STR), ('layer', STR), ('id', 'I'), ('is_water_raw', 'B'), ('is_river_raw', 'B'), ('river_start', 'I'),
        since(5, ('river_texture', STR), ('noise_texture', STR), ('alpha_edge', STR), ('sparkle', STR),
              ('bump_texture', STR), ('sky_texture', STR), ('additive_raw', 'B'), ('river_rgb', '3B'),
              ('unknown_byte', 'B'), ('uv_speed', '2f'), ('river_alpha', 'f')),
        ('points', items('3i'))))),
    'TriggerAreas': ((1,), items(record(
        ('name', STR), ('layer', STR), ('id', 'I'), ('points', items('2f')), ('unknown_u32', 'I')))),
    'StandingWaterAreas': ((2,), items(record(
        *_AREA, ('bump_texture', STR), ('sky_texture', STR), ('points', items('2f')),
        ('water_height', 'I'), ('shader', STR), ('depth_colors', STR)))),
    'RiverAreas': ((1, 2), items(record(
        *_AREA, ('texture', STR), ('noise', STR), ('alpha_edge', STR), ('sparkle', STR),
        ('color_bytes', '4B'), ('alpha', 'f'), ('water_height', 'I'), ('min_lod', STR),
        ('cross_sections', items('4f'))))),
    'StandingWaveAreas': ((1, 2), items(record(
        *_AREA, ('points', items('2f')), ('unknown_u32', 'I'), ('wave_parameters_raw', '9I'),
        ('texture', STR), since(2, ('enable_pca', 'I'))))),
    'PostEffectsChunk': ((1,), items(record(('name', STR), ('blend_factor', 'f'), ('lookup_image', STR)), count='B')),
    'EnvironmentData': ((2, 3), record(
        since(3, ('water_max_alpha_depth', 'f'), ('deep_water_alpha', 'f')),
        ('macro_texture_stretched', 'B'), ('macro_texture', STR), ('cloud_texture', STR))),
    'NamedCameras': ((2,), items(record(('look_at', '3f'), ('name', STR), *_VIEW))),
    'CameraAnimationList': ((1, 3), items(record(
        ('type', FOURCC), ('name', STR), ('num_frames', 'I'), ('start_offset', 'I'),
        when('type', ('free',), ('camera_frames', items(record(
            *_FRAME, ('position', '3f'), ('rotation_raw', '4f'), ('fov_or_focal_parameter', 'f'))))),
        when('type', ('look',), ('camera_frames', items(record(
            *_FRAME, ('position', '3f'), ('roll', 'f'), ('fov_or_focal_parameter', 'f')))),
             ('target_frames', items(record(*_FRAME, ('look_at', '3f')))))))),
    'WaypointsList': ((1,), items(record(('start_id', 'i'), ('end_id', 'i')))),
    'SkyboxSettings': ((1,), record(('position', '3f'), ('scale', 'f'), ('rotation', 'f'), ('texture_scheme', STR))),
}

# An Object v3: position, angle, flags, template and its properties.
OBJECT = record(('x', 'f'), ('y', 'f'), ('z', 'f'), ('angle', 'f'), ('flags', 'I'), ('template', STR),
                ('properties', PROPS))

# Every child chunk with a layout: name: {version: record}.
CHILDREN = {'ScriptList': _SCRIPT_LIST, 'ScriptGroup': _GROUP, 'Script': _SCRIPT, 'OrCondition': _OR,
            'Condition': _CONDITION, 'ScriptAction': _ACTION, 'ScriptActionFalse': _ACTION,
            'MPPositionInfo': LAYOUTS['MPPositionList'][1][1]['MPPositionInfo'],
            'LibraryMaps': LAYOUTS['LibraryMapLists'][1][1]['LibraryMaps'], 'Object': {3: OBJECT}}


# Sections with their own codec: name: (versions, decode(data, version, m), encode(value, version, m)).
def _objects_decode(data, version, m):
    r = Reader(data)
    value = _read(r, chunks({'Object': {3: OBJECT}}), version, m)
    r.finish()
    if any('raw' in o for o in value):
        raise ValueError('Only BFME2 Object v3 is supported')
    return [{k: v for k, v in o.items() if k not in ('chunk', 'version')} for o in value]


def object_payload(o, m):
    """One Object v3 chunk's payload."""
    out = bytearray()
    _write(out, OBJECT, o, 3, m)
    return bytes(out)


def _objects_encode(value, version, m):
    out = bytearray()
    _write(out, chunks({'Object': {3: OBJECT}}), [dict(o, chunk='Object', version=3) for o in value], version, m)
    return bytes(out)


def _codecs():
    from mapworkshop.formats import castles, lighting, terrain
    return {
        'HeightMapData': ((5,), lambda d, v, m: terrain.decode_heights(d),
                          lambda x, v, m: terrain.encode_heights(x)),
        'BlendTileData': (tuple(range(8, 19)), terrain.decode_blend, terrain.encode_blend),
        'ObjectsList': ((3,), _objects_decode, _objects_encode),
        'GlobalLighting': (tuple(range(1, 9)), lambda d, v, m: lighting.decode(d, v),
                           lambda x, v, m: lighting.encode(x, v)),
        'CastleTemplates': ((1, 2, 3, 4, 5), lambda d, v, m: castles.decode(d, m.names, v),
                            lambda x, v, m: castles.encode(x, m.intern, v)),
    }


@lru_cache(maxsize=None)
def codecs():
    return _codecs()


def versions(name):
    """The versions of a section that decode and encode support."""
    if name in LAYOUTS:
        return LAYOUTS[name][0]
    if name in codecs():
        return codecs()[name][0]
    raise ValueError(f'No layout for {name}')


SECTIONS = ('HeightMapData', 'BlendTileData', 'WorldInfo', 'MPPositionList', 'SidesList', 'LibraryMapLists',
            'Teams', 'PlayerScriptsList', 'BuildLists', 'ObjectsList', 'PolygonTriggers', 'TriggerAreas',
            'StandingWaterAreas', 'RiverAreas', 'StandingWaveAreas', 'GlobalLighting', 'PostEffectsChunk',
            'EnvironmentData', 'NamedCameras', 'CameraAnimationList', 'WaypointsList', 'SkyboxSettings',
            'CastleTemplates')


# The engine -----------------------------------------------------------------
@lru_cache(maxsize=None)
def _single(fmt):
    return len(struct.unpack('<' + fmt, bytes(struct.calcsize('<' + fmt)))) == 1


def _read(r, kind, version, m):
    if kind == STR:
        return r.string()
    if kind == PROPS:
        return m.properties(r)
    if kind == NAME:
        return m.names[int.from_bytes(r.take(3), 'little')]
    if kind == FOURCC:
        return r.take(4)[::-1].decode('ascii')
    if isinstance(kind, str):
        value = r.get(kind)
        return value[0] if _single(kind) else value
    if kind[0] == 'items':
        n, = r.get(kind[2])
        if n > MAX_ITEMS:
            raise ValueError('Unreasonable record count')
        return [_read(r, kind[1], version, m) for _ in range(n)]
    if kind[0] == 'chunks':
        return [_read_child(child, kind[1], m) for child in split_chunks(r.take(len(r.data) - r.pos), m.names)]
    out = {}
    _read_fields(r, kind[1], version, m, out)
    return out


def _read_child(child, children, m):
    name = m.names[child.name_id]
    layout = children.get(name, {}).get(child.version)
    if layout is None:
        return dict(chunk=name, version=child.version, raw=child.data)
    try:
        r = Reader(child.data)
        fields = _read(r, layout, child.version, m)
        r.finish()
        return dict(chunk=name, version=child.version, **fields)
    except (ValueError, KeyError, UnicodeDecodeError, struct.error) as error:
        return dict(chunk=name, version=child.version, raw=child.data, error=str(error))


def _read_fields(r, fields, version, m, out):
    for field in fields:
        if field[0] == 'if':
            if field[1](version, out):
                _read_fields(r, field[2], version, m, out)
        else:
            out[field[0]] = _read(r, field[1], version, m)


def _write(out, kind, value, version, m):
    if kind == STR:
        out += string(value)
    elif kind == PROPS:
        out += m.encode_properties(value)
    elif kind == NAME:
        out += m.intern(value).to_bytes(3, 'little')
    elif kind == FOURCC:
        out += value.encode('ascii')[::-1]
    elif isinstance(kind, str):
        out += struct.pack('<' + kind, *((value,) if _single(kind) else value))
    elif kind[0] == 'items':
        out += struct.pack('<' + kind[2], len(value))
        for item in value:
            _write(out, kind[1], item, version, m)
    elif kind[0] == 'chunks':
        for child in value:
            data = _child_payload(child, kind[1], m)
            out += Chunk(m.intern(child['chunk']), child['version'], data).encode()
    else:
        _write_fields(out, kind[1], value, version, m)


def _child_payload(child, children, m):
    if 'raw' in child:
        return child['raw']
    out = bytearray()
    _write(out, children[child['chunk']][child['version']], child, child['version'], m)
    return bytes(out)


def read_child(chunk, m):
    """One child chunk (formats.map.Chunk) read with its layout from CHILDREN;
    as `raw` bytes when it has none or does not parse."""
    return _read_child(chunk, CHILDREN, m)


def child_payload(child, m):
    """The payload of one decoded child chunk (a script node, an MPPositionInfo,
    ...), e.g. for its size."""
    return _child_payload(child, CHILDREN, m)


def _write_fields(out, fields, value, version, m):
    for field in fields:
        if field[0] == 'if':
            if field[1](version, value):
                _write_fields(out, field[2], value, version, m)
        else:
            _write(out, field[1], value[field[0]], version, m)


# Reading and writing ----------------------------------------------------------
def decode(name, version, data, m=None):
    """A section payload as Python values: dicts for records, lists for counted
    items and child chunks. `m` (the map) is needed for its name table."""
    if name in codecs():
        if version not in versions(name):
            raise ValueError(f'Unsupported {name} version {version}')
        return codecs()[name][1](data, version, m)
    if name not in LAYOUTS:
        raise ValueError(f'No layout for {name}')
    if version not in versions(name):
        raise ValueError(f'Unsupported {name} version {version}')
    r = Reader(data)
    value = _read(r, LAYOUTS[name][1], version, m)
    r.finish()
    return value


def encode(name, version, value, m=None):
    """The payload for values as decode returns them; other keys are ignored."""
    if version not in versions(name):
        raise ValueError(f'Unsupported {name} version {version}')
    if name in codecs():
        return codecs()[name][2](value, version, m)
    out = bytearray()
    _write(out, LAYOUTS[name][1], value, version, m)
    return bytes(out)


def read(m, name):
    c = m.chunk(name)
    return decode(name, c.version, c.data, m)


def write(m, name, value):
    c = m.chunk(name)
    c.data = encode(name, c.version, value, m)
