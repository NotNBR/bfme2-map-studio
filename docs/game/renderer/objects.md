# Objects and vegetation

How the game lights and draws map objects, trees and shrubs, and what the
renderer reproduces ([how the game draws a map](README.md)).

- Objects: W3D models in bind pose (HLOD, hierarchy, skins) with
  `InstanceScaleFuzziness`; units in a still pose ([units](#units)). The light environment is the map's object
  ambient and object lights as `LightEnvironmentClass::Add_Light`
  (0x00140770) keeps them: lights below 0.05 in every channel are dropped
  (Greywater's third light), the rest sorted by brightness. At Low and Medium
  (ShaderLOD <= 1) the scene (0x0006E716) and the vegetation step
  (0x00071A1F) scale it by the GlobalLighting chunk's final three values;
  W3DPropDraw props (`W3DPropBuffer::drawProps`) are not scaled.
- Classic W3D materials (no FX chunk) go through the fixed-function path at
  every detail level: per-vertex lighting from the vertex material, with DCG
  folded in as `MeshMatDescClass::Post_Load_Process` does (diffuse and
  ambient taken from the vertex colour), saturated, times the texture
  (`MODULATE2X` when the map is overbright). Blending, depth writes and
  culling follow `ShaderClass::Apply`: alpha test >= 0x60, >= 1 for
  SrcAlpha/InvSrcAlpha blending, back faces culled unless the mesh is
  two-sided. High's `ShaderMaterialReplacement` (DefaultW3D.fx) is not
  reproduced.
- FX materials: the technique is picked like water's (`InitializeShader`).
  `normalmapped.fx` runs `Default_M` at Medium (DirectionalLight[0] and [2]
  per vertex, DirectionalLight[1] bump-mapped, specular from light 0) and
  `Default_L` at Low (vertex lighting, doubled); High's two-pass `Default`
  is drawn with the `Default_M` port and flagged in the report
  (`fx_materials`). Other effects are drawn as lit textured materials.
- Trees and shrubs: `KindOf TREE` / `KindOf SHRUB` templates with a
  `W3DTreeDraw` are handed to the tree and shrub buffers at map load with
  the map position, the map angle and the template's `Scale`: a new game
  creates each one's drawable at the map angle and its `W3DTreeDraw` adds it
  (BFME1/Zero Hour `reactToTransformChange`; only a loaded savegame re-adds
  them with an identity matrix and scale 1, GameLogic 0x00246422). Positions
  are rotated, normals stay in model space (0x000E7DF3). Zero Hour and BFME1
  zero the scale randomness (WorldBuilder rolls it into the map), so
  `InstanceScaleFuzziness` is not applied at load; a map's per-object
  `objectPrototypeScale` is, and native captures show tree-buffer trees at
  those sizes (Greywater's build gives each tree 0.75..1.3 and each shrub
  0.8..1.2, as hand-tuned retail maps do). The buffers copy the
  model's first mesh (bone translation only, model-space normals, DCG with
  alpha 255, UVs clamped to [0, 1]) and the `TextureName` texture, and keep
  the first 1,200 trees and 2,000 shrubs in map order (64 types each);
  shrubs need `ShowProps` (Medium and up). They are drawn with
  `vegetation.fx` (`Vegetation.fx`, technique `Default` at the global
  ShaderLOD): `Default_L` at Low and Medium, `Default` at High. Lighting is
  |N.L| for each light, (lights + ambient) x vertex colour x 0.5 saturated,
  then x 2 with the texture; `Default` also multiplies the cloud texture.
  Alpha test >= 96; trees alpha-blend (`Vegetation.IsAlphaBlendEnabled`),
  shrubs do not; back faces are culled. Sway: `SwayOffsets` from the default
  breeze (ScriptEngine::reset) scaled by height above the tree's base, one
  of ten random sway types per tree (none for `TaintedTree`), animated by
  `--time`.


Previews draw every tree and shrub of the map. The game keeps only the first
1,200 trees and 2,000 shrubs in map order; `render --vegetation-limits` (or
`MapRenderer(vegetation_limits=True)`) applies those limits, and the render
report lists how many were dropped under `vegetation`.

A draw module's `ModelConditionState = WORLD_BUILDER` is the editor's: the
game never enters that state. Templates whose only model is there are drawn
by WorldBuilder and not by the game: the AI's `FarmTemplate`,
`ExpansionLocatorTemplate`, `WallHubTemplate` and `ThreatFinder`, the
cinematic particle, fire and smoke proxies, and the summoning eggs
(`FarmTemplate`: `DefaultModelConditionState` `Model = None`,
`WORLD_BUILDER` `GBFarm_WB`). The renderer leaves these editor markers out
(`render --editor-markers`, `MapRenderer(editor_markers=True)` and the
viewer's **Editor markers** draw them, and the render report counts them
under `editor_markers`). Hordes and castle centres also have only an editor
model; the game shows their units or castle in its place. The renderer draws
a horde's members instead ([units](#units)) and keeps the editor model as the
castle centre's stand-in.

## Units

Templates with `EditorSorting = UNIT` (faction units, heroes, hordes, creeps)
are drawn as a new game creates them, still (`render.assets`,
`MapRenderer._placed_units`):

- A horde fills itself from its `HordeContain` (or `HorseHordeContain`):
  `InitialPayload` members (sizes from `gamedata.ini`'s `#define`s), each at
  the next `RankInfo` `Position` for its `UnitType`, rank by rank. Positions
  are in the horde's frame, X forward, and members face the horde's way. They
  stand on the ground, or level with a horde raised above it (on a wall).
- A template with `BuildVariations` (`RohanPeasant`) becomes one of them; a
  hash of the object stands in for the game's random pick.
- Each unit is posed at the first frame of its idle animation: the first
  `AnimationName` of the draw module's `IdleAnimationState`, else the
  `DefaultModelConditionState`'s animation, `#include`d files read
  (`GameAssets.unit_animation`). The animation's bones replace the bind pose
  by name (`ModelCache.load('model+animation')`); uncompressed (0x200),
  timecoded (0x282) and BFME motion channels (0x284) are decoded
  (`formats.w3d.channels`). A unit without one stays in its bind pose.
- Each unit leaves out the sub-objects its `OnCreated` script hides: the
  `AILuaEventsList` of its AI module names an `EventList` in
  `data/scripts/scriptevents.xml` (one without `OnCreated` takes its
  `Inherit`'s), whose function in `data/scripts/scripts.lua` calls
  `ObjectHideSubObject[Permanently](self, "Name", true)`
  (`GameAssets.hidden_subobjects`, `ModelCache.load('model|mesh,mesh')`).
  These are the upgrades' meshes, which the models carry unhidden: forged
  blades, fire arrow tips, shields. A list with no `OnCreated` hides nothing,
  so the Isengard berserker (`InfantryFunctions`) keeps its `Forged_Blade`
  beside its sword. Any object also leaves out what its draw module's
  `IdleAnimationState` `BeginScript` hides with
  `CurDrawableHideSubObject("Name")` (or its `Permanently` form) when the script has no `if`
  (`CINE_DwarvenCatapult` hides its crew so). BFME2 has no `HideSubObject`
  field in a model condition state: no retail INI uses one and `game.dat`
  holds no such name.

Not reproduced: the game's random idle choice and start frame (members
differ slightly in the game, all alike here), banner carriers and
`RandomTexture` swaps. `render --no-units` and the viewer's
**Units** leave every unit out; the render report counts them under `units`
(hidden, hordes, members, posed).

## Open questions

- Sway phases: the game rolls each sway type's speed and amplitude with
  `GetGameClientRandomValueReal`; fixed factors stand in, and the cycle
  assumes one sway step per logic frame (30 per second). Per-tree sway types
  are a hash of the object index.
- ShaderMaterialReplacement at High and normalmapped.fx `Default` (High) are
  not ported (see Objects above).
