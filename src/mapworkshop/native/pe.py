"""The few facts the launcher needs from a 32-bit Windows executable or DLL:
its image size, its import slots, its exports and its code sections.

A small reader instead of the pefile package: the launcher reads game.dat
while the game waits at its loader breakpoint, and pefile's full parse of the
11 MB file took half a second there.
"""
import struct
from pathlib import Path


class PE:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        d = self.data
        if d[:2] != b'MZ':
            raise ValueError(f'{path}: not an executable')
        self.nt = struct.unpack_from('<I', d, 0x3C)[0]
        if d[self.nt:self.nt+4] != b'PE\0\0':
            raise ValueError(f'{path}: no PE header')
        sections, optional_size = struct.unpack_from('<2xH12xH', d, self.nt+4)
        opt = self.nt+24
        if struct.unpack_from('<H', d, opt)[0] != 0x10B:
            raise ValueError(f'{path}: not a 32-bit image')
        self.image_base, = struct.unpack_from('<I', d, opt+28)
        self.image_size, = struct.unpack_from('<I', d, opt+56)
        self.directories = [struct.unpack_from('<II', d, opt+96+8*i) for i in range(16)]
        self.sections = []           # (name, rva, virtual size, file offset, raw size, characteristics)
        for i in range(sections):
            o = opt+optional_size+40*i
            name = d[o:o+8].rstrip(b'\0').decode('latin1')
            vsize, rva, raw_size, raw = struct.unpack_from('<4I', d, o+8)
            flags, = struct.unpack_from('<I', d, o+36)
            self.sections.append((name, rva, vsize, raw, raw_size, flags))

    def offset(self, rva):
        for _, start, vsize, raw, raw_size, _ in self.sections:
            if start <= rva < start+max(vsize, raw_size):
                return raw+rva-start
        raise ValueError(f'RVA {rva:#x} is in no section')

    def cstring(self, rva):
        o = self.offset(rva)
        return self.data[o:self.data.index(b'\0', o)]

    def imports(self):
        """{(dll in lower case, function name): RVA of its import address slot}."""
        rva, size = self.directories[1]
        out = {}
        if not rva:
            return out
        o = self.offset(rva)
        while True:
            lookup, _, _, name, first = struct.unpack_from('<5I', self.data, o)
            if not name:
                break
            dll = self.cstring(name).decode('latin1').lower()
            table = lookup or first
            i = 0
            while True:
                entry, = struct.unpack_from('<I', self.data, self.offset(table)+4*i)
                if not entry:
                    break
                if not entry & 0x80000000:          # by name: a hint word, then the name
                    out[(dll, self.cstring(entry+2).decode('latin1'))] = first+4*i
                i += 1
            o += 20
        return out

    def exports(self):
        """{name: RVA} of the exported symbols."""
        rva, size = self.directories[0]
        if not rva:
            return {}
        o = self.offset(rva)
        functions, names, addresses, name_table, ordinals = struct.unpack_from('<5I', self.data, o+20)
        out = {}
        for i in range(names):
            name = self.cstring(struct.unpack_from('<I', self.data, self.offset(name_table)+4*i)[0])
            ordinal, = struct.unpack_from('<H', self.data, self.offset(ordinals)+2*i)
            out[name.decode('latin1')] = struct.unpack_from('<I', self.data, self.offset(addresses)+4*ordinal)[0]
        return out

    def code(self):
        """(RVA, bytes) of each executable section."""
        return [(rva, self.data[raw:raw+raw_size]) for _, rva, _, raw, raw_size, flags in self.sections
                if flags & 0x20000000]
