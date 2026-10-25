# Getting started

You need:

- **Battle for Middle-earth II**, patched to 1.06. The workshop reads its files and
  never changes them.
- **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/).
  Tick "Add python.exe to PATH" in the installer.
- For the viewer and `mw render`: **Rise of the Witch-king 2.01** (English)
  beside BFME2 1.06. Both run on [OpenBFME](testing-in-game.md#openbfme-mw-play---godot),
  a port of the game's engine to Godot, which plays from those files;
  `mw play --godot --download` fetches the ones your installs lack. The first
  start builds OpenBFME, which takes a few minutes.
- A graphics card with Vulkan (for the viewer, `mw render` and `mw item`),
  which any card from the last ten years has.

## Install

Download or clone this repository, then double-click **`Install.cmd`**. It:

1. creates a Python environment in `local\venv` and installs the packages;
2. finds BFME2 (the registry, the usual install folders, or next to this folder),
   or asks you to drag its folder into the window;
3. copies the game's INI files and maps into `local\game` (a few seconds);
4. adds **Map Workshop** to the Start menu;
5. checks everything (`mw doctor`).

Run it again at any time: it only does what is missing. If BFME2 moves, run
`mw setup --game "<folder>"`; `mw setup --force` extracts the game data again
even when it is up to date.

## Rise of the Witch-king

The ROTWK profile combines **all BFME2 archive assets with the complete ROTWK
2.01 archive library**. The expansion overrides matching paths; BFME2-only
assets remain available. It reads the retail expansion archives and official
`_patch201*.big` files, excluding 2.02, HD and timer packs even if they are
installed in the same folder. The studio reads these files; it does not bundle
them into a map.

Configure both game folders once:

```powershell
mw --profile rotwk setup --game "D:\Games\BFME2" --rotwk "D:\Games\ROTWK"
mw config profile rotwk
mw find angmar
mw new "Angmar Valley"
mw dev angmar-valley
```

Omit `--game` if BFME2 is already configured. `mw config profile bfme2` restores
the BFME2 default; `mw --profile bfme2 find bridge` selects it for one command.
Restart an open viewer after changing the default. Its title shows the active
game. Commands and their child processes keep that profile for their lifetime.

ROTWK uses `local/profiles/rotwk/` for extracted data, caches, builds, build
history, marks and renders. BFME2 keeps its existing `local/` paths. Map source
projects are shared, so build a project in the selected profile before viewing
or playing it. Both profiles' stock maps appear in the viewer's Map menu; the
viewer opens them under the RotWK profile, from RotWK's archives.

`mw play` and **Test In-Game** start a ROTWK skirmish directly on the build,
you against an easy AI, in an isolated runtime with clean 2.01 assets. This
requires the verified executable described in [the runtime](../game/runtime.md#rotwk-201).
The shared quickload DLL accelerates its terrain textures automatically.
`mw patch install` also applies it to your configured ROTWK installation.
`mw play MAP --check` runs a short hidden gameplay test and closes it afterward.
ROTWK test games have the same free-camera zoom, tilt, scrolling and reset
controls as BFME2. `mw capture` works in ROTWK too, but ROTWK keeps its
normal fog unless the map's scripts reveal it; automatic fog reveal and native
pathfinding capture remain BFME2 1.06 features.
Model rendering and local walkability estimates work in either profile.

## Open a map

Double-click **`Map Workshop.cmd`** or pick **Map Workshop** from the Start menu.
The viewer opens on your last map; the **Map** menu lists the map projects and
the game's own maps. Press F1 for the controls, or read [the viewer](../viewer.md).

The maps in `maps/` need one build each before they appear: `mw build greywater`,
or **Build** in the viewer.

## The `mw` command

Open a terminal in this folder (in Explorer: type `cmd` in the address bar).
`local\venv\Scripts\mw.exe` is the command; activate the environment once with
`local\venv\Scripts\activate` so that `mw` alone works.

```
mw                         open the viewer on your last map
mw maps                    list the map projects
mw new "Misty Vale"        start a new map project
mw dev [MAP]               rebuild on every save, with the viewer open
mw build [MAP] [--install] build a map
mw play [MAP]              test it in-game: BFME2 straight in a skirmish on it
mw marks [MAP]             print the viewer's marks, for an agent
mw doctor                  check the setup
```

`MAP` is a project id or any unique start of it: `mw play grey` plays the
Greywater Marches. Without a map, commands use the one you worked on last.
`mw --help` lists every command and `mw <command> --help` its options:

| Commands | Guide |
|---|---|
| `mw setup`, `mw doctor`, `mw config`, `mw test` | here, and [projects and builds](projects-and-builds.md#where-things-live) |
| `mw maps`, `mw new`, `mw dev`, `mw build`, `mw history`, `mw diff`, `mw walkable`, `mw rivers`, `mw sites` | [projects and builds](projects-and-builds.md) |
| `mw find`, `mw item`, `mw items` | [finding assets](finding-assets.md) |
| `mw render` | [rendering](rendering.md) |
| `mw engine package`, `mw engine check` | [engine runtime](engine-runtime.md) |
| `mw graphics` | [map graphics](map-graphics.md) |
| `mw play`, `mw capture`, `mw battle`, `mw patch`, `mw walkable --native` | [testing in the game](testing-in-game.md) |
| `mw workspace` | [hand-editing](hand-editing.md) |
| `mw view`, `mw marks` | [the viewer](../viewer.md) |

`mw test` runs the unit tests and the repository's checks (Python syntax,
import layers, documentation links and indexes); `mw test --corpus` also reads
and rewrites every stock map, after a change to `src/mapworkshop/formats/`.

## Next

- [Projects and builds](projects-and-builds.md): a project, its build and how to check it.
- [The toolkit](toolkit.md): what a `map.py` builds with.
- [Designing maps](designing-maps.md): from composition to detail.
- [The viewer](../viewer.md): navigation, live reload, marks and agents.
