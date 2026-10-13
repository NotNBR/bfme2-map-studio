# Worked design example: The White Mountain Marches

This is an original concept exercise demonstrating the
[rough-to-polished workflow](map-workflow.md). It does not load an existing
landscape, specify copied terrain, or represent a completed native map. The title
and location are a fictional LOTR-inspired setting, not a claim of a canonical site.

## The brief

A neglected Gondorian frontier road climbs through green foothills below pale,
weathered mountains. A ruined watch-fort on a shoulder overlooks the main approach.
Sheltered woodland and an old settlement suggest a region slowly returning to wild
growth. The mood is spacious, weathered and inhabited in the past, rather than a
uniform field of ruins or an impenetrable fantasy forest.

The intended mode is a two-player large-army skirmish. Retain original BFME2 unit
behavior. Begin with an empty plane at a size proven by a blank native test; treat
an 840 x 950 playable-tile canvas as a provisional sizing study, not a certified
editor limit. Make the size decision before detailed terrain work.

The player should be able to choose between a broad direct approach, a more exposed
route through a saddle, and a longer approach through broken woodland. Armies need
space to form, reinforce, disengage and turn. The watch-fort is the visual anchor;
whether it is merely scenery or a gameplay objective is an explicit brief decision.

Use pale weathered rock, muted green ground, earth paths and warm grey masonry.
Keep snow confined to an intentional high-altitude story, if used at all. Avoid
unrelated biomes and props that compete with the Gondorian setting.

## First session: a canvas and three rough studies

Save an empty-plane checkpoint before any design features exist. Add temporary
functional starts in a second checkpoint and prove loading/basic movement.

Make three thumbnail alternatives:

| Study | Composition | Main question |
|---|---|---|
| A: diagonal valley | One oblique ridge, broad lowlands and an off-center watch-fort | Do the two sides get comparable access to the saddle? |
| B: twin shoulders | Two broad hills frame a central opening; the fort sits on one shoulder | Does the opening become the only useful route? |
| C: mountain edge | A northern wall opens into several southern approaches | Does the dominant skyline leave enough useful interior terrain? |

Choose provisionally, based on route choice and clear large shapes. For this
exercise, develop A. Record why it beats the others; if testing disproves that
reason, return to the studies rather than defending the first choice.

The first terrain pass contains only the ridge, lowland, saddle and fort shoulder.
Review a thumbnail and a cross-section. It should already suggest a place with
depth. No trees, rubble or finished textures are needed to answer that question.

## Second session: turn the sketch into land

Give the ridge irregular spurs and a visible saddle. Shape a broad valley floor
where formations can deploy. Set the fort shoulder above the approach without
making its base a circular cliff. Sketch the old road along a plausible gradient.

Add a small drainage system only after the low ground makes its course clear. If
the river does not improve movement choices or the physical story, keep it modest
or omit it. A large river is not mandatory just because the previous map had one.
Create crossings intentionally and test them as soon as they exist.

Walk infantry hordes, cavalry and a large unit through all three approaches. Test
opposing traffic and regrouping after the saddle. Compare travel times from both
starts. If a route cannot carry the intended force, widen/regrade it now.

At the end of this session, a plain-material terrain view should be convincing and
a sparse skirmish should function. A flat field with a decorative mountain border
does not pass the elevation review.

## Third session: establish materials and one finished scene

Paint the large ground zones. Put exposed rock where the forms need it and more
soil on gentle shoulders. Blend the road into its approaches; let damp material
follow drainage. Judge the whole map before adding small texture variations.

Complete the watch-fort as the quality reference region. Give it an entrance that
connects to the road, grounded foundations, a believable broken wall and rubble
that reflects that collapse. Keep a readable gathering space and an escape route.
Avoid blocking the entrance with convincing-looking but obstructive debris.

Review that one region in game from near and far. If its asset scale, material
transitions or collision are wrong, fix the method before repeating it elsewhere.

## Fourth session: develop supporting regions

Create woodland as several uneven masses with a recognizable sheltered interior,
thinner edges and purposeful clearings. Keep the long flank route legible. The
old settlement should have an interpretable footprint rather than evenly spaced
ruin objects. Leave the main deployment plain comparatively quiet.

Use seeded placement only after inspecting a small accepted sample. Increase
density gradually and measure the cost. Keep smaller rocks near larger outcrops,
undergrowth at woodland edges, and worn ground near meaningful destinations.
Inspect terrain-relative placement after every elevation change.

The same hierarchy applies within a scene: one dominant shape, a few supporting
shapes, then small accents. Do not distribute equal visual noise everywhere.

## Fifth session: finish and test the whole picture

Play the routes with the intended army sizes and opposing forces. Check retreat,
congestion, expansion space and camera behavior. Test all starts and compare with
the sparse baseline using the same units, resolution and camera positions.

Review side-by-side pictures of the fort shoulder, saddle, forest flank and open
plain. They must be visually distinct and actually show those locations. Inspect
texture seams, floating objects, map edges and the skyline from tactical angles.

Polish the most distracting issues first. Re-run movement tests after collision
edits. Capture a final overview only after the native saved candidate passes its
required gates; package that exact map revision with fresh previews and notes.

## Example iteration record

```text
Pass / revision: secondary terrain, proposed revision 03
Question: can two reinforcing infantry groups pass the saddle without bunching?
Input checkpoint and SHA256: fill from the actual saved candidate
Change: broaden the saddle floor and soften its southern approach
Reason: preserve the ridge silhouette while increasing maneuvering space
Expected effect: less congestion; unchanged route choice
Evidence required: both-direction native movement clip, actual travel times,
                   near view and fixed-camera whole-map comparison
Decision: pending evidence
Next change: none until the proposed change has been inspected
```

This is how the process stays like painting while remaining playable: work from
large forms to small ones, keep returning to the whole composition, and make each
pass solve a visible or playable problem before increasing detail.
