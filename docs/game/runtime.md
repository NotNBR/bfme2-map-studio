# The test-game runtime

How `mw play`, `mw walkable --native`, `mw capture` and `mw patch` drive BFME2
1.06 ([testing in the game](../guide/testing-in-game.md) covers using them).
The code is in [native/](../../src/mapworkshop/native/).

## ROTWK 2.01

[native/rotwk.py](../../src/mapworkshop/native/rotwk.py) adds direct skirmishes
for the local executable whose SHA-256 is
`5481de75b63e22483660ea8097478faef594f90b9ade7de893e092256ba68a26`.
Its version resource is `2.1.2614.37001`. Earlier local analysis records
pre-existing scheduling differences in this binary, so this fingerprint is
not a claim that every retail 2.01 executable is interchangeable with it.
Other fingerprints are rejected before code hooks are installed.

The ROTWK profile prepares `local/profiles/rotwk/runtime/`. It mounts the
complete BFME2 archive set below the retail expansion and official 2.01
archives, omitting 2.02, HD and timer packs. Base archives receive distinct
names at lower priority, so colliding filenames cannot drop shared assets.
The executable and writable files are copied, archives and movies linked;
AppData is redirected and the real install/profile remain untouched.

This executable starts directly as `game.dat`; its retail launcher stalled
before engine initialization during verification. At RVA `0x23CB7B`, after
GameEngine::init's `-file` branch assigns slot zero, the studio sets GameInfo
(`0x9E892C`) to SkirmishGameInfo (`0x9E8930`), assigns random factions to the
first two slots and makes slot one an easy AI. The slot layout is `+0x18`
for the array, `+4` for state, `+8/+9` for acceptance/map ownership and
`+0x18` for faction. These came from the local engine decompilation and were
verified by a live skirmish, not inferred solely from BFME2.

Readiness requires skirmish mode 2 and advancing logic frames through the
GameLogic pointer at `0x9E412C`. `mw play --check` closes after ten frames;
interactive play reports ready after two. The close handler uses RVA `0x18EB`.
The shared quickload DLL recognizes ROTWK's separate terrain call sites and
runs their D3DX compression/mipmaps on workers. The launcher flushes those
jobs at RVA `0x225524` when GameLogic destroys its loading screen, after
textures have been queued and before the map draws. Reports include the
DLL's job counters. `start(..., fast=False)` disables the fix for comparisons.
The isolated menu uses the standalone build, which handles subsequent loads
itself; `mw patch install` can install that build into the configured ROTWK
folder too. Both installers require the verified engine hash.

ROTWK keeps its own camera and fog: BFME2's camera DLL is not injected, and
native screenshot/pathfinding capture is rejected.

[Validation record](../history/rotwk-integration.md) records the asset and
gameplay checks. The rest of this page describes the BFME2 runtime.

## The isolated game

Test games run an isolated copy of the game in `local/runtime/`
([native/runtime.py](../../src/mapworkshop/native/runtime.py)), made on first
use from the installed BFME2, which must be version 1.06:

- `game/`: the install's archives and movies as hard links (no extra disk), the
  rest (about 30 MB) as copies, so nothing a run writes reaches the install;
- `mod/maps/`: the builds installed for test games and their map-cache entries
  (the game starts with `-mod` on this folder);
- `appdata/`: the profile the game is given instead of yours, so your normal
  game, its options and saved games are untouched;
- `logs/`: the launcher logs.

Every start skips the five seconds the game spends on its EA title logo after
loading: the runtime's mod folder carries the game's INI that defines that
image, without it, and the game shows the logo only when the image exists.

## The launcher

