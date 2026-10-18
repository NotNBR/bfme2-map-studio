"""Read-only access to installed BFME2/ROTWK assets: INIs, textures and models.

Lookup follows the game's override order: loose files in the prepared mod
directory win over archives; ROTWK overlays BFME2, with patches over base archives.
Nothing is written back to the game or the mod.
"""

import io
import copy
import posixpath
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from mapworkshop.config import GAME_DATA, archive_paths, game_dir
from mapworkshop.formats.big import BigArchive

TEXTURE_EXTENSIONS = ('.dds', '.tga', '.jpg')
# An object template: its kind, name, parent (ChildObject, ObjectReskin) and
# body, up to the next one. The game also reads indented definitions.
TEMPLATE = re.compile(r'(?ms)^[ \t]*(Object|ObjectReskin|ChildObject)[ \t]+([^\s=]+)(?:[ \t]+([^\s;]+))?[^\n]*\n(.*?)'
                      r'(?=^[ \t]*(?:Object|ObjectReskin|ChildObject)[ \t]+[^\s=]|\Z)')
# A draw module's WorldBuilder-only state: the editor shows its model, the game never does.
WORLD_BUILDER = re.compile(r'(?ims)^\s*ModelConditionState\s*=\s*WORLD_BUILDER\b.*?^\s*End\b')
# Templates whose editor model stands in for what the game makes of them:
# a horde's units, a castle centre's castle.
STAND_INS = {'HORDE', 'CASTLE_CENTER', 'BASE_FOUNDATION'}
COMMENT = re.compile(r'(?:;|//)[^\n]*')


