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
- **Pinning:** the submodule pins a commit of official `main`. When the studio
  needs something `main` does not have yet, the pin moves to a commit that has
  it, and back once OpenBFME merges it.
- **Where it stands:** the user-maps pull request is open
  ([#76](https://github.com/Open-BFME/openbfme-godot/pull/76)), and phase 0
  is done: the submodule pins `studio-2026-10-21-1` in the user's public fork
  (official `main` plus a short, listed set of commits), nothing is written
  into it, and `mw test` checks that. Phase 1 is done: `mw view MAP --godot`
  opens a map in about two seconds, with the Edit camera, and puts map points
  on the same pixels as `mw render`. Phase 2 is done: marking for agents, the
  marks panel, Copy for agent and live reload, through a Python companion.
  Phase 3 is done ([the checklist](parity.md)): the new layout and toolbar,
  the View menu's layers and overlays (grid, map border, the walkability
  estimate and the river flow arrows), Preview (the weather and sun presets,
  as a copy of the map), Photo mode (the free camera, the lens, frames and
  thirds, and `render/photo.py`'s depth of field as a compositor effect), the
  saved views and Copy view, and Properties. Next is phase 4.

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
- Its worktree is dirty: 4 images show as modified, 58 `.uid` and 3 `.import`
  files are untracked (Godot's import writes them; upstream tracks most `.uid`
  files and its syncs miss some), and Godot's cache and the 83 MB library are
  built inside it. The images are unchanged: upstream's `.gitattributes` sends
  `*.png` through Git LFS but the four are stored as plain files, so wherever
  Git LFS is installed Git compares them converted and reports a change.
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
5. **The pin.** By default the submodule pins a commit of official `main`. A
   feature `main` lacks (the user-maps change until it is merged, or the user's
   open pull requests: walls, siege, weather) comes in by pinning a commit that
   has it, for as long as it takes OpenBFME to merge it. Every pin is pushed and
   tagged, and the commit that moves the pin says why. So the features of the
   fork's `studio/main` reach `mw play --godot` and `mw battle` only when a pin
   brings them in.
6. **The other sessions.** The sessions working on OpenBFME do so in the fork's
   own clone, not here, and the plan does not wait for them. Two things still
   touch them: they used to move the studio's pin to the fork's `studio/main`
   (as in `1dbb65e`, `bedb715`), which the pin rule above replaces, so phase 0
   writes it where every agent reads it; and phase 0 rebuilds the studio's
   OpenBFME build, which interrupts an `mw play --godot` or `mw battle` running
   at that moment. They get a one-line note before phase 0 (sent 2026-10-20).
7. **Who writes the user-maps pull request:** the studio's session
   ([#76](https://github.com/Open-BFME/openbfme-godot/pull/76), as `NotNBR`).
8. **Where the pin lives, until official `main` is enough.** The submodule's
   remote stays the user's fork, which is public, and the pin is a tag there:
   official `main` with only the commits the studio's commands need, each
   listed with what replaces it
   ([testing in the game](../guide/testing-in-game.md#the-pin-and-a-clean-submodule)).
   The list shrinks as OpenBFME merges pull requests (user maps part 2 retires
   the archive mount). When it is empty, the remote becomes Open-BFME's, and
   whatever OpenBFME will not take moves into the studio's own code.

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
- four classes: `RetailFileSystem` (`mount_retail`: the game's files),
  `MapTerrainBuilder` (`build_map`: terrain, water, rivers, roads),
  `MapObjectBuilder` (`setup`, `build_objects`, `advance`: objects and animated
  units) and `PathfindView`, each builder's `get_report`, and the nodes the
  layer switches find in what they build (`MapObjects`, `StandingWater`,
  `Rivers`).

**What each side does:**

| Feature | In Godot | From Python |
|---|---|---|
| Drawing the map | OpenBFME's builders; units animated by `advance()` | the build, installed as a user map |
| Edit and Photo cameras | `Camera3D`, the studio's camera maths carried over | the terrain heights, once per load, for picking the ground and keeping the camera on it |
| Marks | drawn over the map and picked under the cursor, as `viewer/overlay.py` draws and picks them; each mouse event goes to the companion with the cursor's ray and what is under it | the editing itself (`viewer/marking.py`'s MarkEditor), `local/marks/<map>.json` in today's format (`viewer/marks.py`), what each mark covers (the marks panel, Copy for agent), from today's code |
| Photo mode | today's lens: the frame from the studio's own camera maths (the sensor and frame rules of `render/photo.py`), the depth of field as a compositor effect porting `render/photo.py`'s blur (phase 1 found Godot's `CameraAttributesPhysical` unfit: see there) | the lens settings, as `mw render` resolves a view |
| Saved views, Copy view | the same `local/views` JSON and `mw render` command | |
| Walkability, river flow | drawn over the terrain | computed as today, sent as an image and line data |
| Weather and sun presets | the copy built in place | a copy of the map with the preset's world weather, lighting, sky domes and `map.ini` Weather |
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
| 0.2 | The submodule pinned to that branch, `update = none` and `ignore = dirty` removed, `source()` checks out the recorded commit when it differs and switches Git LFS off in the submodule's own config (see 0.4), so the studio's `git status` agrees with the check | a fresh `git clone --recursive` and `mw setup` in an empty folder |
| 0.3 | OpenBFME's Godot import and the engine build moved to `local/openbfme/` (so no `.uid` or `.import` file is written into the submodule) | the submodule clean, as 0.4 checks it, after a build and a test game |
| 0.4 | `mw doctor` and `mw test` check the submodule's commit and cleanliness. Clean means every file matches the commit byte for byte, compared with Git LFS off, so upstream's four plain PNGs under its LFS rule pass without a list of exceptions; `docs/licenses/THIRD_PARTY.md` names OpenBFME; the pin rule (decision 5) written in the OpenBFME section of `docs/guide/testing-in-game.md`, where every agent reads it | the checks fail on a deliberately dirtied copy |
| 0.5 | The studio's Godot project skeleton and its assembly under `local/openbfme/viewer/` | assembled twice in a row with the same result |

### Phase 1: proof and a first viewer

The design's weak spots, proved first: a map opens in the assembled project;
the ground under the cursor is picked from Python's heights; one mark is drawn
draped on the terrain; depth of field works through `CameraAttributesPhysical`.
Then `mw view --godot MAP` with the orbit camera, layer switches and
screenshots, and the headless library check in `mw test`.

Verified by: Helm's Deep and the Greywater Marches open within about 4 s; a
point at known map coordinates lands where `mw render` puts it.

**Done (2026-10-21).** `mw view MAP --godot` opens a project's build from the
user maps folder, or a stock map from the archives
([the viewer](../viewer.md#the-godot-viewer)); `viewer/godot_viewer.py` is the
Python side, `viewer/godot/` the Godot project. Measured:

| | |
|---|---|
| Opening the map (mount, terrain, objects) | Helm's Deep 1.9 s, the Greywater Marches 2.6 s; Glacial Crossroads (28,500 units across) 16 s, 12.7 s of it OpenBFME's terrain builder |
| A map point through a view | the camera's projection on mw render's, 0.000 px apart, with heading, elevation, roll, field of view, a focal length and other picture sizes; OpenBFME draws the map in the same frame (`toG`: Godot (x, z, -y) from the playable area's corner, `GodotMapTerrain.cpp`), and screenshots of one view from both line up |
| Picking and marks | the surface Python sends (terrain raised to standing water); circles, rotated rectangles, freehand paths and pins draped on it, drawn over the terrain |
| `mw test` | `viewer/tests/test_godot_viewer.py` opens Blend Lab (else a stock map) headless through the library, checks two probes and that the object layer is there (6 to 10 s; skipped without OpenBFME built) |

Found:

- **Godot's physical camera does not fit the studio's lens.** Set on a
  camera, `CameraAttributesPhysical` takes over its field of view (from the
  focal length on a 24 mm frame height, keep_aspect forced to height) and its
  near and far planes (its frustum's, 4,000 by default). Its depth of field
  treats a world unit as a metre (the studio's lens uses 10 map units to the
  metre) and blurs far less than `render/photo.py`: at f/1.4 a map 900 units
  away shows almost none. The viewer does not use it: a view's focal length
  sets the camera's field of view, and Photo mode got its depth of field as a
  compositor effect, a port of `render/photo.py`'s blur (phase 3).
- **OpenBFME's terrain builder is slow on the largest maps** (12.7 s for Glacial
  Crossroads); worth measuring in OpenBFME and offering a fix upstream.

### Phase 2: the agent loop

The Python companion and its protocol (with unit tests); live reload after
`mw build` and `mw dev`; the marks tools, their panel and Copy for agent.

Verified by: `mw marks` gives the same output for marks drawn in either viewer;
the time from a finished build to the reloaded view is measured.

**Done (2026-10-21).** `mw view MAP --godot` (and `mw dev MAP --godot`) runs as
the viewer's companion, `viewer/godot_link.py`: JSON lines over a local
socket. The editing stays in Python: Godot draws the marks over the map and
finds what is under the cursor with `overlay.py`'s rules (`mark_overlay.gd`),
sends each press, drag, release, click and hover with the cursor's ray, and
the companion's MarkEditor (the studio viewer's own) changes and saves the
marks and answers with what to draw, the panel and the status. Measured:

| | |
|---|---|
| Marks drawn by scripted mouse input in the Godot viewer | a circle and a rectangle drawn, then the circle dragged by its rim (the overlay picking it): the same marks file, and the same `mw marks` text, as the same strokes through the studio viewer's MarkEditor (`viewer/tests/test_godot_link.py`, headless) |
| A rebuild to the reloaded view | 2.9 and 3.2 s (two runs) after the build wrote the map (its file's time: an upper bound of the time after the build finished), for Blend Lab; the viewer's reload 2.5 s of it, more than its first opening, 1.6 s |
| The protocol and the companion | unit tests without Godot: drawing, selecting, moving, deleting, undo, escape, the state and when it is sent, the panel, Copy for agent, errors, the socket, reload and a build that cannot be read |

Found: scripted input (`Input.parse_input_event`, the scene's `drive` steps)
plays the viewer's own input path headless, so the tests exercise the
viewer, the socket and the companion together; a reload takes longer than
the first opening, worth a look when the reload is made faster.

### Phase 3: parity

Photo mode with the lens, frames and thirds; saved views and Copy view; the
toolbar, the camera bar, Build, Test In-Game and Properties; the walkability
and flow overlays; weather and sun presets; the top view, grid and border.

Verified by: a checklist built from `docs/viewer.md`, item by item, with a
screenshot of each in both viewers.

Done ([the checklist](parity.md)): everything the studio viewer has, apart
from what OpenBFME's library has no switch for (detail levels, shadows,
normal maps, clouds, falling rain and snow, units, editor markers, object
limits). The checklist also lists where OpenBFME draws the map differently
from the studio renderer (rivers, fog, rain); phase 4 starts from those.

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
- **The other sessions:** a pin moved to the fork's `studio/main` out of habit
  would undo decision 5; the written rule and the note before phase 0 guard
  against it.
