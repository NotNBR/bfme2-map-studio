# The Godot viewer: plan

## TL;DR

- **What:** the studio's map viewer moves onto OpenBFME, the Godot rebuild of
  RotWK. The Python viewer goes away once the new one does everything it does.
- **Why:** OpenBFME draws a map like the game, units animated, and opens
  Helm's Deep in about 4 seconds, where the Python viewer takes about 30.
- **How:** OpenBFME stays an untouched submodule, the official repository's
  `main`, and is used as a library. Everything the studio adds (marks, Photo
  mode, cameras, menus, overlays) lives in the studio's own small Godot
  project. Python keeps doing what it already does: builds, map analysis, the
  marks summaries for agents.
- **The one missing piece:** OpenBFME cannot open maps from outside the game
  yet. We add that the way retail RotWK does it, reading the player's user maps
  folder, as a pull request to OpenBFME (it is on their roadmap as MOD-5).
- **Clean means:** the submodule is pinned to a pushed commit and updated by
  plain git commands, nothing is ever written into it, and checks in `mw test`
  and `mw doctor` prove it.
- **Order:** groundwork (the user-maps change, a clean submodule), then a
  small proof that the design holds, then the viewer feature by feature, then
  `mw render` and the switch.
- **Checked by:** two reviewing agents at the end of every phase, one for the
  design, one for cleanliness.
- **Still to decide:** who writes the user-maps pull request, and whether
  `mw play --godot` and battles may lose the features from the fork's open pull
  requests until OpenBFME merges them.

## Where we are

**OpenBFME can already do most of the drawing.** Its map viewer
(`godot/scripts/map_viewer.gd`) opened the studio's Helm's Deep build,
measured on 2026-10-20:

| | OpenBFME's map viewer | Studio viewer |
|---|---|---|
| Open the map | 3.8 s in all (Godot start, game files, screenshot); the map itself in 0.29 s | about 30 s |
| Units | 1,298 static and 10,748 animated objects, no model missing | 12,024 objects, frozen in their first idle frame |
| Roads | drawn | not drawn |

**The official repository cannot open studio maps.** OpenBFME reads only the
game's verified archives and refuses loose map files in the install folders as
contamination (its stop S-039, PLAN rules 6 and 7: everything follows retail
semantics). The studio reaches it today only through the user's fork
(NotNBR/openbfme-godot), whose commit `e19bf823` mounts extra archives named in
an environment variable. That is not retail behaviour, so it is not what
OpenBFME wants. The fork is 54 commits ahead of official `main` and 3 behind:
besides that mount, the user's open pull requests (walls, siege, weather, big
battles), another contributor's, and studio-only changes (map cinematics in
skirmish, staged armies, `--no-shroud`, the free-camera tilt).

**The submodule is not clean** (audit of 2026-10-20):

