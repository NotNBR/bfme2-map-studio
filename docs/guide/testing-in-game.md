# Testing in the game

The viewer, `mw render` and the walkability estimate are fast previews; the game decides.
`mw play` starts BFME2 on a map to play it, and two tools read the game without
showing it: `mw walkable --native` (its pathfinding grid) and `mw capture`
(screenshots). All three run an isolated copy of the game, so your own install,
profile and saved games are untouched. [The runtime](../game/runtime.md)
describes how they work. `mw play --godot` opens the map in OpenBFME, the
Godot rebuild of ROTWK, instead ([below](#openbfme-mw-play---godot)), and
`mw battle` plays a map headless to trace how its units move
([below](#headless-battles-mw-battle)).

With the **ROTWK profile**, `mw play` and the viewer's **Test In-Game** start
directly in a player-versus-easy-AI skirmish, or the project's
[line-up](#line-ups). The isolated runtime uses BFME2
assets plus retail ROTWK and official 2.01 patches, excluding community mods.
It needs the [verified ROTWK executable](../game/runtime.md#rotwk-201); other
hashes are rejected before hooks run. The [free camera](#camera) works in
ROTWK test games too. `mw capture` works in ROTWK as well. ROTWK keeps its
normal fog, also in captures, unless the map's own scripts reveal it;
automatic fog reveal (`--fog` controls BFME2 and OpenBFME) and `mw walkable --native`
remain BFME2 1.06 features. The shared
loading fix accelerates ROTWK test games automatically; `mw patch install`
also supports the verified ROTWK engine in your configured game folder.

`mw play MAP --check` works in either profile: it runs a hidden skirmish until
ten logic frames have elapsed, closes the test, and saves `check-MAP.json` in
that profile's `runtime/logs/`. A timeout or crash fails the command. This
checks gameplay startup, not visual appearance or match balance.

For ROTWK, `mw play --normal-game` opens the **isolated clean runtime's menu**
and installs the map into that runtime's user maps. `mw build --install` also
uses those isolated user maps. Your modded ROTWK installation and its saves
are untouched. The remaining sections describe BFME2's additional features.

## `mw play`

`mw play <map>` (the viewer's **Test In-Game**) starts BFME2 straight in a
skirmish on the current build, without going through the menus: the game opens
in a 1600 x 1200 window, you against an easy AI (or the project's
[line-up](#line-ups)), at Medium detail
(`--graphics Low|Medium|High|UltraHigh` for another). `--rebuild` builds the
map first.

The map is revealed to you for the whole game, without shroud or fog of war,
so all of it shows, including objects and their particle effects, which the
game hides wherever your view is fogged; `--fog` keeps the shroud and fog of
war.

`mw play` returns when the skirmish is playable ("playable in BFME2, 5 s after
the start"), or with the launcher's last line if the game ends before then;
the viewer's status bar shows the start, then "playable", then "closed" when
the game ends. Closing the game's window works (retail BFME2 ignores it; the
launcher catches it). The launcher log is `local/runtime/logs/play-<map>.log`.
It needs no administrator rights. The installed BFME2 must be version 1.06.

With `mw play --normal-game`, or when the game is not BFME2 1.06, the build
goes into the game's user maps folder
(`%APPDATA%\My Battle for Middle-earth(tm) II Files\Maps`) and BFME2 starts at
its menu; pick the map under Skirmish. `mw build --install` copies it there
too.

### Line-ups

A project's `map.toml` can seat the test game's slots instead, in both
profiles; `mw play` and `mw play --check` use it:

```toml
[play]
slots = [                               # slot k takes start k (Player_k_Start)
    {faction = "Men", team = 1},        # the first slot is you
    {faction = "Elves", team = 1, ai = "hard"},
    {faction = "Mordor", team = 2, ai = "brutal"},
    {faction = "Wild", team = 2, ai = "medium"},
]
```

- `ai`: easy, medium, hard or brutal, for every slot but the first.
- `faction`: a playable faction's name in `playertemplate.ini` without
  `Faction` (Men, Elves, Dwarves, Isengard, Mordor, Wild for the goblins, and
  Angmar in ROTWK); random without one.
- `team`: 1 to 4; no team without one.

The launcher writes them into the game's slots as the skirmish menu would
([runtime.py](../../src/mapworkshop/native/runtime.py) `seat()`; the slot
layout is Open-BFME-2's `GameSlot`, which ROTWK shares). A map seats at most
its `players`, and at most 8; an observer would take a slot too.

### Camera

BFME2 and ROTWK test games have a free camera, to look at the map from any
distance and angle. It is enabled by `mw play` and **Test In-Game**; the
normal-game menu and the installed loading patch keep the game's own camera.
`mw play --godot` starts OpenBFME with its own free camera on
(`--free-camera`; Ctrl+Z turns it off and on). It steers as OpenBFME's does:
the fork's tilt and zoom as in the table are not in the
[pinned commit](#the-pin-and-a-clean-submodule).

| Input | Does |
| --- | --- |
| Mouse wheel | zooms, from close up to far enough to see the whole map |
| Middle button held, mouse up or down | tilts, from near the horizon to straight down |
| Middle button held, mouse sideways | rotates (the game's own) |
| Middle click | the game's own camera again, at its default angle and zoom |

Scrolling, the minimap and rotation work as usual, and scrolling covers as
much of the screen per step at any zoom. The camera stays the game's own
until you first zoom or tilt, and scripted camera moves hand it back to the
game. The game draws no sky near the horizon, so low angles show black above
the terrain, and the map's edge shows as black.

## OpenBFME: `mw play --godot`

`mw play <map> --godot` opens the map in
[OpenBFME](https://github.com/Open-BFME/openbfme-godot), a rebuild of ROTWK
2.01 in Godot, instead of the original game. It starts straight in a
skirmish on the map, as `mw play` does: you against an easy AI, or the
project's [line-up](#line-ups). OpenBFME's LAN host (`--net-host`,
`--net-slots`) seats the slots without the lobby screens and, with every other
slot a computer, starts at once. The game is drawn without its shroud and fog
of war, as BFME2's test games reveal the map: the studio's OpenBFME has a
`--no-shroud` option (its viewers' debug view: only the drawing
changes, the players and the AI keep their shroud); `--fog` keeps them.
The game is not recorded as a replay unless you add `--record`. OpenBFME
records every LAN game by default. A replay also stores the full game state's
hash for every logic frame, and in the Nanduhirion v2 battle that hashing was
a third of the simulation's time.
A map's [cinematics](../game/scripts.md#cinematics) play only in the
original game for now: the fork's commit that plays them in a skirmish is
not in the [pinned commit](#the-pin-and-a-clean-submodule). In the viewer, choose **OpenBFME (Godot)** in the
dropdown beside **Test In-Game**. `--godot --check` runs a headless scripted
skirmish instead: OpenBFME clicks through its menus, starts the map against an
AI, plays five seconds of game time and closes. The report goes to
`local/openbfme/logs/check-<map>.json`, with the load time, the logic frame
and the number of objects. A failure prints OpenBFME's reason. Either uses the
current build of the active profile; OpenBFME always plays it with ROTWK 2.01's
data.

The first run sets up everything in `local/openbfme/`, in about three
minutes plus the time to check the game files:

- **Engine:** it fetches the `native/openbfme-godot` submodule (left out of
  `mw setup`) at the commit this repository pins
  ([the pin](#the-pin-and-a-clean-submodule)). It also downloads llvm-mingw and Godot 4.7.2, pinned to their
  releases' SHA-256, then builds the engine into `local/openbfme/build/`.
  Godot runs a copy of the submodule's `godot/` folder,
  `local/openbfme/project/`: the built GDExtension, Godot's import cache and
  the `.uid` and `.import` files Godot writes stay in the copy, and nothing
  is written into the submodule. Each run brings the copy up to date with the
  files the submodule tracks there, and Godot re-imports only the files that
  changed. CMake and
  Ninja must be on PATH or in the studio's environment
  (`pip install cmake ninja`). Windows only. Keep the checkout's path short:
  the paths in godot-cpp, OpenBFME's own submodule, pass Windows's 260
  characters in a deep folder, and its checkout then fails (or set
  `git config --global core.longpaths true`). A later run rebuilds only when
  the submodule's commit changes or its engine files have changes not
  committed yet.
- **Extra archives:** the fork adds one thing upstream lacks:
  the `OPENBFME_EXTRA_ARCHIVES` variable, which mounts extra `.big` files.
  OpenBFME reads maps only from verified archives and ignores loose map files.
  So each map is packed into `local/openbfme/maps/<name>.big`, and
  `local/openbfme/mapcache.big` carries the Skirmish list (retail's
  `maps\mapcache.ini` plus every packed map).
- **Performance:** the fork makes big battles
  smoother without changing what the logic computes. Its first changes, the
  ones under "Logic frame cost", were checked with OpenBFME's 10,000-troop
  benchmark, which gives the same state hash every frame with and without
  them. The later logic changes (the horde lookups, the computer players'
  scans) give the same results by construction but haven't been hash-tested.
  - **Stalls after each logic frame.** The game's network overlay, which runs
    in every `mw play --godot` game, hashed the whole game state on the render
    thread on every frame while the logic was idle. That stalled two or three
    rendered frames by 40–50 ms each after every logic frame, in the
    Nanduhirion v2 battle. It now reuses the worker's hash, or hashes at most
    every 50 logic frames.
  - **Render cost per soldier.** Every render frame, each horde member's
    model flags were merged with its horde's one bit at a time, 591 bits. That
    was 13% of the render thread in the arena clash. It now merges whole
    words, with the same result. The clash ran at 43 instead of 34 frames per
    second, with 11% instead of 19% of frames over 40 ms.
  - **Horde lookups.** `Object::getHordeObject`, asked for every unit by the
    sound and HUD code, searched the object-type names for `HORDE` up to three
    times per call. That was about 3 ms of each spike frame. It now looks the
    type up once.
  - **Fog refresh.** When the fog changed, about once per logic frame in a
    battle, the fog texture was rebuilt and five shader parameters were set on
    every terrain material. That took about 4 ms of the frame that already
    carries the most work. The texture is now skipped while the fog isn't
    drawn (`--no-shroud`, as `mw play` runs it), and the materials are only
    updated when a parameter's value changes.
  - **Computer players' scans.**
    - When it plans a building, the skirmish AI counts enemies near the
      site. That count walked every object and looked up five object types by
      name for each one. It now tests the distance first and looks up each
      type once.
    - Special-power checks ask whether the player owns an object a filter
      allows. They now evaluate the filter once per template instead of once
      per object.
    - Together with leaving out the replay hash, a logic frame of the v2
      battle in the inn zoom dropped from a median of 147 ms to 86 ms.
  - **Vision on several cores.** The shroud's update of a moving army is now
    split in two:
    - Each unit's vision (its template's values, the cells it covers, how
      far it sees) is worked out on OpenBFME's logic job threads.
    - The results are then applied to the shared grid one by one, in the
      original order.

    The 10,000- and 20,000-troop benchmarks give the same hash chains as
    before. In the inn zoom, a logic frame dropped from a median of 86 ms to
    79 ms, and freezes over 40 ms from 40 to 12 per 25 s.
  - **Logic frame cost.** It no longer builds strings or looks them up for
    every unit every frame. That saved about 6% of a logic frame in the
    benchmark: about 149 to 140 ms, against run-to-run noise of about 10%.
    Units still step while the logic takes longer than its 200 ms frame.
  - **Pathfinding,** taken from the OpenBFME fork in `D:\LAN\openbfme-godot-fork`
    (its lanes PATHPERF-2 and PATHPERF-4, in `engine/src/GameLogic/AI/`); none
    of it has been benchmarked or hash-tested here.
    - PATHPERF-2 makes path searches cheaper with the same results:
      - a search remembers which straight lines between cells it has already
        found passable or blocked;
      - its open list keeps the cells' costs in one dense array;
      - a cell's occupant cost is worked out from inputs gathered once per
        unit.
    - PATHPERF-4 lets the pathfinder's pool of cell records grow, up to
      1,000,000 records (about 100 MB), instead of failing when it is full,
      as retail's grows. In a battle that used to fill the pool, searches and
      reservations that failed now succeed, so the results differ from before
      exactly there.
    - PATHPERF-4 also lengthens the path-request queues from 511 to 16,384
      units and quadruples the cells searched per frame, but only in
      OpenBFME's Uber profile; a normal game keeps retail's limits.
    - In the Uber profile, the studio adds a rush rule: when more than 64
      path requests are waiting (a mass order, such as a battle script's
      charge), that logic frame may search 400,000 cells, retail's own
      budget for a game's first 5 seconds. Units ordered together then get
      their paths, and set off, in the same frame, at the cost of one heavy
      logic frame. Without it, the 4 x 4,000 cells a frame serve a large
      order over several frames, a few hordes at a time (worked out from the
      code, not measured).
  - **Named units belong to the scripts.** The skirmish AI no longer
    recruits or sends off a unit that has a script name (a map object's
    `objectName`, or a unit a script created by name). Units a map stages
    for its scripts then wait for the scripts' orders. Before, a computer
    player took over its own staged army once it was 10 seconds old: in the
    Nanduhirion v2 film, 658 of Mordor's units moved before the 39-second
    charge; with the rule, 23 (a few archers and catapults shifting in the
    first seconds, for a reason not yet known). The AI's own trained units
    have no names and stay its own. Unlike retail, so a map whose scripts
    name player units behaves differently here.
  - **Uber profile in `mw play --godot`.** OpenBFME's Uber performance mode
    is the line `OpenBFMEUberPerformance = yes` in
    `local/openbfme/appdata/Godot/app_userdata/OpenBFME/Options.ini` (`no`
    or no line: the normal Faithful profile). Upstream, only the Skirmish
    and LAN menus read it; the patch makes the game `mw play` hosts read it
    too and carry it in its game message. The game's log then shows
    `GAME simulation profile: uber (ok)`.
- **Game files:** OpenBFME accepts only unmodified English ROTWK 2.01 and
  BFME2 1.06 archives (its policies are in the submodule's
  `engine/data/retail-archives/`). Mod, patch 2.02 and other-language archives
  are refused. The run hard-links every file whose MD5 matches from your
  configured installs (`mw config game` and `rotwk`) into
  `local/openbfme/assets/`. If some are missing, it lists them, and
  `--download` fetches them from the service the OpenBFME launcher uses,
  checking each file's MD5.

OpenBFME has eight player slots, so a map lists its first eight starts. Its
profile, options and logs stay in `local/openbfme/appdata/`. `mw doctor`
reports how far the setup has got. OpenBFME is an alpha: what it does not do
yet is listed in its README.

### The pin and a clean submodule

The submodule pins one commit, recorded in this repository. By default it is
a commit of OpenBFME's official `main`
([Open-BFME/openbfme-godot](https://github.com/Open-BFME/openbfme-godot)). A
feature `main` lacks comes in by pinning a commit that has it, for as long as
OpenBFME takes to merge it. Once OpenBFME has merged it, the pin goes back to a
commit of `main`. Every pinned commit is pushed and tagged in the fork
[NotNBR/openbfme-godot](https://github.com/NotNBR/openbfme-godot) (the
submodule's remote), its tags are never deleted, and the commit here that moves
the pin says why. Don't move the pin to the fork's `studio/main`: its features
reach `mw play --godot` and `mw battle` only when a pin brings them in. An
engine change goes to OpenBFME as a pull request; the few the studio alone
needs are commits on the pinned tag, listed below, each with what replaces it.
This is decision 5 of the [Godot viewer plan](../history/godot-viewer-plan.md#decisions).

The pin is `studio-2026-10-21-3`: OpenBFME's `main` (`1ee8f2e9`) with

| Commits | For | Until |
|---|---|---|
| user maps ([#76](https://github.com/Open-BFME/openbfme-godot/pull/76)) | the studio's Godot viewer opens a build from the user maps folder | OpenBFME merges it |
| rivers as the game draws them ([#79](https://github.com/Open-BFME/openbfme-godot/pull/79)) | the viewer's and `mw render`'s rivers: their texture, ripples, colour and additive blending | OpenBFME merges it |
| siege, walkable walls, big battles ([#64](https://github.com/Open-BFME/openbfme-godot/pull/64), with [#63](https://github.com/Open-BFME/openbfme-godot/pull/63) and [#62](https://github.com/Open-BFME/openbfme-godot/pull/62)) | Helm's Deep's assault, and the battle log's siege phases | OpenBFME merges them |
| extra archives (`OPENBFME_EXTRA_ARCHIVES`) | `mw play --godot`, `--check` and `mw battle` mount a studio map | games on a user map (part 2 of the user-maps change) |
| a unit's path (`GameWorld.get_object_path`) | the viewer's Test mode draws the paths units follow | OpenBFME takes it, or the viewer reads paths another way |
| `--no-shroud` | `mw play --godot` draws the map revealed | OpenBFME takes it as a debug option, or a pin without it and `--fog` as the default |
| the headless battle log (`openbfme_peer --battle-log`) | `mw battle` | OpenBFME takes it, or the log moves into the studio |

Not in the pin, though `studio/main` has them: the weather pull request
([#59](https://github.com/Open-BFME/openbfme-godot/pull/59)), map cinematics
in a skirmish, staged armies and the free camera's tilt.

To move the pin to a pushed tag:

```powershell
git -C src/mapworkshop/native/openbfme-godot fetch --tags
git -C src/mapworkshop/native/openbfme-godot checkout <tag>
git add src/mapworkshop/native/openbfme-godot      # then commit, saying why
```

Nothing is ever written into the submodule: the build, Godot's import and the
games write to `local/openbfme/`. `mw test` and `mw doctor` check that it is
clean: checked out at the recorded commit, every file as that commit has it,
nothing untracked and nothing its `.gitignore` names, and godot-cpp, its own
submodule, the same. Files are compared with Git LFS off: upstream stores four
plain PNGs under its LFS rule, and Git with LFS reports them changed although
they are not. The same comparison by hand:

```powershell
git -C src/mapworkshop/native/openbfme-godot -c filter.lfs.process= -c filter.lfs.clean=cat -c filter.lfs.smudge=cat -c filter.lfs.required=false status --porcelain --ignored
```

Whatever it lists was written by something else: an older build of the studio
(before `local/openbfme/project/`), or a tool run inside the submodule. Find
out what wrote it before you remove it: a changed tracked file may be someone's
unfinished work.

## The game's pathfinding grid: `mw walkable --native`

`mw walkable <map> --native` starts the game headless (no window appears),
reads its pathfinding grid at logic frame 10 (about 7 seconds) and compares it
with the local estimate; `--compare` compares with the grid saved last time
without starting the game. See [walkability](projects-and-builds.md#walkability) for
what the estimate leaves out.

## Screenshots from the game: `mw capture`

```powershell
mw capture greywater --shot ford 5200 3100 300 --shot overview 6750 4500 3000
mw capture water-lab --graphics High --shot falls 800 1500 400
mw capture bridge-battle --shot start 3000 2000 600 --at 10 --shot clash 3000 2000 600 --at 300
mw capture hollin --view valley 4000 3000 2500 25 90
```

saves screenshots rendered by the game, HUD included, into
`local/renders/game/<map>/` (or `--out`), about 10 seconds for a few shots. It
runs headless: the game starts on a hidden desktop of its own, so no window
appears and your focus stays where it is, and it ends as soon as it has the
shots. `--show` runs it in a visible window instead. In BFME2 the map is
revealed; in ROTWK the shroud stays unless the map's scripts lift it. The
skirmish is seated as `mw play`'s ([line-ups](#line-ups)).

- `--shot NAME X Y HEIGHT`: the camera looks at the ground at X, Y from
  HEIGHT (the game's own camera; 300 is its usual zoom).
- `--view NAME X Y DISTANCE PITCH HEADING`: a cinematic shot instead: the
  camera DISTANCE from the ground at X, Y, PITCH degrees below the horizon,
  facing HEADING (0 north, 90 east), angles the game's own camera never
  takes. The game draws no sky near the horizon, so keep the pitch above
  about 20 degrees for views that reach far.
- `--still NAME`: the frame as the game's own camera shows it, a map's
  scripted camera say ([cinematics](../game/scripts.md#cinematics)); after the
  `--view` shots.
- `--at FRAME` (one per shot, rising) holds each shot until the game's
  logic reaches that frame, about 5 per second of game time, to photograph a
  scripted scenario as it plays out; `--timeout` (240 s) gives a long one
  time. Particle effects fill in over game time: a particle stream needs
  `--at` about 70.
- After moving the camera each shot waits `--settle` rendered frames (30)
  and, with `--delay MS`, at least that many milliseconds.

Use it for what the viewer does not show, such as the water reflections at
High, and when a check needs the game's own view.

## Headless battles: `mw battle`

```powershell
mw battle helms-deep-battle                          # its first minute, every unit the map places traced
mw battle helms-deep-battle --seconds 120 --watch IsengardPikemanHorde,IsengardSiegeLadder
mw battle horde-spacing-lab --rotwk --seconds 1      # RotWK's battalion destinations and goals
mw battle horde-spacing-lab --rotwk --seconds 1 --cells
```

plays a map without graphics and shows how its units move
([native/battle.py](../../src/mapworkshop/native/battle.py)). Its output goes
to `local/openbfme/battles/<map>/` (or `--out`).

- **In OpenBFME** (the default), the engine's headless game process
  (`openbfme_peer`, built with the game) hosts the map's skirmish with its
  [line-up](#line-ups) and plays `--seconds` of game time (60), at about real
  time. Every `--every` logic frames (5, a second) its battle log gets a line:
  each player's troops, those on walls, battalions and heroes, the hurt gates
  and wall pieces, the siege engines by phase and the map scripts' counters.
  Under it stands every object of the `--watch` templates (by default the
  units the map places for its players): name, position, health, AI state,
  target and siege phase. The command then sums up how each template moved
  (how many never moved, when they started and stopped, how far east and
  north, how many went south) and draws `tracks.png` and `battle.gif` (the
  positions second by second) over a top render; `--no-plot` skips them. The
  studio's OpenBFME plays in its Uber performance profile; `--faithful` plays
  the original rules, to tell a difference between the two apart.
- **In RotWK** (`--rotwk`, the ROTWK profile), the original game runs headless
  under the studio's debugger until `--seconds` and reports, for every
  battalion, where its destination was moved to (adjustDestination) and where
  its members reserved their goals, relative to it; `--cells` adds every cell
  the destination search tried, with its result. Everything is in
  `rotwk.json`. Use it to find out what the original game does where
  OpenBFME differs: [battalions](../game/battalions.md) was measured this way.

## Faster loading in your normal game: `mw patch`

Test games load maps in a few seconds instead of tens of seconds (Brightwater
Fold 4.5 s instead of 17 s, the Greywater Marches 9.2 s instead of 49 s).
`mw patch install` puts the same faster loading into the selected game's folder, for
every map and every game you start there, skirmish or multiplayer:

```
mw patch            # status: not installed, installed, outdated or foreign
mw patch install    # copy dinput8.dll into the game folder
mw patch remove     # take it out again
```

- It supports BFME2 1.06 and the verified ROTWK 2.01 engine (`install` checks
  `game.dat` by hash). Use `mw --profile rotwk patch install` for ROTWK or
  `mw --profile bfme2 patch install` for BFME2. The DLL only forwards DirectInput
  when it does not recognize the engine's code layout.
- It changes how fast textures are built, not what the game simulates, so it
  should not affect multiplayer; that is untested.
- `install` never replaces a `dinput8.dll` that is not this patch (another
  mod's), and `remove` never deletes one. A folder in Program Files needs an
  administrator prompt.

The patch is its own public project,
[bfme2-map-quickload](https://github.com/NotNBR/bfme2-map-quickload): players
can download `dinput8.dll` from its releases without this toolkit.
