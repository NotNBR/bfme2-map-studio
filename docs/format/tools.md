# Inspecting map files

Tools that read a `.map` or a whole archive without changing it. Generated
reports stay local; the retail corpus is not redistributed.

```powershell
mw diff MAP OTHER                       # what differs between two maps, in readable lines
mw workspace inspect 'path/to/map.map'  # measure a map and validate its terrain and texture references
python -m mapworkshop.mapkit.checks.analyze 'path/to/map.map' --out local/renders/map-analysis.json
python -m mapworkshop.mapkit.checks.coverage 'path/to/Maps.big' --out local/renders/map-coverage.json
python -m mapworkshop.mapkit.checks.terrain_audit 'path/to/Maps.big' --out local/renders/terrain-audit.json
mw test --corpus                        # every section of every stock document, read and written back
```

- `analyze` decodes every record of one map, scripts and terrain records
  included, and reports what it could not resolve.
- `coverage` inventories which sections and versions an archive's documents
  hold, with each document's hash and exact round-trip status.
- `terrain_audit` surveys the terrain records of an archive's maps.
- `mw test --corpus` checks the writers: every section of all 270 documents in
  `Maps.big`, `Bases.big` and `Libraries.big`, decoded and encoded again
  through `formats.sections`, gives back its exact bytes.

In code, `sections.read(m, name)` gives a section's values and
`sections.write(m, name, value)` stores changed ones; `Map.objects()` and
`Map.set_objects()` do the same for objects
([formats/sections.py](../../src/mapworkshop/formats/sections.py)).

## Limits

Observed versions are not an exhaustive list of legal files. Structural
decoding does not establish every field's meaning or permit arbitrary edits.
Modern terrain authoring requires v18; older versions have inspection support.
Preserve unknown data and references, and refuse spatial transforms whose
coordinate-bearing payloads cannot be updated safely. [Coverage](coverage.md)
records the gaps.
