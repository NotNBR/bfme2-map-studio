"""Read-only BIG/INI adapter. Emits a small, git-ignored local balance pack.

This deliberately supports a subset of SAGE, not arbitrary Behavior execution.
No retail binaries are copied. Optional portraits stay in ignored local content.
Values retain their source provenance.
"""

from mapworkshop.config import CACHE
import argparse
import hashlib
import io
import json
import pathlib
import re
import struct
import subprocess

class BigArchive:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.entries = {}
        total = self.path.stat().st_size
        with self.path.open('rb') as stream:
            header = stream.read(16)
            if len(header) != 16 or header[:4] not in (b'BIG4', b'BIGF'):
                raise ValueError('Not a supported BIG4/BIGF archive')
            count, directory_end = struct.unpack('>II', header[8:])
            if count > 100000 or not 16 <= directory_end <= total:
                raise ValueError('Invalid archive directory')
            for _ in range(count):
                entry = stream.read(8)
                if len(entry) != 8:
                    raise ValueError('Truncated archive entry')
                offset, size = struct.unpack('>II', entry)
                name = bytearray()
                while True:
                    c = stream.read(1)
                    if not c or len(name) > 4096 or stream.tell() > directory_end:
                        raise ValueError('Unterminated archive path')
                    if c == b'\0':
                        break
                    name.extend(c)
                if offset < directory_end or offset + size > total:
                    raise ValueError('Archive entry lies outside payload')
                key = name.decode('cp1252').replace('\\', '/').lower()
                self.entries[key] = (offset, size)

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


def block(text, kind, name):
    # Top-level SAGE blocks begin at column zero in the retail files.
    found = re.search(r'^' + re.escape(kind) + r'\s+' + re.escape(name) + r'\s*(?:;[^\n]*)?$', text, re.M | re.I)
    if not found:
        return ''
    tail = text[found.end():]
    end = re.search(r'^(?:End|Object\s|ChildObject\s|Weapon\s|Locomotor\s)', tail, re.M | re.I)
    return tail[:end.start()] if end else tail


def field(text, name):
    match = re.search(r'^\s*' + re.escape(name) + r'\s*=\s*([^;\r\n]+)', text, re.M | re.I)
    return match[1].strip() if match else ''


SPECS = {
    'soldier': ('GondorFighter', 'GondorFighterHorde'),
    'archer': ('GondorArcher', 'GondorArcherHorde'),
    'cavalry': ('GondorCavalry', 'GondorCavalryHorde'),
    'ranger': ('GondorRanger', 'GondorRangerHorde'),
    'hero': ('GondorAragorn', None),
    'orc': ('MordorFighter', 'MordorFighterHorde'),
    'orcarcher': ('MordorArcher', 'MordorArcherHorde'),
    'troll': ('MordorAttackTroll', None),
    'siege': ('MordorCatapult', None),
}


def convert(archive):
    texts = {key: archive.read(key) for key in archive.entries if key.endswith(('.ini', '.inc'))}
    constants = {}
    for text in texts.values():
        constants.update(definitions(text))
    objects, weapons = {}, {}
    for path, text in texts.items():
        for kind, name in re.findall(r'^(Object|Weapon)\s+(\w+)', text, re.M):
            (objects if kind == 'Object' else weapons)[name] = (path, block(text, kind, name))
    output, missing = {}, []
    for key, (unit, horde) in SPECS.items():
        if unit not in objects:
            missing.append(unit)
            continue
        path, body = objects[unit]
        hpath, hbody = objects.get(horde, (path, body))
        record = {'object': unit, 'horde': horde, 'source': path, 'hordeSource': hpath, 'portraitName': field(body, 'SelectPortrait')}
        for dst, src, txt in [('health', 'MaxHealth', body), ('cost', 'BuildCost', hbody), ('buildTime', 'BuildTime', hbody)]:
            val = number(field(txt, src), constants)
            if val is not None:
                record[dst] = val
        count = re.search(r'InitialPayload\s*=\s*' + re.escape(unit) + r'\s+(\w+)', hbody)
        if count:
            record['count'] = number(count[1], constants)
        # First primary weapon, ignoring conditions/upgrades: explicitly a subset.
        w = re.search(r'^\s*Weapon\s*=\s*PRIMARY\s+(\w+)', body, re.M)
        if w and w[1] in weapons:
            wpath, wbody = weapons[w[1]]
            record['weapon'] = w[1]
            record['weaponSource'] = wpath
            for dst, src in [('damage', 'Damage'), ('range', 'AttackRange'), ('attackDelayMs', 'DelayBetweenShots')]:
                val = number(field(wbody, src), constants)
                if val is not None:
                    record[dst] = val
        output[key] = record
    return output, missing