The launcher ([native/debugger.py](../../src/mapworkshop/native/debugger.py),
ported from openbfme2's test harness) runs the game as its debugger. That is
how it starts the game in a skirmish (it finishes the setup the skirmish menu
would do), keeps it on the sandbox profile and away from focus stalls, and
learns from the game itself, not from a timer, when the skirmish is ready: a
breakpoint at the end of the game's new-game pass, after the map is loaded and
the players placed, reports it. Retail BFME2 ignores its window's close button
and Alt+F4; the launcher catches that close request and ends the game.

## The free camera

The free camera comes from a small DLL the launcher loads into every game it
starts ([native/ingame/ingame.cpp](../../src/mapworkshop/native/ingame/ingame.cpp),
committed built; `python -m mapworkshop.native.msvc ingame` rebuilds it with
Visual C++ .NET 2003, setting `msvc71`). It lets the game build its camera,
then turns it to the chosen tilt and moves it to the chosen distance from the
same focus point, before the game sets it and the terrain picks what to draw
from it; it also moves the clip planes out, which the game keeps at 10 to
1,800 units. It replaces the game's zoom steps (the wheel arrives there only
when no menu took it), watches the mouse for the middle-button drag, and
scales the scroll offset. `mw capture` uses the same DLL to place the camera
and copy the frame.

## Headless runs

`mw walkable --native` and `mw capture` start the game on a hidden desktop of
its own and end it as soon as they have what they came for. Direct3D 9 does
not render on a desktop that is not shown, so headless runs start
`local/runtime/game-headless/`: hard links to the runtime's files plus the
`d3d9.dll` of [DXVK](https://github.com/doitsujin/dxvk), which runs Direct3D 9
on Vulkan. The first headless run downloads that DXVK release (18 MB) and
checks it against its published SHA-256. Its frames match native Direct3D 9 to
about 2 levels in 255 on average, at Medium and at High with water
reflections; test games and `--show` keep native Direct3D 9. A `dxvk.conf`
there turns DXVK's graphics pipeline libraries off: with them the loading
screen waited on shader compilation, about 5 seconds per start.

## Faster map loading

Most of a map's loading time is the game building its terrain textures: for
each one it composites the terrain on the CPU, then Microsoft's D3DX library
compresses it to DXT1 and builds its mipmaps, one texture after another on one
core (about 8.5 of 10 seconds on Brightwater Fold at Medium; 1,156 textures).
Every runtime start loads
[loading.cpp](https://github.com/NotNBR/bfme2-map-quickload/blob/main/loading.cpp)
(the `native/loading` submodule) into the game, which hands those two D3DX
calls to worker threads (one fewer than the processor count, up to 15) while
the map loads: each texture gets the same calls with the same input, on a
CPU-only staging copy made on a Direct3D device of the DLL's own
(multithreaded, on a window that is never shown, so the workers never touch
the game's device, which is not thread-safe), and the game's main thread
copies the finished textures in; the launcher waits for the last ones when the
new-game pass ends, before the first frame. The terrain comes out the same:
screenshots with and without it differ only where things move (water, trees,
the HUD). Any other caller, a texture outside Direct3D's managed pool, or the
game after loading gets the game's own synchronous calls.

| Brightwater Fold, Medium | Gameplay after | Three screenshots |
| --- | --- | --- |
| Before (title logo, one core) | 17.0 s (headless 22.5 s) | about 30 s |
| Without the title logo | 12.2 s | 20.7 s |
| With loading.dll as well | 4.5 s | 9.0 s |

Larger maps gain more. The Greywater Marches (1,350 x 900 cells, 5,340
terrain textures) reaches gameplay in 9.2 s instead of 49 s (headless 11 s),
and two screenshots take 13 s instead of 54.

`runtime.start(..., fast=False)` loads the map as the game alone does, for
comparisons. The rest of the load (about 2 s to the engine, 2 s of map on
Brightwater Fold) stays on the main thread.

## The patch in the normal game

`src/mapworkshop/native/loading/` is the
[bfme2-map-quickload](https://github.com/NotNBR/bfme2-map-quickload)
repository as a submodule: its `loading.cpp` builds both `bin/loading.dll`,
which test games load, and `bin/dinput8.dll`, which `mw patch` installs. The
game imports DirectInput from `dinput8.dll` and finds this copy before
Windows' own, which it forwards to. Without a launcher, the DLL works out the
end of each load itself: it defers while the game shows its loading screen and
finishes the terrain textures in the tactical view's first update after it,
before the map is drawn. It also skips the five seconds of title logo after
loading, by setting the 5000 milliseconds of that wait to 0 in memory, so the
fade-in after it still runs. Brightwater Fold reaches gameplay 4.5 s after the
start, the Greywater Marches 9.3 s. The runtime does not copy it: test games
load `loading.dll` themselves.
