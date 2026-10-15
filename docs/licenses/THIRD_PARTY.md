# Native integration notices

The new bmfe-workshop native adapter code is distributed under **GPL-3.0-only**. See `LICENSE.txt` for the license text. Retail BFME assets are separate, user-supplied inputs; this does not license those assets.

## OpenSAGE

Source: https://github.com/OpenSAGE/OpenSAGE

`src/formats/w3d.py` adapts the adaptive-delta decoding algorithm described by `W3dAdaptiveDeltaCodec.cs` and `W3dAdaptiveDeltaBlock.cs`, with the motion-channel layouts from the associated parser files. Copyright remains with the OpenSAGE contributors. The source was retrieved on 7 October 2026.

OpenSAGE's complete license notice is preserved in [OPENSAGE-LICENSE.md](OPENSAGE-LICENSE.md), including its reference to EA-derived components. [OPENSAGE-LICENSE-EA.md](OPENSAGE-LICENSE-EA.md) is also preserved. The adapter does not embed EA game binaries or claim ownership of original art.

`src/formats/` and `src/mapkit/` use native map layouts cross-checked on 8 October 2026 with OpenSAGE's `HeightMapData`, `BlendTileData`, `BlendTileTexture`, `MapObject`, `AssetPropertyCollection`, `AssetProperty`, and row-padded bit-array reader. It preserves unedited native chunks. The authoring operations, transaction workflow, diagnostic preview and Computer Use session adapter are project code. Retail maps used for local verification remain ignored runtime inputs.

## WorldBuilder terrain research

The section coverage expansion also consults OpenSAGE's `BuildListInfo`,
`BuildLists`, `SidesList`, camera animation/frame, water/wave, environment,
post-effect, skybox and global-lighting schemas. The additional layouts and
unresolved meanings are recorded in the [mapping reference](../format/coverage.md).
No retail payloads are included in the synthetic tests.

The script decoder additionally consults OpenSAGE's `Scripting/Script`,
`ScriptGroup`, `ScriptContent`, `ScriptArgument` and related chunk schemas,
and Open-BFME-2's parameter/condition/script writers. The independently written
decoder preserves numeric IDs instead of copying another game's opcode enum.
See [map scripts](../game/scripts.md) for the source revision and evidence limits.

The bundled `src/mapworkshop/mapkit/data/bfme2-1.06-scripts.json` records compatibility
metadata extracted from Open-BFME-2's action/condition initializers at revision
`33f02e4222f3ac9c284d9b71cf5e7438799988bb` and reconciled with local native template
memory. It retains source file hashes and provenance. It does not redistribute
retail scripts or executable bytes. Lighting and castle serializers independently
implement layouts cross-checked against matched routines from the same source;
see [lighting](../format/lighting.md) and [bases](../game/bases-and-libraries.md).

The independently written terrain decoder and audit tools were cross-checked on
8 October 2026 against EA's [Generals/Zero Hour WorldBuilder source](https://github.com/electronicarts/CnC_Generals_Zero_Hour),
particularly `WHeightMapEdit.cpp`, `WorldHeightMap.cpp`, and `TileData.h`, as well
as OpenSAGE's `BlendDescription` and `CliffTextureMapping`. EA's source is
copyright Electronic Arts Inc. and distributed under GPL-3.0-or-later; no upstream
implementation is vendored by this change. The field descriptions, local evidence
and interpretation limits are recorded in [WorldBuilder terrain](../game/terrain-textures.md).

The independently written road-pair inspector and writer use flag names from
EA's `Common/MapObject.h`, compared with OpenSAGE's `RoadType.cs` and OpenBFME2's
road-buffer source. Corpus and native evidence, and the limits of those source
comparisons, are recorded in [roads and bridges](../game/roads-and-bridges.md).

## Recoil / Spring

Source and releases: https://github.com/beyond-all-reason/RecoilEngine

Pinned local release: `2026.07.04`, Windows amd64. Archive SHA-256:

`2e0a43744115e6b3cbd7db4a36aecc3d28afdef4fb615d07ab01703e4b5525e1`

The engine is downloaded as a separate ignored runtime. Its GPL source and license are available in that repository. Built-in Lua gadget and unit-script handlers retain the original authors' notices inside the engine's base packages. `unit_script.lua` invokes that existing handler, attributed to Tobi Vollebregt.

## openbfme2 and BFME II

[openbfme2 (Open-BFME-2)](https://github.com/Open-BFME/Open-BFME-2) supplies reconstruction, symbols and file-layout references under its GPLv3 license. No retail installation or extracted game assets are distributed here; the game runtime (`local/runtime/`) is made from a user-supplied BFME II installation and stays in ignored files.

`src/mapworkshop/native/debugger.py` and `src/mapworkshop/native/runtime.py` are ported, trimmed and modified from openbfme2's test harness, `tools/game_smoke.py` and `tools/boot_smoke.py` (GPL-3.0): the Win32 debugger loop, breakpoint and remote-call handling, the version, profile and focus redirections and their x86 stubs, and the skirmish slot setup, with the BFME2 1.06 addresses they use. The game addresses in `native/play_game.py`, `native/pathgrid.py`, `native/capture.py` and `native/ingame/` come from Open-BFME-2's matched sources.

`src/mapworkshop/native/ingame/ingame.cpp` takes from bfme-workshop's strategic extension (GPL-3.0-only; same author) its hook trampoline, the camera placement of its photo mode, its camera matrix layout and its D3D9 render-target readback. Direct3D9 interface slots were cross-checked there against mingw-w64's `d3d9.h`, which is not copied. `ingame.dll` is built with the MSVC 7.1 toolchain of openbfme2's reference checkout; the compiler is not redistributed by this project.

## DXVK

Headless game runs use the 32-bit `d3d9.dll` of [DXVK](https://github.com/doitsujin/dxvk) (zlib licence), Direct3D 9 on Vulkan, by Philip Rebohle and contributors. It is not distributed here: `src/mapworkshop/native/runtime.py` downloads the pinned release into the ignored `local/runtime/dxvk/` and checks its SHA-256.

## Python dependencies

Python dependencies are declared in `pyproject.toml`: NumPy and Pillow, with moderngl and glfw for rendering and imageio-ffmpeg for video. They are installed separately and retain the license notices included in their distributions.
