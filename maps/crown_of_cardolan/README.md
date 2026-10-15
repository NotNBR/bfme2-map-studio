# The Crown of Cardolan

An original eight-player battlefield around a fallen Arnorian hill-city. The
landscape is invented for this workshop, inspired by the ruined northern kingdoms of
Middle-earth; it is not presented as a canonical reconstruction of a named city.

## Composition

Eight rival marches share a ring of open moorland around the ruined Crown.
The 920 × 920 playable tiles span 9,200 × 9,200 world units, with a 30-tile border
and 980 × 980 stored height samples. Eight perimeter starts are evenly spaced
around the same radius. Each has a graded building area, a direct inward approach
and access to a winding outer road. The breached city has its own circulation
route, so reaching the centre does not require passing through one narrow gate.

The repeating gameplay opportunities are intentional. Scenery is asymmetric:
Black Pines and Greywood have different tree families; the eastern barrows are
small earthen mounds with stones and broken statues; the Old Quarry has an excavated
floor and abandoned stone; Northwatch overlooks the road; outer hamlets retain
lanes, carts and fire pits. The central citadel combines a broken stronghold,
tower, statues, fragments of curtain wall and eight ruined gate districts.

Building space and army routes are reserved before optional detail. Rubble clusters
around masonry and the backs of settlement plots. Forest floor objects follow
woodland edges. Exposed shoulders receive rock outcrops; empty plains are not
covered with random prop noise. The base terrain uses muted, fine stony soil,
with material changes reserved for wear and exposed rock. There is no broad soil
camouflage pass. Native cast shadows and visible props use the tested Medium preset.

## Painting stages

1. Create a new uniform plane, then add eight functional starts in a separate checkpoint.
2. Compose a broken crown around open moorland. A central bottleneck was rejected
   because seven opponents would overload it; isolated corner forts would leave
   the central landscape without a purpose. The selected layout offers a centre
   and two circulation routes.
3. Sculpt boundary shoulders, interior spurs and a city terrace. Domain warp,
   rotated fBm and thermal relaxation break up the forms; road and base grading
   happen afterward.
4. Check level base disks and flood the graded road band to confirm all eight
   starts connect. This is an authoring check, not a substitute for horde movement.
5. Inspect the actual terrain artwork, then paint a restrained material palette.
6. Place the main keep first, then breached walls, districts and regional scenes.
7. Add ecological clusters, masonry rubble and forest floor detail; review actual
   native close-ups and the whole-map view before accepting the result.

## Build and play

```
mw build crown-of-cardolan     build it
mw view crown-of-cardolan      look at it in the viewer
mw play crown-of-cardolan      install it into the game and start BFME2
```

`mw build crown-of-cardolan -- --phase functional|terrain|detail` builds an earlier stage
(`polish`, the default, is the finished map).
The map has eight unrestricted starts; choose teams in a normal skirmish lobby.

## History

The launch presets, native checks, captures and recorded builds made with
bfme-workshop, the repository this one grew out of, are in
[its history](../../docs/history/crown-of-cardolan.md).
