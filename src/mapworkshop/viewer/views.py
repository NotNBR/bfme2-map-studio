"""The viewer's saved camera views, and a view as a `mw render` argument.

Views are kept per map in local/views/<map file name>.json, in the form
`mw render --views` reads: {"views": {name: spec}}, each spec the keys of a
render.camera view (an Edit view: target, distance, elevation, heading, fov;
a Photo view: eye, target, focal, roll and the photo keys it uses). The
viewer's own facts sit beside them under "viewer": {name: {"slot": 1-9 or
null, "mode": "edit" or "photo"}}. Each view's thumbnail is
local/views/<map file name>/<name>.png.
"""

import json
import re
from pathlib import Path

from mapworkshop.config import VIEWS

SLOTS = range(1, 10)
THUMBNAIL = (192, 108)


def views_path(map_path):
    return VIEWS/(Path(map_path).stem + '.json')


def _round(value, digits=1):
    value = round(float(value), digits)
    return int(value) if value == int(value) else value


def edit_spec(camera):
    """An Edit view of viewer.camera.Camera's goal."""
    g = camera.goal
    target = (g['x'], g['y'], camera.ground(g['x'], g['y']))
    return dict(target=[_round(v) for v in target], distance=_round(g['distance']),
                elevation=_round(g['elevation']), heading=_round(g['heading'] % 360), fov=_round(camera.fov))


def photo_spec(fly):
    """A Photo view of a viewer.camera.FlyCamera."""
    target = fly.eye + fly.forward()*fly.focus
    spec = dict(eye=[_round(v) for v in fly.goal], target=[_round(v) for v in target], focal=_round(fly.focal))
    if abs(fly.roll) > 0.05:
        spec['roll'] = _round(fly.roll)
    if fly.aperture:
        spec['aperture'] = _round(fly.aperture)
        spec['focus'] = _round(fly.focus)
    if abs(fly.ev) > 1e-6:
        spec['ev'] = _round(fly.ev, 2)
    return spec


def render_words(spec):
    """A spec as `mw render --view` key=value words."""
    out = []
    for key, value in spec.items():
        if isinstance(value, (list, tuple)):
            value = ','.join(str(v) for v in value)
        out.append(f'{key}={value}')
    return ' '.join(out)


def render_command(project_id, name, spec):
    """The `mw render` command that renders a view."""
    slug = re.sub(r'[^\w-]+', '-', name.strip().lower()).strip('-') or 'view'
    return (f'mw render --map {project_id} --out local/renders/{project_id}-views '
            f'--view {slug} {render_words(spec)}')


class Views:
    """The saved views of one map, loaded from and written to its file at once."""

    def __init__(self, map_path):
        self.path = views_path(map_path)
        self.thumbnails = self.path.with_suffix('')
        self.items = []               # dict(name, slot, mode, spec), in the file's order
        self.load()

    def load(self):
        self.items = []
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        meta = data.get('viewer', {})
        for name, spec in data.get('views', {}).items():
            facts = meta.get(name, {})
            self.items.append(dict(name=name, slot=facts.get('slot'), mode=facts.get('mode', 'edit'), spec=spec))

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = dict(views={v['name']: v['spec'] for v in self.items},
                    viewer={v['name']: dict(slot=v['slot'], mode=v['mode']) for v in self.items})
        self.path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    def by_name(self, name):
        return next((v for v in self.items if v['name'] == name), None)

    def by_slot(self, slot):
        return next((v for v in self.items if v['slot'] == slot), None)

    def free_slot(self):
        used = {v['slot'] for v in self.items}
        return next((s for s in SLOTS if s not in used), None)

    def new_name(self):
        n = len(self.items)+1
        while self.by_name(f'View {n}'):
            n += 1
        return f'View {n}'

    def save(self, mode, spec, slot=None, thumbnail=None):
        """Save a view in `slot` (replacing the view there), or as a new view in
        the first free slot. Returns its entry."""
        old = self.by_slot(slot) if slot is not None else None
        if old is not None:
            old.update(mode=mode, spec=spec)
            entry = old
        else:
            entry = dict(name=self.new_name(), slot=slot if slot is not None else self.free_slot(), mode=mode, spec=spec)
            self.items.append(entry)
        self.write()
        if thumbnail is not None:
            self.thumbnails.mkdir(parents=True, exist_ok=True)
            thumbnail.save(self.thumbnail_path(entry['name']))
        return entry

    def thumbnail_path(self, name):
        return self.thumbnails/(re.sub(r'[\\/:*?"<>|]+', '_', name) + '.png')

    def rename(self, name, new):
        new = new.strip()
        entry = self.by_name(name)
        if entry is None or not new or new == name:
            return False
        if self.by_name(new):
            raise ValueError(f'a view is already called {new!r}')
        old_thumb = self.thumbnail_path(name)
        entry['name'] = new
        self.write()
        if old_thumb.exists():
            old_thumb.replace(self.thumbnail_path(new))
        return True

    def delete(self, name):
        entry = self.by_name(name)
        if entry is None:
            return False
        self.items.remove(entry)
        self.write()
        self.thumbnail_path(name).unlink(missing_ok=True)
        return True
