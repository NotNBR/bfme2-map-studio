# Map lighting

`formats/lighting.py` reads and writes `GlobalLighting v1–8`. The modern v8
layout is **1,360 bytes**; v7 is 1,348. Every stored field is exposed, but several
roles remain unresolved. Use neutral names for those fields.

## Stored order

Start with `u32 timeOfDay`. For each of four time configurations, write records
in this order. Each record is nine floats: ambient RGB, diffuse RGB, direction XYZ.

| Version introduced | Records, in disk order |
| --- | --- |
| 1 | Terrain light 0, object light 0 |
| 2 | Object lights 1 and 2 |
| 3 | Terrain lights 1 and 2 |
| 4 | Third-array lights 0, 1 and 2 |

These are grouped by the native serialization order, not three targets repeated
for each light. The reader initializes missing secondary lights to black with
direction `(0,0,-1)`. Before v4 it copies object lighting into the third array.
The purpose of that array is not established here.

After all four configurations:

| Version introduced | Fields | Established reader behavior |
| --- | --- | --- |
| 5 | f32 overbright value | Enables shader overbright only when greater than 1; writer emits 1 or 2 |
| 6 | u32 flag, vec3 triplet 0 | Flag becomes a boolean; vector meaning unresolved |
| 7 | vec3 triplets 1 and 2 | Meanings unresolved |
| Optional in older versions | u32 shadow color | Read if bytes remain; stored in shadow manager |
| 8 | Three f32 final values | Earlier versions initialize them to `(1,1,1)`; purpose unresolved |

The v8 writer requires shadow color before the final values. The serializer
rejects nonfinite floats and incorrect slot/count order; it does not impose
unverified artistic ranges. Keep raw color bits until channel semantics are
independently established. Decoding does not normalize directions or color values.

## Evidence and correction

The previous analyser incorrectly named the first word after the light records
as shadow color and left the following 44 bytes opaque. The actual first word
is an overbright **float**; shadow color follows the flag and nine vector floats.
The blank-map generator also used the wrong light-slot order. Both are corrected;
existing map files are not rewritten automatically.

The 67 `Maps.big` lighting chunks decode and re-encode byte-for-byte, including
the older v7 example. Synthetic fixtures use distinct values to detect swapped
fields, cover all eight versions and reject truncated/trailing data.

Source: [Open-BFME-2 at revision 33f02e4](https://github.com/Open-BFME/Open-BFME-2/blob/33f02e4222f3ac9c284d9b71cf5e7438799988bb/Code/GameEngineDevice/Source/W3DDevice/GameClient/GlobalLightingDataChunk.cpp).
The upstream ledger marks reader RVA `0x000ACAF7` (1,563 bytes) and writer
`0x000AD112` (1,494 bytes) matched to BFME2. This is upstream ledger evidence,
not a fresh compiler byte-match run in this repository. Neutral source labels
are preserved rather than assigning meanings from another SAGE game.

For native readback, add `--lighting-probe` to the [script lab](../scripts/README.md).
It gives every time/light slot distinct original values and records the engine's
arrays, overbright toggle, flag, vectors, shadow color and final values. The
observer only reads memory and compares it with the authored map. A successful
readback verifies loading, not every rendering effect of those values.

Native run `script-lab/run-004` passed on 9 October 2026 with map SHA-256
`79a5e9e7136f63153e083378cdd22dbce86d9b938b93d28ac0eb72b04f9f0db5`.
All 36 distinct records and all extension fields matched; the strategic
extension was disabled. The existing script markers also passed. This uses
the isolated workshop runtime, not a clean-menu or multiplayer test.
