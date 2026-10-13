# File structure

BFME2 maps use a chunked binary document with a shared name table. Chunks describe
terrain, objects, sides, scripts, water, cameras and other map state; many records
refer to assets and rules in the installed game rather than embedding them.

**Start with the [map-file specification](specification.md).** It describes the
package, compression, primitive encodings, container, section payloads, version
differences and cross-record references, with byte layouts and a worked hex example.

| Reference | Use it for |
| --- | --- |
| [Map-file specification](specification.md) | The technical format description, read from outer file to individual fields |
| [Container and terrain format](format.md) | Headers, compression, name IDs, properties, section offsets and spatial units |
| [Versioned reference and coverage](reference.md) | Corpus results, section/version tables, additional record layouts and authoring constraints |
| [Original-map construction findings](ashen-march-findings.md) | How The Ashen March was built without a donor map |
| [Bases and libraries](../players-economy-and-ai/bases.md) | `.bse` files, castle templates and script libraries |

The local audit covers **270 documents**, **23 section names** and **43
section/version pairs** from `Maps.big`, `Bases.big` and `Libraries.big`. Every
observed layout has a decoder and an encoder, from one layout per section in
[formats/sections.py](../../../../src/mapworkshop/formats/sections.py): every
section of every document decodes to Python values and encodes back to its
exact bytes (`mw test --corpus`). Unknown field meanings are retained and labelled.

## Tools

```powershell
mw workspace inspect 'path/to/map.map'
python -m mapkit.analyze 'path/to/map.map' --out local/artifacts/map-analysis.json
python -m mapkit.coverage 'path/to/Maps.big' --out local/artifacts/map-coverage.json
```

In code, `sections.read(m, name)` gives a section's values and
`sections.write(m, name, value)` stores changed ones; `Map.objects()` and
`Map.set_objects()` do the same for objects.

Run from an installed checkout; generated reports stay local. The corpus is not
redistributed. See the [repository setup](../../../getting-started.md).

## Limits

Observed versions are not an exhaustive list of legal files. Structural decoding
does not establish every field's meaning or permit arbitrary edits. Modern
terrain authoring requires v18; older versions have inspection support. Preserve
unknown data and references, and refuse spatial transforms whose coordinate-bearing
payloads cannot be updated safely. The [reference](reference.md) records the gaps.
