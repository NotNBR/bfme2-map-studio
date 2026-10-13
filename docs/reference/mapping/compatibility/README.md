# Compatibility and evidence

The current target is **BFME II 1.06 on Windows**, using a user-provided complete
game installation. Further compatibility checks are **paused as of 9 October
2026**. The results below describe completed work; pending items are not certified.

| Layer | Evidence | What it does not prove |
| --- | --- | --- |
| File preservation | 270 local map/base documents round-trip; every observed section/version has a decoder and an encoder | Every legal variant, unknown field meaning or safe arbitrary edit |
| Tooling | 94 unit tests passed at this checkpoint | Native engine behavior by itself |
| Original map loading | Generated maps and feature labs load in the isolated runtime | Every normal-menu installation or downloadable map package |
| Native behavior | Script markers/timers, lighting readback, flags, water depths, slopes, roads and walkable bridges | All opcodes, locomotors, formations, AI or building placement |
| Screenshots | [Native D3D9 captures](screenshots.md) with map/camera metadata | Multiplayer, balance, persistence or long-match stability |

Script, lighting and navigation observations run without the strategic extension.
The screenshot harness uses the extension for camera/reveal control; its results
must be labelled separately. The isolated runtime and launch helpers are shared
infrastructure, so these tests are not equivalent to a clean stock-menu or network
test. Recorded map hashes identify the exact authored inputs.

## Reproducing existing work

Start with [setup](../../../getting-started.md).
Each area documents its existing commands, expected evidence and limitations.
Use fresh evidence directories, finish one run before installing another map
variant, and keep failed results when a validator or experiment is corrected.

Generated maps, extracted retail data, native reports and captures remain in
the ignored `local/` folder. Public documentation records findings and
hashes; another checkout must generate its own evidence from its own game copy.

## Pending checks

- Normal-menu discovery, packaging, map sidecars and exact cache/checksum rules.
- Multiplayer transfer, synchronized behavior and map-hash agreement.
- Save/load of scripts, objects, bases and long-running scenarios.
- Sustained large-map performance and practical engine limits.
- Other game patches, expansion compatibility and combined-feature regressions.

No new native checks are required to read or use the current documentation.
Resume this work explicitly when further compatibility evidence is wanted.
