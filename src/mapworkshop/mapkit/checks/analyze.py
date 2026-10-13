"""Read-only structural dissection of native BFME2 maps.

Run: python -m mapworkshop.mapkit.checks.analyze FILE.map --out analysis.json
Layouts cross-checked with OpenSAGE; unresolved payloads are explicitly reported.
"""

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from mapworkshop.formats import sections
from mapworkshop.formats.map import Map, sha


# The sections read as records (the rest through nested() or the terrain).
RECORD_SECTIONS = {'Teams', 'SidesList', 'BuildLists', 'NamedCameras', 'WaypointsList', 'TriggerAreas',
                   'StandingWaterAreas', 'RiverAreas', 'StandingWaveAreas', 'EnvironmentData', 'PostEffectsChunk',
                   'GlobalLighting', 'CameraAnimationList', 'SkyboxSettings', 'PolygonTriggers', 'CastleTemplates'}
WAVE_PARAMETERS = ('final_width', 'final_height', 'initial_width_fraction', 'initial_height_fraction',
                   'initial_velocity', 'time_to_fade', 'time_to_compress', 'second_wave_time_offset',
                   'distance_from_shore')


def props(properties):
    return {k: v for k, _, v in properties}


def records(m, name):
    """A section as formats.sections reads it, with property dictionaries as
    plain dicts and the wave parameters named."""
    value = sections.read(m, name)
    if name == 'Teams':
        return [props(p) for p in value]
    if name == 'SidesList':
        return dict(unknown_boolean=value.get('unknown_boolean'),
                    players=[dict(props(p['properties']), build_list=p['build_list']) for p in value['players']])
    if name == 'StandingWaveAreas':
        for item in value:
            item['wave_parameters'] = dict(zip(WAVE_PARAMETERS, item['wave_parameters_raw']))
    return value


def nested(m, name):
    """A section of child chunks, each with its name, version and size."""
    if name == 'PlayerScriptsList':
        from mapworkshop.formats.scripts import player_scripts
        return player_scripts(m)
    expected = {'MPPositionList': 0, 'LibraryMapLists': 1}
    if m.chunk(name).version != expected.get(name):
        raise ValueError(f'Unsupported {name} version {m.chunk(name).version}')
    result = []
    for child in sections.read(m, name):
        item = dict(chunk=child['chunk'], version=child['version'], bytes=len(sections.child_payload(child, m)))
        if 'raw' in child:
            item['payload_decoded'] = False
        else:
            item.update((k, v) for k, v in child.items() if k not in ('chunk', 'version'))
            if child['chunk'] == 'MPPositionInfo':
                item.setdefault('side_restrictions', [])
        result.append(item)
    return result


def blend_details(m):
    from mapworkshop.formats.terrain import terrain_records

    b = m.blend(inspection=True)
    tail = terrain_records(m, b)
    blends, cliffs = tail['blends'], tail['cliffs']
    tile_count = sum(t['tile_count'] for t in b['textures'])
    issues = Counter(b['inspection_issues'])
    for record in blends:
        if record['direction'] is None: issues['unrecognized_blend_direction'] += 1
        if record['unknown_flag_bits']: issues['unknown_blend_flag_bits'] += 1
        if record['long_diagonal'] not in (0, 1): issues['nonboolean_long_diagonal'] += 1
        if record['marker'] != 0x7ada0000: issues['unexpected_blend_marker'] += 1
        if not -1 <= record['custom_edge_class'] < len(tail['edge_textures']):
            issues['custom_edge_outside_table'] += 1
    for record in cliffs:
        if record['flip'] not in (0, 1) or record['mutant'] not in (0, 1):
            issues['nonboolean_cliff_flags'] += 1
    for name, records in [('blend', blends), ('cliff', cliffs)]:
        issues[f'{name}_tile_outside_palette'] = sum(r['tile'] >= tile_count for r in records)
    return dict(texture_cells=tail['texture_cells'], textures=tail['textures'],
                blend_records=len(blends), cliff_mappings=len(cliffs),
                declared_blend_count=tail['declared_blend_count'],
                declared_cliff_count=tail['declared_cliff_count'],
                edge_texture_cells=tail['edge_texture_cells'], edge_textures=tail['edge_textures'],
                tail_fully_consumed=True, cliff_mapping_offset=tail['cliff_mapping_offset'],
                interpretation='Generals source names; BFME2 v18 layout cross-checked on retail maps',
                blend_example=blends[:1], cliff_example=cliffs[:1],
                blend_directions=dict(Counter(r['direction'] or r['direction_hex'] for r in blends)),
                blend_flags=dict(Counter(str(r['flags']) for r in blends)),
                long_diagonal_values=dict(Counter(str(r['long_diagonal']) for r in blends)),
                custom_edge_classes=dict(Counter(str(r['custom_edge_class']) for r in blends)),
                blend_markers=dict(Counter(hex(r['marker']) for r in blends)),
                cliff_flags=dict(Counter(f"{r['flip']},{r['mutant']}" for r in cliffs)),
                record_issues={k: v for k, v in issues.items() if v},
                arrays=[dict(name=k, shape=list(v.shape), offset=b['offsets'][k],
                             minimum=int(v.min()), maximum=int(v.max()), nonzero=int(np.count_nonzero(v)))
                        for k, v in b['arrays'].items()])


