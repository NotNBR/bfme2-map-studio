# Map projects

Each folder is a project: a `map.toml` that names it and a `map.py` (or, in
the four oldest, a `build.py`) that builds it
([projects and builds](../docs/guide/projects-and-builds.md)). `mw build <id>`
builds one; `mw maps` lists them. A map's description is its README, or the
docstring at the top of its `map.py`.

## Maps

| Map | Id | Players | Build | |
|---|---|---|---|---|
| [Glacial Crossroads](glacial_crossroads/README.md) | `glacial-crossroads` | 16-site landscape | `map.py`, `design.py`, `terrain.py`, `features.py`, `scenery.py` | eroded alpine ranges, snowy passes, spruce groves and Dwarven ruins around a central ice field split by two deep ruptures |
| [The Greywater Marches](greywater_marches/README.md) | `greywater-marches` | 6 | `map.py`, `scenery.py` | rocky grasslands, mountain passes and branching rivers, from a supplied heightmap |
| [The Hollin Dales](hollin_dales/README.md) | `hollin-dales` | 6 (3 vs 3) | `map.py` | autumn Eregion: a closed dale per player, gate-courts, the Sirannon through the ruins of Ost-in-Edhil |
| [Bramble Hollow](bramble_hollow/README.md) | `bramble-hollow` | 2 | `map.py` | a Shire valley: millpond hamlet, wooden footbridges, a creek gorge |
| [Brightwater Fold](brightwater_fold/README.md) | `brightwater-fold` | 2 | `map.py` | a Rohan dale: a river parting round an island hold, fords, creeks, horse paddocks |
| [Eight Kingdoms](eight_kingdoms/README.md) | `eight-kingdoms` | 8 | `build.py` + modules | eight realms round a ruined citadel, 24 stone bridges, from supplied references |
| [The Crown of Cardolan](crown_of_cardolan/README.md) | `crown-of-cardolan` | 8 | `build.py` | a fallen Arnorian hill-city, barrows and old woodland |
| [The Ashen March](ashen_march/README.md) | `ashen-march` | 2 | `build.py` | a ruined Gondorian watch on the edge of Mordor; the first map built from an empty document |
| [Ithilien Frontier](ithilien_frontier/README.md) | `ithilien-frontier` | 2 | `build.py` | the stock Ithilien enlarged threefold, with new relief and scenery |
| [Nanduhirion](nanduhirion/map.py) | `nanduhirion` | 8 | `map.py` | the community 2.02 patch's Nanduhirion, unchanged, beside its enlarged copy |
| [Nanduhirion Enlarged](nanduhirion_enlarged/map.py) | `nanduhirion-enlarged` | 8 | `map.py` | the terrain of the 2.02 patch's Nanduhirion stretched to 14,250 x 14,250; terrain and player starts only |
| [Nanduhirion v1](nanduhirion_v1/map.py) | `nanduhirion-v1` | 8 (16 sites) | `map.py`, `scenery.py`, `blends.py` | Nanduhirion Enlarged laid out for 8 vs 8: sixteen base sites, eight with starts while the game seats eight, wider ramps into the basins, the original's objects at its density, its neutral sites in the middle with a second outpost in each basin lane, soft texture changes through in-between textures chosen per pair |

The `build.py` projects are older: their `main()` reads output folders from
globals the pipeline sets. Start new maps with `map.py` and `build(b)`.

## Scenes

| Project | Id | |
|---|---|---|
| [Battle of the Sirannon Bridge](bridge_battle/map.py) | `bridge-battle` | the Hollin Dales with two armies drawn up at the bridge of Ost-in-Edhil, scripted to clash: a film set, for `mw capture --at`; it starts from the latest `hollin-dales` build, so build that first |
| [Battle of Nanduhirion](nanduhirion_battle/map.py) | `nanduhirion-battle` | Nanduhirion v1 in the thick of a 4 vs 4 that stands for 8 vs 8 (two bases and a double army per player), seated by its `[play]` line-up: you and seven AI; it starts from the latest `nanduhirion-v1` build, so build that first |
| [Battle of Nanduhirion (film)](nanduhirion_battle_film/map.py) | `nanduhirion-battle-film` | the Battle of Nanduhirion with a scripted camera and the interface hidden, for recording; it starts from the latest `nanduhirion-battle` build |

## Labs

Small maps that each answer one question about the game, in the game and in
the renderer. The docstring of each `map.py` lays out the test and records the
answer; the findings are in [how BFME2 behaves](../docs/game/README.md).

| Lab | Id | Question |
|---|---|---|
| [Water Lab](water_lab/map.py) | `water-lab` | how can water run downhill? Waterfalls, stepped rivers, pools and rapids, particle streams ([water](../docs/game/water.md)) |
| [Bridge Lab](bridge_lab/map.py) | `bridge-lab` | do bridges spanned between two endpoints work in BFME2? ([spanned bridges](../docs/game/roads-and-bridges.md#spanned-bridges)) |
| [Cliff Lab](cliff_lab/map.py) | `cliff-lab` | how does the game draw cliff-mapped terrain? ([cliff mapping](../docs/game/terrain-textures.md#cliff-mapping)) |
| [Reflection Lab](reflection_lab/map.py) | `reflection-lab` | what do water reflections show at High, in the game and in the renderer? ([water](../docs/game/renderer/water.md)) |
| [Specular Lab](specular_lab/map.py) | `specular-lab` | how does High terrain shine on textures without a normal map? ([terrain](../docs/game/renderer/terrain.md)) |
| [Blend Lab](blend_lab/map.py) | `blend-lab` | how can a change of terrain texture be wider and softer than the game's one-cell blend? Sixteen approaches side by side, among them bands of in-between textures of varying number and width ([blends](../docs/game/terrain-textures.md#blends)) |

## Adding a map

`mw new "Title"` makes the folder, its `map.toml`, a starting `map.py` and a
README. Add the map to the table above (`mw test` checks that every project
is listed here), and describe it in its README or its `map.py` docstring:
what is where, and what the build checks.
