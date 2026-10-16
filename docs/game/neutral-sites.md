# Neutral sites, Gollum and ambient sound

What the stock skirmish maps place beyond starts and scenery, measured in the
13 multiplayer and 38 War of the Ring maps (`local/game/maps`).
`mapworkshop.mapkit.sites` and `mapworkshop.mapkit.ambient` place the same.

## What each site gives

From the game's INI (`object/neutral/*.ini`, `gamedata.ini`,
`commandset.ini`), BFME2's and the RotWK profile's alike except where the
table says; not measured in play:

| Site | Gives its owner |
|---|---|
| `Outpost` | 25 command points (`OUTPOST_COMMAND_POINT_BONUS`) and 60 resources every 10 seconds (`AutoDepositUpdate`), no bonus on capture |
| `SignalFire` | faster power recharge (`SpellRechargeModifierUpgrade`; RotWK lists -25% and -50%, BFME2 also -35%) |
| `Inn` | one unit to recruit, chosen by the owner's faction (`CommandSetInn...Faction`; RotWK: Dunedain rangers for Men, hobbit shirriffs for Elves; BFME2: elven warriors for Men, Rohan peasants for Elves) |
| Creep lairs | guards that come back after they die: `CaveTrollLair` one cave troll and `FireDrakeLair` one fire drake (every 120 s), `MoriarGoblinLair` eight goblins (every 60 s) |

`mw sites <map>` measures how far each base walks to them
([projects and builds](../guide/projects-and-builds.md#neutral-sites-and-walking-distances)).

## Capture flags

Outposts, inns, signal fires and shipwrights are `LINKED_TO_FLAG`. Each stands
with a neutral `CaptureFlag` beside it, and the flag is what a player
captures: the maps hold 236 flags for 234 such structures, and only one flag
stands alone. The two are linked by nearness alone: no property names the
other. Open-BFME-2 has both kinds (`LINKED_TO_FLAG`, `CAPTUREFLAG`) but not
yet the code that links them.

| Structure | Flag's median distance | Most common direction from the structure's facing |
|---|---|---|
| Outpost | 105 | 0 degrees (46 of 84) |
| Inn | 109 | 225 degrees (31 of 50) |
| SignalFire | 76 | 0 degrees (16 of 59) |
| ShipWright | 145 | 180 degrees (21 of 41) |

`neutral_site(m, template, x, y, angle)` places a structure with its flag
there (`flag=(x, y)` puts it elsewhere). For a site both players walk to,
put the flag where it is equally far from both. Creep lairs (`WargLair`,
`CaveTrollLair`, `BarrowWightLair`, `SpiderLair`, `FireDrakeLair`,
`MoriarGoblinLair` and the snow variants) belong to `PlyrCreeps` and have no
flag: `creep_lair`.

Whether a structure without a flag can be captured at all has not been tested
in the game.

## Gollum

Every multiplayer and War of the Ring map has 4 to 8 waypoints named
`SpawnPoint_SkirmishGollum_<n>`, about 770 to 2,000 from the nearest start;
skirmish Gollum appears at them. `gollum_spawns(m, points)` adds them after the
map's other waypoints; `spread` picks evenly spaced points from candidates.

## Ambient sound

Each multiplayer map has one `AmbStream_` object near its centre, a looping
bed heard everywhere (Harlindon adds wind in three corners), and 6 to 94
`Amb_` emitters heard round where they stand. The same sound repeats about
700 to 1,000 apart (median of the nearest same-sound distances 985, lower
quartile 684). Water sounds follow rivers, creeks and lakes, birds the woods
and open country, wind and falling stones the heights, village sounds the
settlements. `ambient(m, palette, centre, zones)` places a palette's bed and,
for each kind of place, emitters from candidate points at least 700 apart
(`along` samples a line). The palettes (`rohan`, `grassland`, `forest`,
`shire`, `winter`, `desert`) list the emitters the stock maps place with each
bed.
