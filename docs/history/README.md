# History

Records of earlier work, kept for what they measured and how. Most of it was
done with [bfme-workshop](https://github.com/NotNBR/bfme-workshop), the
repository this one grew out of, between 8 and 13 October 2026, before this
repository had its own game runtime (`mw play`, `mw capture`,
`mw walkable --native`). Its commands, launchers and `local/artifacts/` paths
are that repository's and do not exist here.

**Don't follow these pages as instructions.** What they established is in
[how BFME2 behaves](../game/README.md) and the [guides](../guide/projects-and-builds.md);
a page here is for when you need the evidence behind a finding, or the map
hash it was measured on.

| Page | What it records |
| --- | --- |
| [ROTWK integration](rotwk-integration.md) | clean 2.01 asset overlays and direct skirmish startup verification |
| [Experiments in bfme-workshop](bfme-workshop-experiments.md) | the navigation lab (barriers, water depth, slopes), the road and bridge runs, the script lab, the lighting readback, the terrain-record audit and terrain lab |
| [Compatibility and evidence](compatibility.md) | what had been verified on 9 October 2026, and the checks then paused |
| [Native map screenshots](native-screenshots.md) | bfme-workshop's screenshot harness (now `mw capture`) |
| [Grey Mountains analysis](grey-mountains-analysis.md) | the first byte-level analysis of three stock maps (now [the format](../format/README.md)) |
| [The Ashen March](ashen-march.md) | the first map built from an empty document: composition and painting passes |
| [Ashen March findings](ashen-march-findings.md) | the technical log of building it: the new-document constructor, revisions 1 to 3 and what each fixed |
| [Eight Kingdoms](eight-kingdoms.md) | launch presets, the prepared 4v4 battle and trailer, verification and recorded builds |
| [Ithilien Frontier](ithilien-frontier.md) | launching, building and verifying the enlarged stock map, and its 8,000-pixel photograph |
| [The Crown of Cardolan](crown-of-cardolan.md) | its eight-player setup and native review |
| [The Godot viewer: plan](godot-viewer-plan.md) | moving the viewer, `mw render` and `mw item` onto OpenBFME, phase by phase, and the Python viewer's and renderer's removal (October 2026) |
| [The Godot viewer against the Python viewer](godot-viewer-parity.md) | phase 3's feature-by-feature check, with what OpenBFME drew differently then |

bfme-workshop also staged an
[Eight Kingdoms 4v4 scenario](https://github.com/NotNBR/bfme-workshop/tree/main/examples/scenarios/eight_kingdoms_4v4):
a staged battle demonstration with slots 1–4 against 5–8, which does not prove
normal AI economy or all team arrangements.
