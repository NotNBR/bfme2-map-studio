# The Godot viewer against the Python viewer

Phase 3's check ([the plan](plan.md#phase-3-parity)): every feature of
the Python viewer, as [the viewer's page](../viewer.md) described it then,
section by section, in the Godot viewer (then `mw view MAP --godot`; since
phase 4 the viewer, `mw view MAP`). Each item is one of:

- **same**: it behaves as the Python viewer's, checked as the last column says;
- **drawn differently**: the feature is there, but OpenBFME's library draws the
  map differently from the studio renderer;
- **missing**: it is not in the Godot viewer, and why.

Checked on 2026-10-21 at `aa4026b`, with Battle of Helm's Deep (a night map
with rain) and Water Lab. The screenshot pairs are made by a script outside
the repository into `local/renders/parity/<item>-studio.png` and
`<item>-godot.png`. The studio side is `mw render` (the Python viewer's
renderer) at 1600 x 1000, or for `open` the Python viewer's own window; the
Godot side is the Godot viewer's `--screenshot` or a scripted run with its
companion. The tests named are in `src/mapworkshop/viewer/tests/`.

## Opening a map

| Item | State | Checked by |
|---|---|---|
| `mw view MAP`, a project, a stock map or a `.map` file of either | same; a loose `.map` file is refused (OpenBFME opens user maps and its archives) | `test_godot_viewer` |
| `--size` | same | the probes, below |
| `--weather`, `--sun` | same, as Preview | `rain`, `ember` pairs |
| `--fps` | same, as the toolbar's cap | |
| `--lod` | missing: OpenBFME has no detail levels | |
| `--samples` | missing: the viewer draws without MSAA, as OpenBFME's map viewer | |
| The whole map at the start | same framing and camera (target 2000, 2000, distance 3000, tilt 55) | `open` pair |
| A view at the start (`--view`), on mw render's pixels | same, within 0.01 px for Edit and Photo views | `LibraryTests` |

## Moving around

| Item | State | Checked by |
|---|---|---|
| The Edit camera: orbit, pan, zoom to the cursor, fly to a double-click, the keys, the whole map, top-down | same (a port of the Python viewer's Camera) | phase 1, by hand; `open`, `top` pairs |
| V, Ctrl+1..9, Ctrl+Shift+1..9, Ctrl+C | same | `ViewsTests`, a scripted run |
| 1, 2, 6, 7, 8, M, G, B, P, F5, Ctrl+B, F1, Del, Ctrl+Z, Esc | same | `CompanionTests`, scripted runs |
| 3, 4, 5, 9, U (shadows, normal maps, clouds, editor markers, units) | missing: OpenBFME draws none of them as a switch | |

## Photo mode and the camera bar

| Item | State | Checked by |
|---|---|---|
| The free camera, its mouse and keys | same (a port of the Python viewer's FlyCamera) | a scripted run |
| Views: thumbnails, go, save, rename, delete; the same `local/views` files | same; renaming and deleting sit at the end of the list | `ViewsTests`, a scripted run |
| Copy view | same command; units, shadows, clouds, detail, time and normal maps stay at `mw render`'s defaults | `ViewsTests` |
| The lens: focal length, aperture, focus, exposure; the presets, wheel and drag | same | `lens` pair: the blur matches |
| Focus on the centre | same: 699 for a view 700 units away | a scripted run |
| Thirds, the frame and its crop | same | `photo` screenshot |
| The readout, with the sharp range | same | `photo` screenshot |
| Photo screenshots | same, named `<map> photo <time>.png` in `renders/godot/` | |

## Live reload

| Item | State | Checked by |
|---|---|---|
| A new build reloads in place, the camera stays | same, about three seconds after a small map's build | `test_a_new_build_is_reloaded_once_it_has_settled`, phase 2 |
| A build that cannot be read leaves the last good map | same | `test_a_build_that_cannot_be_read_keeps_the_last_good_one` |
| Loading in the background, a progress bar | drawn differently: the window waits while the library builds the map (seconds), with a toast and no progress bar | |

## The toolbar

| Item | State | Checked by |
|---|---|---|
| Map: projects, the game's maps, Open project folder, Browse... | same; Browse... opens a project's build or a stock map only | `CompanionTests` |
| Properties | same window (the Python viewer's own); its Save builds, and the build reloads | `CompanionTests` |
| Build, its chip; Test In-Game and its choice | same, the Python viewer's own jobs | `CompanionTests` |
| Preview: Weather, Sun | same lighting, fog and sky (a copy of the map); no falling rain or snow; the sky only on `WaterReflectionSkydome` objects | `rain`, `ember` pairs, `PreviewTests` |
| Preview: Detail | missing: OpenBFME has no detail levels | |
| View: objects, water, roads, fog, Animate, grid, border, walkable, flow, marks | same, with the border drawn differently (below) | the overlay pairs |
| View: units, shadows, clouds, normal maps, rain and snow, object limits, editor markers | missing: no such switches in OpenBFME | |
| Top view, Reset view, Screenshot, the frame rate and its cap | same | `top` pair |

## Marking the map for an agent

| Item | State | Checked by |
|---|---|---|
| The tools, selecting, moving, resizing, rotating, Del, Ctrl+Z, Esc | same: the Python viewer's MarkEditor does the editing | `DrivenViewerTests`: the same marks as the Python viewer's for the same strokes |
| The marks panel, Copy for agent, `mw marks` | same text, from the same marks file | `CompanionTests` |

## Overlays

| Item | State | Checked by |
|---|---|---|
| Walkable, grid | same | `walkable` pair |
| River flow arrows | same; on every river, as OpenBFME draws them all | `flow` pair |
| Map border | drawn differently: without Map border the ground outside the playable area fades to black, not to the sky, and water and roads there stay | `border` pair |

## How OpenBFME draws the map differently

These are differences in the drawing itself, not in the viewer. They matter
for phase 4, where `mw render` moves onto the Godot viewer:

- **No falling rain or snow**: the studio renderer draws the map's own rain on
  Helm's Deep (`view`, `lens` pairs) and the presets' (`rain`).
- **Rivers**: the Deeping Stream is lit pale at night where the studio
  renderer draws it dark (`open`, `view`, `top`; it is the river, not a road:
  it stays with the roads switched off). Water Lab's rivers are dark and flat
  under Rain and Ember, where the studio draws their texture and foam (`rain`,
  `ember`, `flow`), and of the nine short rivers at its north-west corner
  OpenBFME draws two; the game draws all nine, as its minimap shows
  (`mw render --top`, all three engines).
- **Fog**: Dusk with Ember hazes Water Lab far less than the studio renderer
  does from 4,200 units away (seen while building Preview; at the `ember`
  pair's 2,600 units both show little). The map.ini values are the same, so the
  difference is in how far from the camera each renderer fogs.
- **The map's edge**: beyond the map the Godot viewer is black, where the
  studio draws a grey-blue background.
