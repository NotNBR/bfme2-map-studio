# Getting started

You need:

- **Battle for Middle-earth II**, patched to 1.06. The workshop reads its files and
  never changes them.
- **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/).
  Tick "Add python.exe to PATH" in the installer.
- A graphics card with **OpenGL 4.3**, which any card from the last ten years has.

## Install

Download or clone this repository, then double-click **`Install.cmd`**. It:

1. creates a Python environment in `local\venv` and installs the packages;
2. finds BFME2 (the registry, the usual install folders, or next to this folder),
   or asks you to drag its folder into the window;
3. copies the game's INI files and maps into `local\game` (a few seconds);
4. adds **Map Workshop** to the Start menu;
5. checks everything (`mw doctor`).

Run it again at any time: it only does what is missing. If BFME2 moves, run
`mw setup --game "<folder>"`.

## Open a map

Double-click **`Map Workshop.cmd`** or pick **Map Workshop** from the Start menu.
The viewer opens on your last map; the **Map** menu lists the map projects and
the game's own maps. Press F1 for the controls, or read [the viewer](viewer.md).

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

## Next

- [Making maps](making-maps.md): a project, its build and the toolkit.
- [The viewer](viewer.md): navigation, live reload, marks and agents.
- [Map workflow](map-workflow.md): designing a map from composition to detail.
