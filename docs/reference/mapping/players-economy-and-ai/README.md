# Players, economy and AI

Map starts, sides, teams, object ownership, build lists and scripts work together.
Their binary records are decoded, but broad gameplay and AI behavior still need
controlled scenarios. Existing map projects provide basic playable setups.

| Topic | Current support |
| --- | --- |
| Player starts | Original skirmish maps with distinct `Player_N_Start` waypoints and unique IDs, using 2–8 starts |
| Sides and teams | Property dictionaries, multiplayer slot records and owner/team references |
| Ownership | Native script tests verify the declared owner of laboratory units |
| Bases and build lists | [Castle templates and libraries](bases.md), versioned readers/writers and nonempty retail corpus inspection |
| Economy, diplomacy and victory | Existing scenarios use game rules; comprehensive map-authoring tests remain |
| AI | Build-list and library formats understood structurally; sustained base-building and attack behavior unverified |

Read the [player/build-list layouts](../file-structure/reference.md#players-build-lists-and-links)
alongside the [script reference](../scripts/README.md). A map's start count, side
count and active player count are different quantities; neutral and supporting
sides also occupy records. Keep side-indexed library/script entries aligned and
resolve owner/team names when changing a setup.

The [Eight Kingdoms 4v4 scenario](https://github.com/NotNBR/bfme-workshop/tree/main/examples/scenarios/eight_kingdoms_4v4) (bfme-workshop)
is a staged battle demonstration. It does not prove normal AI economy or all
team arrangements. Its current adapter uses slots 1–4 against 5–8.

## Remaining work

- Starting resources, settlements, creeps, resource objects and victory/defeat.
- Diplomacy and team changes, AI/human slot restrictions and faction variants.
- Build-list execution, rebuilding, base/rally footprints and recruitment.
- AI routes, attack priorities, scripted teams and sustained-match behavior.

Retail bases and scripts remain local licensed inputs; the repository includes
original generators, compatibility metadata and test fixtures, not game assets.
