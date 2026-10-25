# Documentation

Four kinds of page, each in its own folder. A guide tells you how to do
something with the workshop; a game page says what BFME2 does; the format
describes the bytes of a map file; history records earlier work and is not
instructions.

## Guides: using the workshop

| Task | Page |
|---|---|
| Install, open a map, the `mw` command | [Getting started](guide/getting-started.md) |
| Start a project, `map.toml`, the build, `mw diff`, where things live | [Projects and builds](guide/projects-and-builds.md) |
| Which module does what in a `map.py` | [The toolkit](guide/toolkit.md) |
| Find an object, texture, road, sound or effect by what it is; look at it; turn it the right way | [Finding assets](guide/finding-assets.md) |
| Design a map, from composition to detail | [Designing maps](guide/designing-maps.md) |
| Render views of a map without the game | [Rendering](guide/rendering.md) |
| Engine bundles, source builds and the Studio/OpenBFME boundary | [Engine runtime](guide/engine-runtime.md) |
| Inspect terrain relief, slopes and scenery; compare maps | [Map graphics](guide/map-graphics.md) |
| Play a map, read its pathfinding grid, take screenshots in the game, faster loading | [Testing in the game](guide/testing-in-game.md) |
| Hand-edit a single `.map` file, with WorldBuilder | [Hand-editing](guide/hand-editing.md) |
| The viewer: navigation, live reload, marks for agents | [The viewer](viewer.md) |

The map projects themselves are listed in [maps/](../maps/README.md).

## How BFME2 behaves

[The index](game/README.md) lists what is known, page by page: water, rivers,
terrain textures, navigation, roads and bridges, walls, neutral sites, scripts,
bases; how the game draws a map, and how the test-game runtime works; and
what is not yet established.

## The map-file format

[The specification](format/README.md): the bytes of a `.map` and its companion
files, chapter by chapter, with the corpus coverage, the rules a writer must
keep and the tools that inspect a map.

## History

[Earlier work](history/README.md), most of it done with bfme-workshop, the
repository this one grew out of: lab runs with their map hashes, the first
maps' build logs. Its commands do not exist here.

## Licenses

[Licenses and provenance](licenses/README.md).

## Keeping the docs in order

- A new or changed command or option goes into its guide; a new `mapkit`
  module gets a docstring and an entry in [the toolkit](guide/toolkit.md).
- Something measured about the game goes into its page in [game/](game/README.md),
  with how it was measured; a new lab goes into [maps/README.md](../maps/README.md).
- A run log, a map hash, a dated revision: [history/](history/README.md), with a
  one-line pointer from the page whose finding it supports.
- Change a page in place; don't append dated notes to a guide.
- `mw test` checks every link and anchor, that `maps/README.md` lists every
  project, that the guides show every `mw` command, and that no page outside
  `history/` gives bfme-workshop's commands.