def import_portraits(game, ini_archive, units, output_dir):
    """Optional Pillow-based conversion of locally owned texture atlas regions."""
    from PIL import Image
    mapped = {}
    for key in ini_archive.entries:
        if 'mappedimages/' not in key or not key.endswith('.ini'):
            continue
        text = ini_archive.read(key)
        for name in re.findall(r'^MappedImage\s+(\w+)', text, re.M | re.I):
            mapped[name.lower()] = block(text, 'MappedImage', name)
    textures = {}
    for path in sorted(game.glob('Textures*.big')):
        archive = BigArchive(path)
        for key in archive.entries:
            textures[pathlib.PurePosixPath(key).name.lower()] = (archive, key)
    output_dir.mkdir(parents=True, exist_ok=True)
    for key, unit in units.items():
        definition = mapped.get(unit.get('portraitName', '').lower(), '')
        texture = field(definition, 'Texture').lower()
        candidates = [texture, str(pathlib.PurePosixPath(texture).with_suffix('.dds'))] if texture else []
        entry = next((textures[name] for name in candidates if name in textures), None)
        if not entry:
            continue
        archive, entry_key = entry
        coords = dict((k.lower(), int(v)) for k, v in re.findall(r'(Left|Top|Right|Bottom):(\d+)', field(definition, 'Coords'), re.I))
        try:
            image = Image.open(io.BytesIO(archive.read_bytes(entry_key))).convert('RGBA')
            if len(coords) == 4:
                image = image.crop(tuple(coords[k] for k in ['left', 'top', 'right', 'bottom']))
            image.thumbnail((192, 192))
            image.save(output_dir / (key + '.png'))
            unit['portrait'] = '/local-content/portraits/' + key + '.png'
        except (OSError, ValueError) as exc:
            print(f'Portrait skipped for {key}: {exc}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=pathlib.Path, required=True)
    parser.add_argument('--reference', type=pathlib.Path)
    parser.add_argument('--portraits', action='store_true', help='Also import local unit portraits; requires Pillow')
    parser.add_argument('--output', type=pathlib.Path, default=CACHE/'bfme-content.json')
    args = parser.parse_args()
    archive_path = args.game / 'INI.big'
    archive = BigArchive(archive_path)
    units, missing = convert(archive)
    if not units:
        raise SystemExit('No supported BFME2 units found; output was not written.')
    if args.portraits:
        import_portraits(args.game, archive, units, args.output.parent / 'portraits')
    reference = None
    if args.reference and (args.reference / '.git').exists():
        reference = subprocess.check_output(['git', '-C', str(args.reference), 'rev-parse', 'HEAD'], text=True).strip()
    data = {
        'schemaVersion': 1, 'title': 'Local BFME2 INI.big',
        'archiveSha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        'openbfme2Commit': reference, 'units': units, 'missing': missing,
        'limitations': ['INI.big only: patch archives are not overlaid.', 'Base health, horde cost/count/build time, first primary weapon only.', 'Movement, armor, powers and animation remain prototype rules.']
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(f'Imported {len(units)} unit definitions into {args.output}')
    for key, unit in units.items():
        print(key, {k: v for k, v in unit.items() if not k.lower().endswith('source')})
    if missing:
        print('Missing:', ', '.join(missing))


if __name__ == '__main__':
    main()
