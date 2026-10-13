# Ithilien Frontier

`build.py` builds this map from the stock map "map wor ithilien" (from `mw setup`).

```
mw build ithilien-frontier     build it
mw view ithilien-frontier      look at it in the viewer
mw play ithilien-frontier      install it into the game and start BFME2
```

> The native checks, launch presets and captures recorded below were made with
> [bfme-workshop](https://github.com/NotNBR/bfme-workshop), whose `workshop.py play` presets and launchers are not
> part of this repository.

A native BFME2 battlefield for bfme-workshop's strategic zoom, built by enlarging the
original Ithilien landscape and adding a reproducible scenery pass. It retains
BFME2 terrain, assets, native starts and river crossings.

Double-click **scripts/launchers/Launch Ithilien Frontier.cmd** in the project root. It starts a
standard Mordor-versus-Elves skirmish, fully revealed, at 1600 x 1200. This map
launch uses normal base-building; the existing prepared Grey Mountains battle
remains available through its own shortcut.

## Battlefield

- 840 x 953 playable tiles: 800,520 tiles, **3.001 times Grey Mountains' area**.
- 900 x 1,013 stored terrain samples, including a 30-tile border.
- Two native player starts and large open areas around the bases.
- Four named fords, twelve river strips, wooded hills and Gondorian ruins.
- Sculpted mountain walls, ridges, rolling hills, an eastern escarpment and a
  raised western ruin terrace. Maximum terrain elevation is about 913 game units;
  the median playable elevation rises from about 48 to 152.
- River ribbons and submerged beds are unchanged. Main road surfaces and 700-unit
  base circles keep their original elevations, with smooth shoulders into new hills.
- Steep new faces receive native rock textures; slopes above 1.05 rise/run are
  additionally flagged impassable. Native engine and object collision still apply.
- 5,854 placed records, including **4,111 added** trees, undergrowth, rocks and ruins.
- Scenery generation protects a 650-world-unit radius around base markers and
  135 units either side of native road segments. Collision/pathfinding also depends
  on the original terrain and object geometry; these spacing rules are not a full
  pathfinding guarantee.
- Native texture scale retained, with terrain texture subtiles and secondary
  blends rephased for the expanded grid.
- Strategic camera ceiling 16,000. Native distance fog disabled for the far view.

## Build and editable files

```powershell
.\local\venv\Scripts\python.exe -m examples.maps.ithilien_frontier.build
.\local\venv\Scripts\python.exe src/host/launch.py --window --map-check
```

The builder reads only the isolated stock Ithilien copy, then writes:

`scripts/launchers/Setup Workshop.cmd` also rebuilds and registers the map after extracting the
stock files, so repeating setup retains this launch option.

```text
local/runtime/bfme-host/mod/maps/map mp bfmexbar ithilien frontier/
  map mp bfmexbar ithilien frontier.map
  map.ini
  map mp bfmexbar ithilien frontier_art.tga
  map mp bfmexbar ithilien frontier_pic.tga
```

Preview images are copied from the source map because its overall terrain layout
is retained. The builder adds a separate multiplayer entry to the isolated map
cache; that registration is required for the native `-file` startup to start a
skirmish. Use the short virtual path `maps\map mp bfmexbar ithilien frontier.map`.

The default detail seed is 20261008. `--detail 0` produces a terrain/format probe;
the normal build requests 4,200 additions and accepts fewer when spacing constraints
leave no suitable locations. Dimensions and detail count have explicit CLI options.
The builder refuses embedded scripts or unhandled coordinate sections instead of
silently carrying stale positions into an enlarged map.

The generated `.map` is a native WorldBuilder document. Direct WorldBuilder UI
opening/saving has not been verified because the Computer Use helper failed to
initialize. Original game files and the openbfme2 reference checkout remain untouched.

## Verification and limits

The native BFME2 smoke test loads the complete map, advances the simulation, reveals
it, and photographs the raised ruins, wooded hills, northern mountain pass and
strategic overview. A held camera target prevents the previous repeated-river views;
the report records the actual focus coordinates of every shot.
Screenshots are read directly from the game's D3D9 render target because Windows'
GDI capture returned a blank image. Readback is opt-in and inactive during normal
play. Results and pictures are in `local/artifacts/ithilien-frontier/`.

This is a first playable large-map build. Short native load/render checks do not
establish long-match performance, army-scale pathfinding at every crossing, multiplayer
compatibility or WorldBuilder's UI size limit. The current generator caps stored
grids at 1,024 samples per axis as an experiment bound, not a discovered engine limit.

Map data and copied retail previews stay in ignored local/runtime/artifact folders. Source
tooling and recipes are in Git; the original BFME2 assets are not redistributed.

## High-resolution map photograph

```powershell
.\local\venv\Scripts\python.exe src/host/launch.py --window --map-photo
```

This starts a dedicated native capture session and exports an 8,000 x 8,000 PNG
and JPEG under `local/artifacts/ithilien-frontier/photo/`. The camera is tilted 20 degrees
from vertical. Sixty orthographic tiles share a fixed camera; only the view plane
moves. Each frame contributes its upper 720 rows, excluding the native HUD, and
pixels are assembled without upscaling. Trees, ruins, textures and water are
rendered by BFME2. The simulation and water animation continue during capture,
so this is a landscape portrait rather than one simultaneous gameplay frame.
Photo mode is opt-in and does not alter the normal gameplay camera.
