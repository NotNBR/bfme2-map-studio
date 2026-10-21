# Agent guide

Read this before working in the repository. It routes each task to the page
that covers it; [docs/README.md](docs/README.md) indexes them all.

## Basics

- Every tool runs through one command: `local/venv/Scripts/mw.exe <command>`
  (`mw` once the environment is active). `mw --help` lists the commands. Use the
  checkout's Python, `local/venv/Scripts/python`; the system Python lacks the
  packages.
- If `mw doctor` reports problems, `mw setup` fixes most of them.
- Don't search `local/` or `.claude/` for source code: they hold build output and
  copies of the repository.
- `mw test` runs the tests and checks (Python syntax, import layers, doc links
  and indexes). Run it after changing code or docs; after changing
  `src/mapworkshop/formats/`, run `mw test --corpus`, which also reads and
  rewrites every stock map.
- Commit or push only when the user asks.

## Where to look

| Task | Read |
|---|---|
| Change a map | its project in `maps/<folder>/` ([maps/README.md](maps/README.md)); its README or `map.py` docstring describes it |
| Start a map, the build, `mw diff`, where output goes | [projects and builds](docs/guide/projects-and-builds.md) |
| Which module to use in a `map.py` | [the toolkit](docs/guide/toolkit.md), then that module's docstring |
| Find, look at, turn and measure objects; textures, roads, sounds, effects | [finding assets](docs/guide/finding-assets.md) |
| Design, assess or rework a map's landscape | [designing maps](docs/guide/designing-maps.md), [map graphics](docs/guide/map-graphics.md) for terrain and scenery diagnostics |
| Water, fords, rivers, bridges, walls, sites, scripts: what the game does | [how BFME2 behaves](docs/game/README.md) |
| A picture from the viewer or `mw render` disagrees with the game | [how the game draws a map](docs/game/renderer/README.md), [where it differs](docs/guide/rendering.md#where-it-differs-from-the-game) |
| Render a view; check in the game | [rendering](docs/guide/rendering.md), [testing in the game](docs/guide/testing-in-game.md) |
| The bytes of a `.map` | [the format](docs/format/README.md) |

Pages in [docs/history/](docs/history/README.md) record earlier work, most of it
in bfme-workshop, the repository this one grew out of; their commands do not
exist here. Use them for evidence, not instructions.

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
   - Use names the game knows: `mw find` searches them by what they are
     (`mw find stone bridge`, `mw find --type tree --region shire`,
     `mw find --textures mordor --type cliff`), and `mw item <template> --info`
     prints what the game says about one. A `!` marks obsolete, cinematic,
     game-spawned and faction gameplay templates
     ([finding assets](docs/guide/finding-assets.md)).
   - To choose between objects, look at them: `mw find ... --render` or
     `mw items "*bridge*"` renders a labelled collage with each one's size.
   - Before setting a building's angle, find its front by looking
     (`mw items <template> --views 0/40,90/40,180/40,270/40`), and write in the
     code which side you chose as its front
     ([turning a building](docs/guide/finding-assets.md#turning-a-building-to-face-the-right-way)).
   - To place something against an object's real edges (foam on a bridge's
     piers, a path along a wall), measure it instead of guessing from a
     render: `mw where <map> NAME --section Z` cuts the placed object at the
     map height Z and prints its outline in map coordinates; `mw item NAME
     --section H | --footprint | --bones` does so in the object's own frame
     ([measuring](docs/guide/finding-assets.md#measuring-outlines-footprints-and-positions)).
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
   `mw walkable <map> --compare` checks against an existing native capture
   without starting the game. Use `mw walkable --native` only for an explicit
   game verification (about 7 s). `mw capture <map> --shot NAME X Y HEIGHT
   [--graphics High]` saves screenshots rendered by the game itself (about
   10 s; it runs headless, unseen). Like `--native`, use it only when the user
   wants the game's own view, for example to check something the viewer
   cannot show (water reflections at High).

## Keeping the repository in order

Put each new file where its kind already lives:

- Toolkit code in `src/mapworkshop/<package>/`, each module opening with a
  docstring; its tests beside it in `tests/`.
- Maps, scenes and labs as projects in `maps/`, listed in [maps/README.md](maps/README.md);
  things made with the workshop in `misc/`.
- Build output, renders and one-off scripts in the ignored `local/`, never in
  the repository. No stray files at the root; when something has no obvious
  place, ask.
- Move with `git mv` and update every link and path naming the old place.
  Remove what a change makes obsolete in the same change.

The docs are read by agents first; keep each fact in one place:

- A new or changed command or option: its guide in `docs/guide/`. A new
  `mapkit` module: a docstring, and a line in [the toolkit](docs/guide/toolkit.md).
- Something measured about the game: its page in `docs/game/`, saying how it
  was measured. A new lab: `maps/README.md` and its `map.py` docstring.
- Run logs, map hashes, dated revisions: `docs/history/`, with a one-line
  pointer from the page the finding is on.
- Change a page in place; don't append notes to the end of a guide.