class GameAssets:
    def __init__(self, game=None, mod=None, expansion=None):
        """`game`: the BFME2 folder (default: the configured one); `mod`: loose
        files that override the archives (default: this profile's extracted data).
        `expansion`: optional ROTWK folder over an explicit BFME2 `game` folder.
        With no folders, use the configured profile's combined asset library."""
        paths = archive_paths(game, expansion)
        game = expansion or game or game_dir()
        if game is None:
            raise RuntimeError('BFME2 not found: run `mw setup` (or `mw config game <folder>`)')
        self.game = Path(game)
        self.mod = Path(mod or GAME_DATA)
        self.entries = {}
        self.basenames = {}
        # Per-base-index cache: map scopes share it without retaining a new
        # assets instance for every map switch in a class-level LRU.
        self.image = lru_cache(maxsize=512)(self._image)
        self.archive_paths = paths
        for path in paths:
            try:
                archive = BigArchive(path)
            except ValueError:
                continue
            for key in archive.entries:
                self.entries[key.lower()] = archive
        for key in self.entries:
            stem = key.rsplit('/', 1)[-1]
            self.basenames.setdefault(stem.rsplit('.', 1)[0], []).append(key)

    _shared = None
    map_ini = ''          # the map's map.ini text, in assets scoped to a map (for_map)

    @classmethod
    def shared(cls):
        """One instance of the configured game's assets for the whole process,
        so that a build indexes the archives and parses the INIs once. Treat
        it as read-only; for a map's own templates use for_map, which copies."""
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    # Files ------------------------------------------------------------------
    def read(self, key):
        key = key.replace('\\', '/').lower()
        loose = self.mod/key
        if loose.is_file():
            return loose.read_bytes()
        archive = self.entries.get(key)
        if archive is None:
            raise FileNotFoundError(key)
        return archive.read_bytes(key)

    def exists(self, key):
        key = key.replace('\\', '/').lower()
        return (self.mod/key).is_file() or key in self.entries

    def ini_text(self, relative):
        """Concatenated INI text for a file or a directory below data/ini."""
        base = self.mod/'data/ini'/relative
        if base.is_dir():
            return '\n'.join(p.read_text(encoding='cp1252', errors='replace') for p in sorted(base.rglob('*.ini')))
        if base.is_file():
            return base.read_text(encoding='cp1252', errors='replace')
        return self.read('data/ini/'+relative).decode('cp1252', errors='replace')

    # Textures ---------------------------------------------------------------
    def texture_key(self, name):
        """Resolve a texture name as the game does, including compiled textures."""
        stem = Path(name.replace('\\', '/')).name.lower().rsplit('.', 1)[0]
        candidates = self.basenames.get(stem, [])
        preferred = [k for k in candidates if k.endswith(TEXTURE_EXTENSIONS)]
        if not preferred:
            return None
        # Loose terrain TGAs, then compiled textures, then anything else.
        rank = lambda k: (0 if k.startswith('art/terrain/') else 1 if '/compiledtextures/' in k else 2,
                          TEXTURE_EXTENSIONS.index(k[-4:]))
        return sorted(preferred, key=rank)[0]

    def _image(self, name):
        """RGBA uint8 array, top row first, or None when the texture is absent."""
        key = self.texture_key(name)
        if key is None:
            return None
        with Image.open(io.BytesIO(self.read(key))) as im:
            return np.asarray(im.convert('RGBA')).copy()

    def for_map(self, text):
        """An isolated template overlay over the shared, read-only game index."""
        base = getattr(self, '_base', self)
        scoped = copy.copy(base)
        scoped._base = base
        scoped._templates = dict(base.templates)
        scoped._models = {}
        scoped._units = {}
        scoped.map_ini = text
        scoped.add_map_templates(text)
        return scoped

    # Terrain ----------------------------------------------------------------
    @property
    def terrain_textures(self):
        if not hasattr(self, '_terrain'):
            text = self.ini_text('terrain.ini')
            self._terrain = {n.lower(): f for n, f in
                             re.findall(r'(?ms)^Terrain\s+(\w+)\s.*?Texture\s*=\s*(\S+)', text)}
        return self._terrain

    # Object templates -------------------------------------------------------
    @property
    def templates(self):
        """Every object template by lowercase name: kind, parent, body, name,
        and where it is defined (`file` below data/ini, `line`)."""
        if not hasattr(self, '_templates'):
            found = {}
            ini = self.mod/'data/ini'
            for path in sorted((ini/'object').rglob('*.ini')):
                text = path.read_text(encoding='cp1252', errors='replace')
                file, line, counted = path.relative_to(ini).as_posix(), 1, 0
                # Yield between template matches instead of holding the GIL for
                # one regex over the entire game's object INIs during a load.
                for match in TEMPLATE.finditer(text):
                    kind, name, parent, body = match.groups()
                    line += text.count('\n', counted, match.start())
                    counted = match.start()
                    found[name.lower()] = dict(kind=kind, parent=parent.lower() if kind != 'Object' and parent else None,
                                               body=body, name=name, file=file, line=line)
            self._templates = found
        return self._templates

    def add_map_templates(self, text):
        """Object definitions from a map's map.ini, which the game loads on
        top of the INI templates for that map."""
        if self is GameAssets._shared:
            raise RuntimeError('The shared assets are read-only: add map templates to a copy (for_map)')
        for kind, name, parent, body in TEMPLATE.findall(text):
            self.templates[name.lower()] = dict(kind=kind, parent=parent.lower() if kind != 'Object' and parent else None,
                                                body=body, name=name, file='map.ini', line=None)
        self._models = {}
        self._units = {}

    def template_model(self, template):
        """Draw information for a template's default state, or None.

        Returns dict(model, scale, texture, fuzziness, shadow, tree, kinds,
        tainted, editor, unit). W3DTreeDraw's TextureName replaces the model's own
        texture, as the tree buffer does; `kinds` is the template's KindOf set
        and `tainted` W3DTreeDraw's TaintedTree (no sway). A model of the
        WORLD_BUILDER state is taken only when the template has no other:
        `editor` is then True for an editor marker the game does not draw at
        all (FarmTemplate, the cinematic particle proxies), False for a horde
        or castle centre, whose units or castle the game shows in its place.
        `unit`: EditorSorting UNIT (faction units, heroes, hordes, creeps).
        """
        cache = self.__dict__.setdefault('_models', {})
        if template.lower() not in cache:
            cache[template.lower()] = self._template_model(template)
        return cache[template.lower()]

    def _template_model(self, template):
        seen = set()
        name = template.lower()
        found = {}
        while name and name not in seen:
            seen.add(name)
            entry = self.templates.get(name)
            if entry is None:
                break
            body = entry['body']
            match = re.search(r'(?im)^\s*KindOf\s*=\s*([^;\n]*)', body)
            if match and 'kinds' not in found:
                found['kinds'] = {k.lstrip('+').upper() for k in match.group(1).split() if not k.startswith('-')}
            for key, pattern in [('scale', r'(?im)^\s*Scale\s*=\s*([\d.]+)'),
                                 ('fuzziness', r'(?im)^\s*InstanceScaleFuzziness\s*=\s*([\d.]+)')]:
                match = re.search(pattern, body)
                if match and key not in found:
                    found[key] = float(match.group(1))
            if re.search(r'(?im)^\s*Draw\s*=\s*W3DPropDraw\b', body):
                found.setdefault('prop', True)
            match = re.search(r'(?im)^\s*Shadow\s*=\s*(\w+)', body)
            if match and 'shadow' not in found:
                found['shadow'] = match.group(1).upper()
            match = re.search(r'(?im)^\s*EditorSorting\s*=\s*(\w+)', body)
            if match and 'sorting' not in found:
                found['sorting'] = match.group(1).upper()
            if 'model' not in found:
                tree = re.search(r'(?ims)^\s*Draw\s*=\s*W3DTreeDraw.*?^\s*End', body)
                if tree:
                    model = re.search(r'(?im)^\s*ModelName\s*=\s*([\w.]+)', tree.group(0))
                    texture = re.search(r'(?im)^\s*TextureName\s*=\s*([\w.]+)', tree.group(0))
                    if model:
                        found['model'] = model.group(1).lower()
                        found['texture'] = texture.group(1) if texture else None
                        found['tree'] = True
                        found['tainted'] = bool(re.search(r'(?im)^\s*TaintedTree\s*=\s*Yes', tree.group(0)))
                game = WORLD_BUILDER.sub('', body)
                for match in re.finditer(r'(?im)^\s*(?:Model|ModelName)\s*=\s*([\w.]+)', game):
                    if 'model' not in found and match.group(1).lower() != 'none':
                        found['model'] = match.group(1).lower()
                        # A model-condition texture swap (Texture = old new).
                        swap = re.search(r'(?im)^\s*Texture\s*=\s*[\w.]+\s+([\w.]+)', game[match.end():])
                        if swap and 'texture' not in found:
                            found['texture'] = swap.group(1)
                for state in WORLD_BUILDER.findall(body):
                    match = re.search(r'(?im)^\s*Model\s*=\s*(?!none\b)([\w.]+)', state)
                    if match and 'editor_model' not in found:
                        found['editor_model'] = match.group(1).lower()
            name = entry['parent']
        editor = 'model' not in found and 'editor_model' in found
        if editor:
            found['model'] = found['editor_model']
        if 'model' not in found:
            return None
        return dict(model=found['model'], scale=found.get('scale', 1.0), texture=found.get('texture'),
                    fuzziness=found.get('fuzziness', 0.0), shadow=found.get('shadow', 'SHADOW_NONE'),
                    tree=found.get('tree', False), kinds=found.get('kinds', set()),
                    tainted=found.get('tainted', False), prop=found.get('prop', False),
                    editor=editor and not found.get('kinds', set()) & STAND_INS,
                    unit=found.get('sorting') == 'UNIT')

    def _bodies(self, template):
        """The template's body, then its parents', with their #include files
        in place and comments removed."""
        seen, name, bodies = set(), template.lower(), []
        while name and name not in seen and name in self.templates:
            seen.add(name)
            entry = self.templates[name]
            bodies.append(COMMENT.sub('', self._included(entry['body'], entry['file'])))
            name = entry['parent']
        return bodies

    def _included(self, text, file, depth=0):
        """INI text with each #include "path" (relative to `file`, below
        data/ini) replaced by that file's text."""
        if depth > 4 or '#include' not in text.lower():
            return text
        includes = self.__dict__.setdefault('_includes', {})

        def include(match):
            path = posixpath.normpath(posixpath.join(posixpath.dirname(file), match.group(1).replace('\\', '/')))
            if path not in includes:
                try:
                    includes[path] = self._included(self.ini_text(path), path, depth+1)
                except (FileNotFoundError, OSError):
                    includes[path] = ''
            return includes[path]
        return re.sub(r'(?im)^[ \t]*#include\s+"([^"]+)"', include, text)

    @property
    def constants(self):
        """The INIs' #define values by name (gamedata.ini holds the horde sizes)."""
        if not hasattr(self, '_constants'):
            from mapworkshop.formats.big import definitions
            try:
                self._constants = definitions(self.ini_text('gamedata.ini'))
            except FileNotFoundError:
                self._constants = {}
        return self._constants

    def unit_animation(self, template):
        """The animation file a unit stands in at the start of a game: the
        first AnimationName of its IdleAnimationState, else its
        DefaultModelConditionState's animation; None when it has none."""
        return self._unit_cached('animation', template, self._unit_animation)

    def _unit_animation(self, template):
        for body in self._bodies(template):
            body = WORLD_BUILDER.sub('', body)
            names = []
            idle = re.search(r'(?im)^\s*IdleAnimationState\b', body)
            if idle:
                names += re.findall(r'(?im)^\s*AnimationName\s*=\s*([\w.]+)', body[idle.end():])[:1]
            default = re.search(r'(?ims)^\s*DefaultModelConditionState\b(.*?)^\s*End\b', body)
            if default:
                names += re.findall(r'(?im)^\s*(?:AnimationName|IdleAnimation|Animation)\s*=\s*([\w.]+)', default.group(1))
            for name in names:
                # 'Skeleton.Animation' names the file of the animation.
                animation = name.rsplit('.', 1)[-1].lower()
                if self.model_key(animation):
                    return animation
        return None

    def hidden_subobjects(self, template):
        """The sub-objects an object hides as it is created, lower case:
        - a unit's: the ObjectHideSubObject[Permanently](self, "Name", true)
          calls of the OnCreated function that its AILuaEventsList names in
          data/scripts/scriptevents.xml (an EventList without one takes its
          Inherit's), read from data/scripts/scripts.lua. The upgrades'
          meshes are among them (Forged_Blade, FireArowTip).
        - the CurDrawableHideSubObject[Permanently]("Name") calls of its draw
          module's IdleAnimationState BeginScript, when the script has no
          condition (CINE_DwarvenCatapult hides its crew so)."""
        def hidden(name):
            found = set()
            for body in self._bodies(name):
                for state in re.findall(r'(?ims)^\s*IdleAnimationState\b(.*?)^\s*End\b', body):
                    for script in re.findall(r'(?is)\bBeginScript\b(.*?)\bEndScript\b', state):
                        if not re.search(r'(?i)\bif\b', script):
                            found.update(n.lower() for n in re.findall(
                                r'CurDrawableHideSubObject(?:Permanently)?\(\s*"([^"]+)"\s*\)', script))
                if found:
                    break
            for body in self._bodies(name):
                events = re.search(r'(?im)^\s*AILuaEventsList\s*=\s*(\w+)', body)
                if events:
                    break
            else:
                return frozenset(found)
            lists, hides = self._lua_created()
            seen, events = set(), events.group(1).lower()
            while events in lists and events not in seen:
                seen.add(events)
                inherit, created = lists[events]
                if created:
                    return frozenset(found | hides.get(created, frozenset()))
                events = inherit
            return frozenset(found)
        return self._unit_cached('hidden', template, hidden)

    def _lua_created(self):
        """({event list: (its Inherit, its OnCreated function)}, {function:
        the sub-objects it hides}), all lower case."""
        if '_lua' not in self.__dict__:
            lists, hides = {}, {}
            try:
                xml = re.sub(r'(?s)<!--.*?-->', '', self.read('data/scripts/scriptevents.xml').decode('latin-1'))
                lua = re.sub(r'--[^\n]*', '', self.read('data/scripts/scripts.lua').decode('latin-1'))
            except (FileNotFoundError, KeyError, OSError):
                xml = lua = ''
            for head, body in re.findall(r'(?is)<EventList\b([^>]*)>(.*?)</EventList>', xml):
                name = re.search(r'(?i)\bName\s*=\s*"([^"]+)"', head)
                inherit = re.search(r'(?i)\bInherit\s*=\s*"([^"]+)"', head)
                created = re.search(r'(?i)EventName\s*=\s*"OnCreated"\s+ScriptFunctionName\s*=\s*"([^"]+)"', body)
                if name:
                    lists[name.group(1).lower()] = (inherit.group(1).lower() if inherit else None,
                                                    created.group(1).lower() if created else None)
            for function, body in re.findall(r'(?ims)^function\s+(\w+)\s*\([^)]*\)(.*?)^end\b', lua):
                hides[function.lower()] = frozenset(n.lower() for n in re.findall(
                    r'ObjectHideSubObject(?:Permanently)?\(\s*self\s*,\s*"([^"]+)"\s*,\s*true\s*\)', body))
            self._lua = lists, hides
        return self._lua

    def horde_members(self, template):
        """The members a horde fills itself with at the start of a game,
        [(template, x, y)] in the horde's frame (x forward, map units): its
        HordeContain's InitialPayload, each member at the next RankInfo
        Position for its UnitType, rank by rank. [] for anything else."""
        return self._unit_cached('members', template, self._horde_members)

    def build_variations(self, template):
        """BuildVariations: the templates the game creates one of in its
        place (RohanPeasant: RohanPeasant1, 3 or 4); [] for none."""
        def variations(name):
            for body in self._bodies(name):
                match = re.search(r'(?im)^\s*BuildVariations\s*=([^\n]*)', body)
                if match:
                    return [v for v in match.group(1).split() if v.lower() in self.templates]
            return []
        return self._unit_cached('variations', template, variations)

    def _unit_cached(self, kind, template, compute):
        cache = self.__dict__.setdefault('_units', {})
        key = (kind, template.lower())
        if key not in cache:
            cache[key] = compute(template)
        return cache[key]

    def _horde_members(self, template):
        for body in self._bodies(template):
            contain = re.search(r'(?ims)^\s*Behavior\s*=\s*\w*HordeContain\b(.*?)(?=^\s*(?:Behavior|Draw|Body)\s*=|\Z)', body)
            if contain:
                break
        else:
            return []
        from mapworkshop.formats.big import number
        ranks = []
        for line in re.findall(r'(?im)^\s*RankInfo\s*=([^\n]*)', contain.group(1)):
            rank = re.search(r'(?i)RankNumber:\s*(\d+)', line)
            unit = re.search(r'(?i)UnitType:\s*(\S+)', line)
            for x, y in re.findall(r'(?i)Position:\s*X:\s*(-?[\d.]+)\s+Y:\s*(-?[\d.]+)', line):
                ranks.append((int(rank.group(1)) if rank else 0, unit.group(1) if unit else '', float(x), float(y)))
        ranks.sort(key=lambda r: r[0])                      # stable: positions keep their order in a rank
        payload = [(name, number(count, self.constants))
                   for name, count in re.findall(r'(?im)^\s*InitialPayload\s*=\s*(\S+)\s+(\S+)', contain.group(1))]
        if not payload:
            payload = [(unit, None) for unit in dict.fromkeys(r[1] for r in ranks)]
        free, members = list(ranks), []
        for name, count in payload:
            fitting = [r for r in free if r[1].lower() == name.lower()] or free
            for r in fitting[:len(fitting) if count is None else int(count)]:
                free.remove(r)
                members.append((name, r[2], r[3]))
        return members

    def model_key(self, model):
        stem = model.lower().rsplit('.', 1)[0] if model.lower().endswith('.w3d') else model.lower()
        for key in self.basenames.get(stem, []):
            if key.endswith('.w3d'):
                return key
        return None
