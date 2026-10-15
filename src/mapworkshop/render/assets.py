"""Read-only access to installed BFME2 assets: archives, INIs, textures and models.

Lookup follows the game's override order: loose files in the prepared mod
directory (local/game) win over archives, and `_patch*.big` archives win over base archives.
Nothing is written back to the game or the mod.
"""

import io
import copy
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from mapworkshop.config import GAME_DATA, game_dir
from mapworkshop.formats.big import BigArchive

TEXTURE_EXTENSIONS = ('.dds', '.tga', '.jpg')
# An object template: its kind, name, parent (ChildObject, ObjectReskin) and
# body, up to the next one. The game also reads indented definitions.
TEMPLATE = re.compile(r'(?ms)^[ \t]*(Object|ObjectReskin|ChildObject)[ \t]+([^\s=]+)(?:[ \t]+([^\s;]+))?[^\n]*\n(.*?)'
                      r'(?=^[ \t]*(?:Object|ObjectReskin|ChildObject)[ \t]+[^\s=]|\Z)')


def _archive_order(path):
    # Patch archives are applied after the base archives.
    name = path.name.lower()
    return (name.startswith('_patch'), name)


class GameAssets:
    def __init__(self, game=None, mod=None):
        """`game`: the BFME2 folder (default: the configured one); `mod`: loose
        files that override the archives (default: local/game, from `mw setup`)."""
        game = game or game_dir()
        if game is None:
            raise RuntimeError('BFME2 not found: run `mw setup` (or `mw config game <folder>`)')
        self.game = Path(game)
        self.mod = Path(mod or GAME_DATA)
        self.entries = {}
        self.basenames = {}
        # Per-base-index cache: map scopes share it without retaining a new
        # assets instance for every map switch in a class-level LRU.
        self.image = lru_cache(maxsize=512)(self._image)
        for path in sorted(self.game.glob('*.big'), key=_archive_order):
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

    def template_model(self, template):
        """Draw information for a template's default state, or None.

        Returns dict(model, scale, texture, fuzziness, shadow, tree, kinds,
        tainted). W3DTreeDraw's TextureName replaces the model's own texture,
        as the tree buffer does; `kinds` is the template's KindOf set and
        `tainted` W3DTreeDraw's TaintedTree (no sway).
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
                for match in re.finditer(r'(?im)^\s*(?:Model|ModelName)\s*=\s*([\w.]+)', body):
                    if 'model' not in found and match.group(1).lower() != 'none':
                        found['model'] = match.group(1).lower()
                        # A model-condition texture swap (Texture = old new).
                        swap = re.search(r'(?im)^\s*Texture\s*=\s*[\w.]+\s+([\w.]+)', body[match.end():])
                        if swap and 'texture' not in found:
                            found['texture'] = swap.group(1)
            name = entry['parent']
        if 'model' not in found:
            return None
        return dict(model=found['model'], scale=found.get('scale', 1.0), texture=found.get('texture'),
                    fuzziness=found.get('fuzziness', 0.0), shadow=found.get('shadow', 'SHADOW_NONE'),
                    tree=found.get('tree', False), kinds=found.get('kinds', set()),
                    tainted=found.get('tainted', False), prop=found.get('prop', False))

    def model_key(self, model):
        stem = model.lower().rsplit('.', 1)[0] if model.lower().endswith('.w3d') else model.lower()
        for key in self.basenames.get(stem, []):
            if key.endswith('.w3d'):
                return key
        return None
