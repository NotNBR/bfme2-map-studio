# Glacial Crossroads

A **28,500 x 28,500-unit alpine landscape**, built from an empty native
map. The supplied clean [vector layout](references/layout.svg) establishes
sixteen numbered sites, sixty connections and sixty-eight ridge guides.
[design.py](design.py) reads those anchors and bends the routes and crests
through a shared geographic deformation, keeping base centres and junctions.
The supplied [landscape reference](references/landscape.jpg) sets the intended
scale: continuous mountain masses, deeply cut valleys and base cirques.
[terrain.py](terrain.py) shapes the landscape and snow cover;
[features.py](features.py) defines the two glacier ruptures and the sealed
gates; [scenery.py](scenery.py) places the ruins, gates, shrines, camps and
battle remains, [wilds.py](wilds.py) the forests, thickets, boulders and
tarns, both through the shared clearances of [placement.py](placement.py).
[map.py](map.py) validates it and writes the native map.

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
snow. Independent long profiles on the two banks alternate projecting rock
shoulders with snow-filled recesses. The main valleys have larger bays;
tributary and rear saddle passes have quieter, narrower variations. Recesses
favour the outside of bends and taper towards junctions. Their amplitude
reduces beside the capture sites and inner divides, preserving the authored
battle hollows and the narrow spurs between approaches.
At the four marked outer diagonal crossings, side valleys meet the main
trough at staggered mouths rather than a single X. Their bends blend over
1,700 units into the existing passes, leaving unequal projecting mountain
shoulders between the openings. `CONFLUENCES` in [design.py](design.py)
records the pins and the separate joining stations.
Junctions share a continuous floor. These widths are terrain clearances,
not verified army-formation capacities. The central ice is walkable terrain;
liquid meltwater is confined to the bottoms of its two ruptures.

The center pin at (14253.6, 14191.3) carries `RuinedTowerSnow` at 4x scale,
with its door facing south. Its level footing sits 80 units above the ice;
broad, unequal snowy shoulders and rocky buttresses merge it into the
glacier. Its map-local child template, `GlacialArenaRuinedTower`, inherits
the stock artwork and enlarges its collision radius and height explicitly.
Twelve snowy arches form four broken arcs with broad cardinal entrances;
eight outer snowy rock spires vary from 2x to 3.2x native scale. Map-local
definitions give the enlarged scenery matching collision geometry.
The build checks the foundation and connectivity between all four entrances.
This centerpiece is the deliberate exception to the scenery's ice exclusion.

Base 13, immediately north of the ice field, contains one normal-scale
`DwarvenFortressCitadel` as a size reference. Its entrance ramp faces south.
The asset measures about 234 x 113 x 109 units before rotation, compared with
the 1,500 x 1,500-unit level pad. It is in the `ScaleReference` layer, named
`Base13_ScaleReference`; the `base-scale` saved view frames the clearing.

Each base's height band is clipped against the radial valley grade, which
left dead-flat terraces bending into straight ramps along the cirque rims,
and trenches beside the inner basins (twelve viewer marks around the inner
ring). A screened relaxation of the floor at 30-unit spacing, about 650
units in reach, now rounds those creases into long transitions; the pads
and the ice core are fixed, and the correction fades out around the capture
sites, whose walking distances were balanced on the unrelaxed floor.
The shared valley floor uses smooth grades and shallow snow rolls that fade
out before reaching the construction pads. Base height envelopes approach
a rise/run of 0.30 outside their gentle shoulders. The surrounding bedrock
forms continuous summit chains, unequal cols and descending buttresses.
Their overlapping height envelopes form continuous saddles; four backing
ranges carry the landscape out to the map boundary. Different flank slopes
and variable valley cross-sections give the massifs irregular footprints.
Snow aprons vary in depth along each flank: some rock feet meet the valley
directly while other reaches carry broader snow slopes. These transitions
follow a long geological field rather than a fixed offset from the route.
The sculpting field smooths the signed distance across valley boundaries,
preventing raster stair steps from becoming repeated scallops along a face.
A rounded change of grade joins the apron to the steep rock above it; the
native route and construction reservations remain protected separately.
Unequal scree fans break up the lower faces. Inner divides retain pronounced
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
Before that operator runs, small irregularities and ridged ribs are added to
the steep faces only, with their mean removed; flow gathers between the ribs,
so even the smaller spurs carry aretes and gullies rather than smooth cones.
This is an authored landform process, not a hydraulic simulation. Geological
fields are calculated at 30-unit spacing and reconstructed cubically onto
the native 10-unit terrain grid. Base floors and route clearance masks stay
at native resolution throughout; mountain shaping cannot enter those cores.

