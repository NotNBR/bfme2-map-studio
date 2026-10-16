# Glacial Crossroads

A **28,500 x 28,500-unit alpine landscape**, built from an empty native
map. The supplied clean [vector layout](references/layout.svg) establishes
sixteen numbered sites, sixty connections and sixty-eight ridge guides.
[design.py](design.py) reads those anchors and bends the routes and crests
through a shared geographic deformation, keeping base centres and junctions.
The supplied [landscape reference](references/landscape.jpg) sets the intended
scale: continuous mountain masses, deeply cut valleys and base cirques.
[terrain.py](terrain.py) shapes the landscape and snow cover;
[features.py](features.py) defines the two glacier ruptures;
[scenery.py](scenery.py) places winter woods, moraine boulders and ruined
waystations. [map.py](map.py) validates it and writes the native map.

The footprint, base clearings, ice basin and reference geometry are enlarged
1.5 times horizontally. Route widths and the fortress's game scale stay
fixed; elevations retain their existing bands within the native height range.
The project opts into the constructor's experimental large-grid support:
2,850 playable cells per side plus a 30-cell border (2,910 stored samples).
Local builds and previews do not establish native loading or performance at
this size.

| Ground | Provisional height |
|---|---:|
| High corner bases 1, 4, 7, 10 | 1,650 |
| Middle bases 2, 3, 5, 6, 8, 9, 11, 12 | 850 |
| Inner bases 13-16 | 220 |
| Central solid ice field | 120 sheet; raised rupture lips below 220 |
| Two glacier ruptures | floors near 8 and 12; explicitly impassable |

Snowy mountain masses rise toward 2,500, with shoulders and inner divides
between the passes. All pads reserve 1,500 x 1,500 units of level construction
ground within individually shaped, elongated cirques. Sixteen authored
profiles vary the glacial axes, breadths, off-centre headwalls and curved
shoulders. Their height influence fades into the established saddle grading;
the four inner rear entrances remain open. Orange main ways in
the vector layout reserve at least 340 units of passage; their inner-base ice
descents reserve 300 units. Blue side ways reserve 180 units in softer white
snow. Unequal snow-filled recesses widen the actual valley floor between
mountain feet. Broad bends and smaller scallops vary each bank independently;
the narrow spurs beside capture approaches retain their topology.
At the four marked outer diagonal crossings, side valleys meet the main
trough at staggered mouths rather than a single X. Their bends blend over
1,700 units into the existing passes, leaving unequal projecting mountain
shoulders between the openings. `CONFLUENCES` in [design.py](design.py)
records the pins and the separate joining stations.
Junctions share a continuous floor. These widths are terrain clearances,
not verified army-formation capacities. The central ice is walkable terrain;
liquid meltwater is confined to the bottoms of its two ruptures.

Base 13, immediately north of the ice field, contains one normal-scale
`DwarvenFortressCitadel` as a size reference. Its entrance ramp faces south.
The asset measures about 234 x 113 x 109 units before rotation, compared with
the 1,500 x 1,500-unit level pad. It is in the `ScaleReference` layer, named
`Base13_ScaleReference`; the `base-scale` saved view frames the clearing.

The shared valley floor uses smooth grades and shallow snow rolls that fade
out before reaching the construction pads. Base height envelopes approach
a rise/run of 0.30 outside their gentle shoulders. The surrounding bedrock
forms continuous summit chains, unequal cols and descending buttresses.
Their overlapping height envelopes form continuous saddles; four backing
ranges carry the landscape out to the map boundary. Different flank slopes
and variable valley cross-sections give the massifs irregular footprints.
Short snow aprons lead into steep mountain faces; unequal scree fans replace
a fixed band along the foot of every pass. Inner divides retain pronounced
rock spines into the glacier approaches, below the larger crowns, with less
crest rounding than the backing ranges. Cirque shoulders vary around each
base. Two compact buttresses on the southeast and south-saddle approach
bends preserve their detours as the gentle margins reopen. The protected
route floors retain their grading and clearance.

