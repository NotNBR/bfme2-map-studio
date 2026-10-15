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
