# Battalions

Where a battalion's soldiers stand, where a battalion sent to a taken point
stops, and which attack orders a battalion carries out. Measured in ROTWK 2.01
(the [verified executable](runtime.md#rotwk-201)) with the
[Horde Spacing Lab](../../maps/horde_spacing_lab/map.py) and
`mw battle --rotwk` ([testing in the game](../guide/testing-in-game.md#headless-battles-mw-battle)),
which logs the game's own destination choices and goal reservations under a
debugger; addresses are that executable's.

## The formation stands centred on the battalion

A battalion (a HORDE object) holds its soldiers in slots. The slot table is
built from the INI's `RankInfo` positions (X ahead, Y to the side), followed by
one slot at `LeaderPosition` when `LeadersAllowed` is set (no 2.01 battalion
sets it) and one per `BannerCarrierPosition` when `BannerCarriersAllowed` is
set. The game then centres the whole table on the battalion object: it
subtracts the mean of every slot, or, when a rank's unit type is a MACHINE,
that rank's first slot (RW 0x877751, the centring RW 0x86C4EA).

So the soldiers stand around the battalion's position, not ahead of it. For a
`GondorArcherHorde` (ranks at X 50, 30 and 10, five each, banner carrier at
70) the mean of the 16 slots is 32.5, and its archers stand at X 17.5, -2.5
and -22.5; an `ElvenMirkwoodArcherHorde` (ranks at 0 and 20, one at 15,
banner at 40) stands at 7.73, 2.73 and -12.27. The members reserve their goals
at these slots when the battalion is given a destination (updateGoal RW
0x8E24D3); the battalion's own goal is only remembered, never reserved.

## Two battalions sent to one point

The first battalion takes the point's cell. The second one's destination is
searched in a spiral around the point (RW 0x6FA2A4), testing at each cell a
box of its geometry's size (checkDestination RW 0x6F1584) against the goals
reserved there. Every cell around the point meets the first battalion's
members, so the second stops one formation length away, side by side along
the march. The second battalion's destination, from the point's cell, with
both sent from 500 west of it:

| Battalion | Second battalion |
|---|---|
| `GondorArcherHorde`, `GondorFighterHorde` | 60 east (ahead) |
| `ElvenLorienArcherHorde`, `DwarvenAxeThrowerHorde` | 50 east |
| `ElvenMirkwoodArcherHorde` | 40 east |
| `AngmarDarkRangerHorde` | 40 west (behind) |
| `MordorArcherHorde`, `GoblinArcherHorde`, `IsengardUrukCrossbowHorde` | varies: a `RandomOffset` jitters their slots with the game's random draws, so the side changes from run to run (`GoblinArcherHorde` 80 west in one run, 80 east in the next) |

Scripted armies therefore need no spacing of their own to avoid stacking: a
battalion ordered onto a point another holds stops beside it.

## Attack orders a battalion cannot carry out

A script's `NAMED_ATTACK_NAMED` (or a player's attack order) is accepted when
one of the unit's weapons may target that kind of object, but the attack ends
at once when none of its weapons can damage it: the weapon choice (RW
0x6C8A4E) skips a weapon whose estimated damage against the target is 0 (RW
0x6CDBF3, 0x68D91A), and the battalion stands idle with the order given. At
Helm's Deep the Deeping Wall's pieces and the culvert wear `HelmsDeepWalls`,
0% to everything but SIEGE (25%), MAGIC and FORCE (10%): Isengard's pikemen
(SPECIALIST damage) ordered to attack them did nothing for the battle's first
minute, while the main gate (`DefaultWallArmor`, 10% by default) fell to the
same order. Established from the code as OpenBFME ports it and traced there
with `mw battle`; not yet observed in ROTWK itself. A map that wants infantry
at such a wall sends them there with a move or attack-move order instead
([Helm's Deep](../../maps/helms_deep_battle/map.py) does).
