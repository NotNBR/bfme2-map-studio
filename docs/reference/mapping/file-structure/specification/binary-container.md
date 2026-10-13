# Binary encoding and container

[Specification index](../specification.md) · [Previous](files.md) · [Next](sections.md)

## Primitive encodings

All numbers are **little-endian**, except explicitly identified RefPack header
lengths. Records are packed consecutively: **no implicit alignment or padding**.

| Notation | Encoding |
| --- | --- |
| `u8`, `u16`, `u24`, `u32` | Unsigned integer of 1, 2, 3 or 4 bytes |
| `i32` | Signed 32-bit integer |
| `f32` | IEEE-754 binary32 float |
| `vec2`, `vec3` | Two/three consecutive `f32` values |
| `str` | `u16 byteCount`, then exactly that many CP1252 bytes; no terminator |
| `wstr` | `u16 codeUnitCount`, then that many UTF-16LE code units; no terminator |
| `nameStr` | Unsigned base-128 variable-length byte count, then UTF-8 bytes |
| `nameKey` | `u8 kind`, then `u24 nameID`; the kind's meaning depends on the enclosing record |
| `props` | Property dictionary defined below |
| `T[n]` | Exactly `n` serialized instances of `T` |
| `count + T[]` | A count immediately followed by records; count is `u32` unless stated otherwise |

For a variable-length name length, each byte contributes its low seven bits,
least-significant group first; bit 7 indicates another byte follows. Name-table
strings and ordinary record strings use **different length encodings and
character encodings**. UTF-16 lengths count code units, not Unicode code points.

Boolean-labelled fields retain their stored integer widths and raw values.
They are not all single-byte fields: script operation enable fields are `u32`.


## Compression

The current reader accepts either an uncompressed `CkMp` document or this wrapper:

| Offset | Type | Value |
| ---: | --- | --- |
| 0 | 4 bytes | `45 41 52 00` = `EAR\0` |
| 4 | `u32` | Decompressed byte length |
| 8 | remaining bytes | RefPack stream producing a complete `CkMp` document |

The RefPack stream begins with two flag/signature bytes. The implemented profile
requires `(byte0 & 0x3e) == 0x10` and `byte1 == 0xfb`. Length fields are **big-endian**
and use four bytes when bit `0x80` of byte0 is set, otherwise three. Bit `0x01`
adds an initial length field before the decompressed length; the current reader
skips that initial field. Do not confuse this with the wrapper's little-endian
length at offset 4.

After the RefPack header, read commands until a terminal command. Let `a` be the
first command byte and `b,c,d` additional bytes as shown. First copy `L` literal
bytes from the stream; then copy `N` bytes from output at backward distance `D`.
Backward copies can overlap and repeat previously emitted bytes.

| `a` range | Extra bytes | `L` | `N` | `D` |
| --- | --- | --- | --- | --- |
| `00..7f` | `b` | `a & 3` | `((a & 0x1c) >> 2) + 3` | `((a & 0x60) << 3) + b + 1` |
| `80..bf` | `b,c` | `b >> 6` | `(a & 0x3f) + 4` | `((b & 0x3f) << 8) + c + 1` |
| `c0..df` | `b,c,d` | `a & 3` | `((a & 0x0c) << 6) + d + 5` | `((a & 0x10) << 12) + (b << 8) + c + 1` |
| `e0..fb` | none | `((a & 0x1f) + 1) * 4` | 0 | unused |
| `fc..ff` | none | `a & 3` | 0 | terminal after literals |

Output must equal the RefPack declared length and the outer EAR declared length.
Truncated commands, literals or impossible backward references are invalid.
The toolkit's 128 MiB decompression cap is defensive tool policy.

`Map.encode()` writes uncompressed CkMp. Round-trip evidence therefore compares
**decompressed bytes**, not an identical EAR/RefPack encoding. The general map
reader does not accept a standalone bare RefPack stream as a `.map` container.


## Document and chunk container

```text
Document:
  bytes[4] magic = "CkMp"          # 43 6b 4d 70
  u32 nameCount
  repeat nameCount times:
    nameStr name
    u32 nameID
  Chunk[]                         # until document end, no chunk count

Chunk:
  u32 nameID
  u16 version
  u32 payloadBytes
  bytes[payloadBytes] payload
```

The observed name table stores IDs in descending order `nameCount ... 1`.
The toolkit requires that order and contiguous IDs. Chunk names, property keys,
script operation names and faction keys share this table. An ID is a reference,
not a byte offset or global engine enum.

A chunk header is **10 bytes**. `payloadBytes` excludes the header. A child chunk
uses exactly the same header and shared name table; there is no new local table.
Only specific sections contain child chunks. **Do not recursively parse every
payload as chunks**: terrain planes, counted records and dictionaries have their
own layouts. Children consume their parent's remaining payload, not the file.

No top-level section order is asserted as universally mandatory. Preserve the
observed order when editing; the original-map constructor emits a known working
profile. An unknown chunk can be skipped by length and retained byte-for-byte,
but its name-table references and possible spatial references remain significant.


## Property dictionaries

```text
props:
  u16 propertyCount
  repeat propertyCount times:
    u8 type
    u24 nameID
    value(type)
```

| Type | Stored value | Interpretation |
| ---: | --- | --- |
| 0 | `u8` | Boolean-labelled value; retain raw byte |
| 1 | `i32` | Integer |
| 2 | `f32` | Float |
| 3 | `str` | Narrow string |
| 4 | `wstr` | Wide string |
| 5 | `str` | Narrow string; retain distinct type tag |

There is no individual property payload length. Unknown type tags cannot be
safely skipped without their type definition. Preserve dictionary ordering and
all tags when editing; property meanings depend on the owning section and game
consumer. A known dictionary layout is not a closed catalogue of valid keys.