def analyze(data, source=''):
    m = Map(data)
    report = m.report(inspection=True)
    report['source'] = source
    report['file_sha256'] = sha(data)
    report['file_bytes'] = len(data)
    report['container'] = data[:4].decode('ascii', errors='replace')
    report['decompressed_bytes'] = len(m.original)
    offset = len(m.original) - sum(10 + len(c.data) for c in m.chunks)
    report['name_table'] = dict(entries=len(m.names), starts_at=8, ends_at=offset)
    for info, c in zip(report['chunks'], m.chunks):
        info.update(header_offset=offset, payload_offset=offset + 10, end_offset=offset + 10 + len(c.data))
        offset += 10 + len(c.data)
    report['decoded_sections'], report['unresolved_sections'] = {}, {}
    for name in ['SidesList', 'Teams', 'BuildLists', 'NamedCameras', 'WaypointsList', 'TriggerAreas',
                 'StandingWaterAreas', 'RiverAreas', 'StandingWaveAreas', 'EnvironmentData', 'PostEffectsChunk',
                 'GlobalLighting', 'CameraAnimationList', 'CastleTemplates', 'SkyboxSettings', 'PolygonTriggers',
                 'MPPositionList', 'LibraryMapLists', 'PlayerScriptsList']:
        if name in ('CastleTemplates', 'SkyboxSettings', 'PolygonTriggers') and not any(
                m.names[c.name_id] == name for c in m.chunks):
            continue
        try:
            report['decoded_sections'][name] = nested(m, name) if name in ('MPPositionList', 'LibraryMapLists', 'PlayerScriptsList') else records(m, name)
        except (ValueError, KeyError) as error:
            report['unresolved_sections'][name] = str(error)
    report['blend_details'] = blend_details(m)
    objects = m.objects()
    report['waypoints'] = [dict(position=[o['x'], o['y'], o['z']], properties={k: v for k, _, v in o['properties']})
                           for o in objects if o['template'] == '*Waypoints/Waypoint']
    report['object_flags'] = dict(Counter(str(o['flags']) for o in objects))
    from mapworkshop.mapkit.roads import inspect as inspect_roads
    report['roads'] = inspect_roads(objects)
    report['object_layers'] = dict(Counter(v for o in objects for k, _, v in o['properties'] if k == 'objectLayer'))
    report['object_example'] = {k: v for k, v in objects[0].items() if k != 'chunk'} if objects else None
    report['not_semantically_decoded'] = ['Script opcode meanings, argument constraints and execution behavior', 'Build-list runtime behavior and whiner flag',
                                         'Lighting third array, flag, vector and final-value semantics', 'Camera animation interpolation and focal-parameter semantics',
                                         'BFME2-specific terrain rendering behavior and camera fields']
    if m.encode() != m.original:
        raise AssertionError('Analysis failed lossless round-trip check')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('map', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    data = args.map.read_bytes()
    report = analyze(data, str(args.map.resolve()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if args.map.read_bytes() != data:
        raise RuntimeError('Source changed during analysis')
    print(json.dumps(dict(report=str(args.out), chunks=len(report['chunks']), unresolved=report['unresolved_sections'], source_unchanged=True)))


if __name__ == '__main__':
    main()
