"""Inventory actual map sections without treating preserved bytes as understood.

Read-only: accepts a user-supplied Maps.big; exports structural evidence, not maps.
"""

import argparse
from collections import Counter
import json
from pathlib import Path

from mapworkshop.formats.big import BigArchive
from mapworkshop.formats.map import Map, Reader, sha
from mapworkshop.mapkit.checks.analyze import RECORD_SECTIONS, blend_details, nested, records


def section(m, c):
    name=m.names[c.name_id]
    result=dict(name=name,version=c.version,bytes=len(c.data),layout='opaque',
                semantics='See docs/reference/mapping/file-structure/reference.md; parsing alone is not semantic verification')
    try:
        if name in RECORD_SECTIONS:
            value=records(m,name)
            result['layout']='partial' if name in ('SidesList','NamedCameras','StandingWaveAreas','GlobalLighting','TriggerAreas','CameraAnimationList') else 'decoded'
            if name=='SidesList':
                result['build_entries']=sum(len(p['build_list']) for p in value['players'])
            if name=='BuildLists':
                result['build_entries']=sum(len(p['items']) for p in value)
            if isinstance(value,list): result['records']=len(value)
        elif name in ('MPPositionList','LibraryMapLists','PlayerScriptsList'):
            value=nested(m,name)
            result.update(layout='decoded',records=len(value))
            if name=='PlayerScriptsList':
                result['script_children']=sum(len(v.get('children',[])) for v in value)
                result['layout']='partial'  # Even empty scripts don't verify opcode semantics.
            if any(v.get('payload_decoded') is False for v in value):result['layout']='partial'
        elif name=='HeightMapData':
            m.heightmap();result['layout']='decoded'
        elif name=='BlendTileData':
            value=blend_details(m)
            result.update(layout='partial',record_issues=value['record_issues'])
        elif name=='ObjectsList' and c.version==3:
            result.update(layout='decoded',records=len(m.objects()))
        elif name=='WorldInfo' and c.version==1:
            r=Reader(c.data);m.properties(r);r.finish();result['layout']='decoded'
        else:
            result['reason']='No verified decoder for this section/version'
    except (ValueError,KeyError) as error:
        result.update(layout='unsupported',reason=str(error))
    return result


def audit(path):
    archive=BigArchive(path)
    maps=[];failures=[];totals={}
    for name in sorted(archive.entries):
        if not name.endswith('.map'):continue
        try:
            data=archive.read_bytes(name);m=Map(data)
            entries=[section(m,c) for c in m.chunks]
            for entry in entries:
                key=(entry['name'],entry['version'])
                row=totals.setdefault(key,dict(name=key[0],version=key[1],maps=0,bytes=0,
                                              layouts=Counter(),nonempty_build_maps=0,build_entries=0,
                                              script_children=0,examples={}))
                row['maps']+=1;row['bytes']+=entry['bytes'];row['layouts'][entry['layout']]+=1
                row['build_entries']+=entry.get('build_entries',0)
                row['nonempty_build_maps']+=bool(entry.get('build_entries',0))
                row['script_children']+=entry.get('script_children',0)
                row['examples'].setdefault(entry['layout'],dict(map=name,reason=entry.get('reason')))
            maps.append(dict(map=name,file_sha256=sha(data),raw_roundtrip_exact=m.encode()==m.original,sections=entries))
        except (ValueError,KeyError) as error:
            failures.append(dict(map=name,reason=str(error)))
    return dict(schema=1,scope='Supplied BFME2 map corpus; not proof of every legal map or engine rule',
                semantics_complete=False,maps=len(maps),container_failures=failures,
                sections=[totals[key] for key in sorted(totals)],files=maps)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args()
    if args.archive.resolve()==args.out.resolve():parser.error('Output must not overwrite the archive')
    report=audit(args.archive)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='files'}))


if __name__=='__main__':main()
