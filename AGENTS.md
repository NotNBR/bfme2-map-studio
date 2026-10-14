# Agent guide

Read this before working in the repository. The [README](README.md) has the
layout; [docs/README.md](docs/README.md) indexes the rest.

## Basics

- Every tool runs through one command: `local/venv/Scripts/mw.exe <command>`
  (`mw` once the environment is active). `mw --help` lists the commands. Use the
  checkout's Python, `local/venv/Scripts/python`; the system Python lacks the
  packages.
- If `mw doctor` reports problems, `mw setup` fixes most of them.
- Don't search `local/` or `.claude/` for source code: they hold build output and
  copies of the repository.
- `mw test` runs the tests and checks (Python syntax, import layers, doc links).
  Run it after changing code; after changing `src/mapworkshop/formats/`, run
  `mw test --corpus`, which also reads and rewrites every stock map.
- Commit or push only when the user asks.

## Acting on marks in the viewer

The user points at a map in the viewer with numbered pins, circles, rectangles
and freehand areas. A request like "add farmland in the marked area" or "remove
this bridge" refers to those marks; the user may also paste the text that the
viewer's **Copy for agent** button copies.

1. **Read the marks:** `mw marks` (the map whose marks changed last), or
   `mw marks <map>`. Add `--json` for the exact outline points.
   - Coordinates are map units, x east and y north; z is the terrain height.
   - Each mark lists the objects inside it with their positions, and its
     vegetation by template.
   - An object's `[layer]` is the layer name the build placed it with
     (`add_object(..., layer=...)`); search the project's source for that name
     to find the code that placed it.
   - "Mark 2" or "pin 1" is that id. With a single mark, it is "the marked area".
   - The last line names the map's project and the file that builds it.
2. **Change the project, not the `.map` file.** Builds overwrite
   `local/build/`. The project is `maps/<folder>/`: `map.py` with `build(b)`, or
   `build.py` with `main()` in older projects. Greywater Marches keeps its terrain,
   textures (`PALETTE`), water, sky and lighting in `map.py`, and its objects in
   `scenery.py` (`populate()` and its `place(...)` helper).
   - Keep mark-based edits together in one clearly named function, called from
     the build.
   - Write each mark's coordinates into the code. Mark files live in the ignored
     `local/marks/` and don't travel with the repository.
   - Use names the game knows: templates from `GameAssets().templates`
     (`mapworkshop.render.assets`), textures from `local/game/data/ini/terrain.ini`.
     Prefer what the map already uses.
   - To choose between objects, look at them: `mw items "*bridge*"` (or names,
     or `--from-map <map> --layer <layer>`) renders a labelled collage with each
     one's size in map units, and its JSON lists the sizes; `mw item <template>`
     renders one from any angle ([rendering](docs/rendering.md)).
   - Before setting a building's angle, find its front by looking: models don't
     agree on which side that is, and many have doors on more than one side.
     `mw items <template> --views 0/40,90/40,180/40,270/40` shows its local
     -y, -x, +y and +x sides. Map angles are radians, counter-clockwise; at
     angle 0 a model's local +y points north. Write in the code which side
     you chose as its front.
3. **Build:** `mw build <map>`. A failed build leaves the previous one in place;
   an open viewer reloads a successful one by itself. The build ends with what
   it changed since the previous build; `mw diff <map>` shows it again.
4. **Check:** the changes should be the requested ones: a deliberate edit lists
   first, with the layers it shifted (seeded scatter around it) after it.
   `mw marks <map>` again shows the new objects under the mark.
   `mw render --map <map> --out local/renders/check --view name target=X,Y distance=1500`
   renders a view to look at. After changing terrain, water, buildings or
   bridges, `mw walkable <map>` computes a local walkability estimate and lists
   areas cut off from every start; add `--walkable` to a render to see it.
   After changing rivers, add `--flow` to a render to see which way each strip
   flows and where strips join.
   `--compare` checks against an existing native capture without starting the
   game. Use `--native` only for an explicit game verification (about a minute).

[Making maps](docs/making-maps.md) documents projects, the build and the
toolkit; [the viewer](docs/viewer.md) documents marks.
