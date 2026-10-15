# Rivers, shore waves and shipwrights

Measured in the stock maps (`local/game/maps`). `mapworkshop.mapkit.rivers`
writes the sections; `mapworkshop.mapkit.sites.shipwright` places the yard.
The record layouts are in the
[specification](../format/triggers-and-water.md).

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

The strips reach onto their banks. At the two ends of the stock cross-sections
the ground lies 1 to 10 above the river (median), 40 to 95% of them under the
bank, while 10% in from each end it is 2 to 6 below. So `TWAlphaEdge`'s pale
outer fringe (its outer eighth on each side, where its alpha rises from 0)
falls at the shoreline and partly under the bank. A strip narrower than its
channel puts that fringe over open water as two hard lines along it.
`bank_width(line, height_at, height)` gives `add_river` a width that runs out
to where the ground stands above the river on both sides.

The renderer draws rivers (`render.rivers`) as the game does, ported from
`WaterRenderObjClass::drawRiverWater` (RVA 0x00100A0B, reconstructed in
Open-BFME-2) and the game's `RiverWater.fx` (`shaders/compiled/riverwater.fxo`):

- One vertex pair per cross-section. The river and sparkle textures run 0 to
  0.5 across, the alpha edge 0 to 1; v advances evenly per cross-section, one
  repeat about as long as the first cross-section is wide, scrolls by
  UV speed x seconds and wobbles by sin(2 pi v - 3 x scroll) / 22.
- The noise texture lies in world space at 1/16 scale and scrolls diagonally
  by UV speed x seconds, whatever way the river runs.
- Colour = sparkle x noise + vertex colour x river texture + alpha edge;
  alpha = alpha edge x river alpha x vertex alpha x the river's alpha. A
  white river (all stock ones) is lit as flat ground by the terrain lights,
  times the time of day's `WaterSet` `DiffuseColor` in `water.ini`.
- Blending: source alpha onto one (additive) or inverse source alpha; depth
  test without depth writes, no fog. The game draws every standing water
  area first and the rivers over it, with nothing masked under a river.
- A river whose minimum LOD is above the detail level's WaterLOD is not drawn.

A strip is drawn flat at its height even over a sloping channel (Water Lab's
[channels](../../maps/water_lab/channels.py), in game): a river runs downhill only in flat steps or as particle water, see
[water that runs downhill](water.md).

Not confirmed: which stored end of a cross-section the game puts first (it
mirrors the river texture across), and whether `Opacity` reaches the shader's
w component. Whether a river strip alone (without standing water) affects
movement has not been tested. `mw render --flow` and
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
