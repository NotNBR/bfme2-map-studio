# Particle effects

Objects get particle effects in two ways, and the renderer draws both:

- **W3D emitters.** The model's HLOD aggregate array (chunk `0x705`) names
  emitter files on bones. `GenericTorch`'s `GBTORCH`, for example, has
  `E_Fire_SM`, `E_Smoke_SM` and `E_FireSparks_SM`, which hold its flame.
- **INI particle systems.** `ParticleSysBone = <bone> <system>` lines in the
  draw module's `DefaultModelConditionState` and `IdleAnimationState` attach
  an `FXParticleSystem` from `fxparticlesystem.ini`, or from the map's
  `map.ini`, read after it, so a map's own systems are drawn and replace the
  game's of the same name. `FireCampfire`'s embers and `FireBonfire`'s glow
  and smoke work this way.

Only drawables in the scene run effects. `W3DPropDraw` templates go to the
prop buffer, which renders their models without adding them to a scene, so
their emitters never update: `W3DPropDraw::reactToTransformChange` feeds
`W3DPropBuffer`, and `ParticleEmitterClass::Render` is empty. Trees and shrubs
have none.

Effects are shown as on a map that has run for a while:

- Systems that stop stay off: those with a `SystemLifetime`, `IsOneShot`, or
  emitters with `MaxEmissions`.
- Systems below the detail level's `MinParticlePriority` (`gamelod.ini`;
  `HIGH_OR_ABOVE` is off at Medium) are not drawn.

Each particle's state is a closed-form function of its age, so any instant
renders without simulating up to it. Randomness is a hash of the object, the
emission and the particle, so stills are reproducible and the viewer animates.

- **Emitters** (WW3D2 `part_emt.cpp`, `part_buf.cpp`, `pointgr.cpp`):
  - Emission every `int(1000 / rate)` ms, in bursts.
  - Position: a random point in the creation volume and a velocity (random,
    plus outward, plus base), both rotated by the bone, under world
    acceleration.
  - Colour, opacity, size, rotation and texture frame follow the keyframes,
    plus per-particle randoms.
  - The point group forces the MODULATE gradient.
  - Triangle particles span a frame 3.464 x size wide; quads are 1 x size.
  - The object's scale scales sizes, offsets and speeds.
- **INI systems** (Zero Hour `ParticleSys.cpp`):
  - A burst every BurstDelay + 1 frames.
  - Each frame, as `Particle::update`: velocity plus gravity, times damping;
    position plus velocity plus drift; damped size and angle rates.
  - Colour keys, with BFME2's colour scale drawn per non-zero channel of keys
    1 to 6 (the colour module constructor, 0x0055BCF1).
  - Alpha keys for non-additive shaders.
  - Point, line, sphere, box and cylinder volumes, with ortho, outward,
    spherical, hemispherical and cylindrical velocities.
  - Placed at the bone's position times the object's scale, turned by the
    bone's Z rotation only (W3DModelDraw).
  - Drawn as `DefaultDraw` camera-facing quads (ground-aligned ones flat),
    with the sprite shader of their `Shader`.

Particles are drawn after water, without depth writes: alpha-blended groups
first, sorted back to front, then additive ones. Fog fades additive particles
to black. Particle textures are uploaded as they are: additive textures keep
colour under zero alpha, which the alpha bleed applied to object textures
would overwrite.

The render report lists `effects`: emitters and systems attached, and those
skipped with the reason.

## Flame and glow meshes

Many lamps also carry flames and glows as meshes. `GPTOWNLAMP5` (the hanging
lantern `TownLamp5`) has only these, and they work in the prop buffer too.

- **Camera-facing meshes.** W3D geometry type `CAMERA_ORIENTED` (`0x60000`)
  or `CAMERA_ALIGNED` (`0x10000`). The DX8 mesh renderer draws them with
  `Obj_Look_At` at the bone's position instead of the mesh transform: local
  +x points at the camera (oriented) or along the camera's z axis (aligned),
  and y stays level (dx8renderer.cpp). The geometry type is a field, not
  bits: `0x60000` shares the skin bit, which the loader used to take for a
  skin.
- **Grid mapper.** Stage-0 mapping `0x00070000`
  (`GridTextureMapperClass`). The UVs cover the first frame of a
  2<sup>Log2Width</sup> grid, which is stepped at `FPS` frames per second,
  row by row, up to `Last` frames. The flame sequence `EXFireTorchSeq` is a
  4 x 4 grid at 15 frames per second.
- **Detail stage.** `DetailColorFunc` combines texture stage 1, with its own
  UVs, into stage 0. DETAIL, SCALE, ADD, ADDSIGNED, ADDSIGNED2X and SCALE2X
  are drawn. `FIREGLOW` multiplies its glow spot by itself (SCALE), which
  darkens the spot's grey surround to almost black.
- **Textures used as stored.** Materials that neither alpha blend nor alpha
  test skip `bleed_alpha`, in the fixed-function path, `normalmapped.fx` and
  `simple.fx` alike. Additive glows draw the colour under zero alpha, which
  the bleed would replace with neighbouring atlas art; `FIREGLOW` then showed
  as a patterned red square. An opaque texture's alpha need not mean
  coverage at all: `GBAmonHen1`'s atlas is 95% transparent, and the bleed
  turned the Amon Hen rocks that use it pale white.

## Approximations

- Burst delays use the mean of `BurstDelay`.
- `Wind`, `StartSizeRate`, slave and per-particle attached systems, `Event`
  modules and the cylinder's `RadiusRate` are left out.
- Other draw modules are skipped: `StreakDraw`, `GpuDraw`, `RenderObjectDraw`,
  `LightningDraw` and `ButterflyDraw`.
- Whether BFME2 also adds the colour scale every frame, as Generals does, is
  not recovered.
- Effects of other model-condition states (damaged, night, snow) are not
  drawn.
