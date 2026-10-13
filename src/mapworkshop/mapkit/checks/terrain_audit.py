"""Read-only terrain survey of a user-supplied Maps.big; exports no game assets."""

import argparse
from collections import Counter
import json
from pathlib import Path

from mapworkshop.formats.big import BigArchive
from mapworkshop.formats.map import Map, sha
from mapworkshop.mapkit.checks.analyze import blend_details


def audit(path):
    archive = BigArchive(path)
    results, skipped = [], []
    fields = ('blend_directions', 'blend_flags', 'long_diagonal_values',
              'custom_edge_classes', 'blend_markers', 'cliff_flags', 'record_issues')
    totals = {key: Counter() for key in fields}
    versions = Counter()
    for name in sorted(archive.entries):
        if not name.endswith('.map'):
            continue
        try:
            data = archive.read_bytes(name)
            m = Map(data)
            versions[str(m.chunk('BlendTileData').version)] += 1
            detail = blend_details(m)
            if m.encode() != m.original:
                raise ValueError('Decompressed map round-trip differs')
            results.append(dict(map=name, file_sha256=sha(data),
                                raw_roundtrip_exact=True, terrain=detail))
            for key in fields:
                totals[key].update(detail[key])
        except (ValueError, KeyError) as error:
            skipped.append(dict(map=name, reason=str(error)))
    return dict(schema=1, scope='BFME2/legacy v8..18 terrain inspection; range anomalies reported, no renderer validation',
                maps_checked=len(results), maps_skipped=len(skipped), versions=dict(versions),
                blend_records=sum(r['terrain']['blend_records'] for r in results),
                cliff_mappings=sum(r['terrain']['cliff_mappings'] for r in results),
                totals={k: dict(v) for k, v in totals.items()}, maps=results, skipped=skipped)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.archive.resolve() == args.out.resolve():
        parser.error('Output must not overwrite the source archive')
    report = audit(args.archive)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'maps'}))


if __name__ == '__main__':
    main()
