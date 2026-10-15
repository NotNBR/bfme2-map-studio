# ROTWK integration, 15 October 2026

The studio was tested with `D:\LAN\lotrbfme2\local\bfme2` and
`D:\LAN\lotrbfme2\local\rotwk`. The ROTWK profile selects retail archives and
official 2.01 patches; `__patch202.big`, the HD pack, timer and music packs
are excluded. All 18 root BIG archives in the disc image's `0compressed.zip`
matched the installed files' ZIP CRCs. The original image is
`D:\LAN\analysis-materials\games\BFME2\builds\lotr-builds\LOTRBFME2EP1-003.mdf`.

The effective library had 29,801 archive paths, including all 26,935 BFME2
paths (zero missing), 4,605 object templates, 116 named Angmar templates and
129 stock maps. AngmarFortress, AngmarMill and ShireGeneric01 rendered together
using the shared asset loader. Counts describe this installation, not a
guarantee for arbitrary modified game folders.

The exact engine is SHA-256
`5481de75b63e22483660ea8097478faef594f90b9ade7de893e092256ba68a26`, version
`2.1.2614.37001`. Its local analysis workspace identifies existing scheduling
differences; it is not asserted to be an untouched retail executable.
The startup addresses were checked against
`D:\LAN\lotrbfme2\engine-reconstruction\full-export`: GameEngine::init
(`0063ad4f`), setSlot (`008016c3`), GameSlot setup (`008014f1`), and the
engine update (`006325a0`).

A bounded hidden test built Water Lab in the ROTWK profile and started it
under the studio debugger with DXVK. The report recorded successful player
slot setup, skirmish mode 2, and logic frame 10 at 17.0 seconds, with no
first-chance exceptions. It then closed its processes. This demonstrates
gameplay startup; it does not verify match balance, all factions, the free
camera or native screenshot/pathfinding capture.

The public repeatable check is `mw --profile rotwk play water-lab --check`;
reports are kept in the profile's ignored `runtime/logs/`. See the current
[runtime guide](../game/runtime.md#rotwk-201) for behavior and limits.

The public command with `--graphics Low` subsequently reached frame 11 at
13.3 seconds, again without first-chance exceptions. The final repository
suite passed in both profiles: 269 tests, four skipped, plus syntax, import
layer, documentation link and index checks. ROTWK `mw doctor` passed and
the catalogue indexed 4,605 templates, 1,260 terrain textures and 3,082 effects.

## Loading fix

Later on the same day, the shared `bfme2-map-quickload` DLL gained a separate
ROTWK engine layout. Local disassembly identified the D3DX import slots at
`0x7D0A1C`/`0x7D0A20`, terrain call returns at `0xEEFBD`/`0xEEFE3`, the camera
update at `0x8546A`, and the title wait at `0x245CB1`. GameLogic's LoadScreen
is still at `+0x120`; function `0x625524` destroys it. The studio flushes its
queued textures there before gameplay. The standalone build detects each
load and flushes at the camera update, as it does for BFME2.

Water Lab (same map hash as the integration check) at Medium detail, hidden
DXVK, reached frame 10 in 23.2 seconds without acceleration, 11.6 seconds
with the launcher DLL and 10.2 seconds with the standalone DLL. Each patched
run deferred and copied all 1,260 terrain textures on 15 workers, with zero
failed jobs or first-chance exceptions. All three runs already skipped the
title logo; timings are individual local measurements, not general promises.
BFME2 regression runs also completed 1,260 textures without failures: 12.7
seconds with the launcher/camera DLLs together, 10.6 with the standalone DLL.
Automatic loading of `dinput8.dll` from the isolated ROTWK game folder also
passed, reaching frame 11 in 12.3 seconds with all 1,260 textures copied and
zero failures. This verifies the proxy's import forwarding as well as its
hooks; the earlier standalone comparison injected the same DLL explicitly.

The repository suite passed 271 tests (four skipped), plus syntax, import
layer, documentation and index checks. Source and both DLL builds live in
the quickload submodule. Native screenshot/pathfinding capture and the free
camera remain BFME2-only.