- `.gitmodules` sets `update = none` (git clone and `mw setup` skip it;
  `native/openbfme.py` fetches it itself, only when it is missing) and
  `ignore = dirty` (the studio's `git status` hides what is changed inside it).
- Its worktree is dirty: 4 images show as modified (upstream committed them
  outside Git LFS), 58 `.uid` and 3 `.import` files are untracked (Godot's
  import writes them; upstream tracks most `.uid` files and its syncs miss
  some), and Godot's cache and the 83 MB library are built inside it.
- Nothing checks that it sits at the commit the studio records. That commit
  (`f2e889c9`, tag `studio-2026-10-19-2`) is pushed and fetchable.

## Decisions

Taken:

1. The submodule follows the **official** repository's `main` (Open-BFME/openbfme-godot).
2. The Godot viewer **replaces** the Python viewer.
3. BFME2 maps are shown with RotWK's data, as RotWK itself plays them (RotWK
   reads BFME2's archives and the same map format; a few templates differ).
4. `mw render` moves to Godot as well, with a flag to render in the original
   game instead, for comparison.

Open:

1. Who writes the user-maps pull request: the studio's session, or one of the
   sessions working on OpenBFME (`open-bfme-2-3c`, `open-bfme-2-59`).
2. Whether `mw play --godot`, `mw battle` and the Battle of Helm's Deep may
   lose walls, siege, weather, cinematics and `--no-shroud` until OpenBFME
   merges the user's pull requests for them. Proposing the studio-only changes
   upstream too (`--no-shroud`, the camera tilt) would shorten that.
3. When the sessions working on OpenBFME can pause for phase 0, which rebuilds
   the engine and moves its library.

## Architecture

```
studio repository
  src/mapworkshop/viewer/godot/            the studio's Godot project (scenes, GDScript):
                                           cameras, marks, Photo mode, menus, overlays,
                                           the link to Python
  src/mapworkshop/native/openbfme-godot/   submodule: official OpenBFME, never written to

local/openbfme/                            generated, ignored by git
  viewer/                                  the studio project assembled with OpenBFME's
                                           library and its four shaders; Godot's cache here
  project/, build/                         OpenBFME's own Godot project and engine build

running
  Godot window (the viewer)  <-- local socket, JSON lines -->  Python (mw view)
```

**What OpenBFME provides, and all the studio uses:**

- its library (the GDExtension), built from the submodule;
- four shaders it loads by fixed path: `res://shaders/terrain.gdshader`,
  `water_standing.gdshader`, `road.gdshader`, `river.gdshader` (its other
  `res://` files belong to its game menus);
- four classes: `RetailFileSystem` (the game's files), `MapTerrainBuilder`
  (`build_map`: terrain, water, rivers, roads), `MapObjectBuilder` (`setup`,
  `build_objects`, `advance`: objects and animated units) and `PathfindView`.

**What each side does:**

| Feature | In Godot | From Python |
|---|---|---|
| Drawing the map | OpenBFME's builders; units animated by `advance()` | the build, installed as a user map |
| Edit and Photo cameras | `Camera3D`, the studio's camera maths carried over | the terrain heights, once per load, for picking the ground and keeping the camera on it |
| Marks | drawn draped on the terrain and edited in Godot; saved as `local/marks/<map>.json` in today's format | what each mark covers (the marks panel, Copy for agent), from today's code |
| Photo mode | `CameraAttributesPhysical`: focal length, aperture, focus, exposure, depth of field; the sensor and frame rules of today's lens | |
| Saved views, Copy view | the same `local/views` JSON and `mw render` command | |
| Walkability, river flow | drawn over the terrain | computed as today, sent as an image and line data |
| Weather and sun presets | reload | the map's `map.ini` variant |
| Build, Test In-Game, Properties | buttons | today's code runs them |
| Live reload | the map built again in place | tells Godot a build has finished |
| `mw render` | the same scene in screenshot mode, on a hidden desktop as `mw capture` does | the command and the views |

**Rules that keep it clean:**

1. Nothing is written into the submodule. Godot's import, its cache and the
   engine build go to `local/openbfme/`.
2. The studio uses only the library's methods and the four shaders, never
   OpenBFME's scenes or scripts, and no studio code goes into OpenBFME.
3. Studio maps reach OpenBFME only as retail RotWK reads them: the user maps
   folder.
4. The submodule is pinned. A headless check in `mw test` builds a test map
   through the library (`build_map`, `build_objects`; this needs no window),
   so a submodule update that breaks the studio fails at once.
5. Analysis stays in Python and reaches Godot as data; Godot never reimplements
   what `mapkit` computes.

## The engine change: user maps

Retail RotWK loads WorldBuilder maps from the player's user data folder,
`My The Lord of the Rings, The Rise of the Witch-king Files\Maps\<name>\`.
OpenBFME already ports that folder (`engine/src/GameClient/UserDataFolder.cpp`,
from RW 0x644148) for options and Create-a-Hero saves, but does not read its
`Maps` subfolder. OpenBFME's roadmap lists it (milestone M10, MOD-5:
"WorldBuilder-made user maps"); no pull request or issue for it existed on
2026-10-20.

- The pull request reproduces retail's behaviour in OpenBFME's style, with the
  retail addresses and tests: opening a user map by name (what the viewer
  needs), then the user map cache and the skirmish list (which may follow in a
  second pull request).
- The studio then installs a build into OpenBFME's user maps folder exactly as
  it does for the game (`game.install`), and the archive mount goes.
- Until it is merged, the submodule sits on a minimal branch of the fork:
  official `main` plus that one commit, tagged at each pin. Once merged, the
  submodule follows official `main` and the studio no longer needs the fork.

## Phases

Each phase ends with both reviewing agents' checks (below) passing.

### Phase 0: groundwork

| Step | Deliverable | Verified by |
|---|---|---|
| 0.1 | The user-maps pull request to OpenBFME; meanwhile a minimal fork branch (official `main` + that commit) | OpenBFME's tests; a studio map opens in its map viewer from the user maps folder |
| 0.2 | Fork-side fixes offered upstream: the missing `.uid` files, the 4 images through LFS | the submodule's `git status` clean after an import |
| 0.3 | The submodule pinned to that branch, `update = none` and `ignore = dirty` removed, `source()` checks out the recorded commit when it differs | a fresh `git clone --recursive` and `mw setup` in an empty folder |
| 0.4 | OpenBFME's Godot import and the engine build moved to `local/openbfme/` | `git status --ignore-submodules=none` clean after a build and a test game |
| 0.5 | `mw doctor` and `mw test` check the submodule's commit and cleanliness; `docs/licenses/THIRD_PARTY.md` names OpenBFME | the checks fail on a deliberately dirtied copy |
| 0.6 | The studio's Godot project skeleton and its assembly under `local/openbfme/viewer/` | assembled twice in a row with the same result |

### Phase 1: proof and a first viewer

The design's weak spots, proved first: a map opens in the assembled project;
the ground under the cursor is picked from Python's heights; one mark is drawn
draped on the terrain; depth of field works through `CameraAttributesPhysical`.
Then `mw view --godot MAP` with the orbit camera, layer switches and
screenshots, and the headless library check in `mw test`.

Verified by: Helm's Deep and the Greywater Marches open within about 4 s; a
point at known map coordinates lands where `mw render` puts it.

### Phase 2: the agent loop

The Python companion and its protocol (with unit tests); live reload after
`mw build` and `mw dev`; the marks tools, their panel and Copy for agent.

Verified by: `mw marks` gives the same output for marks drawn in either viewer;
the time from a finished build to the reloaded view is measured.

### Phase 3: parity

Photo mode with the lens, frames and thirds; saved views and Copy view; the
toolbar, the camera bar, Build, Test In-Game and Properties; the walkability
and flow overlays; weather and sun presets; the top view, grid and border.

Verified by: a checklist built from `docs/viewer.md`, item by item, with a
screenshot of each in both viewers.

### Phase 4: rendering and the switch

`mw render` on Godot (`--engine godot`, the default), `--engine game` through
`mw capture`, and during the change `--engine studio` (the Python renderer,
which `docs/game/renderer/` was measured with). Then `mw view` opens the Godot
viewer, the Python viewer's interface is removed, and the Python renderer goes
once the Godot one has matched it against the game's own screenshots.

Verified by: the same views through all three engines; the docs updated in
place (`docs/viewer.md`, `docs/guide/rendering.md`).

## The two reviewing agents

| Agent | Checks |
|---|---|
| Design | the work matches this plan; the boundaries hold (only the listed library methods and shaders; no studio code in OpenBFME; analysis in Python); each feature against the parity checklist; the docs describe what was built |
| Cleanliness | the submodule at its pushed, tagged commit; `git status --ignore-submodules=none` clean; nothing generated outside `local/`; no stray files; `mw test` and `mw doctor` pass; each commit holds one change and only its own files |

## Risks

- **Decals on OpenBFME's terrain shader** are unverified; marks then become
  meshes draped on the terrain, as the Python viewer draws them.
- **Shadows and detail levels** are missing from OpenBFME's map drawing; they
  need engine work, as pull requests of their own.
- **Rendering on a hidden desktop** with Vulkan or Direct3D 12 is unverified;
  without it, `mw render` would show a window while it works.
- **OpenBFME's library interface is not declared stable**; the pin and the
  headless check catch a breaking update.
- **Review time** for the user-maps pull request is OpenBFME's; the minimal
  fork branch carries the work meanwhile.
- **No viewer without RotWK:** OpenBFME needs English RotWK 2.01 and BFME2 1.06.
- **The other sessions:** phase 0 rebuilds the engine and moves its library,
  under `mw play --godot` and `mw battle` while they run.
