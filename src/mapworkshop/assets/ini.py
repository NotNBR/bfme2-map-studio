"""Reading the game's INI text: object templates and the blocks inside them.

The one reader the toolkit has (assets.library, mapkit.pathing,
render.catalog):

- Comments, `;` and `//` to the end of the line, are not text (strip_comments).
- A template stands with its ObjectReskin and ChildObject parents (chain); each
  body has its #include files in place where the assets can read them
  (bodies, through GameAssets.included).
- Nesting (statements): `End` closes a block. A module line opens one
  (`Draw = W3DModelDraw ModuleTag_01`; Behavior, Body, ClientUpdate,
  ClientBehavior), as do the set and state lines (LocomotorSet, ArmorSet,
  WeaponSet, ModelConditionState, AnimationState, TransitionState, Animation =
  ...; `=` is optional, as in the game), a bare word (DefaultModelConditionState,
  IdleAnimationState, ...; LONE_FIELDS excepted) and an override's AddModule,
  ReplaceModule and InheritableModule. Statements with
  arguments (ParticleSysBone bone system, a script's
  CurDrawableHideSubObject(...)) do not; BeginScript ... EndScript is skipped.
- An object's own properties (KindOf, Scale, Geometry, Shadow, ...) are its
  top-level statements (top, inherited): a module's own Scale or Geometry
  must not stand for them.
- A number is what a value starts with, as the game's reader takes it (number).
"""
from collections import namedtuple
import re

COMMENT = re.compile(r'(?:;|//)[^\n]*')
NUMBER = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'
BLOCK_KEYS = frozenset(('draw', 'behavior', 'body', 'clientupdate', 'clientbehavior', 'locomotorset', 'armorset',
                        'weaponset', 'modelconditionstate', 'animationstate', 'transitionstate', 'animation'))
MODULE_KEYS = frozenset(('draw', 'behavior', 'body', 'clientupdate', 'clientbehavior'))
EDITS = frozenset(('addmodule', 'replacemodule', 'inheritablemodule'))
# A bare word opens a block (ArmorSet, Turret, FireWeaponNugget, ...), but for
# the two fields the retail object INIs leave without a value: of their 31
# bare words, `GeometryName ;= Geom_Orig` (AngmarHallofTwilight) and StateName.
LONE_FIELDS = frozenset(('geometryname', 'statename'))
# One line: `path`, the blocks it lies in (their keys, lowercase, outermost
# first); its `key` (lowercase) and the rest, `value`; `opens`: it starts a block.
Statement = namedtuple('Statement', 'path key value opens')
_ASSIGN = re.compile(r'(\w+)\s*=\s*(.*)')
_WORD = re.compile(r'\w+')


def strip_comments(text):
    return COMMENT.sub('', text)


def words(value):
    """A value's words, a quoted one ("Bip L Finger2", a bone name) as one,
    without its quotes."""
    return [w.strip('"') for w in re.findall(r'"[^"]*"|\S+', value or '')]


def number(text, default=0.):
    """The number a value starts with, as the game's INI reader takes it:
    '177.0+' and '8.0CA' (both in the retail INI) read 177.0 and 8.0."""
    match = re.match(NUMBER, (text or '').strip())
    return float(match.group(0)) if match else default


def statements(text):
    """Each statement of INI text as a Statement, comments taken out."""
    path, script = [], False
    for raw in text.splitlines():
        line = COMMENT.sub('', raw).strip()
        if not line or line.startswith('#'):
            continue
        lower = line.lower()
        if script:
            script = not re.match(r'endscript\b', lower)
            continue
        if re.match(r'beginscript\b', lower):
            script = True
            continue
        if re.match(r'end\b', lower):
            if path:
                path.pop()
            continue
        match = _ASSIGN.match(line)
        if match:
            key, value = match.group(1).lower(), match.group(2).strip()
            opens = key in BLOCK_KEYS
        else:
            # The game's tokenizer takes `=` as a separator: `Scale 1.75` is Scale = 1.75.
            word, *rest = line.split(None, 1)
            key, value = word.lower(), rest[0].strip() if rest else ''
            opens = key in BLOCK_KEYS or key in EDITS or \
                (not value and _WORD.fullmatch(word) is not None and key not in LONE_FIELDS)
        yield Statement(tuple(path), key, value, opens)
        if opens:
            path.append(key)


def top(text):
    """{key: value} of the top-level statements, the first of each key."""
    found = {}
    for s in statements(text):
        if not s.path and s.key not in found:
            found[s.key] = s.value
    return found


def in_module(text, module):
    """{key: value} of the statements inside the modules of kind `module`
    (`Draw = W3DTreeDraw ModuleTag`: 'W3DTreeDraw'), however deep, the first
    of each key."""
    found, current, module = {}, None, module.lower()
    for s in statements(text):
        if not s.path:
            current = s.value.split()[0].lower() if s.opens and s.key in MODULE_KEYS and s.value else None
        elif current == module and s.key not in found:
            found[s.key] = s.value
    return found


def chain(templates, name):
    """The entries of template `name` and its parents, nearest first; a loop
    of parents ends it. Empty when the game does not define it."""
    out, seen, key = [], set(), (name or '').lower()
    while key and key not in seen and key in templates:
        seen.add(key)
        entry = templates[key]
        out.append(entry)
        key = entry.get('parent')
    return out


def body(source, entry):
    """One template entry's body with comments taken out and, when `source`
    can read them (GameAssets.included), its #include files in place."""
    included = getattr(source, 'included', None)
    return strip_comments(included(entry['body'], entry['file']) if included and 'file' in entry else entry['body'])


def bodies(source, name):
    """The bodies (body) of a template and its parents (chain), nearest
    first. `source` is GameAssets, anything else with `templates`, or the
    templates dict itself."""
    return [body(source, e) for e in chain(getattr(source, 'templates', source), name)]


def inherited(texts, key):
    """The first top-level value of `key` in texts (a template's bodies,
    nearest first), or None."""
    key = key.lower()
    for text in texts:
        value = top(text).get(key)
        if value is not None:
            return value
    return None
