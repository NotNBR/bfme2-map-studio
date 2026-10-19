"""Read-only BIG archives (BIG4 and BIGF): their directories and entries, and
the #define constants and numbers of the INI files inside them.

Compressed (RefPack) entries are refused, not decoded.
"""

import pathlib
import re
import struct

_DIRECTORIES = {}   # (path, size, mtime) -> entries: a process reads each archive's directory once


class BigArchive:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        stat = self.path.stat()
        key = (str(self.path.resolve()), stat.st_size, stat.st_mtime_ns)
        if key not in _DIRECTORIES:
            _DIRECTORIES[key] = self._directory(stat.st_size)
        self.entries = dict(_DIRECTORIES[key])

    def _directory(self, total):
        """The archive's entries, from its directory read in one piece."""
        entries = {}
        with self.path.open('rb') as stream:
            header = stream.read(16)
            if len(header) != 16 or header[:4] not in (b'BIG4', b'BIGF'):
                raise ValueError('Not a supported BIG4/BIGF archive')
            count, directory_end = struct.unpack('>II', header[8:])
            if count > 100000 or not 16 <= directory_end <= total:
                raise ValueError('Invalid archive directory')
            directory = stream.read(directory_end - 16)
        pos = 0
        for _ in range(count):
            if pos + 8 > len(directory):
                raise ValueError('Truncated archive entry')
            offset, size = struct.unpack_from('>II', directory, pos)
            end = directory.find(b'\0', pos + 8, pos + 8 + 4098)
            # The path's terminator must lie inside the directory, the path at most 4096 bytes.
            if end < 0:
                raise ValueError('Unterminated archive path')
            if offset < directory_end or offset + size > total:
                raise ValueError('Archive entry lies outside payload')
            entries[directory[pos + 8:end].decode('cp1252').replace('\\', '/').lower()] = (offset, size)
            pos = end + 1
        return entries

    def read_bytes(self, key):
        offset, size = self.entries[key]
        with self.path.open('rb') as stream:
            stream.seek(offset)
            data = stream.read(size)
        if data.startswith(b'\x10\xfb'):
            raise ValueError('RefPack compressed entry is not supported: ' + key)
        return data

    def read(self, key):
        return self.read_bytes(key).decode('cp1252')


def definitions(text):
    return dict(re.findall(r'^\s*#define\s+(\w+)\s+([^;\r\n]+)', text, re.M))


def number(value, constants):
    value = value.strip()
    seen = set()
    while value in constants:
        if value in seen:
            return None
        seen.add(value)
        value = constants[value].strip()
    try:
        n = float(value)
        return n if n > 0 and n < 1e7 else None
    except ValueError:
        return None
