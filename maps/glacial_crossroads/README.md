# Glacial Crossroads

A first-phase **28,500 x 28,500-unit mountain terrain draft**, built from an
empty native map. The supplied clean [vector layout](references/layout.svg) defines
all sixteen numbered sites, sixty route axes and sixty-eight mountain ridges.
The route axes and ridge guides are read directly by [design.py](design.py).
The supplied [landscape reference](references/landscape.jpg) sets the intended
scale: continuous mountain masses, deeply cut valleys and base cirques.
[map.py](map.py) shapes the terrain and writes the map.

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
| Central solid ice field | 120 |

Snowy mountain masses rise toward 2,500, with shoulders and inner divides
between the passes. All pads reserve 1,500 x 1,500 units of level construction
ground plus 150-unit deployment shoulders. Orange main ways in the vector
layout become 340-unit packed-snow corridors; their inner-base ice descents
are 300 units wide. Blue side ways become 180-unit passages in softer white
snow. Junctions share a continuous floor. These widths are terrain clearances,
not verified army-formation capacities. The central ice is walkable terrain,
with no liquid-water plane.

Base 13, immediately north of the ice field, contains one normal-scale
`DwarvenFortressCitadel` as a size reference. Its entrance ramp faces south.
The asset measures about 234 x 113 x 109 units before rotation, compared with
the 1,500 x 1,500-unit level pad. It is in the `ScaleReference` layer, named
`Base13_ScaleReference`; the `base-scale` saved view frames the clearing.

The shared valley floor uses smooth grades. Base approaches limit their
rise/run to 0.30 as they leave the level pads. The surrounding bedrock fills
the spaces between routes, rather than adding isolated ridge strips to a
plain. Named SVG ridges guide the shoulders of these masses; variable valley
cross-sections, relief at several scales and talus relaxation shape their
faces. A 30-unit apron protects the exact route cores after sculpting. The
central ice field is about 4,200 units across, with broad fracture fields and
a frosted shore. Snow-covered scree and exposed rock distinguish steep ground
from the two types of passage. The source line colors are design semantics,
not literal orange or blue paint on the snow.

```powershell
mw build glacial-crossroads
mw view glacial-crossroads
mw walkable glacial-crossroads
mw render --map glacial-crossroads --out local/renders/glacial-phase1 --views maps/glacial_crossroads/views.json
```

Each build saves a labelled `layout.png`, exact `layout.json` geometry and a
`report.json` in its history folder. Checks require the pads to be level at
their specified heights, ice to be the lowest ground, and all sixteen sites
to reach the centre with 70-unit edge clearance through slopes no steeper
than 0.65. Every site must also connect when the central basin is excluded.
In addition, every cell across each of the sixty individual route widths
must be open and have slope at most 0.65; an alternative route cannot mask a
blocked connection. Per-route measured slopes and clear widths are saved in
the build report.
Closed mountain ground is explicitly impassable, not inferred from height.

This phase is for reviewing layout, mountain masses and access. Economy,
scenery, combat balance and native building/formation behaviour are not
verified. The experimental sixteen-site document scaffold follows Frozen
Sundering's local approach; it does **not** establish native sixteen-player
skirmish support. No game launch or installation is part of this draft.
