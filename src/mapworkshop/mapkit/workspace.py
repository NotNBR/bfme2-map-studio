"""Workspaces for hand edits of a map file: `mw workspace --help`.

Check out a .map into local/workspaces/<name>, apply recipes, checkpoint,
diff and hand it to WorldBuilder; every step records file hashes.
"""

from mapworkshop.config import LOCAL, game_dir
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
import sys
import uuid

import numpy as np
from PIL import Image, ImageDraw

from mapworkshop.mapkit.author import apply_recipe
from mapworkshop.formats.map import Map, differences, sha

WORKSPACES = LOCAL/'workspaces'


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def json_write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def workspace(name):
    if not re.fullmatch('[a-z][a-z0-9_-]{0,47}', name):
        raise ValueError('Workspace name must be lowercase letters, digits, underscores or hyphens')
    path = WORKSPACES / name
    if path.is_symlink() or (path.exists() and path.resolve().parent != WORKSPACES.resolve()):
        raise ValueError('Workspace must stay within local/workspaces')
    return path


def working_file(name):
    return workspace(name) / 'working' / name / (name + '.map')


def checkpoint(name, note):
    root, source = workspace(name), working_file(name)
    data = source.read_bytes()
    report = Map(data).report()
    target = root / 'checkpoints' / (sha(data)[:16] + '-' + uuid.uuid4().hex[:12])
    target.mkdir(parents=True)
    destination = target / (name + '.map')
    if destination.exists() and destination.read_bytes() != data:
        raise ValueError('Checkpoint collision')
    destination.write_bytes(data)
    # Include map.ini and other native sidecars in every snapshot.
    sidecars = {}
    for sidecar in source.parent.iterdir():
        if sidecar.is_file() and sidecar != source:
            shutil.copy2(sidecar, target / sidecar.name)
            sidecars[sidecar.name] = sha(sidecar.read_bytes())
    json_write(target / 'report.json', dict(time=timestamp(), note=note, source=str(source), report=report, sidecars=sidecars))
    return str(target)


