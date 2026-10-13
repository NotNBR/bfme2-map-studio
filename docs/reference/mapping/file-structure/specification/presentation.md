# Lighting, environment and cameras

[Specification index](../specification.md) · [Previous](triggers-and-water.md) · [Next](constraints-and-evidence.md)

## GlobalLighting v1–8

The corpus observes v7/v8; earlier branches have matched-source/synthetic support.
Begin with `u32 timeOfDay`. Then write **four configurations**, each containing
the light slots supported by that version, in this order:

| Added in version | Slots appended to each configuration |
| ---: | --- |
| 1 | Terrain light 0, object light 0 |
| 2 | Object lights 1 and 2 |
| 3 | Terrain lights 1 and 2 |
| 4 | Third-array lights 0, 1 and 2 |

Each light is `vec3 ambientRGB, vec3 diffuseRGB, vec3 directionXYZ` (**36 bytes**).
After all four configurations:

```text
if version >= 5: f32 overbrightValue
if version >= 6: u32 chunkFlagRaw, vec3 triplet0
if version >= 7: vec3 triplet1, vec3 triplet2
u32 shadowColorRaw                  # optional at end of older versions
if version >= 8: f32 finalValues[3] # requires preceding shadow color here
```

Modern v8 payload: **1,360 bytes**; v7 with shadow: **1,348 bytes**. The word
immediately following the light arrays is **overbright float**, not shadow color.
The third array, triplets, flag and final-value meanings remain partly unknown;
do not invent descriptive target names. Full slot/tail readback is documented in
[lighting evidence](../../terrain-and-presentation/lighting.md).

## Environment and post effects

```text
EnvironmentData v2/v3:
  if version >= 3: f32 waterMaxAlphaDepth, f32 deepWaterAlpha
  u8 macroTextureStretched, str macroTexture, str cloudTexture

PostEffectsChunk v1:
  u8 effectCount
  repeat effectCount: str name, f32 blendFactor, str lookupImage

SkyboxSettings v1:
  vec3 position, f32 scale, f32 rotation, str textureScheme
```

An empty PostEffectsChunk is **one zero byte**, unlike the four-byte zero counts
in most list sections. Do not confuse visual water-alpha settings with logical
water depth or movement permission.

## NamedCameras v2

```text
u32 cameraCount
repeat cameraCount:
  vec3 lookAt
  str name
  f32 pitch, f32 roll, f32 yaw, f32 zoom, f32 fieldOfView, f32 unknownRaw
```

Field names are current source/reader interpretations. Exact angle/focal units
for all camera fields have not been independently established; the object-angle
radian rule must not be blindly applied to every camera field.

## CameraAnimationList v1/v3

Both versions use the inspected track layout:

```text
u32 animationCount
repeat animationCount:
  bytes[4] typeCode
  str name, u32 numFrames, u32 startOffset
  CameraTrack
  if typeCode decodes to "look": TargetTrack

Track:
  u32 keyCount
  repeat keyCount:
    u32 frameIndex
    bytes[4] interpolationCode
    vec3 positionOrTarget
    if free camera: f32 rotationRaw[4]
    if look camera: f32 roll
    if camera (not target): f32 focalParameterRaw
```

Stored FourCC bytes are reversed relative to human labels: `eerf` → `free`,
`kool` → `look`, `mtac` → `catm`, `enil` → `line`. These identify the decoded
track shapes. Interpolation timing, rotation interpretation and focal semantics
remain incomplete. Target keys do not contain the extra rotation/focal fields.
