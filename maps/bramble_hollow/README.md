# Bramble Hollow

A small, cozy 2-player Shire valley, 500 x 500 cells.

```
mw dev bramble-hollow       rebuild on every save, with the viewer open
mw play bramble-hollow      install it into the game and start BFME2
```

- **Valley.** A gentle green valley ringed by low wooded hills, with a high
  ridge along the north-west border that rises above the treeline.
- **Brook.** It winds in from the north edge, fills a millpond in the middle
  and leaves by the south edge. Units can cross it only at two wooden
  footbridges. The channel stays deep beneath and beside the decks, so there
  is no ford around either bridge.
- **Creek.** On player 1's bank a creek runs in from the west edge through a
  deep gorge in the hills and the ridge, past the orchard, into the brook just
  above the pond. The bank lane crosses it only on a third footbridge,
  and a plank rope bridge spans the gorge high on the ridge
  (scenery, in the border).
- **Millpond.** An oval pond with a rocky island and an old tree, a dock and
  rowboat on each bank, ducks and rushes.
- **Hamlet.** Cottages and a barn on both banks of the pond, each with a
  footpath to the lane, gardens, an orchard, haystacks, carts and sheep, with
  hedges and flowers along the lanes.
- **Fairness.** The layout is point-symmetric about the centre (apart from
  the ridge, the creek and the six cottages beyond the hamlet's ends). Both starts are level, open and equally
  far from the hamlet and from each bridge; the build measures the walking
  distances and refuses an unfair result.

`map.py` builds the map: heights, textures, objects, water and sky. See
[Making maps](../../docs/making-maps.md).