Long grooves start on the flanks and survive the valley cross-section cut,
leaving projecting ribs and recessed gullies instead of continuous planar
walls. Smaller rock shelves vary the faces in depth, while the larger ranges
retain their broader snow shoulders. A deterministic downhill contributing-area
operator joins tributaries and incises gullies, followed by talus relaxation.
This is an authored landform process, not a hydraulic simulation. Geological
fields are calculated at 30-unit spacing and reconstructed cubically onto
the native 10-unit terrain grid. Base floors and route clearance masks stay
at native resolution throughout; mountain shaping cannot enter those cores.

Snow gathers in sheltered hollows and on gentler slopes. Wind-polished snow
marks exposed shoulders, while softer drifts collect in lee hollows. Steep
exposed faces use cliff-mapped rock; scree and partly covered stone mark the lower talus.
Large native snow tiles provide the quiet base surface; grainier snow marks
wind-loaded drifts and compacted travel. Their close tones avoid painted
stripes. The snow fields cross construction pads and basin edges freely,
so the level building squares have no corresponding material outline.
Main ways carry faint traces that wander across the floor and disappear
beneath broad drifts; side ways retain softer white snow.
Broad, slowly moving cloud shadows use a
5,200 x 4,700-unit repeat instead of the stock 660-unit pattern, avoiding
a repeated dark grid across the snow at this landscape's scale.
The stretched `TSNoiseUrb` macro supplies broad mottled tint. The default
relief-like macro was visible as fingerprint ripples even on perfectly flat ice.
The central ice field is about 4,200 units
across, with branching sheet fractures. Its snow cover crosses the basin
boundary in unequal wind-drifted lobes: bare ice reaches between them onto
the low approaches, while frost, compacted snow and soft snow form a broad,
frayed transition. The visible snow line is independent of the movement
boundary. Two offset,
jagged ruptures cut the northern and southern parts of the central field.
Each is roughly 2,200 units long, with a varying opening roughly 200 units
wide, short branching fissures, steep blue walls, still meltwater and
uneven frost lips. Two separate pond-shader water areas sit at height 35,
85 units below the solid sheet, with the dry banks defining their shorelines.
Broad bays and smaller chips vary the rupture widths; intermittent cornices
break the raised rims into unequal sections.
Each build verifies that every submerged sample remains inside its rupture.
Their beds
are about 100-112 units beneath the sheet and their rims rise above it. The
ruptures and their steep shoulders are explicitly impassable. A broad middle
crossing and passages around their tapered ends connect the surrounding ice;
approaches entering the basin can turn around the hazards. Three tapered snow
tongues with frayed edges enter from the valley mouths. The ice and its raised rims stay below
the inner base terraces. The source line colors
are design semantics, not literal orange or blue paint on the snow.

Small Dwarven waystations overlook the inner glacier approaches and selected
high cirques. Watchwalls, broken shelters, fallen walls and low waymarkers
have different surviving structures, grouped fragments and small collapse
fans. Exposed stone follows the masonry instead of a large oval apron.
Their open faces look into the adjoining clearings. Snowy
spruce groves and low twig scrub gather on the lower cirque margins below the high corner sites;
their irregular wings leave the construction pads open. Boulders collect in
broken trains along the main passes and in small groups around cirque edges.
Each lower basin has two unequal woodland sites: a larger sheltered stand
and a smaller wind-torn edge. Sampling concentrates trees into irregular
cores with sparse outliers, leaving other flanks bare. Native crowns may
overlap slightly within a stand, while stems remain separated and their full
measured outlines still clear all protected ground.
Scenery footprints retain at least 70 units beyond the protected pads, route
cores and ice field, and never straddle a terrain movement boundary. Trees
are capped at 1,080, below the native 1,200-tree limit. Cold wind, creaking
woods and occasional rockfalls supply local ambient sound.

Eight capture sites follow the eight circles in the supplied overhead image
`1000073095.jpg`, replacing the previous four diagonal/saddle checkpoints.
Four inner diagonal passes carry native neutral `SignalFire` towers;
the north, east, south and west rear saddles carry stone-and-timber `Inn`
buildings. Each has a nearby `CaptureFlag` using the stock proximity link.
The exact image anchors, final positions, approaches and surrounding base
numbers are recorded in [features.py](features.py).

