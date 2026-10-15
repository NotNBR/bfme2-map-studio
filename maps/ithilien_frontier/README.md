# Ithilien Frontier

`build.py` builds this map from the stock map "map wor ithilien" (from `mw setup`).

```
mw build ithilien-frontier     build it
mw view ithilien-frontier      look at it in the viewer
mw play ithilien-frontier      install it into the game and start BFME2
```

The stock Ithilien landscape enlarged to three times Grey Mountains' area, with
sculpted new relief and a reproducible scenery pass; BFME2's own terrain,
starts and river crossings are kept. It was made for bfme-workshop's strategic
zoom, and is the one project built from a stock map rather than an empty one.
`mw build ithilien-frontier -- --detail 0` builds the terrain alone (the
default adds 4,200 objects, seed 20261008); `--width` and `--height` set the
playable size. The build refuses embedded scripts or unhandled coordinate
sections rather than carrying stale positions into the enlarged map.

## Battlefield

- 840 x 953 playable tiles: 800,520 tiles, **3.001 times Grey Mountains' area**.
- 900 x 1,013 stored terrain samples, including a 30-tile border.
- Two native player starts and large open areas around the bases.
- Four named fords, twelve river strips, wooded hills and Gondorian ruins.
- Sculpted mountain walls, ridges, rolling hills, an eastern escarpment and a
  raised western ruin terrace. Maximum terrain elevation is about 913 game units;
  the median playable elevation rises from about 48 to 152.
- River ribbons and submerged beds are unchanged. Main road surfaces and 700-unit
  base circles keep their original elevations, with smooth shoulders into new hills.
- Steep new faces receive native rock textures; slopes above 1.05 rise/run are
  additionally flagged impassable. Native engine and object collision still apply.
- 5,854 placed records, including **4,111 added** trees, undergrowth, rocks and ruins.
- Scenery generation protects a 650-world-unit radius around base markers and
  135 units either side of native road segments. Collision/pathfinding also depends
  on the original terrain and object geometry; these spacing rules are not a full
  pathfinding guarantee.
- Native texture scale retained, with terrain texture subtiles and secondary
  blends rephased for the expanded grid.
- Strategic camera ceiling 16,000. Native distance fog disabled for the far view.

## History

The launch presets, native checks, captures and recorded builds made with
bfme-workshop, the repository this one grew out of, are in
[its history](../../docs/history/ithilien-frontier.md).
