"""Compiled D3DX9 effects (fx_2_0 `.fxo`): parameters, techniques, shaders.

    python -m mapworkshop.formats.fxo FILE.fxo [--disassemble] [--technique NAME]

The layout follows Wine's d3dx9 effect parser: a 0xFEFF0901 tag, the offset
of the effect body, a data area holding typedefs, values and strings, then
the parameter, technique and pass tables, the object (string and shader)
blobs and the resources that bind shader objects and array selectors to pass
states. Shader bytecode is disassembled with d3dcompiler_47's D3DDisassemble
when it is available.
"""

import argparse
import struct
from pathlib import Path

TYPES = ['void', 'bool', 'int', 'float', 'string', 'texture', 'texture1d', 'texture2d', 'texture3d',
         'texturecube', 'sampler', 'sampler1d', 'sampler2d', 'sampler3d', 'samplercube',
         'pixelshader', 'vertexshader', 'pixelfragment', 'vertexfragment', 'unsupported']
CLASSES = ['scalar', 'vector', 'matrix_rows', 'matrix_columns', 'object', 'struct']
OBJECT_TYPES = {4, 5, 6, 7, 8, 9, 15, 16}
SAMPLER_TYPES = {10, 11, 12, 13, 14}
# Wine d3dx9 state_table indices for the states this reader needs by name.
STATE_NAMES = {146: 'VertexShader', 147: 'PixelShader'}


class Reader:
    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def u32(self):
        value, = struct.unpack_from('<I', self.data, self.pos)
        self.pos += 4
        return value

    def blob(self):
        size = self.u32()
        start = self.pos
        self.pos += (size + 3) & ~3
        return self.data[start:start+size]


