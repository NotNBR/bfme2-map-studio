# Grass Lab

A standalone visual test scene opened by **Grass Lab** in the studio toolbar
or map picker, or `mw view --grass-lab`. It is a Godot lab, not a playable
retail `.map` project; it has no map build and needs no retail assets.

Nine plots compare 25/50/100% density, grass-to-earth and grass-to-stone
transitions, a winding path, short/tall blades and a slope. Density, height
and wind sliders update immediately. Keys 1-4 select comparison views; WASD
moves, right-drag orbits, the wheel zooms, G toggles grass, T ground detail,
and Space wind. MSAA 4x is enabled for this scene only.

The shader and scene snapshot comes from the optional ground-cover work in
OpenBFME. Its shaders keep their GPL-3.0 notices and live under a separate
`res://labs/grass/` namespace. The terrain mesh and blend records are built
by the pinned engine's `build_test_patch`; the lab selects its own enhanced
terrain shader. The studio's regular map rendering and pinned engine are
unchanged. Textures are procedural test materials; these plots do not test
retail map-file parsing, multi-layer terrain blends, or camera streaming.

`openbfme.viewer_files()` assembles this folder's `godot/` into the viewer.
For a GPU smoke run, launch the assembled scene with
`-- --lab-smoke --lab-captures=ABSOLUTE_DIRECTORY`: it checks plot counts,
density, transition masks and the slope and saves four views before exiting.
