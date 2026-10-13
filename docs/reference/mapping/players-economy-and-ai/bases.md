# Bases and script libraries

BFME2 mapping extends beyond `Maps.big`. `Bases.big` contains base templates and
faction build lists; `Libraries.big` contains reusable script/team libraries.
These remain local licensed inputs. The repository ships original test fixtures
and tools, not extracted retail templates or scripts.

## Corpus and versions

The 9 October 2026 local audit found 150 `.bse` and two `.map` documents in
`Bases.big`, plus 51 `.map` documents in `Libraries.big`. All parse and preserve
their decompressed bytes. The base templates contain **4,817 building entries**,
**51 paths and 951 points**. Both standalone faction lists and embedded side
lists contain **677 build entries** in the two base `.map` documents; these are
two stored representations, not 1,354 distinct buildings.

Additional inspected variants include terrain v8/9/11/15/16/17, SidesList v5,
PlayerScriptsList v6, EnvironmentData v2, PolygonTriggers v4, RiverAreas v1,
StandingWaveAreas v1 and CameraAnimationList v1. Their layouts consume the
corpus exactly. Runtime behavior and authoring support do not follow from that
fact. Modern terrain editing still requires v18. Empty variant records need
nonempty synthetic/source checks before claiming their full compatibility.

```powershell
python -m mapkit.coverage 'C:\path\to\BFME2\Bases.big' --out local/artifacts/bases-coverage.json
python -m mapkit.coverage 'C:\path\to\BFME2\Libraries.big' --out local/artifacts/libraries-coverage.json
python -m mapkit.script_audit 'C:\path\to\BFME2\Libraries.big' --out local/artifacts/library-scripts.json
```

## CastleTemplates

`formats/castles.py` reads/writes v1–5 with explicit version guards. The payload
starts with a four-byte name key (low byte retained; upper 24 bits refer to the
map's name table), then a building count. Every building stores two strings
(instance name, object template), XYZ floats and an angle float. Version 4 adds
two signed integers: priority and phase. Version 2 adds a path count; v5 adds
each path's name. Each path has a point count, followed by XYZ signed integers
in v2 or XY floats from v3 onward.

The matched writer derives the key from the `.bse` filename before the first
dot. It chooses the center from base-object positions, or from member-piece
positions if there are no base objects. It stores building and path coordinates
relative to that center. Piece selection uses `objectBaseName` and excludes
objects marked `objectIsABase`; the source also treats kind-of bit 18 specially.
Do not guess that bit's meaning from another game's enum.

The matched retail reader **discards priority/phase, path names, and the third
integer in old path points**. Preserve them in the file nevertheless: editor
and other consumers may use them. A section alone does not make a complete
working AI base; object definitions, base references and AI selection still need
native tests. The writer is not yet a full original `.bse` project generator.

## Side build lists and library linking

The matched side reader supports at most 20 sides. It reads an embedded build
entry's XYZ but forces its runtime Z to zero; the standalone faction-list reader
retains Z. Do not treat the two contexts as interchangeable. Build-list fields
and units are listed in [the mapping reference](../file-structure/reference.md).

Library loading reads teams, player scripts and per-side library names from a
map document. The matched linker recursively visits referenced libraries,
tracks names case-insensitively to avoid cycles and merges scripts from library
side 1. It remaps copied team ownership to the receiving player and tags copied
teams with their source library. This explains why a library need not be a
playable skirmish map. Merge precedence and placeholder substitution still need
original native scenarios before becoming an authoring contract.

The expanded script audit reads all 152 base and 51 library documents. Six
base signatures and fourteen library signatures have the same internal name
and argument types at a different current opcode ID. Three other library
signatures require argument migration: two forms of `SHOW_MILITARY_CAPTION`
and the older two-argument `OVERRIDE_PLAYER_COMMAND_POINTS`. The comparison
tool reports these separately and never rewrites them automatically. Native
behavior of those migrations remains to be tested.

Source: [Open-BFME-2 SidesListDataChunks.cpp](https://github.com/Open-BFME/Open-BFME-2/blob/33f02e4222f3ac9c284d9b71cf5e7438799988bb/Code/GameEngine/Source/GameLogic/Map/SidesListDataChunks.cpp).
The ledger marks castle reader/writer RVAs `0x0032F664`/`0x0032B88C`, side reader
`0x0032F13C`, faction-list reader `0x0032CE9E`, library-list reader `0x0032C779`
and library linker `0x0032FA07` matched. These are upstream claims cross-checked
against local file layouts; this project has not rerun their compiler matching.
