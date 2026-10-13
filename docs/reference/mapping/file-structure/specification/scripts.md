# Scripts

[Specification index](../specification.md) · [Previous](players-and-bases.md) · [Next](triggers-and-water.md)

`PlayerScriptsList` v1/5/6 contains `ScriptList v1` chunks; there is no leading
count. The modern hierarchy is:

```text
PlayerScriptsList
  ScriptList
    ScriptGroup                    # optional; prefix followed by children
      Script / ScriptGroup
    Script
      OrCondition
        Condition
      ScriptAction                 # true branch
      ScriptActionFalse            # false branch
```

All nodes have normal chunk headers. Prefix fields below are followed by child
chunks until the node's payload boundary; **there is no child count**.

| Node/version | Prefix |
| --- | --- |
| `ScriptList v1` | None |
| `ScriptGroup v1–3` | `str name, u8 active, u8 subroutine`; nested groups only supported from v3 |
| `Script v1` | Four strings: name, comment, conditions comment, actions comment; six bytes: active, deactivate-on-success, easy, medium, hard, subroutine |
| Script v2 addition | `u32 evaluationIntervalRaw` |
| Script v3 addition | `u8 sequential, u8 loop, i32 loopCount, u8 targetTypeRaw, str targetName` |
| Script v4 addition | `str playerMaskText` |
| `OrCondition v1` | None; contains conditions |

Conditions inside one `OrCondition` form an AND group; groups are OR alternatives
in the native lab. More complex sequential/group/difficulty behavior remains
partially understood. Preserve evaluation and target fields instead of assuming
their values or treating them as editor-only comments.

Operation payload:

```text
u32 opcodeRaw
nameKey internalName
u32 argumentCount
Argument arguments[argumentCount]
if Condition version >= 5: u32 enabledRaw, u32 conditionFlag4dRaw
if ScriptAction/ScriptActionFalse version >= 3: u32 enabledRaw

Argument:
  u32 typeID
  if typeID == 16: vec3 position
  otherwise: i32 integerValue, f32 floatValue, str stringValue
```

Supported operation versions are Condition v4/5/6 and both action branches v2/3.
For a non-position argument, the integer, float and string are **all stored**;
they are not a union. Do not drop apparently unused fields. Type 16 positions
must be considered when moving/resizing geometry.

`conditionFlag4dRaw` is **not established as condition inversion**; an original
native test disproved that shortcut. Numeric opcodes can move between versions:
retain the internal name and argument types. The bundled BFME2 1.06 catalogue
has 595 named action / 195 named condition signatures, not verified behavior for
every operation. Legacy argument migrations are separate from layout decoding.

See the [script reference](../../scripts/README.md) for argument types, version
comparisons, writer constraints and native observations.