class Effect:
    def __init__(self, data):
        tag, offset = struct.unpack_from('<II', data, 0)
        if tag != 0xFEFF0901:
            raise ValueError(f'Not an fx_2_0 effect (tag {tag:#x})')
        self.base = data[8:]
        r = Reader(self.base, offset)
        parameter_count, technique_count = r.u32(), r.u32()
        r.u32()
        self.object_count = r.u32()
        self.objects = {}
        self.parameters = [self._parameter(r) for _ in range(parameter_count)]
        self.techniques = [self._technique(r) for _ in range(technique_count)]
        string_count, resource_count = r.u32(), r.u32()
        for _ in range(string_count):
            object_id = r.u32()
            self.objects[object_id] = r.blob()
        self.resources = [self._resource(r) for _ in range(resource_count)]

    # Data-area helpers --------------------------------------------------------
    def string(self, offset):
        size, = struct.unpack_from('<I', self.base, offset)
        return self.base[offset+4:offset+4+size].split(b'\0')[0].decode('latin-1')

    def _typedef(self, offset):
        r = Reader(self.base, offset)
        return self._typedef_at(r)

    def _typedef_at(self, r):
        kind, klass, name, semantic = r.u32(), r.u32(), r.u32(), r.u32()
        t = dict(type=kind, cls=klass, name=self.string(name) if name else '',
                 semantic=self.string(semantic) if semantic else '')
        if klass in (0, 1, 2, 3):
            t.update(elements=r.u32(), columns=r.u32(), rows=r.u32())
        elif klass == 5:
            t['elements'] = r.u32()
            t['members'] = [self._typedef_at(r) for _ in range(r.u32())]
        elif klass == 4:
            t['elements'] = r.u32()
        t['_end'] = r.pos
        return t

    def _value(self, t, offset):
        r = Reader(self.base, offset)
        count = max(t.get('elements', 0), 1)
        if t['cls'] == 4 and t['type'] in OBJECT_TYPES:
            return dict(objects=[r.u32() for _ in range(count)])
        if t['cls'] == 4 and t['type'] in SAMPLER_TYPES:
            samplers = []
            for _ in range(count):
                states = []
                for _ in range(r.u32()):
                    states.append(self._state(r))
                samplers.append(states)
            return dict(samplers=samplers)
        if t['cls'] == 5:
            return dict(raw=None)
        n = count * max(t.get('columns', 1), 1) * max(t.get('rows', 1), 1)
        values = struct.unpack_from(f'<{n}I', self.base, offset)
        if t['type'] == 3:
            values = struct.unpack_from(f'<{n}f', self.base, offset)
        return dict(values=list(values))

    def _annotation(self, r):
        t = self._typedef(r.u32())
        return dict(name=t['name'], type=TYPES[t['type']], value=self._value(t, r.u32()))

    def _state(self, r):
        operation, index, typedef, value = r.u32(), r.u32(), r.u32(), r.u32()
        t = self._typedef(typedef)
        return dict(operation=operation, name=STATE_NAMES.get(operation, f'state{operation}'),
                    index=index, type=TYPES[t['type']], value=self._value(t, value))

    def _parameter(self, r):
        typedef, value, flags, annotations = r.u32(), r.u32(), r.u32(), r.u32()
        t = self._typedef(typedef)
        p = dict(name=t['name'], semantic=t['semantic'], type=TYPES[t['type']], cls=CLASSES[t['cls']],
                 elements=t.get('elements', 0), flags=flags,
                 annotations=[self._annotation(r) for _ in range(annotations)])
        p['value'] = self._value(t, value)
        return p

    def _technique(self, r):
        name, annotations, passes = r.u32(), r.u32(), r.u32()
        t = dict(name=self.string(name) if name else '',
                 annotations=[self._annotation(r) for _ in range(annotations)], passes=[])
        for _ in range(passes):
            pname, pannotations, states = r.u32(), r.u32(), r.u32()
            p = dict(name=self.string(pname) if pname else '',
                     annotations=[self._annotation(r) for _ in range(pannotations)])
            p['states'] = [self._state(r) for _ in range(states)]
            t['passes'].append(p)
        return t

    def _resource(self, r):
        technique, index, element, state, usage = r.u32(), r.u32(), r.u32(), r.u32(), r.u32()
        res = dict(technique=technique, index=index, element=element, state=state, usage=usage)
        if usage == 0:
            # Shader bytecode for the object bound to this state.
            res['data'] = r.blob()
        elif usage == 1:
            # Name of the parameter this state reads.
            res['parameter'] = r.blob().split(b'\0')[0].decode('latin-1')
        elif usage == 2:
            # Array selector: the shader-array parameter plus a preshader that
            # computes the element index.
            data = r.blob()
            size, = struct.unpack_from('<I', data, 0)
            res['parameter'] = data[4:4+size].split(b'\0')[0].decode('latin-1')
            res['data'] = data[4+((size+3) & ~3):]
        else:
            raise ValueError(f'Unknown resource usage {usage}')
        return res

    # Queries ------------------------------------------------------------------
    def parameter(self, name):
        return next((p for p in self.parameters if p['name'] == name), None)

    def target(self, res):
        """The state a resource binds: (technique, pass, state) or (parameter, element, state)."""
        if res['technique'] == 0xFFFFFFFF:
            p = self.parameters[res['index']]
            return ('parameter', p['name'], res['element'], res['state'])
        t = self.techniques[res['technique']]
        return ('pass', t['name'], t['passes'][res['index']]['name'], res['state'])

    def shader_objects(self):
        """Object id -> bytecode for every shader object, including array members."""
        # Shader-array members are stored with the strings, as object blobs
        # that start with a vs/ps version token.
        shaders = {i: b for i, b in self.objects.items()
                   if len(b) >= 4 and b[2:4] in (b'\xfe\xff', b'\xff\xff')}
        for res in self.resources:
            if res['usage'] != 0:
                continue
            kind, owner, element, state = self.target(res)
            if kind == 'pass':
                t = next(t for t in self.techniques if t['name'] == owner)
                p = next(p for p in t['passes'] if p['name'] == element)
                ids = p['states'][state]['value'].get('objects', [])
                for i in ids:
                    shaders[i] = res['data']
            else:
                p = self.parameter(owner)
                ids = p['value'].get('objects', [])
                if element != 0xFFFFFFFF and element < len(ids):
                    shaders[ids[element]] = res['data']
                elif len(ids) == 1:
                    shaders[ids[0]] = res['data']
        return shaders


# fx_2_0 expression (preshader) opcodes, after Wine d3dx9 preshader.c.
_EXPR_OPS = {0x000: 'nop', 0x100: 'mov', 0x101: 'neg', 0x103: 'rcp', 0x104: 'frc', 0x105: 'exp', 0x106: 'log',
             0x107: 'rsq', 0x108: 'sin', 0x109: 'cos', 0x10a: 'asin', 0x10b: 'acos', 0x10c: 'atan', 0x200: 'min',
             0x201: 'max', 0x202: 'lt', 0x203: 'ge', 0x204: 'add', 0x205: 'mul', 0x206: 'atan2', 0x208: 'div',
             0x300: 'cmp', 0x500: 'dot'}
_EXPR_TABLES = {1: 'imm', 2: 'c', 4: 'o', 5: 'ob', 6: 'oi', 7: 'r'}