Retreating ice left broken lateral moraines a little way out from the
mountain feet and hummocky till across the open floors: low ridges and
rounded mounds up to about 34 units, lower than the 55-unit rise that closes
ground to movement, fading out before route cores, pads, capture shelves and
the ice. Their crests are wind-scoured, with stones breaking through. Each
sealed gate (below) stands in a carved portal: a level forecourt before it
and a sheer face behind, which covers the back of the arch.

Snow gathers in sheltered hollows and on gentler slopes. Wind-polished snow
marks exposed shoulders, while softer drifts collect in lee hollows; high lee
snowfields are smooth blue-white cornice snow. Rock shows through the snow
by the actual slope, in three steps: stones breaking through in patches below
gullies and on scoured slopes, snow-streaked ledges, and bare cliff-mapped
faces. Gullies, hollows and lee faces hold snow onto steeper ground, so the
faces are streaked rather than uniform walls. Cliff and ledge texture follow
the face's broad slope, keeping each mapped cliff one continuous region in
which only the flat treads hold snow; unmapped rock textures beside mapped
ones showed as offset blocks. Cells are cliff-mapped from a slope of 0.7.
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
across, with branching sheet fractures, broad irregular fields of older
crazed ice and fine snow dust blown into streaks along the wind. Low pressure
swells of a few units move the light across it; they fade out before the
tower's footing and the rupture rims. Its snow cover crosses the basin
boundary in unequal wind-drifted lobes: bare ice reaches between them onto
the low approaches, while frost, compacted snow and soft snow form a broad,
frayed transition 620-960 units deep. The visible snow line is independent of the movement
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

An old Dwarven road crossed these passes. Small waystations overlook the
inner glacier approaches and selected high cirques. Watchwalls, broken
shelters, fallen walls and low waymarkers have different surviving
structures, grouped fragments and small collapse fans. Exposed stone follows
the masonry instead of a large oval apron. Their open faces look into the
adjoining clearings. In the headwall behind each high corner cirque stands
the sealed gate of an abandoned hold (`GATES` in [features.py](features.py)):
an Erebor arch and doors between two columns, set into the rock, with two
hooded statues guarding the forecourt, derelict ore carts, fallen masonry
and a skeleton before the doors. About two dozen carved shrines
(`EreborNiche01`) stand at the mountain feet beside the main ways, roughly
every 1,900 units and alternating sides, their open backs set into the
slope. Five middle cirques have a travellers' camp in a sheltered margin:
two tents facing a fire, a broken cart, barrels and beams on trampled snow.
Bones, cast-off arms and broken carts lie scattered through the four
fighting hollows; they are flat props that do not obstruct movement, so
they may lie inside the hollows, but keep off the route cores.

Spruce forest fills the sheltered lower slopes and valley margins below a
treeline that wanders around 1,400 units ([wilds.py](wilds.py)). A density
field combines broad stands, shelter (concavity over about 250 units),
altitude, slope, ground and distance from the ice: tall dense cores in the
hollows at the mountain feet, smaller and thinner trees at the edges, and
stunted spruce and weathered snags where the forest gives out. Stands thin
out toward routes and pads instead of ending in a row along the clearance
line. Around the high corner cirques the treeline climbs to about 1,960, so
their basins at 1,650 are wooded like the lower ones, the stands dwindling
into stunted trees below the headwalls; the sealed gates' forecourts stay clear.
Trees take per-object scales (0.52-1.48) and occasional windfall logs; lone
gnarled dead trees punctuate the open floors. Low thickets gather at forest
edges and in hollows; talus boulders collect below the faces and, smaller
and farther from routes, on the open moraines; groups of enlarged pinnacles
stand on convex crests, always on closed ground. Most lower cirques have a
small painted frozen tarn of clear blue ice with a frost rim, outside the
pad; the stock FrozenPond models read as dark holes against this snow.
Faint trodden lines wander from each base out to the mouths of its passes.
Boulder trains still follow the main passes, with small groups around the
cirque edges.

Scenery footprints retain at least 70 units beyond the protected pads, route
cores and ice field, and never straddle a terrain movement boundary. The
map places about 9,900 trees and 2,000 shrubs, far past the game's tree and
shrub buffers ([objects and vegetation](../../docs/game/renderer/objects.md)):
the game draws only the first 1,200 trees and 2,000 shrubs in map order.
Forest trees are placed nearest the bases first, so the stands around the
bases are the ones the game draws; `mw render --engine studio
--vegetation-limits` shows that view. Cold wind, creaking woods and occasional rockfalls supply local
ambient sound.

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
a close view along a pass, two sealed gates, a travellers' camp, a forest
edge, a road shrine and the existing fortress scale reference.
Omit `--no-objects` to see the scenery and the fortress in `base-scale`.

This phase is for reviewing landscape, scenery and access. Economy,
combat balance and native building/formation behaviour are not
verified. The experimental sixteen-site document scaffold follows Frozen
Sundering's local approach; it does **not** establish native sixteen-player
skirmish support. No game launch or installation is part of this draft.
