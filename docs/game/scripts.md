# BFME2 map scripts

The decoder reads stored structure and arguments; it does not execute scripts,
rewrite them, or declare every opcode understood. This is one workstream of the
[mapping guide](README.md).

## Verified corpus

The 9 October 2026 read-only audit of local retail `Maps.big` decoded all script
payloads in **all 67 maps**, including `shellmapbackup` with PlayerScriptsList v5.
The modern 66-map subset contains:

| Record | Version | Count |
| --- | ---: | ---: |
| ScriptList | 1 | 819 |
| ScriptGroup | 3 | 590 |
| Script | 4 | 3,332 |
| OrCondition | 1 | 3,612 |
| Condition | 6 | 4,175 |
| ScriptAction | 3 | 10,166 |
| ScriptActionFalse | 3 | 63 |

That modern subset contains **26,482 arguments of 53 numeric types**, including **46 explicit XYZ
coordinates**. The corpus exposes 73 condition opcodes, 243 true-branch action
opcodes and 14 false-branch action opcodes (the latter sets can overlap). This
is an observed subset, not the complete engine catalogue.

The legacy file adds eight Script v2 records, eleven Condition v4 records and
25 Action v2 records. Across all 67 maps there are 3,340 scripts, 4,186 conditions,
10,254 actions and 26,550 arguments. All stored layouts are consumed exactly;
legacy execution behavior has not been retested in the lab.

The expanded [base/library audit](bases-and-libraries.md) additionally decodes 152 base
documents and 51 script libraries. It covers Script v3, Group v2, Condition v5,
FalseAction v2 and outer PlayerScriptsList v6 that were absent from `Maps.big`.
It also exposes legacy opcode/name and argument-migration cases.

The map analyzer (`python -m mapworkshop.mapkit.checks.analyze FILE.map --out
FILE.json`) prints a map's script trees with their field values.

## Stored hierarchy

Nested records use the normal 10-byte chunk header and shared name table:

```text
PlayerScriptsList v1
  ScriptList v1 (one per list/side slot)
    ScriptGroup v3 (may contain groups and scripts)
    Script v4
      OrCondition v1
        Condition v6
      ScriptAction v3
      ScriptActionFalse v3
```

Groups contain a name string, active byte and subroutine byte before children.
Scripts contain four strings (name and three comments), six bytes (active,
deactivate on success, easy, medium, hard, subroutine), u32 evaluation interval,
sequential byte, loop byte, i32 loop count, target-type byte, target-name string
and player-mask string before children. Numbers are little-endian; strings use
uint16 byte lengths and CP1252.

OpenSAGE describes the final string as unknown; the local BFME2 script writer
reconstruction identifies a player-mask serialization path. `ALL` is its all-bits
form. The decoder retains the text without inventing a mapping of other labels
to player slots. Timing units, target values and flag interactions still need
BFME2-specific verification.

Earlier source-described Script v1–v3, Group v1/v2, Action v2 and Condition v4/v5
layouts are also implemented. Script v2, Action v2 and Condition v4 now have
retail coverage from the legacy file. The expanded base/library corpus also
covers Script v3, Group v2, Condition v5 and FalseAction v2. Unknown versions
remain undecoded. Outer lists v5/v6 share the ScriptList child layout of v1;
the writer still emits modern v1.

## Actions, conditions and arguments

Modern actions and conditions store:

1. u32 numeric opcode.
2. Property-style key: u8 kind plus three-byte name-table ID.
3. u32 argument count, followed by arguments.
4. Action v3: one u32 flag. Condition v6: two u32 flags.

OpenSAGE calls the trailing flags enabled and inverted. Native BFME2 testing
confirmed enable/disable behavior but **did not confirm inversion**: setting the
second flag on a constant-false condition did not make it true. The decoder
therefore uses `enabled_raw` and `condition_flag_4d_raw`; the writer deliberately
offers a raw `condition_flag`, not a semantic NOT operator. Condition v4 lacks
both flags; v5 has them; action v2 lacks its flag.

Each argument starts with u32 type ID. Type **16** stores three float32 XYZ
values. Every other type stores **all three** of i32 value, float32 value and
string value. They are not mutually exclusive storage alternatives: retaining
only the field apparently used by an opcode loses data.

Retain IDs and internal names together. For example, the corpus stores condition
opcode 1 as `COUNTER` with argument types `[4, 6, 0]`, and opcode 4 as
`TIMER_EXPIRED` with `[4]`. These are stored signatures, not evidence for timer
units, comparison rules or a complete authoring contract.

Do not interpret every ID through a Generals or generic OpenSAGE enum. Its source
explicitly notes the need for game-specific enums, and our corpus includes IDs
beyond that enum. The native parameter reader also performs compatibility
conversions for some types. The audit reports storage before runtime migrations.

## Complete template inventory, separate from behavior

The package includes a source-attributed, native-reconciled BFME2 1.06 catalogue
at `src/mapworkshop/mapkit/data/bfme2-1.06-scripts.json`. `Writer(map)` uses it
by default, so a clean checkout can author typed scripts; `Writer(map,
catalog=load_catalog(path))` takes another extraction. This contains names, IDs, argument types and
provenance, not retail scripts or engine implementations.