def preview(path, output):
    m = Map(path.read_bytes())
    t, b = m.heightmap(), m.blend()
    border = t['border']
    z = t['elevations'].astype(float) * 0.0390625
    dy, dx = np.gradient(z, 10)
    shade = np.clip((1 - dx * 0.55 - dy * 0.35) / np.sqrt(1 + dx * dx + dy * dy), 0.2, 1)
    rgb = np.zeros(z.shape + (3,))
    for texture in b['textures']:
        name = texture['name'].lower()
        color = (95, 122, 70)
        for keyword, candidate in [('dirt', (146, 118, 80)), ('rock', (130, 130, 118)), ('cliff', (145, 143, 128)), ('sand', (175, 154, 106)), ('snow', (222, 230, 230)), ('water', (77, 135, 165)), ('road', (164, 146, 114))]:
            if keyword in name:
                color = candidate
        mask = ((b['arrays']['tiles'] >= texture['tile_start']) & (b['arrays']['tiles'] < texture['tile_start'] + texture['tile_count']))
        rgb[mask] = color
    rgb *= (0.40 + 0.60 * shade[:, :, None])
    blocked = b['arrays']['impassable'].astype(bool)
    rgb[blocked] = rgb[blocked] * 0.6 + np.array([150, 45, 38]) * 0.4
    terrain = Image.fromarray(np.flipud(rgb[border:t['height']-border, border:t['width']-border].astype('uint8')))
    scale = min(1100 / terrain.width, 1000 / terrain.height)
    terrain = terrain.resize((round(terrain.width * scale), round(terrain.height * scale)))
    image = Image.new('RGB', (terrain.width + 48, terrain.height + 100), '#17221e')
    image.paste(terrain, (24, 65))
    draw = ImageDraw.Draw(image)
    draw.text((24, 15), path.stem + ' | authoring diagnostic', fill='#edf1de')
    draw.text((24, 35), 'Height shading + texture categories; red = painted impassability. Not an in-game render.', fill='#b6c6ba')
    extent_y = (t['height'] - 2 * border) * 10
    for obj in m.objects():
        x = 24 + obj['x'] / 10 * scale
        y = 65 + (extent_y - obj['y']) / 10 * scale
        if not (24 <= x < 24 + terrain.width and 65 <= y < 65 + terrain.height):
            continue
        template = obj['template'].lower()
        if 'tree' in template:
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill='#183f23')
        elif 'waypoint' in template:
            label = next((v for k, _, v in obj['properties'] if k == 'waypointName'), '')
            if re.match(r'Player_\d+_Start$', label):
                draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill='#ffdb64', outline='#000000')
                draw.text((x + 8, y - 4), label, fill='#ffffff', stroke_width=1, stroke_fill='#000000')
        elif 'building' in template or 'ruin' in template:
            draw.rectangle((x - 2, y - 2, x + 2, y + 2), fill='#e3d3ac')
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return dict(preview=str(output), interpretation='Diagnostic only; water geometry and actual art are not rendered')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'catalog'):
        s = sub.add_parser(name)
        s.add_argument('map', type=Path)
        s.add_argument('--out', type=Path)
    s = sub.add_parser('checkout'); s.add_argument('source', type=Path); s.add_argument('name')
    s = sub.add_parser('apply'); s.add_argument('name'); s.add_argument('recipe', type=Path)
    s.add_argument('--expect-sha', required=True, help='Current on-disk file SHA256 from status; rejects stale edits')
    s = sub.add_parser('checkpoint'); s.add_argument('name'); s.add_argument('--note', required=True)
    for name in ('status', 'handoff'):
        s = sub.add_parser(name); s.add_argument('name')
    s = sub.add_parser('preview'); s.add_argument('map', type=Path); s.add_argument('output', type=Path)
    s = sub.add_parser('diff'); s.add_argument('before', type=Path); s.add_argument('after', type=Path)
    s = sub.add_parser('plan-size'); s.add_argument('map', type=Path); s.add_argument('--area-factor', type=float, default=3)
    args = p.parse_args(argv)
    if args.command in ('inspect', 'catalog'):
        m = Map(args.map.read_bytes())
        result = m.report()
        if args.command == 'catalog':
            result = dict(templates=result['templates'], textures=result['textures'],
                          landmarks=[{k: v for k, v in o.items() if k != 'chunk'} for o in m.objects() if 'Waypoint' in o['template']])
        if args.out:
            json_write(args.out, result)
    elif args.command == 'checkout':
        root, target = workspace(args.name), working_file(args.name)
        source = args.source.resolve()
        data = source.read_bytes()
        report = Map(data).report()
        if root.exists():
            raise ValueError('Workspace exists; choose a new name or continue with status')
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        for sidecar in source.parent.iterdir():
            if sidecar.is_file() and sidecar.suffix.lower() != '.map':
                new_name = sidecar.name.replace(source.stem, args.name)
                shutil.copy2(sidecar, target.parent / new_name)
        json_write(root / 'workspace.json', dict(schema=1, name=args.name, source=str(source), source_sha256=sha(data), created=timestamp()))
        base = checkpoint(args.name, 'Untouched source copy')
        result = dict(working_map=str(target), checkpoint=base, source_preserved=True, dimensions=report['dimensions'])
    elif args.command == 'apply':
        target, root = working_file(args.name), workspace(args.name)
        source = target.read_bytes()
        if sha(source) != args.expect_sha:
            raise ValueError('Map changed since inspection; inspect the latest saved editor document first')
        recipe_bytes = args.recipe.read_bytes()
        recipe = json.loads(recipe_bytes)
        history = root / 'transactions'
        history.mkdir(exist_ok=True)
        for record in history.glob('*/report.json'):
            if json.loads(record.read_text())['recipe_sha256'] == sha(recipe_bytes):
                raise ValueError('Recipe already applied to this workspace; branch a checkpoint for a replay')
        output, diff = apply_recipe(source, recipe)
        checkpoint(args.name, 'Before recipe ' + recipe['id'])
        transaction = history / uuid.uuid4().hex
        transaction.mkdir()
        (transaction / 'recipe.json').write_bytes(recipe_bytes)
        (transaction / 'before.map').write_bytes(source)
        (transaction / 'after.map').write_bytes(output)
        result = dict(time=timestamp(), recipe_sha256=sha(recipe_bytes), diff=diff, file_sha256=sha(output))
        temp = target.with_suffix('.pending')
        temp.write_bytes(output)
        if sha(target.read_bytes()) != args.expect_sha:
            raise ValueError('Concurrent editor save detected; candidate preserved in transaction directory')
        temp.replace(target)
        json_write(transaction / 'report.json', result)
        checkpoint(args.name, 'After recipe ' + recipe['id'])
        preview(target, root / 'preview.png')
    elif args.command == 'checkpoint':
        result = dict(checkpoint=checkpoint(args.name, args.note))
    elif args.command in ('status', 'handoff'):
        target, root = working_file(args.name), workspace(args.name)
        data = target.read_bytes()
        result = dict(working_map=str(target), file_sha256=sha(data), map=Map(data).report(),
                      editor_verified=False, game_verified=False)
        if args.command == 'handoff':
            result.update(editor=str((game_dir() or Path('<BFME2 folder>'))/'Worldbuilder.exe'),
                          instructions=['Save and close any current map before external edits.',
                                        'Open working_map in WorldBuilder; inspect terrain, starts and routes.',
                                        'Save in WorldBuilder, then checkpoint and diff its saved file.',
                                        'Run a native match; verify rendering, crossings, reinforcement routes and frame rate.'])
            json_write(root / 'handoff.json', result)
    elif args.command == 'preview':
        result = preview(args.map, args.output)
    elif args.command == 'diff':
        before, after = Map(args.before.read_bytes()), Map(args.after.read_bytes())
        result = differences(before, after)
        from mapworkshop.mapkit.mapdiff import compare, lines
        result['changes'] = lines(compare(before, after))
    elif args.command == 'plan-size':
        if not math.isfinite(args.area_factor) or args.area_factor <= 0:
            raise ValueError('Area factor must be positive and finite')
        d = Map(args.map.read_bytes()).report()['dimensions']
        width, height = [round(v * math.sqrt(args.area_factor)) for v in d['playable_tiles']]
        result = dict(base=d, proposed_playable_tiles=[width, height], actual_area_factor=width * height / d['playable_area_tiles'],
                      applied=False, editor_and_engine_support_verified=False,
                      note='Sizing plan only. Resizing requires coordinated terrain, blend, object, water, camera and start data updates.')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps(dict(error=str(error))), file=sys.stderr)
        sys.exit(1)
