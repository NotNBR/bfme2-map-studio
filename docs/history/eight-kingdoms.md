# Eight Kingdoms: history

> **History.** Recorded with
> [bfme-workshop](https://github.com/NotNBR/bfme-workshop), the repository this
> one grew out of, in October 2026. Its launchers, commands and paths
> (`scripts/launchers/`, `scripts/workshop.py`, `src/host/`, `local/artifacts/`,
> `local/runtime/bfme-host/`) are that repository's and do not exist here.

Eight Kingdoms as it was played, recorded and verified in bfme-workshop; the map itself is described in its [README](../../maps/eight_kingdoms/README.md).

## Play

Run **scripts/launchers/Launch Eight Kingdoms.cmd** in this worktree. It starts a standard native
skirmish: one human playing Men and seven easy AI opponents. Strategic zoom is
enabled. Normal fog, recruitment and faction economies remain active.

The generated map lives in
`local/runtime/bfme-host/mod/maps/map mp bfmexbar eight kingdoms/`.

`local/artifacts/eight-kingdoms/Eight-Kingdoms.zip` contains the map folder, map settings
and minimap artwork. This worktree's mod, profile and reports are separate from
the original checkout. The launcher reads the existing local BFME2 game assets.

## Prepared battle and trailer

The separate **scripts/launchers/Launch Eight Kingdoms Battle.cmd** preset stages a mid-game 4v4
battle. All eight slots have fixed starts and verified alliances. Each player
receives 12 native battalions, one hero and eight completed faction buildings:
96 battalions, eight heroes and 64 buildings across four fronts. The initial
battalions contain 1,548 members. Reinforcements receive staggered attack orders.
Each army also receives four heavy units, for 32 total: Ents, attack trolls,
cave trolls, mountain giants, trebuchets, catapults, ballistas and rams. Ranged
engines begin behind infantry; melee monsters enter from the forward flanks.
Buildings form uneven production clusters beside the approaches, with resource
buildings farther out and entrances oriented toward nearby routes. Each base
has a distinct seeded layout. Two fights take place around bases; two take
place on inland routes with a 1,250-unit exclusion zone for player buildings.
Army approaches and headings vary between fronts instead of repeating a grid.
Each battalion, hero and heavy unit receives a separate terrain-checked contact
lane, avoiding fortress footprints and rock props at the destination. Prepared
battles show one strategic marker per battalion; heroes and heavy units retain
their individual symbols. Visibility checks run before marker grouping.
The map file and normal skirmish launcher retain their existing behavior.

`local/artifacts/eight-kingdoms/trailer/Eight-Kingdoms-Trailer.mp4` is a 76-second,
1920 x 1080, 30 fps trailer. It combines a full-map title card, 64 seconds of
native battle footage, and a closing card, with an original synthesized score.
The footage is cropped to exclude the HUD and lightly brightened during editing.
The recorder suppresses the verified native hero-death notification wrapper
in its recording process so popups do not cover the action. Interactive play
keeps notifications enabled; the game binary on disk is never changed.
It portrays a prepared battle, rather than a match played from an empty base.
The four close battle scenes devote 16 seconds to base sieges and 16 seconds
to open-field fighting. Another 32 seconds show overhead strategic views and
continuous zooms between theatre and battle scales. These use the native
tactical symbol renderer, with icons fading out as the camera approaches.
Zooms use eased logarithmic scale changes, land exactly on the next shot, and
move closer to the siege engines and monsters. Chapter titles fade in and out;
the score's percussion and musical phrases follow the eight-scene edit.
The 720p `Eight-Kingdoms-Mobile.mp4` stays below the 10 MiB cloud upload limit.

To reproduce the capture and edit (requires `imageio-ffmpeg`):

```powershell
& .\local\venv\Scripts\python.exe src/strategic/build.py
& .\local\venv\Scripts\python.exe src/host/launch.py --kingdoms-trailer
& .\local\venv\Scripts\python.exe examples/showcases/eight_kingdoms/edit.py
```

The native recorder temporarily writes about 8.8 GB of raw frames. The encoded
footage and trailer can be retained after removing the temporary `.bgr0` file.
Battle and export checks are recorded beside the video in
`battle-validation.json` and `export-validation.json`.
Native checks also record movement and battalion casualties at each of the
four fronts, heavy-unit orders and movement, and strategic frames with visible
symbols, including duplicate soldier markers collapsed into battalion markers.
Both delivery videos are decoded in full and checked for all 2,280 frames.
The master audio is checked against its loudness and true-peak targets before
export validation passes.

## Rebuild

Follow [setup](../guide/getting-started.md) to prepare the Python environment and local
game assets, then run from the repository root:

```powershell
.\local\venv\Scripts\python.exe scripts/workshop.py map build eight-kingdoms --run-id my-polish-001
```

The seeded generator saves empty, functional, terrain and detailed checkpoints,
retains superseded checkpoint hashes, validates the complete native document,
registers eight start positions and exports a map archive. `build.json` records
the reference SHA-256, map SHA-256, scenery counts and authoring-grid checks.
Each run writes `map/`, `previews/` and `validation/` under
`local/artifacts/maps/eight-kingdoms/<run-id>/`, and installs the package in the local
mod. Rebuilding does not launch the game or run native compatibility checks.

## Verification scope

The authoring-grid audit checks graded starting terrain, all starts connected
through conservative bridge footprints, reachable bridge banks and central access.
Serialized bridge checks verify all 24 names, positions, native local-Y axes and
terrain-relative heights after the ocean translation. These are offline checks;
they do not establish native pathfinding or visual quality.
Scenery reports separately record footprint clearance, per-base vegetation and
reserved building pockets. Terrain connectivity does not include native object
collision, so placement checks are not a substitute for a gameplay test.

When explicitly run, the native check loads BFME2, verifies eight instantiated player builder groups,
captures four locations and checks extension faults and the original profile.
It also orders two actual builders over horizontal and diagonal bridge spans,
recording positions across the decks and arrival on the opposite banks.
Measured outcomes are in `local/artifacts/eight-kingdoms/detail-pass/native/native-validation.json`.

The crossing probes cover individual builders on two bridges. They do not
establish all-bridge horde movement, prolonged AI performance, network play or
competitive balance. WorldBuilder open/save has not been verified.

## Research polish

The October 2026 pass applies the documented
[lighting layout](../format/lighting.md) and
[bridge geometry](../game/roads-and-bridges.md):

- Named terrain/object sunlight slots replace byte-offset edits that also
  brightened a fill light. Fill lights and unresolved fields are preserved.
- Water uses the typed writer, retaining the original water polygon and settings.
- Scenery follows slope, woodland transitions and varied settlement layouts.
- Bridge connectivity uses a conservative 275-unit half-length, with serialized
  origin/orientation checks. Starting clearance includes scenery footprints.

That pass preserved the coastline, both natural internal gaps, ocean margin,
material assignments, eight starts, 24 bridge transforms and gameplay sites. Current
build evidence is recorded below; previous native screenshots and trailer
footage remain evidence of their original map hash.

## Recorded builds

The current vegetation build (`natural-vegetation-02`) contains **3,953 objects**:
140 added base trees, 192 pieces of base undergrowth and 93 props in 36 meadow
pockets, alongside small adjustments to existing placements. All eight bases
have vegetation inside the former exclusion zone. Footprint checks keep the
fortress cores, additional building pockets and route clearances open.
Height, water, passability flags, starts and gameplay-site transforms are unchanged.
All **98 offline unit tests** pass. Reports, package and diagnostic overview are
in `local/artifacts/maps/eight-kingdoms/natural-vegetation-02/`; the map SHA-256 is
`7ce3fb6d443ee6ebdfc701c0b6a42a1956e5274e3d9a6d15d4336188600cb2ad`.
**Native checks remain paused; appearance and gameplay on this hash have not
been verified in BFME2.**

The lighting/scenery polish build (`findings-polish-02`) contains **3,522 objects** and
passes **97 offline unit tests**. All eight starts and 24 bridge banks are
connected in the authoring-grid audit; all serialized bridge placement checks
pass. Terrain, materials, water, starts and gameplay-site transforms match the
previous build. Only `ObjectsList` and `GlobalLighting` payloads changed.
The map SHA-256 is
`d9afec1095cb12b31054be833bfd34a0f88860b1fc542c451689784cf613a3dc`.
Local reports and a diagnostic overview are in
`local/artifacts/maps/eight-kingdoms/findings-polish-02/`.
This earlier polish hash was also checked offline only.

The previous native-checked build contains 3,731 object records and passed 29 automated tests.
BFME2 loaded the map, instantiated all eight player builder groups, rendered all
four camera views and completed both native builder crossing probes with no
extension faults or original-profile changes. The packaged map SHA-256 is
`f4d7f626bc2863adb86abddbea90b3545187b0d5570623090b8691218a0d21ea`.

That native tour and 8K photograph include both reshaped internal
hollows. The photograph metadata records the matching map hash.