The catalogue was extracted from a separately installed Open-BFME-2 checkout
with bfme-workshop's `script_catalog` ([log](../history/bfme-workshop-experiments.md#script-lab)).

The two source functions are labelled matched in that checkout's function ledger:
action RVA `0x003D46DB`, 62,675 bytes; condition RVA `0x003CF6B7`, 20,516 bytes.
They define 595 named actions in 599 slots and 195 named conditions in 202 slots.
Nine action signatures depend on defaults absent from those initializer stores.
The native observer reads both complete tables after the engine initializes;
reconciliation fills only missing values and rejects disagreements with explicit
source declarations. All nine missing defaults were resolved, and all **331
distinct stored retail signatures**, including the legacy file, match the
reconciled catalogue (330 in the modern subset).

Action holes: 227, 343, 382, 480. Condition holes: 59, 60, 67, 68, 72, 73, 122.
These slots are not automatically authorable actions/conditions. Internal,
campaign and Living World operations may have mode-specific prerequisites even
when their names and argument signatures exist in the table.

## Original authoring and native lab

`script_writer.Writer` creates Script v4, Condition v6 and Action v3 records
using explicit typed arguments and a catalogue. It rejects wrong argument
types/counts, ambiguous names and unresolved signatures. It installs only into
an empty side's ScriptList; existing scripts cannot be silently overwritten.
It currently exposes ordinary scripts, not every sequential/group setting.

bfme-workshop's script lab tested these records in BFME2 1.06 with twelve
scripts whose results spawn named marker units
([log](../history/bfme-workshop-experiments.md#script-lab)):

| Case | Native result |
| --- | --- |
| Counter equality plus flag, both conditions in one group | One marker created |
| True plus false in one group | No marker; AND behavior |
| False group followed by true group | One marker; OR behavior |
| False branch followed by disabling that script | Exactly one marker |
| Disabled action and disabled script | No markers |
| Disabled false condition | Skipped; script created its marker |
| Constant false with second condition flag set | Remained false; no semantic inversion claim |
| Named unit inside authored trigger polygon | One marker created |
| Frame timer set to 60 | First observed 63 simulation frames after initialization |
| Seconds timer set to 2.0 | First observed about 2.1 elapsed seconds later |

Sampling occurs roughly once per second, so first-seen times are observation
windows, not exact execution timestamps. In this instrumented run simulation
advanced at about five frames/second; seconds timers and frame timers clearly
used different progress measures. General pause/game-speed behavior remains open.

## Remaining authoring work

- Establish legal values, named references, mode restrictions and compatibility
  migrations for the full recovered catalogue. Signature coverage does not mean
  all 790 named operations have native behavior tests.
- Extend flag tests beyond constant conditions; verify group activation,
  evaluation cadence, sequential execution, loops and subroutine context.
- Resolve references to players, teams, objects, areas, waypoints, timers,
  counters, strings and assets. Placeholders such as `<This Player>` need context.
- Extend the writer and native cases to teams/reinforcements, objectives/victory,
  cinematics, groups, sequential actions and difficulty settings.
- Account for typed coordinates and referenced geometry during transformations.
  Finding XYZ arguments alone does not establish safe script-aware resizing;
  existing resize restrictions remain in force.

Synthetic tests cover nested conditions, both action branches, raw argument
preservation, unknown IDs/versions, truncation, trailing bytes, bad references
and nesting limits. Authoring tests reject wrong signatures, preserve existing
scripts, and reject conflicting source/native catalogue evidence. Observation
tests cover positive controls, object-list cycles, duplicate and forbidden markers.

## Sources and evidence

Layouts:
[OpenSAGE Script](https://github.com/OpenSAGE/OpenSAGE/blob/master/src/OpenSage.Game/Scripting/Script.cs),
[ScriptGroup](https://github.com/OpenSAGE/OpenSAGE/blob/master/src/OpenSage.Game/Scripting/ScriptGroup.cs),
[ScriptContent](https://github.com/OpenSAGE/OpenSAGE/blob/master/src/OpenSage.Game/Scripting/ScriptContent.cs),
[ScriptArgument](https://github.com/OpenSAGE/OpenSAGE/blob/master/src/OpenSage.Game/Scripting/ScriptArgument.cs)
and the [argument-type caveat](https://github.com/OpenSAGE/OpenSAGE/blob/master/src/OpenSage.Game/Scripting/ScriptArgumentType.cs).

BFME2-specific cross-check: local
[Open-BFME-2 revision 33f02e4](https://github.com/Open-BFME/Open-BFME-2/tree/33f02e4222f3ac9c284d9b71cf5e7438799988bb),
`Code/GameEngine/Source/GameLogic/ScriptEngine/ParameterReadParameter.cpp` and
`ConditionWriteDataChunk.cpp`. Its ledger labels parameter reader RVA
`0x003B5CA1` (516 bytes) and condition writer RVA `0x003B428C` (183 bytes) as
matched. This is upstream ledger evidence, not a fresh byte-match run here.
`ScriptWriteDataChunk.cpp` supplies the player-mask interpretation. The complete
stored layouts were independently checked against the retail corpus above.
No retail scripts or upstream implementations are included in the test fixtures.
