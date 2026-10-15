# Testing in the game

The renderer and the walkability estimate are fast previews; the game decides.
`mw play` starts BFME2 on a map to play it, and two tools read the game without
showing it: `mw walkable --native` (its pathfinding grid) and `mw capture`
(screenshots). All three run an isolated copy of the game, so your own install,
profile and saved games are untouched. [The runtime](../game/runtime.md)
describes how they work.

## `mw play`

`mw play <map>` (the viewer's **Test In-Game**) starts BFME2 straight in a
skirmish on the current build, without going through the menus: the game opens
in a 1600 x 1200 window, you against an easy AI, at Medium detail
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

### Camera

Test games have a free camera, to look at the map from any distance and angle:

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

## The game's pathfinding grid: `mw walkable --native`

`mw walkable <map> --native` starts the game headless (no window appears),
reads its pathfinding grid at logic frame 10 (about 7 seconds) and compares it
with the local estimate; `--compare` compares with the grid saved last time
without starting the game. See [the viewer](../viewer.md#walkable-areas) for
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
shots. `--show` runs it in a visible window instead.

- `--shot NAME X Y HEIGHT`: the camera looks at the ground at X, Y from
  HEIGHT (the game's own camera; 300 is its usual zoom).
- `--view NAME X Y DISTANCE PITCH HEADING`: a cinematic shot instead: the
  camera DISTANCE from the ground at X, Y, PITCH degrees below the horizon,
  facing HEADING (0 north, 90 east), angles the game's own camera never
  takes. The game draws no sky near the horizon, so keep the pitch above
  about 20 degrees for views that reach far.
- `--at FRAME` (one per `--shot`, rising) holds each shot until the game's
  logic reaches that frame, about 5 per second of game time, to photograph a
  scripted scenario as it plays out; `--timeout` (240 s) gives a long one
  time. Particle effects fill in over game time: a particle stream needs
  `--at` about 70.
- After moving the camera each shot waits `--settle` rendered frames (30)
  and, with `--delay MS`, at least that many milliseconds.

Use it for what the renderer does not show, such as the water reflections at
High, and when a check needs the game's own view.

## Faster loading in your normal game: `mw patch`

Test games load maps in a few seconds instead of tens of seconds (Brightwater
Fold 4.5 s instead of 17 s, the Greywater Marches 9.2 s instead of 49 s).
`mw patch install` puts the same faster loading into your BFME2 folder, for
every map and every game you start there, skirmish or multiplayer:

```
mw patch            # status: not installed, installed, outdated or foreign
mw patch install    # copy dinput8.dll into the game folder
mw patch remove     # take it out again
```

- It works only with BFME2 1.06 (`install` checks `game.dat`); in any other
  version, or any other program that loads it, it only forwards DirectInput.
- It changes how fast textures are built, not what the game simulates, so it
  should not affect multiplayer; that is untested.
- `install` never replaces a `dinput8.dll` that is not this patch (another
  mod's), and `remove` never deletes one. A folder in Program Files needs an
  administrator prompt.

The patch is its own public project,
[bfme2-map-quickload](https://github.com/NotNBR/bfme2-map-quickload): players
can download `dinput8.dll` from its releases without this toolkit.
