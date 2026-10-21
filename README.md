# BFME2 Map Studio

Create **Battle for Middle-earth II** maps with Python, preview them in a live
3D viewer, and mark places on the map for an AI coding agent to edit.

> Built with help from [OpenBFME2](https://github.com/Open-BFME/Open-BFME-2).

https://github.com/user-attachments/assets/cc486383-fd9f-493d-bc89-0c6fc610a626

Map Studio showcase · 82 seconds · 8 MB preview ·
[1080p MP4 (19.5 MB)](docs/media/viewer-trailer.mp4)

Explore a map, mark areas for an agent, and see edits reload in the viewer.

- **Maps as code.** A map is a folder with a `map.toml` and a `map.py`: heights,
  textures, water, objects and sky, in Python. Every build is reproducible and
  kept.
- **A live viewer.** The map as the game draws it, on OpenBFME (a port of the
  game's engine to Godot), with the units in their idle animations. It reloads
  whenever the map is rebuilt, so `mw dev` turns saving a file into seeing the
  result.
- **Marks for agents.** Pin, circle, frame or draw around a place, press **Copy
  for agent** and ask for "a forest in mark 2". The marks come with their map
  coordinates and the objects inside them.
- **Into the game.** `mw play` (**Test In-Game** in the viewer) starts BFME2
  straight in a skirmish on your map, with a free camera that zooms out to the
  whole map and tilts to any angle.
- **Check your map.** Estimate walkability, inspect changes between builds, and
  render views for review. Walkability is a local estimate; verify final gameplay
  in BFME2.

## Start

You need **Windows**, your own copy of **BFME2 patched to 1.06**,
[Python 3.11+](https://www.python.org/downloads/) and a graphics card with
Vulkan support. The viewer and `mw render` also need
**Rise of the Witch-king 2.01** (English), whose files OpenBFME plays from
([getting started](docs/guide/getting-started.md)). An optional **Rise of the Witch-king** profile adds the
expansion's assets to BFME2's library, with separate builds and caches; see
[ROTWK setup](docs/guide/getting-started.md#rise-of-the-witch-king). ROTWK 2.01
supports direct skirmish tests and the free camera with the verified engine;
native capture tools require BFME2 1.06. BFME1 support has not been tested.

1. [Download the source](https://github.com/NotNBR/bfme2-map-studio/archive/refs/heads/main.zip)
   and extract it, or clone the repository:

   ```sh
   git clone --recursive https://github.com/NotNBR/bfme2-map-studio.git
   ```

   `--recursive` also fetches [bfme2-map-quickload](https://github.com/NotNBR/bfme2-map-quickload),
   the faster map loading test games use (`mw setup` fetches it in a clone made
   without). The zip download lacks it: test games then load at the game's own
   speed.

2. Open the folder and double-click **`Install.cmd`**. It finds the game, sets everything up and adds
   **Map Workshop** to the Start menu.
3. Double-click **`Map Workshop.cmd`** to open the viewer.

The launcher and command-line tool still use the names **Map Workshop** and
**`mw`**. In PowerShell, from the repository folder:

```powershell
.\local\venv\Scripts\Activate.ps1
mw new "Misty Vale"     # Start a map
mw dev misty-vale       # Build, open the viewer, and rebuild on every save
mw play misty-vale      # Test it in-game
```

You can also run `.\local\venv\Scripts\mw.exe` directly without activating the
environment. More in [Getting started](docs/guide/getting-started.md).

## The maps

| Map | Players | |
|---|---|---|
| [The Greywater Marches](maps/greywater_marches/README.md) | 6 | Rocky grasslands, mountain passes and branching rivers |
| [The Hollin Dales](maps/hollin_dales/README.md) | 6 | Autumn Eregion: a dale for each player, the Sirannon through the ruins of Ost-in-Edhil |
| [Eight Kingdoms](maps/eight_kingdoms/README.md) | 8 | Eight realms around a ruined citadel, 24 stone bridges |
| [The Crown of Cardolan](maps/crown_of_cardolan/README.md) | 8 | A fallen Arnorian hill-city, barrows and old woodland |
| [The Ashen March](maps/ashen_march/README.md) | 2 | A ruined Gondorian watch on the edge of Mordor |
| [Ithilien Frontier](maps/ithilien_frontier/README.md) | 2 | A wooded Gondorian frontier with four river crossings |
| [Bramble Hollow](maps/bramble_hollow/README.md) | 2 | A Shire valley with a millpond hamlet, wooden footbridges and a creek gorge |
| [Brightwater Fold](maps/brightwater_fold/README.md) | 2 | A Rohan dale: a river parting round an island hold, creeks, fords and horse paddocks |

[maps/](maps/README.md) also holds a battle scene and the labs, small maps that
each test one thing in the game.

## Documentation

- [Getting started](docs/guide/getting-started.md), then [projects and builds](docs/guide/projects-and-builds.md)
  and [the toolkit](docs/guide/toolkit.md)
- [Designing maps](docs/guide/designing-maps.md): from composition to detail
- [The viewer](docs/viewer.md): navigation, live reload, marks for agents
- [How BFME2 behaves](docs/game/README.md): water, navigation, bridges, scripts and the rest, measured in the game
- [The map-file format](docs/format/README.md)

[docs/](docs/README.md) indexes every page.

Agents start with [AGENTS.md](AGENTS.md).

## Layout

| Folder | |
|---|---|
| `maps/` | the map projects |
| `src/mapworkshop/` | the toolkit: `formats` (native files), `mapkit` (building maps), `render`, `viewer`, `native` (the game runtime: test games, the pathfinding grid, screenshots) and the `mw` command |
| `docs/` | `guide/` (using the workshop), `game/` (how BFME2 behaves), `format/` (the map file), `history/` (earlier work) |
| `local/` | ignored: the environment, the game data, builds, marks and renders |

`mw test` runs the tests and the repository checks.

## License

Code is GPL-3.0-only; see [LICENSE.txt](LICENSE.txt) and the
[third-party notices](docs/licenses/README.md). The game and its assets
are not included: you supply your own copy of BFME2, and Map Studio only reads
it. This project is not affiliated with or endorsed by EA or its licensors.
