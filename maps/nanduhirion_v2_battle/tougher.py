"""Tougher units for the v2 battle: a map.ini that multiplies its units' health.

A map.ini can override an Object: the override starts as a copy of the game's,
and `ReplaceModule <tag>` swaps one of its modules for a new one of the same
class under a new tag. So for every unit the battle places (its armies, heroes
and waves, and the soldiers inside each horde: HordeContain's InitialPayload
and RankInfo UnitType) the unit's Body comes again under the tag `<tag>_Life`
with MaxHealth, InitialHealth and MaxHealthDamaged multiplied by `life`, every
other line as it was; a unit whose Body it inherits (ChildObject) takes its
parent's. (A Weapon override does not reach the units: their weapon sets hold
the weapons the game loaded before the map.ini.)

The game's INI text comes through the assets' templates. A map.ini allows no
macros, so every macro reference is replaced by its text and every #ADD /
#SUBTRACT / #MULTIPLY / #DIVIDE group by its number (plain float arithmetic;
the game evaluates them in x87 single precision, which differs only in the last
digits). One error stops the game reading the rest of a map.ini without a word
in its log: check a unit's max_health in the game after changing this.
"""
import re

ARITHMETIC = {'ADD': lambda a, b: a + b, 'SUBTRACT': lambda a, b: a - b, 'MULTIPLY': lambda a, b: a*b, 'DIVIDE': lambda a, b: a/b}
SCALED = ('MaxHealth', 'InitialHealth', 'MaxHealthDamaged')   # the Body fields `life` multiplies


def defines(assets):
    """Every #define of the game's INI files (data/ini, *.ini and *.inc), by upper-case name; the first wins."""
    out = {}
    for key in sorted(k for k in assets.entries if k.startswith('data/ini/') and k.endswith(('.ini', '.inc'))):
        for name, value in re.findall(r'(?m)^#define\s+(\w+)\s+([^;\r\n]*)', assets.read(key).decode('cp1252', 'replace')):
            out.setdefault(name.upper(), value.split('//')[0].strip())
    return out


def split(text):
    return re.sub(r'(#\w+\()|(\))', r' \1\2 ', text).split()


def evaluate(tokens, macros, depth=0):
    """The number a token stream starts with: a number, a macro, or #OP( a b ) of either; the tokens it used are taken."""
    if depth > 50:
        raise ValueError('macro recursion')
    tok = tokens.pop(0)
    if tok.startswith('#') and tok.endswith('('):
        op = tok[1:-1].upper()
        a, b = evaluate(tokens, macros, depth + 1), evaluate(tokens, macros, depth + 1)
        if tokens.pop(0) != ')':
            raise ValueError(f'#{op} not closed')
        return ARITHMETIC[op](a, b)
    try:
        return float(tok.rstrip('%'))
    except ValueError:
        if tok.upper() in macros:
            return evaluate(split(macros[tok.upper()]), macros, depth + 1)
        raise ValueError(f'not a number: {tok}') from None


def expand(tokens, macros, depth=0):
    """Tokens with every macro replaced by its own tokens (a text macro stays text) and every #OP group by its number."""
    if depth > 50:
        raise ValueError('macro recursion')
    toks, out = list(tokens), []
    while toks:
        if toks[0].startswith('#') and toks[0].endswith('('):
            out.append(f'{evaluate(toks, macros):g}')
        elif toks[0].upper() in macros:
            out += expand(split(macros[toks.pop(0).upper()]), macros, depth + 1)
        else:
            out.append(toks.pop(0))
    return out


def body(templates, name):
    """(class, tag, lines) of the Body module `name` has or inherits, its lines without comments and its End; None without one."""
    seen = set()
    while name and name not in seen and name in templates:
        seen.add(name)
        lines = [re.split(r';|//', l)[0].strip() for l in templates[name]['body'].splitlines()]
        for i, line in enumerate(lines):
            m = re.match(r'^Body\s*=\s*(\w+)\s+(\S+)$', line)
            if not m:
                continue
            block, depth = [], 1
            for inner in lines[i + 1:]:
                if not inner:
                    continue
                if inner.lower() == 'end':
                    depth -= 1
                    if depth == 0:
                        return m.group(1), m.group(2), block
                elif '=' not in inner:
                    depth += 1                             # a nested block inside the body
                block.append(inner)
            return None
        name = templates[name]['parent']
    return None


def members(templates, name):
    """The soldier templates a horde holds (HordeContain's InitialPayload and RankInfo UnitType)."""
    text = templates[name]['body'] if name in templates else ''
    found = re.findall(r'(?im)^\s*InitialPayload\s*=\s*(\w+)', text) + re.findall(r'(?i)UnitType:(\w+)', text)
    return [n for n in dict.fromkeys(found) if n.lower() in templates]


def map_ini(assets, names, life):
    """The map.ini overrides for the units `names` and the soldiers in them. Returns (units, text)."""
    templates, macros = assets.templates, defines(assets)
    units = list(dict.fromkeys(n for name in names for n in [name] + members(templates, name.lower())))
    out, count = [], 0
    for name in units:
        found = body(templates, name.lower())
        if not found:
            continue
        kind, tag, lines = found
        count += 1
        out += [f'Object {name}', f'  ReplaceModule {tag}', f'    Body = {kind} {tag}_Life']
        for line in lines:
            key, sep, value = line.partition('=')
            if sep:
                value = ' '.join(expand(split(value), macros))
                if key.strip() in SCALED:
                    value = f'{float(value.split()[0])*life:g}'
                line = f'{key.strip()} = {value}'
            out.append('      ' + line)
        out += ['    End', '  End', 'End', '']
    return count, '\n'.join(out)