Small, irregular rock shelves are tucked into the mountain-spur feet.
Beacons sit 24 units above their local valley datum; the wider inn shelves
use a 6-unit rise above the forecourt datum to keep their approaches gentle.
Four marked diagonal passes broaden into elongated fighting hollows around
the towers. Their authored centres are saved in `BATTLE_HOLLOWS` in
[features.py](features.py); the viewer circles locate them without defining
their outlines. Bent axes, unequal banks and tapering ends follow each valley,
with roughly 2,900-3,100 units of length and 920-1,000 units of central
reserved breadth before the snow aprons. The existing graded floors and
shallow snow rolls continue through them; scattered scenery stays outside
the fighting ground. Narrow approaches lead
to the flags; the terrain rises behind the buildings. Only foundations are level, with
broken snow wear and exposed stone instead of circular cleared areas.
Four short connecting paths close the gaps between the outer passes and
inner rear accesses, giving the inns direct approaches from all three
surrounding bases. Positions account for walking distance along these paths,
not just straight-line spacing. The inner towers serve four surrounding
bases apiece. Buildings, flags and ruins retain at least 70 units beyond
the full through-path widths. Doorways/stair-facing sides and flags face
their approaches. These are capturable objectives; the older ruined
waystations remain scenery. Capture behavior has not been tested in a
native match. Each build measures shortest walking paths on a conservative
20-unit grid including water and object footprints. The longest-to-shortest
spread relative to the mean must stay within 6% for each inn's three bases
and 7% for each beacon's four bases. No other base may be closer than those
intended neighbours. Distances and spreads are saved under `capture_access`
in the build report; these are local estimates, not measured unit travel times.
The report also records all sixteen starts' distances and their nearest inn
and beacon, and requires every start to reach every flag. Corner-start parity
is not implied by the neighbouring-group checks. Each capture site has its own
small arrangement of standing wall, broken markers or rockfall behind the
building; decoration
must clear the building footprint and a 70-unit radius around the flag.

The existing fortress reference, start markers and sky object retain their
positions, angles and properties. All objects use the game's normal scale.

```powershell
mw build glacial-crossroads
mw view glacial-crossroads
mw walkable glacial-crossroads
mw render --map glacial-crossroads --out local/renders/glacial-terrain --views maps/glacial_crossroads/views.json --no-objects
```

Each build saves a labelled `layout.png`, exact `layout.json` geometry and a
`report.json` in its history folder. Checks require the pads to be level at
their specified heights, both rupture beds to be at least 95 units below the
sheet with at least 135 units of rim-to-floor relief, all rupture cells to be
blocked, and the remaining ice to be open with slope at most 0.60 and below
the inner bases. All sixteen sites must
reach the centre with 70-unit edge clearance through slopes no steeper
than 0.65. Every site must also connect when the central basin is excluded.
In addition, every cell across each of the sixty individual approach widths
outside the basin must be open and have slope at most 0.65; an alternative
route cannot mask a blocked approach. Every route mouth into the ice must
reach the centre with 70 units of edge clearance. Inside the field, the old
conceptual rays to the centre yield to the two obstacles and open space around
them. Per-route measured slopes, clear widths, rupture depths and scenery
counts are saved in the build report.
Navigation flags follow the steep faces and raised mountain interiors.
Connected gentle snow aprons outside the reserved routes can also be walked;
the route reservations no longer define the entire playable footprint.
Connectivity accounts for the engine's one-cell expansion of blocked terrain,
so tiny necks do not leave isolated pockets along the new walking margins.
Closed mountain ground is explicitly impassable, not inferred from height.
Builds measure cross-sections through the three reviewed mountain marks,
whose coordinates are saved in `MOUNTAIN_MARKS` in [map.py](map.py). They also
check a strip across each of the eight inner spurs: both flanking passages
must be open, with a steep barrier between them and no direct crossing inside
the sampled strip. These local checks complement the full approach and
capture-distance checks; they do not establish native unit behaviour.
The saved cameras include an overview, all four regional directions, the
inner ice terrace, both ruptures, a spruce grove, two ruined waystations,
a close view along a pass and the existing fortress scale reference.
Omit `--no-objects` to see the scenery and the fortress in `base-scale`.

This phase is for reviewing landscape, scenery and access. Economy,
combat balance and native building/formation behaviour are not
verified. The experimental sixteen-site document scaffold follows Frozen
Sundering's local approach; it does **not** establish native sixteen-player
skirmish support. No game launch or installation is part of this draft.
