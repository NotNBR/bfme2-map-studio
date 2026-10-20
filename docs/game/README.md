# How BFME2 behaves

What is known about BFME II 1.06 that a map depends on: measured in the game,
counted in the 72 stock maps, or read from the game's code and the
openbfme2/EA sources. Each page says how its findings were established and
what remains open. The bytes of a map file are in [the format](../format/README.md);
using the toolkit, in [the guides](../guide/projects-and-builds.md).

## Pages

| Page | What it covers | Toolkit |
| --- | --- | --- |
| [Water](water.md) | water is flat: waterfalls, stepped rivers, pools and rapids, particle water; what a map's `map.ini` may define | `blank.water_plane`, `formats.water` |
| [Rivers, shore waves and shipwrights](rivers-and-waves.md) | river strips over standing water, which way they flow, shore waves, where shipwrights stand | `mapkit.rivers`, `sites.shipwright` |
| [Terrain textures](terrain-textures.md) | how blends composite, cliff mapping | `blank.set_materials`, `mapkit.cliffs` |
| [Navigation](navigation.md) | what blocks units: the impassable plane, water deeper than 5, not height | `mapkit.pathing`, `mw walkable` |
| [Roads and bridges](roads-and-bridges.md) | road records, walkable object bridges, bridges spanned between two points | `mapkit.roads`, `mapkit.bridges` |
| [Walls and castles](walls-and-castles.md) | chain walls, castle sites | `mapkit.walls` |
| [Neutral sites](neutral-sites.md) | capture flags, creep lairs, Gollum's spawn points, ambient sound | `mapkit.sites`, `mapkit.ambient` |
| [Battalions](battalions.md) | where a battalion's soldiers stand, where a second battalion sent to a taken point stops, attack orders it cannot carry out | `mw battle` |
| [Scripts](scripts.md) | the stored script tree, the catalogue of 595 actions and 195 conditions, what flags and timers do | `mapkit.script_writer` |
| [Bases and script libraries](bases-and-libraries.md) | `.bse` castle templates, build lists, library linking | `formats.castles` |
| [How the game draws a map](renderer/README.md) | terrain, water, shadows, objects, weather and particle effects, as the renderer reproduces them | `render` |
| [The test-game runtime](runtime.md) | how test games, headless screenshots and faster loading work | `native` |

## Players, economy and AI

Map starts, sides, teams, object ownership, build lists and scripts work
together. Their records are decoded, but broad gameplay and AI behavior still
need controlled scenarios.

- **Starts.** Skirmish maps carry distinct `Player_1_Start` to `Player_N_Start`
  waypoints, N = 2 to 8, with unique IDs; `blank.create` writes the matching
  sides, teams, libraries and script lists. A map's start count, side count
  and active player count are different quantities: neutral, civilian, creep
  and faction-template sides also take records.
- **Ownership.** Keep side-indexed library and script entries aligned and
  resolve owner and team names when changing a setup
  ([players and bases](../format/players-and-bases.md)).
- **Bases and build lists.** Readable and writable ([bases](bases-and-libraries.md));
  whether the AI builds from a map's lists is untested.
- **Untested:** starting resources and victory rules, diplomacy and team
  changes, AI and human slot restrictions, build-list execution and
  rebuilding, AI routes and attack priorities over a long match.

## Not yet established

- Terrain: Rhûn's border-only texture IDs, custom edges, arbitrary cliff and
  blend seams; the dark band on some cliff-mapped faces.
- Water: river and wave units, whether a river strip alone affects movement.
- Lighting: the third light array and the extension fields
  ([lighting](../format/lighting.md)).
- Cameras: interpolation, focal parameters and cinematic authoring.
- Navigation: formation clearance, building placement, bridge destruction,
  every locomotor.
- Scripts: most of the 790 operations' behavior, groups, difficulty,
  objectives and cinematics.
- The game: normal-menu discovery of a map, multiplayer, save and load, long
  matches, other patches.

## How much to trust a finding

A capability needs **read, understand, write, validate and document** coverage.
A byte-perfect round-trip proves preservation; a signature catalogue proves
argument shape; a screenshot proves a rendered view. None alone proves
gameplay behavior. Do not infer a forest speed penalty from trees, or an
impassable mountain from its height: a concept's label is design intent until
the game shows it. Much of what is here was first measured with
[bfme-workshop](https://github.com/NotNBR/bfme-workshop), the repository this
one grew out of; [the history](../history/README.md) keeps those runs.