def decode_expression(blob):
    """Readable text of an fx_2_0 expression blob (array selector): the
    constants it reads (CTAB name -> register) and its instructions."""
    toks = struct.unpack(f'<{len(blob)//4}I', blob[:len(blob)//4*4])
    if not toks or toks[0] & 0xFFFF0000 != 0x46580000:
        return None
    sections, i = {}, 1
    while i < len(toks) and toks[i] != 0xFFFF:
        if toks[i] & 0xFFFF == 0xFFFE:
            n = toks[i] >> 16
            body = blob[(i+1)*4:(i+1+n)*4]
            sections[body[:4]] = body[4:]
            i += 1 + n
        else:
            i += 1
    literals = []
    if b'CLIT' in sections:
        n, = struct.unpack_from('<I', sections[b'CLIT'])
        literals = struct.unpack_from(f'<{n}d', sections[b'CLIT'], 4)
    lines = []
    if b'CTAB' in sections:
        t = sections[b'CTAB']
        count, info = struct.unpack_from('<II', t, 12)
        for k in range(count):
            name, regset, index = struct.unpack_from('<IHH', t, info + 20*k)
            lines.append(f'// c{index} = {t[name:t.index(b"\0", name)].decode("latin-1")}')
    code = struct.unpack(f'<{len(sections.get(b"FXLC", b""))//4}I', sections.get(b'FXLC', b''))
    p = 1

    def operand(p, width):
        if code[p]:          # relative addressing
            p += 2
        table, offset = code[p+1], code[p+2]
        name = _EXPR_TABLES.get(table, f't{table}')
        if name == 'imm':
            text = '(' + ', '.join(f'{literals[offset+k]:g}' for k in range(width) if offset+k < len(literals)) + ')'
        else:
            text = f'{name}{offset//4}.' + ''.join('xyzw'[(offset+k) % 4] for k in range(width))
        return p + 3, text
    for _ in range(code[0] if code else 0):
        word = code[p]; p += 1
        width = word & 0xFFFF
        inputs = code[p]; p += 1
        args = []
        for k in range(inputs):
            p, text = operand(p, 1 if (word & 0x80000000 and k == 0) else width)
            args.append(text)
        p, out = operand(p, width)
        lines.append(f'{_EXPR_OPS.get((word >> 20) & 0x7FF, hex((word >> 20) & 0x7FF))} {out}, {", ".join(args)}')
    return '\n'.join(lines)


def disassemble(bytecode):
    """Shader assembly via D3DDisassemble, or None when d3dcompiler is missing."""
    import ctypes
    try:
        dll = ctypes.WinDLL('d3dcompiler_47.dll')
    except OSError:
        return None
    blob = ctypes.c_void_p()
    hr = dll.D3DDisassemble(ctypes.c_char_p(bytes(bytecode)), ctypes.c_size_t(len(bytecode)),
                            ctypes.c_uint(0), None, ctypes.byref(blob))
    if hr != 0 or not blob.value:
        return None
    vtbl = ctypes.cast(ctypes.cast(blob, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    pointer = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)(vtbl[3])(blob)
    size = ctypes.WINFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p)(vtbl[4])(blob)
    text = ctypes.string_at(pointer, size).decode('latin-1').rstrip('\0')
    ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(blob)
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('file', type=Path)
    parser.add_argument('--disassemble', action='store_true', help='Print shader assembly')
    parser.add_argument('--technique', help='Only this technique')
    args = parser.parse_args(argv)
    effect = Effect(args.file.read_bytes())
    shaders = effect.shader_objects()
    selectors = {(r['technique'], r['index'], r['state']): r for r in effect.resources if r['usage'] in (1, 2)}
    for ti, t in enumerate(effect.techniques):
        if args.technique and t['name'] != args.technique:
            continue
        print(f'technique {ti} {t["name"]}')
        for pi, p in enumerate(t['passes']):
            print(f'  pass {pi} {p["name"]}')
            for si, s in enumerate(p['states']):
                sel = selectors.get((ti, pi, si))
                desc = f'{s["name"]} [{s["type"]}] {s["value"]}'
                if sel:
                    desc += f' <- {sel["parameter"]}' + (' (array selector)' if sel['usage'] == 2 else '')
                print(f'    {desc}')
                if sel and sel['usage'] == 2:
                    # The element index is the expression's output o0.x.
                    for line in (decode_expression(sel['data']) or '').splitlines():
                        print(f'      {line}')
    if args.disassemble:
        for object_id, code in sorted(shaders.items()):
            print(f'\n// object {object_id} ({len(code)} bytes)')
            print(disassemble(code) or '<no disassembler>')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
