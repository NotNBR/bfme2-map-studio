# Triggers and water

[Specification index](../specification.md) · [Previous](scripts.md) · [Next](presentation.md)

Each section below starts with `u32 recordCount`. Record layouts follow.

## TriggerAreas v1

```text
str name, str layer, u32 id
u32 pointCount, vec2 points[pointCount]
u32 unknownRaw
```

Names can be referenced by scripts. Polygon semantics, winding constraints and
the trailing integer are not fully specified by reading this layout alone.

## StandingWaterAreas v2

```text
u32 id, str name, str layer, f32 uvSpeed, u8 additive
str bumpTexture, str skyTexture
u32 pointCount, vec2 points[pointCount]
u32 waterHeight
str shader, str depthColors
```

Water height is a stored integer world elevation, not an elevation sample in
HeightMapData's fixed-point scale. Polygon positions use world XY. Material
references affect rendering; native depth/pathability is a separate question.

## RiverAreas v1/v2

Both inspected versions use this record layout:

```text
u32 id, str name, str layer, f32 uvSpeed, u8 additive
str texture, str noise, str alphaEdge, str sparkle
u8 colorBytes[4]
f32 alpha, u32 waterHeight, str minLOD
u32 crossSectionCount
f32[4] crossSections[crossSectionCount]   # two XY endpoints per section
```

These are cross-sections, not one ordinary polygon vertex array. Preserve endpoint
and section order. The exact color-channel/LOD interpretation is not established
by the raw field names alone.

## StandingWaveAreas v1/v2

```text
u32 id, str name, str layer, f32 uvSpeed, u8 additive
u32 pointCount, vec2 points[pointCount]
u32 unknownRaw
u32 waveParameters[9]
str texture
if version >= 2: u32 enablePCARaw
```

Source-derived parameter order: final width, final height, initial width fraction,
initial height fraction, initial velocity, time to fade, time to compress,
second-wave time offset, distance from shore. They are stored as nine **u32**
values; units/ranges and all runtime effects remain unverified. Shore waves are
separate geometry from water surfaces and navigation.

## PolygonTriggers v4/v5

Legacy combined trigger/water record:

```text
str name, str layer, u32 id
u8 isWaterRaw, u8 isRiverRaw, u32 riverStart
if version >= 5:
  str riverTexture, str noiseTexture, str alphaEdge, str sparkle,
      str bumpTexture, str skyTexture
  u8 additiveRaw, u8 riverRGB[3], u8 unknownByte
  f32 uvSpeed[2], f32 riverAlpha
u32 pointCount, i32[3] points[pointCount]
```

These legacy points are signed integer triplets, not the modern `vec2` floats.
Nonempty old polygon behavior needs further native evidence. Do not convert
between old and modern water/trigger sections by only renaming the chunk.
