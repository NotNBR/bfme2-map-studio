"""Unlimited vegetation: move overflow trees and shrubs out of BFME2's buffers.

BFME2 draws optimized vegetation from fixed buffers. W3DTreeBuffer holds 1,200
trees (an inline array of 0xE8-byte records; W3DTreeDraw adds each tree object
on its first draw and silently drops it when the array is full) and the shrub
buffer takes 2,000 SHRUB templates, which GameLogic hands to TerrainLogic at
map load without creating objects. Anything past those limits is not drawn.

The buffers are inline arrays with fields after them, so they cannot be
enlarged safely in the binary. Instead, map objects past a margin below each
limit are renamed to map-local `GW_` templates, written to the map's map.ini,
that draw the same model (and the same texture, via a model-condition texture
swap where W3DTreeDraw's TextureName differs) through W3DModelDraw, which has
no buffer. They keep SHRUBBERY so they do not block movement, and drop TREE,
SHRUB and the optimized kinds, so nothing routes them back into a buffer.

Status: the first native run with Greywater's 5,606 overflow
objects crashed during map load (logic frame 0, an empty "Game crash" dialog,
no crash report). Not yet diagnosed.
"""

from mapworkshop.assets import ini

TREE_BUFFER = 1200
SHRUB_BUFFER = 2000
PREFIX = 'GW_'
_DROP_KINDS = {'TREE', 'SHRUB', 'OPTIMIZED_TREE', 'OPTIMIZED_PROP', 'CLUB', 'SELECTABLE'}


def describe(templates, name, model_textures=None):
    """Vegetation info for a template, following ObjectReskin/ChildObject
    parents: dict(buffer='tree'|'shrub', model, texture, model_texture,
    fuzziness, kinds) or None when it is not buffered vegetation. `templates`
    is GameAssets (its bodies with their #include files) or its templates."""
    info = {}
    for body in ini.bodies(templates, name):
        tree = ini.in_module(body, 'W3DTreeDraw')
        if tree and 'model' not in info:
            info['model'] = (tree.get('modelname') or '').split()[0] if tree.get('modelname') else None
            info['texture'] = (tree.get('texturename') or '').split()[0] if tree.get('texturename') else None
        own = ini.top(body)
        if 'kinds' not in info and own.get('kindof'):
            info['kinds'] = own['kindof'].split()
        if 'fuzziness' not in info:
            fuzz = ini.number(own.get('instancescalefuzziness'), None)
            if fuzz is not None:
                info['fuzziness'] = fuzz
    if not info.get('model'):
        return None
    kinds = set(info.get('kinds', []))
    if 'TREE' in kinds:
        info['buffer'] = 'tree'
    elif 'SHRUB' in kinds:
        info['buffer'] = 'shrub'
    else:
        return None
    if model_textures is not None:
        info['model_texture'] = model_textures(info['model'])
    return info


def definition(name, info):
    """map.ini Object block drawing the vegetation through W3DModelDraw."""
    kinds = [k for k in info.get('kinds', []) if k not in _DROP_KINDS]
    for k in ('SHRUBBERY', 'IMMOBILE', 'IGNORED_IN_GUI'):
        if k not in kinds:
            kinds.append(k)
    lines = [f'Object {PREFIX}{name}',
             '  Draw = W3DModelDraw ModuleTag_01',
             '    DefaultModelConditionState',
             f'      Model = {info["model"]}']
    old, new = info.get('model_texture'), info.get('texture')
    if old and new and old.lower() != new.lower():
        lines.append(f'      Texture = {old} {new}')
    lines += ['    End',
              '  End',
              '  DisplayName = OBJECT:Prop',
              '  EditorSorting = SHRUBBERY',
              f'  KindOf = {" ".join(kinds)}',
              '  Body = HighlanderBody ModuleTag_02',
              '    MaxHealth = 50.0',
              '  End']
    if info.get('fuzziness'):
        lines.append(f'  InstanceScaleFuzziness = {info["fuzziness"]:g}')
    lines.append('End')
    return '\n'.join(lines)


def plan(objects, templates, model_textures=None, keep_trees=TREE_BUFFER-200, keep_shrubs=SHRUB_BUFFER-200):
    """Which map objects (by index) move to GW_ templates, and the map.ini text.

    The first `keep_trees` trees and `keep_shrubs` shrubs in map order stay
    optimized; the margin below the native limits leaves room for trees the
    game or scripts add."""
    cache = {}
    counts = dict(tree=0, shrub=0)
    keep = dict(tree=keep_trees, shrub=keep_shrubs)
    renamed = {}
    used = {}
    for obj in objects:
        name = obj['template']
        if name not in cache:
            cache[name] = describe(templates, name, model_textures)
        info = cache[name]
        if info is None:
            continue
        counts[info['buffer']] += 1
        if counts[info['buffer']] > keep[info['buffer']]:
            renamed[obj['index']] = PREFIX + name
            used[name] = info
    text = '\n'.join(definition(name, info) for name, info in sorted(used.items()))
    summary = dict(trees=counts['tree'], shrubs=counts['shrub'],
                   optimized_trees=min(counts['tree'], keep_trees),
                   optimized_shrubs=min(counts['shrub'], keep_shrubs),
                   full_models=len(renamed), templates=len(used))
    return renamed, text, summary


def rename(m, renamed):
    """Rewrite ObjectsList with new template names for the given object indices."""
    objects = m.objects()
    for i, template in renamed.items():
        objects[i]['template'] = template
    m.set_objects(objects)
