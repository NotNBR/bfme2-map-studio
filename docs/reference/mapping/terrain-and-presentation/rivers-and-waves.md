# Rivers, shore waves and shipwrights

Measured in the stock maps (`local/game/maps`). `mapworkshop.mapkit.rivers`
writes the sections; `mapworkshop.mapkit.sites.shipwright` places the yard.
The record layouts are in the
[specification](../file-structure/specification/triggers-and-water.md).

## Rivers

A `RiverAreas` record is a strip of cross-sections, each the two bank points,
every 50 to 180 along the river and 100 to 350 wide, at one water height. In
the stock multiplayer maps every additive river lies 1 (at most 2) above a
standing water area that covers it: Argonath 90 over 89, the Fords of Isen
295 over 294, Weathertop 96 over 95. The standing water is what units wade
and sink in; the river is the flowing surface over it.

| Look (`add_river(look=...)`) | Textures | Additive | Stock rivers |
|---|---|---|---|
| `flow` | `TWWaterEmpty`, `Noise0000`, `TWAlphaEdge`, `WaterSurfaceBubbles` | yes | 46 |
| `water` | `TWWater01`, the same others | no | 9 |
| `lava` | `TLava_Mor01`, `TLava_Mor02` as alpha edge | no | 14 |

`TWWaterEmpty` is black: an additive river shows only its moving bubbles and
noise, faded out at both banks by the alpha edge. The strip flows from its
first cross-section to its last; which bank a section names first varies
(1,277 to 910 in the stock maps), so it carries no meaning. UV speed is 0.06 in
almost every stock river.

The renderer draws rivers (`render.rivers`) as an approximation: the game's
river shader is not matched, and whether a river strip alone (without
standing water) affects movement has not been tested. `mw render --flow` and
the viewer's key 8 draw arrows along each strip in its flow direction;
`mw rivers` lists the strips' courses. In the Fords of Isen the strips at
water 365 and 366 end in ones at 295, which agrees with first-to-last flow.

## Shore waves

A `StandingWaveAreas` record is a line of two points (144 of the 255 stock
records; 67 have none, 31 one, 12 three) about 400 long, with nine
parameters: final width, final height, initial width and height (percent),
initial velocity, time to fade, time to compress, second wave offset
(milliseconds) and distance from shore. 209 of the 226 records with points use
`(28, 18, 50, 100, 5, 2000, 1000, 3000, 40)` and `wave256.tga`. The land lies
to the left of the line from its first point to its second in 114 of 144.
`add_shore_waves` lays waves along a shoreline given with the land to its
left. The renderer does not draw shore waves; their units are not verified.

## Shipwrights

The stock shipwrights (49, on 13 maps) stand on the waterline, the ground
under them within about 5 of the water level, with their local +x side to open
water (7 to 35 deep 120 out) and land behind them; their capture flag stands
145 behind (local -x), on the land. `shipwright(m, x, y, water)` takes the
map angle towards the water.
