"""The game's assets as a catalog to search, for picking names to place.

    mw find WORDS... [--type T] [--region R] [--material M] [--variant V] [--size S] [--group G] [--used]
    mw find --textures [WORDS] [--type T] [--region R]     terrain textures (terrain.ini's own classes)
    mw find --roads | --sounds | --effects [WORDS]
    mw item TEMPLATE --info                                 everything known about one template

Each object template gets a group and type (tree, rock, house, wall, bridge,
light / fire, …), a region (Shire, Gondor, Erebor, Mordor, …), variants (Snow,
Ruined, Rubble, …), a material with its evidence, a footprint (the game's
GeometryMajorRadius, map units) and how often the game's own maps place it.
They come from the game's fields where it has them (EditorSorting, KindOf,
Side, the INI a template is defined in, MADE_OF_* flags) and from rules over
names otherwise, so a few templates are misfiled. Material evidence, strongest
first: `game flag`, `type`, `name`, `texture` (the model's texture names),
`culture guess`.

Words match a template's name, type, region, material and variants; every
word must match. Results cover every group (nature, built scenery, gameplay
neutrals, faction buildings and units, creeps, sounds, editor objects,
obsolete and cinematic templates; --group narrows), in order of use in the
stock maps. A `!` notes facts about a template that `mw item NAME --info`
spells out: marked obsolete, made for cinematics, spawned by the game, a
faction's gameplay building.

The index is built once from the extracted game data and the stock maps
(about half a minute) and kept in local/cache/catalog.json until they change.
"""
import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict

from mapworkshop.config import CACHE, GAME_DATA, RENDERS

VERSION = 1
INDEX = CACHE/'catalog.json'

SCENERY = ('Nature', 'Built scenery', 'Gameplay neutrals')
GROUPS = SCENERY + ('Faction structures', 'Faction units', 'Creeps', 'Sound', 'System / editor', 'Obsolete / test')
BUILT_GROUPS = SCENERY + ('Faction structures', 'Obsolete / test')      # things with a material
GAMEPLAY_KINDS = {'FS_FACTORY', 'FS_BASE_DEFENSE', 'FS_CASH_PRODUCER', 'FS_TECHNOLOGY', 'COMMANDCENTER', 'CASTLE_KEEP'}


def has(text, *words):
    return any(w in text for w in words)


# Template facts -----------------------------------------------------------------
def _field(body, key):
    match = re.search(r'(?im)^\s*%s\s*=\s*([^;\n]*)' % key, body)
    return match.group(1).strip() if match else None


def _number(text):
    match = re.match(r'-?[\d.]+', text or '')
    return float(match.group()) if match else None


def facts(assets, name):
    """What a template's INI says, its parents' fields included; None if the
    game does not define it."""
    chain, seen, key = [], set(), name.lower()
    while key and key in assets.templates and key not in seen:
        seen.add(key)
        chain.append(assets.templates[key])
        key = assets.templates[key]['parent']
    if not chain:
        return None
    bodies = [re.sub(r';[^\n]*', '', e['body']) for e in chain]
    get = lambda k: next((v for b in bodies if (v := _field(b, k))), None)
    model = assets.template_model(name)
    own = chain[0]
    return dict(
        name=own['name'], kind=own['kind'], parents=[e['name'] for e in chain[1:]], file=own['file'], line=own['line'],
        sorting=(get('EditorSorting') or '').split()[0].upper() if get('EditorSorting') else '',
        side=(get('Side') or '').split()[0] if get('Side') else '',
        kinds=sorted(model['kinds']) if model else sorted({k.lstrip('+').upper() for k in (get('KindOf') or '').split()
                                                          if not k.startswith('-')}),
        geometry=(get('Geometry') or '').split()[0].upper() if get('Geometry') else '',
        radius=_number(get('GeometryMajorRadius')), height=_number(get('GeometryHeight')),
        buildcost=get('BuildCost'), commandset=get('CommandSet'),
        draws=sorted({d for b in bodies for d in re.findall(r'(?im)^\s*Draw\s*=\s*(\w+)', b)}),
        particles=sorted({p for b in bodies for p in re.findall(r'(?im)^\s*ParticleSysBone\s*=\s*\S+\s+(\w+)', b)}),
        model=model['model'] if model else '', scale=model['scale'] if model else None,
        tree=bool(model and model['tree']))


# Classification -----------------------------------------------------------------
REGIONS = [  # first match wins; tokens match the lowercased name
    ('Angmar', ['angmar', 'carn_dum', 'carndum']),
    ('Minas Morgul', ['minasmorgul', 'mbmm', 'mmbmm', 'morgul']),
    ('Dol Guldur', ['dolgoldur', 'dogoldur', 'dolgul', 'necromancer']),
    ('Mordor', ['mordor', 'cirithungol', 'mountdoom', 'lava', 'morrock', 'mortree', 'shelob', 'barad']),
    ('Isengard', ['isengard', 'isen', 'orthanc']),
    ('Gondor / Minas Tirith', ['minis', 'minastirith', 'gondor', 'pelennor', 'cairandros', 'argonath', 'amonhen', 'gbgen', 'monument']),
    ('Osgiliath', ['osgiliath', 'osgil']),
    ('Ithilien', ['ithilien']),
    ("Helm's Deep", ['helmsdeep', "helm'sdeep", "helm's"]),
    ('Rohan / Edoras', ['rohan', 'edoras', 'westfold']),
    ('Shire', ['shire', 'hobbit', 'sbdock', 'sbferry', 'halfling', 'bombadil', 'oldforest']),
    ('Rivendell', ['rivendell', 'elrond']),     # Riv* buildings: by their INI
    ('Lothlorien', ['lothlorien', 'lorien', 'galadriel', 'lbtreehouse']),
    ('Grey Havens / Lindon', ['greyhaven', 'gbgh', 'ghgarrison', 'harlindon', 'forlindon', 'lindon']),
    ('Mirkwood', ['mirkwood', 'mirkbridge', 'spider', 'web', 'cocoon']),
    ('Erebor', ['erebor']),
    ('Blue Mountains', ['bluemtn', 'bluemountain', 'bluemoutain']),
    ('Iron Hills', ['ironhills']),
    ('Moria', ['moria', 'kaz', 'durin', 'balin']),
    ('Dwarven', ['dwarven', 'dwarvish']),
    ('Dale / Lake-town', ['dale', 'celduin', 'lakecoast']),
    ('Fornost / Arnor', ['fornost', 'forb', 'arnor', 'towerhills', 'barrow']),
    ('Weathertop', ['weathertop', 'gbwtop']),
    ('Ettenmoors', ['ettenmoor', 'goblinking', 'giantskull']),
    ('Harad / Umbar / Easterlings', ['harad', 'umbar', 'easterling', 'corsair', 'rhun']),
    ('Fangorn', ['fangorn']),
    ('Gladden Fields', ['gladden']),
    ('Enedwaith', ['enedwaith']),
    ('Elven', ['elven']),
    ('Wildmen', ['wildmen']),
    ('Snowy north', ['snowy', 'frozen']),
]
# Buildings sorted into one INI per place (object/civilian/<place>buildings.ini).
FILE_REGIONS = {'bluemountains': 'Blue Mountains', 'dale': 'Dale / Lake-town', 'dwarven': 'Dwarven', 'erebor': 'Erebor',
                'ettenmoors': 'Ettenmoors', 'fornost': 'Fornost / Arnor', 'gondor': 'Gondor / Minas Tirith',
                'greyhaven': 'Grey Havens / Lindon', 'harlindon': 'Grey Havens / Lindon', 'helmsdeep': "Helm's Deep",
                'isengard': 'Isengard', 'ithilien': 'Ithilien', 'minasmorgul': 'Minas Morgul',
                'minastirithstructureupgrades': 'Gondor / Minas Tirith', 'ministirith': 'Gondor / Minas Tirith',
                'moriamodules': 'Moria', 'necromancerstatue': 'Dol Guldur', 'osgiliath': 'Osgiliath',
                'rivendell': 'Rivendell', 'rohan': 'Rohan / Edoras', 'shire': 'Shire', 'weathertop': 'Weathertop'}
SIDE_REGIONS = {'mordor': 'Mordor', 'isengard': 'Isengard', 'men': 'Gondor / Minas Tirith', 'gondor': 'Gondor / Minas Tirith',
                'elves': 'Elven', 'dwarves': 'Dwarven', 'wild': 'Goblins / Wild', 'moria': 'Moria', 'angmar': 'Angmar'}


def region(f):
    n, path = f['name'].lower(), f['file'].removeprefix('object/')
    if path.startswith('civilian/') and not has(n, 'umbar'):
        stem = path.rsplit('/', 1)[-1].removesuffix('.ini').removesuffix('buildings')
        if stem in FILE_REGIONS:
            return FILE_REGIONS[stem]
    for name, tokens in REGIONS:
        if has(n, *tokens):
            return name
    if not path.startswith(('nature/', 'civilian/')):
        return SIDE_REGIONS.get(f['side'].lower(), '')
    return ''


NATURE_TYPES = [
    ('Animal / critter', lambda n, f: f['file'].endswith(('natureunits.ini', 'placeholdernatureunits.ini'))
                                       or 'NATUREUNITS_KINDOF' in f['kinds']),
    ('Grass / flowers', lambda n, f: has(n, 'grass', 'flower', 'framvg', 'clumps', 'fern')),
    ('Shrub / bush / hedge', lambda n, f: has(n, 'shrub', 'bush', 'hedge')),
    ('Tree', lambda n, f: f['tree'] or 'TREE' in f['kinds'] or has(n, 'tree', 'stump', 'log0')),
    ('Shrub / bush / hedge', lambda n, f: f['sorting'] == 'SHRUBBERY'),
    ('Water feature', lambda n, f: has(n, 'waterfall', 'wtrfl', 'ripple', 'foam', 'pond', 'lakecoast', 'waterhole',
                                       'lavafall', 'flood', 'water')),
    ('Mountain / backdrop', lambda n, f: has(n, 'mountain')),
    ('Cliff / rock formation', lambda n, f: has(n, 'cliff', 'column', 'arch', 'shelobwall', 'cave')),
    ('Rock / boulder', lambda n, f: has(n, 'rock', 'boulder', 'stone')),
    ('Webs / cocoons', lambda n, f: has(n, 'web', 'cocoon')),
    ('Bones / remains', lambda n, f: has(n, 'bone', 'skull', 'skeleton', 'corpse', 'discarded', 'carcass')),
    ('Roots', lambda n, f: has(n, 'root')),
    ('Atmosphere', lambda n, f: has(n, 'cloud', 'smoke', 'dust', 'haze', 'steam', 'lightning', 'sky', 'divot')),
]
BUILT_TYPES = [
    ('Build plot / flag', lambda n, f: has(n, 'plotflag', 'campflag', 'castleflag', 'outpostflag', 'expansionflag', 'prebuilt',
                                           'sizetemplate', 'campnoflag', 'captureflag', 'aiflag', 'locatortemplate',
                                           'wallhubtemplate', 'basecenter', 'farmtemplate')),
    ('Bones / remains', lambda n, f: has(n, 'bone', 'skull', 'skeleton', 'corpse') and not has(n, 'skullpile')),
    ('Water effect', lambda n, f: has(n, 'ripple', 'foam', 'flood')),
    ('Light / fire', lambda n, f: has(n, 'torch', 'lamp', 'fire', 'bonfire', 'brazier', 'furnace', 'glow', 'pyre', 'firepit',
                                      'sparks', 'bbq', 'liteball', 'godray')),
    ('Decal', lambda n, f: has(n, 'footprint', 'divot', 'scorch', 'crater', 'inchruler')),
    ('Rubble / debris / wreck', lambda n, f: has(n, 'rubble', 'debris', 'wreck', 'broken', 'devastation', 'bits', 'cartpiece',
                                                 'falling')),
    ('Ruin', lambda n, f: has(n, 'ruin')),
    ('Bridge / walkway', lambda n, f: has(n, 'bridge', 'causeway', 'walkway', 'walkcurv', 'walkramp', 'catwalk', 'culvert',
                                          'aquaduct', 'trackmiddle', 'proptrack')),
    ('Gate / door', lambda n, f: has(n, 'gate', 'door', 'portcullis')),
    ('Stairs / ramp', lambda n, f: has(n, 'stair', 'step', 'ramp')),
    ('Tower', lambda n, f: has(n, 'tower', 'lighthouse', 'tow', 'watch')),
    ('Wall / fortification', lambda n, f: has(n, 'wall', 'rampart', 'section', 'corner', 'edge', 'niche', 'hub', 'battlement',
                                              'parapet', 'fortress', 'castle', 'keep', 'arcade', 'gatehouse', 'col', 'segment')),
    ('Statue / monument / tomb', lambda n, f: has(n, 'statue', 'monument', 'guard', 'tomb', 'sarcophag', 'grave', 'mirror',
                                                  'fountain', 'luwell', 'throne') or n.startswith('urn')),
    ('Architectural piece', lambda n, f: has(n, 'pillar', 'arch', 'ceiling', 'floor', 'ground', 'top', 'base', 'ladder',
                                             'seaside', 'skullpile', 'plot0')),
    ('Banner / flag', lambda n, f: has(n, 'banner', 'flag')),
    ('Dock / boat / ship', lambda n, f: has(n, 'dock', 'boat', 'ship', 'ferry', 'pier')),
    ('Tent / camp', lambda n, f: has(n, 'tent', 'camponly')),
    ('Fence / barricade', lambda n, f: has(n, 'fence', 'barricade', 'spike', 'palisade', 'retainingwall', 'trcorner', 'railtie')),
    ('Cart / wagon', lambda n, f: has(n, 'cart', 'wagon', 'wheel', 'batteringram')),
    ('Clutter (barrels, crates, furniture, tools)', lambda n, f: has(
        n, 'barrel', 'crate', 'chest', 'bag', 'sack', 'box', 'keg', 'vat', 'food', 'crop', 'hay', 'timber', 'log', 'beam',
        'rope', 'net', 'trap', 'table', 'stool', 'bench', 'chair', 'rack', 'weapon', 'sword', 'shield', 'bucket', 'hammer',
        'pick', 'shovel', 'supplies', 'props', 'gold', 'treasure', 'trough', 'clothe', 'party', 'sign', 'cage', 'pylon',
        'bombs', 'cutter', 'leaf', 'firework')),
    ('House / building', lambda n, f: has(n, 'house', 'building', 'bldg', 'barrack', 'temple', 'church', 'mill', 'farm',
                                          'smithy', 'inn', 'shack', 'hall', 'prison', 'slaughter', 'stable', 'armory',
                                          'generic', 'gen', 'gazebo', 'wtop', 'amonhen', 'module', 'forge', 'lair',
                                          'outpost', 'mountain')),
]
UNIT_ROLES = [('Hero', 'HERO'), ('Monster', 'MONSTER'), ('Siege', 'SIEGEENGINE'), ('Ship', 'SHIP'), ('Cavalry', 'CAVALRY'),
              ('Archer', 'ARCHER'), ('Infantry', 'INFANTRY'), ('Horde', 'HORDE'), ('Summoned', 'SUMMONED')]


def _first(rules, f, default):
    n = f['name'].lower()
    return next((name for name, rule in rules if rule(n, f)), default)


def obsolete(f):
    return f['side'].lower() == 'obsolete' or f['sorting'] == 'OBSOLETE' or f['file'].startswith('object/obsolete/')


def cinematic(f):
    n = f['name'].lower()
    return (f['file'].startswith(('object/cinematic/', 'object/demotest/', 'object/createahero/'))
            or n.startswith(('cine_', 'cine', 'temp_', 'test', 'cahero')) or 'test' in n)


def classify(f):
    """(group, type) of a template's facts."""
    s, path, n = f['sorting'], f['file'].removeprefix('object/'), f['name'].lower()
    if obsolete(f):
        return 'Obsolete / test', 'Obsolete'
    if cinematic(f):
        return 'Obsolete / test', 'Cinematic / test / placeholder'
    if s == 'AUDIO':
        return 'Sound', 'Ambient sound' + (' stream' if n.startswith('ambstream') else ' emitter')
    if path.endswith(('civiliansubobjects.ini', 'neutral/holes.ini')):
        return 'System / editor', 'Spawned sub-object'
    if s in ('SYSTEM', 'EMITTERS', 'DEBRIS', '') and not (s == '' and path.startswith('nature/')):
        if 'skydome' in n or 'reflection' in n:
            return 'System / editor', 'Water reflection skydome'
        if s == 'EMITTERS' or 'emitter' in n or 'proxy' in n:
            return 'System / editor', 'Particle / critter emitter'
        return 'System / editor', 'Logic / helper object'
    if s == 'UNIT':
        role = next((r for r, k in UNIT_ROLES if k in f['kinds']), 'Other unit')
        return ('Creeps' if path.startswith('neutral/') else 'Faction units'), role
    if path.startswith('neutral/'):
        if has(n, 'lair'):
            return 'Gameplay neutrals', 'Creep lair'
        if has(n, 'flag', 'template', 'locator'):
            return 'Gameplay neutrals', 'Build plot / flag'
        return 'Gameplay neutrals', 'Capturable building'
    if path.startswith(('goodfaction', 'evilfaction')):
        kinds = set(f['kinds'])
        if s != 'STRUCTURE':
            return 'Faction structures', 'Faction prop'
        if kinds & {'WALL_SEGMENT', 'WALL_HUB', 'WALL_UPGRADE'} or has(n, 'wall'):
            return 'Faction structures', 'Wall / gate'
        if kinds & {'CASTLE_KEEP', 'COMMANDCENTER'} or has(n, 'fortress', 'citadel', 'castle'):
            return 'Faction structures', 'Fortress / castle'
        if 'FS_CASH_PRODUCER' in kinds or has(n, 'farm', 'mill', 'mine', 'slaughter', 'furnace', 'lumber'):
            return 'Faction structures', 'Economy'
        if 'FS_BASE_DEFENSE' in kinds or has(n, 'tower'):
            return 'Faction structures', 'Defense'
        if 'FS_FACTORY' in kinds:
            return 'Faction structures', 'Production'
        return 'Faction structures', 'Other / upgrade'
    if s in ('MISC_NATURAL', 'SHRUBBERY') or path.startswith('nature/'):
        return 'Nature', _first(NATURE_TYPES, f, 'Other natural')
    return 'Built scenery', _first(BUILT_TYPES, f, 'Other man-made')


VARIANTS = [('Snow', ['snow', 'frozen', 'winter', 'ice']), ('Ruined', ['ruin']), ('Rubble', ['rubble']),
            ('Damaged', ['damage', 'wreck', 'broken', 'nofired', 'devastation']), ('Dead / burnt', ['dead', 'burnt', 'burned', 'taint']),
            ('Night', ['night']), ('Optimized', ['opt']), ('Camp', ['_camp'])]


def variants(name):
    n = name.lower()
    return [v for v, tokens in VARIANTS if has(n, *tokens)]


MADE_OF = {'MADE_OF_STONE': 'Stone', 'MADE_OF_WOOD': 'Wood', 'MADE_OF_METAL': 'Metal', 'MADE_OF_DIRT': 'Earth'}
TYPE_MATERIALS = {'Tree': 'Vegetation', 'Shrub / bush / hedge': 'Vegetation', 'Grass / flowers': 'Vegetation',
                  'Roots': 'Vegetation', 'Rock / boulder': 'Rock', 'Cliff / rock formation': 'Rock',
                  'Mountain / backdrop': 'Rock', 'Bones / remains': 'Bone', 'Webs / cocoons': 'Web',
                  'Water feature': 'Water', 'Water effect': 'Water', 'Atmosphere': 'Effect', 'Light / fire': 'Fire / light',
                  'Banner / flag': 'Cloth', 'Tent / camp': 'Cloth', 'Decal': 'Ground decal', 'Animal / critter': 'Creature'}
NAME_MATERIALS = [
    ('Wood', ['wood', 'timber', 'log', 'plank', 'pylon', 'beam', 'cart', 'barrel', 'crate', 'keg', 'stool', 'bench', 'table',
              'fence', 'mill', 'lumber', 'shack', 'treehouse', 'boat', 'dock', 'ferry', 'raft', 'trough', 'catwalk', 'wagon', 'stable']),
    ('Stone', ['stone', 'marble', 'statue', 'column', 'monument', 'tomb', 'sarcophag', 'ruin', 'rubble', 'castle', 'fortress',
               'aquaduct', 'causeway', 'culvert', 'niche', 'rampart', 'stair', 'step']),
    ('Metal', ['metal', 'iron', 'chain', 'sword', 'shield', 'cage', 'spike', 'hammer']),
    ('Cloth', ['tent', 'banner', 'flag', 'cloth', 'sack', 'bag', 'net', 'rope', 'rug']),
    ('Straw / thatch', ['thatch', 'hay', 'straw', 'crop'])]
TEXTURE_MATERIALS = [('Wood', ['wood', 'plank', 'timber', 'log']), ('Stone', ['stone', 'marble', 'brick', 'cobble']),
                     ('Metal', ['metal', 'iron', 'steel', 'gold']), ('Straw / thatch', ['thatch', 'hay', 'straw'])]
ARCHITECTURE = {'House / building', 'Wall / fortification', 'Tower', 'Gate / door', 'Bridge / walkway', 'Stairs / ramp', 'Ruin',
                'Statue / monument / tomb', 'Architectural piece', 'Rubble / debris / wreck', 'Creep lair',
                'Capturable building', 'Wall / gate', 'Fortress / castle', 'Defense', 'Production', 'Economy',
                'Other / upgrade', 'Other man-made'}
CULTURE_MATERIALS = {'Rohan / Edoras': 'Wood', 'Shire': 'Wood', 'Dale / Lake-town': 'Wood', 'Wildmen': 'Wood',
                     'Lothlorien': 'Wood', 'Mirkwood': 'Wood'}   # every other region builds in stone


def material(f, type_, region_, textures=()):
    """(material, evidence) or ('', '')."""
    flags = [MADE_OF[k] for k in f['kinds'] if k in MADE_OF]
    if flags:
        return flags[0], 'game flag'
    if type_ in TYPE_MATERIALS:
        return TYPE_MATERIALS[type_], 'type'
    n = f['name'].lower()
    for name, words in NAME_MATERIALS:
        if has(n, *words):
            return name, 'name'
    joined = ' '.join(textures)
    for name, words in TEXTURE_MATERIALS:
        if has(joined, *words):
            return name, 'texture'
    if type_ in ARCHITECTURE and region_ and region_ not in ('Goblins / Wild',):
        return CULTURE_MATERIALS.get(region_, 'Stone'), 'culture guess'
    return '', ''


def size_class(radius):
    if radius is None:
        return ''
    return 'small' if radius < 10 else 'medium' if radius < 40 else 'large' if radius < 120 else 'huge'


def concerns(f):
    """Facts worth knowing before placing this template, as short texts."""
    found = []
    kinds = set(f['kinds'])
    gameplay = bool(kinds & GAMEPLAY_KINDS) and f['sorting'] == 'STRUCTURE'
    if obsolete(f):
        found.append('marked obsolete by the game; a faction building with production, defence or fortress behaviour'
                     if gameplay else 'marked obsolete by the game (Side = Obsolete or object/obsolete/)')
    elif cinematic(f):
        found.append('defined for cinematics or tests')
    elif f['file'].endswith(('civiliansubobjects.ini', 'neutral/holes.ini')):
        found.append('a piece the game spawns itself (damage bits, a destroyed lair\'s hole)')
    elif gameplay and f['file'].startswith(('object/goodfaction/', 'object/evilfaction/')):
        found.append("a faction's gameplay building: it produces, defends, earns or holds a castle for its owner")
    return found


# The index ----------------------------------------------------------------------
def stock_maps():
    """The game's own maps, extracted by `mw setup` (as game.stock_maps)."""
    return sorted((GAME_DATA/'maps').glob('*/*.map'))


def _stamp(assets):
    """What the index depends on: the game archives, the extracted INIs and
    the stock maps."""
    ini = GAME_DATA/'data/ini'
    files = list(assets.archive_paths) + sorted(ini.rglob('*.ini')) + stock_maps()
    return dict(version=VERSION, files=len(files), newest=max((p.stat().st_mtime for p in files), default=0),
                bytes=sum(p.stat().st_size for p in files))


def _texture_names(assets, model):
    """Texture names in a W3D model's meshes (no geometry is decoded)."""
    from mapworkshop.assets.models import chunks
    key = assets.model_key(model) if model else None
    names = set()
    if key:
        try:
            for kind, payload in chunks(assets.read(key)):
                if kind != 0x0:                                  # MESH
                    continue
                for sub, data in chunks(payload):
                    if sub == 0x30:                              # TEXTURES > TEXTURE > TEXTURE_NAME
                        for _, texture in chunks(data):
                            name = dict(chunks(texture)).get(0x32, b'')
                            names.add(name.split(b'\0', 1)[0].decode('latin-1').lower())
        except (OSError, ValueError, KeyError):
            pass
    return sorted(n for n in names if n)


def _named(text, word):
    return re.findall(r'(?m)^%s\s+(\S+)' % word, text)


def build(assets=None, progress=print):
    """Index every object template, terrain texture, road, sound and effect."""
    import numpy as np
    from mapworkshop.formats.map import Map
    from mapworkshop.assets.library import GameAssets
    assets = assets or GameAssets()
    started = time.time()
    progress("Indexing the game's assets (once, about half a minute)...")
    roads = set(n.lower() for n in _named(assets.ini_text('roads.ini'), 'Road'))
    placed, maps, top, road_use = Counter(), defaultdict(set), defaultdict(Counter), Counter()
    tex_cells, tex_maps = Counter(), defaultdict(set)
    for path in stock_maps():
        try:
            m = Map(path.read_bytes())
            for o in m.objects():
                name = o['template'].lower()
                if name in roads:
                    road_use[name] += 1
                placed[name] += 1
                maps[name].add(path.stem)
                top[name][path.stem] += 1
            blend = m.blend(inspection=True)
            tiles = blend['arrays']['tiles'].ravel()
            counts = np.bincount(tiles, minlength=int(tiles.max()) + 1)
            for t in blend['textures']:
                tex_cells[t['name'].lower()] += int(counts[t['tile_start']:t['tile_start'] + t['tile_count']].sum())
                tex_maps[t['name'].lower()].add(path.stem)
        except Exception as error:             # one unreadable stock map never stops the index
            progress(f'  {path.stem}: {error}')
    attached = defaultdict(list)               # particle system -> templates that carry it
    objects = []
    for key in assets.templates:
        f = facts(assets, key)
        group, type_ = classify(f)
        region_ = region(f)
        physical = group in BUILT_GROUPS
        mat, evidence = material(f, type_, region_, _texture_names(assets, f['model'])) if physical else ('', '')
        for p in f['particles']:
            attached[p.lower()].append(f['name'])
        objects.append(dict(name=f['name'], group=group, type=type_, region=region_, variants=variants(f['name']),
                            material=mat, evidence=evidence, radius=f['radius'], size=size_class(f['radius']),
                            side=f['side'], sorting=f['sorting'], file=f['file'], line=f['line'], model=f['model'],
                            placed=placed[key], maps=len(maps[key]), top_maps=top[key].most_common(3),
                            concerns=concerns(f)))
    terrain = []
    for name, body in re.findall(r'(?ms)^Terrain\s+(\w+)\s*\n(.*?)^End', assets.ini_text('terrain.ini')):
        parts = [p.strip().split(None, 1) for p in (_field(body, 'Class') or '').split('NEXT')]
        parts = [p for p in parts if len(p) == 2]
        terrain.append(dict(name=name, texture=_field(body, 'Texture') or '',
                            type=next((v.capitalize() for k, v in parts if k == 'Type'), ''),
                            regions=sorted({v.replace('_', ' ').title().replace("'S", "'s") for k, v in parts if k == 'Region'}),
                            cells=tex_cells[name.lower()], maps=len(tex_maps[name.lower()])))
    effects = [dict(name=n, kind='FX list', theme=fx_theme(n), carried_by=[]) for n in _named(assets.ini_text('fxlist.ini'), 'FXList')]
    for file, word in (('fxparticlesystem.ini', 'FXParticleSystem'), ('particlesystem.ini', 'ParticleSystem')):
        effects += [dict(name=n, kind='particle system', theme=fx_theme(n), carried_by=attached.get(n.lower(), [])[:6])
                    for n in _named(assets.ini_text(file), word)]
    index = dict(stamp=_stamp(assets), objects=objects, terrain=terrain, effects=effects,
                 roads=[dict(name=n, group=road_group(n), placed=road_use[n.lower()])
                        for n in _named(assets.ini_text('roads.ini'), 'Road')],
                 stock_maps=len(stock_maps()))
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(index), encoding='utf-8')
    progress(f'Indexed {len(objects):,} templates, {len(terrain):,} terrain textures and {len(effects):,} effects '
             f'from {index["stock_maps"]} stock maps in {time.time() - started:.0f} s.')
    return index


def load(assets=None, refresh=False, progress=print):
    """The index, rebuilt when the game data or the stock maps changed."""
    from mapworkshop.assets.library import GameAssets
    assets = assets or GameAssets()
    if not refresh and INDEX.exists():
        try:
            index = json.loads(INDEX.read_text(encoding='utf-8'))
            if index.get('stamp') == _stamp(assets):
                return index
        except (OSError, ValueError):
            pass
    return build(assets, progress)


FX_THEMES = [
    ('fire', r'fire|flame|burn|torch|lava|ember|ignite|inferno|blaze|smoulder|scorch'),
    ('water / weather', r'water|splash|ripple|wave|rain|foam|wake|snow|drip|tide|flood|storm|lightning|tornado|wind|thunder'),
    ('smoke / dust', r'smoke|dust|cloud|fog|mist|steam|haze|debris|rubble|dirt|chunk|crack'),
    ('building / destruction', r'structure|building|wall|collapse|damage|tower|castle|gate|fortress|topple|construct|rebuild'),
    ('ambient life', r'bird|leaf|leaves|firefl|insect|butterfl|pollen|ambient|critter'),
    ('magic / aura', r'spell|summon|aura|glow|flare|ray|beam|magic|heal|buff|levelup|shock|blast|light|spark|curse|wizard'),
    ('combat', r'hit|explo|projectile|arrow|impact|die|death|dead|blood|catapult|siege|barrage|bomb|weapon|sword|attack'),
]


def fx_theme(name):
    low = name.lower()
    return next((theme for theme, pattern in FX_THEMES if re.search(pattern, low)), 'unit / hero')


def road_group(name):
    low = name.lower()
    for group, pattern in (('dirt', r'dirt|wagon|fourlane|sand'), ('gravel', r'gravel'), ('paved', r'sidewalk'),
                           ('footprints', r'f[t]?print|footprint'), ('grass', r'grass')):
        if re.search(pattern, low):
            return group
    return 'regional'


# Searching ----------------------------------------------------------------------
def _words(entry):
    return ' '.join([entry['name'], entry.get('type', ''), entry.get('region', ''), entry.get('material', ''),
                     ' '.join(entry.get('variants', [])), entry.get('group', ''), entry.get('theme', ''),
                     ' '.join(entry.get('regions', [])), entry.get('kind', '')]).lower()


def _matches(entry, words):
    text = _words(entry)
    return all(w in text for w in words)


def _like(value, wanted):
    return not wanted or wanted.lower() in (value or '').lower()


def find_objects(index, words=(), type=None, region=None, material=None, variant=None, size=None, group=None,
                 used=False):
    """Matching templates, most used in the stock maps first."""
    words = [w.lower() for w in words]
    hits = [o for o in index['objects'] if _matches(o, words) and _like(o['type'], type) and _like(o['region'], region)
            and _like(o['material'], material) and _like(o['size'], size) and _like(o['group'], group)
            and (not variant or any(_like(v, variant) for v in o['variants'])) and (not used or o['placed'])]
    rank = lambda o: (-o['maps'], -o['placed'], -sum(w in o['name'].lower() for w in words), o['name'])
    return sorted(hits, key=rank)


def _table(rows, headers):
    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    widths[-1] = 0
    line = lambda r: '  ' + '  '.join(str(v).ljust(w) for v, w in zip(r, widths)).rstrip()
    return [line(headers)] + [line(r) for r in rows]


def object_lines(hits, limit, query):
    if not hits:
        return [f'No template matches {query}.']
    rows = []
    for o in hits[:limit]:
        use = f'{o["maps"]} map{"s" if o["maps"] != 1 else ""}, {o["placed"]}x' if o['placed'] else '-'
        mat = f'{o["material"].lower()} ({o["evidence"]})' if o['material'] else '-'
        foot = f'r {o["radius"]:g}' if o['radius'] is not None else '-'
        rows.append([('! ' if o['concerns'] else '') + o['name'], o['group'], o['type'], o['region'] or '-', foot, mat, use])
    out = [f'{len(hits)} template{"s" if len(hits) != 1 else ""} match{"es" if len(hits) == 1 else ""} {query}' + (f' ({len(hits) - limit} more: --limit)' if len(hits) > limit else '')
           + '. Most used in stock maps first:']
    out += _table(rows, ['Template', 'Group', 'Type', 'Region', 'Footprint', 'Material (evidence)', 'Stock maps'])
    if any(o['concerns'] for o in hits[:limit]):
        out.append("! = obsolete, cinematic, spawned by the game or a faction's gameplay building: `mw item NAME --info`.")
    out.append('Footprint: radius in map units (10 per terrain tile). See them: `mw items NAME...` or `mw find ... --render`.')
    return out


def terrain_lines(index, words, type, region, used, limit):
    words = [w.lower() for w in words]
    hits = [t for t in index['terrain'] if _matches(t, words) and _like(t['type'], type)
            and (not region or any(_like(r, region) for r in t['regions'])) and (not used or t['maps'])]
    hits.sort(key=lambda t: (-t['cells'], t['name']))
    rows = [[t['name'], t['type'], ', '.join(t['regions']) or '-', t['texture'], f'{t["maps"]} maps' if t['maps'] else '-']
            for t in hits[:limit]]
    for row, t in zip(rows, hits):
        row[-1] = f'{t["maps"]} map{"s" if t["maps"] != 1 else ""}' if t['maps'] else '-'
    out = [f'{len(hits)} terrain textures match' + (f' ({len(hits) - limit} more: --limit)' if len(hits) > limit else '')
           + '; most painted in stock maps first (terrain.ini: Class = Type ... NEXT Region ...):']
    return out + _table(rows, ['Terrain', 'Type', 'Regions', 'Texture', 'Stock maps']) if hits else ['No terrain texture matches.']


def other_lines(entries, words, limit, title, columns):
    words = [w.lower() for w in words]
    hits = [e for e in entries if _matches(e, words)]
    rows = [[f(e) for _, f in columns] for e in hits[:limit]]
    head = f'{len(hits)} {title} match' + (f' ({len(hits) - limit} more: --limit)' if len(hits) > limit else '') + ':'
    return [head] + _table(rows, [c for c, _ in columns]) if hits else [f'No {title} match.']


# One template ---------------------------------------------------------------------
def describe(assets, name, index=None):
    """Everything known about one template, as lines."""
    f = facts(assets, name)
    if f is None:
        close = sorted(k for k in assets.templates if name.lower() in k)[:8]
        raise LookupError(f'No template {name}' + (f'; similar: {", ".join(assets.templates[k]["name"] for k in close)}'
                                                     if close else ''))
    entry = next((o for o in (index or {}).get('objects', []) if o['name'].lower() == f['name'].lower()), None)
    group, type_ = classify(f)
    region_ = region(f)
    mat, evidence = ((entry['material'], entry['evidence']) if entry else
                     material(f, type_, region_) if group in BUILT_GROUPS else ('', ''))
    out = [f'{f["name"]}  ({f["kind"]}, {f["file"]}' + (f':{f["line"]})' if f['line'] else ')')]
    if f['parents']:
        out.append(f'  Parents:    {" > ".join(f["parents"])}')
    out.append(f'  Is:         {group} > {type_}' + (f'; {", ".join(variants(f["name"]))}' if variants(f['name']) else ''))
    out.append(f'  Region:     {region_ or "-"}' + (f'; Side {f["side"]}' if f['side'] else ''))
    out.append(f'  Material:   {mat or "-"}' + (f' ({evidence})' if evidence else ''))
    out.append(f'  Editor:     EditorSorting {f["sorting"] or "-"}')
    out.append(f'  KindOf:     {" ".join(f["kinds"]) or "-"}')
    shape = ', '.join(x for x in (f['geometry'].lower(), f'radius {f["radius"]:g}' if f['radius'] is not None else '',
                                  f'height {f["height"]:g}' if f['height'] is not None else '') if x)
    out.append(f'  Footprint:  {shape or "-"} (map units)')
    out.append(f'  Model:      {f["model"] or "none"}' + (f', scale {f["scale"]:g}' if f['scale'] not in (None, 1.0) else '')
               + (f'; draw {", ".join(f["draws"])}' if f['draws'] else ''))
    if f['particles'] or 'W3DLightDraw' in f['draws']:
        out.append(f'  Effects:    ' + ', '.join(f['particles'] + (['a light (W3DLightDraw)'] if 'W3DLightDraw' in f['draws'] else [])))
    if f['buildcost'] or f['commandset']:
        out.append(f'  Gameplay:   ' + ', '.join(x for x in (f'BuildCost {f["buildcost"]}' if f['buildcost'] else '',
                                                           f'CommandSet {f["commandset"]}' if f['commandset'] else '') if x))
    if entry is not None:
        used = ', '.join(f'{m} ({n})' for m, n in entry['top_maps'])
        out.append(f'  Stock maps: ' + (f'placed {entry["placed"]} times in {entry["maps"]} maps: {used}' if entry['placed']
                                        else 'never placed'))
    for text in concerns(f):
        out.append(f'  Note:       {text}')
    return out


# Built maps ---------------------------------------------------------------------
PLAYER_OWNER = re.compile(r'(?i)^player_\d')
ROAD_FLAGS = 0x2 | 0x4 | 0x10 | 0x20          # road and bridge end points


def _object_names(assets):
    """The game's object templates, those of crate.ini included, lowercase."""
    return set(assets.templates) | {n.lower() for n in _named(assets.ini_text('crate.ini'), '(?:Object|ChildObject|ObjectReskin)')}


MODULE = re.compile(r'(?i)^(Draw|Behavior|Body|ClientUpdate|ClientBehavior)\s*=\s*(\w+)\s+(\w+)')


def _override_problems(name, body):
    """What an `Object` block overriding one of the game's objects does that
    the game refuses (ThingTemplate::parseModuleName in the OpenBFME fork,
    from the retail code): a module declared outside AddModule, ReplaceModule
    or InheritableModule, and a ReplaceModule whose module keeps the old tag."""
    out, depth, script, replacing = [], 0, False, []
    for raw in body.splitlines():
        line = raw.split(';', 1)[0].split('//', 1)[0].strip()
        if not line or line.startswith('#'):
            continue
        if script:
            script = not re.match(r'(?i)^EndScript\b', line)
            continue
        if re.match(r'(?i)^BeginScript\b', line):
            script = True
            continue
        if re.match(r'(?i)^End\b', line):
            depth = max(0, depth - 1)
            if replacing and replacing[-1][0] == depth:
                replacing.pop()
            continue
        edit = re.match(r'(?i)^(AddModule|ReplaceModule|InheritableModule)\b\s*(\w*)', line)
        if edit:
            if edit.group(1).lower() == 'replacemodule':
                replacing.append((depth, edit.group(2)))
            depth += 1
            continue
        module = MODULE.match(line)
        if module:
            if depth == 0:
                out.append(f'Object {name}: {module.group(1)} {module.group(3)} outside AddModule or ReplaceModule; '
                           'the game stops loading a map whose map.ini overrides an object so '
                           '("You must use AddModule to add modules in override INI files")')
            elif replacing and replacing[-1][0] == depth - 1 and module.group(3).lower() == replacing[-1][1].lower():
                out.append(f'Object {name}: ReplaceModule {replacing[-1][1]} keeps the tag; the game needs a new one')
            depth += 1
            continue
        if re.fullmatch(r'\w+', line) or re.match(
                r'(?i)^(LocomotorSet|ArmorSet|WeaponSet|ModelConditionState|AnimationState|TransitionState|Animation)\s*=', line):
            depth += 1
    return out


def check_ini(assets, ini):
    """Lines naming what a map's map.ini defines that the game will not take:
    an `Object` block adding an object type the game doesn't define (BFME2
    hangs loading a map whose map.ini does; changing the game's own objects
    works, docs/game/water.md), one overriding the game's object with a module
    outside AddModule or ReplaceModule (_override_problems), and a particle
    system whose texture the game doesn't have. `assets` are the game's,
    without the map's templates."""
    from mapworkshop.assets.library import TEMPLATE
    known = _object_names(assets)
    out = [f'Object {name}: adds an object type; BFME2 hangs loading a map whose map.ini does '
           "(change one of the game's objects instead)"
           for name in sorted(set(_named(ini, 'Object')), key=str.lower) if name.lower() not in known]
    for kind, name, _, body in TEMPLATE.findall(ini):
        if kind == 'Object' and name.lower() in known:
            out += _override_problems(name, body)
    for name, body in re.findall(r'(?ms)^FXParticleSystem[ \t]+(\S+)[^\n]*\n(.*?)^End\b', ini):
        texture = _field(body, 'ParticleName')
        if texture and assets.texture_key(texture) is None:
            out.append(f'FXParticleSystem {name}: the game has no texture {texture}')
    return out


def check_map(assets, m, ini=''):
    """Lines naming the templates of a map worth a second look: names the game
    doesn't define, obsolete, cinematic or spawned-only templates, and faction
    gameplay buildings no player owns."""
    if ini:
        assets = assets.for_map(ini)
    known = _object_names(assets) | {n.lower() for n in _named(assets.ini_text('roads.ini'), 'Road')}
    known.add('scorch')                           # a terrain scorch mark, drawn by the engine (MapObject::isScorch)
    found, seen = defaultdict(lambda: [0, set()]), {}
    for o in m.objects():
        name = o['template']
        if name.startswith('*') or o['flags'] & ROAD_FLAGS:
            continue
        props = {k: v for k, _, v in o['properties']}
        if name.lower() not in known:
            problem = 'the game defines no such template'
        else:
            if name.lower() not in seen:
                f = facts(assets, name)
                seen[name.lower()] = concerns(f) if f else []
            problems = seen[name.lower()]
            if problems and problems[0].startswith("a faction's") and PLAYER_OWNER.match(props.get('originalOwner', '')):
                continue                                  # a player's own building is meant to be one
            if not problems:
                continue
            problem = problems[0]
        entry = found[(name, problem)]
        entry[0] += 1
        if props.get('objectLayer'):
            entry[1].add(props['objectLayer'])
    return [f'{name} x{n}' + (f' [{", ".join(sorted(layers))}]' if layers else '') + f': {problem}'
            for (name, problem), (n, layers) in sorted(found.items())]


# Command line -------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(prog='mw find', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('words', nargs='*', help='Words to match: name, type, region, material, variant')
    p.add_argument('--type', help='Type, e.g. tree, rock, house, bridge, "light" (templates) or cliff, grass (--textures)')
    p.add_argument('--region', help='Region, e.g. shire, gondor, mordor, erebor')
    p.add_argument('--material', help='Material, e.g. stone, wood, metal')
    p.add_argument('--variant', help='Variant: snow, ruined, rubble, damaged, dead, night')
    p.add_argument('--size', choices=['small', 'medium', 'large', 'huge'], help='Footprint radius: <10, <40, <120, more')
    p.add_argument('--group', help='Only this group (nature, built, gameplay, faction, creeps, sound, system, obsolete)')
    p.add_argument('--used', action='store_true', help='Only what the stock maps place')
    kinds = p.add_mutually_exclusive_group()
    kinds.add_argument('--textures', action='store_true', help='Search terrain textures instead')
    kinds.add_argument('--roads', action='store_true', help='Search roads instead')
    kinds.add_argument('--sounds', action='store_true', help='Search ambient sound objects instead')
    kinds.add_argument('--effects', action='store_true', help='Search FX lists and particle systems instead')
    p.add_argument('--limit', type=int, default=25, help='Rows to show (25)')
    p.add_argument('--render', action='store_true', help='Also render the shown templates as an `mw items` collage')
    p.add_argument('--json', action='store_true', help='Print the matches as JSON')
    p.add_argument('--refresh', action='store_true', help='Rebuild the index first')
    args = p.parse_args(argv)
    index = load(refresh=args.refresh, progress=lambda text: print(text, file=sys.stderr, flush=True))
    words = args.words
    if args.textures:
        if args.json:
            print(json.dumps([t for t in index['terrain'] if _matches(t, [w.lower() for w in words])], indent=1))
        else:
            print('\n'.join(terrain_lines(index, words, args.type, args.region, args.used, args.limit)))
        return 0
    if args.roads or args.effects:
        entries = sorted(index['roads'], key=lambda e: -e['placed']) if args.roads else index['effects']
        if args.json:
            print(json.dumps([e for e in entries if _matches(e, [w.lower() for w in words])], indent=1))
            return 0
        columns = ([('Road', lambda e: e['name']), ('Kind', lambda e: e['group']),
                    ('Stock maps', lambda e: f'{e["placed"]} points' if e['placed'] else '-')] if args.roads else
                   [('Effect', lambda e: e['name']), ('Kind', lambda e: e['kind']), ('Theme', lambda e: e['theme']),
                    ('Carried by', lambda e: ', '.join(e['carried_by']) or '-')])
        print('\n'.join(other_lines(entries, words, args.limit, 'roads' if args.roads else 'effects', columns)))
        return 0
    group = 'sound' if args.sounds else args.group
    if group:
        group = next((g for g in GROUPS if g.lower().startswith(group.lower())), group)
    hits = find_objects(index, words, args.type, args.region, args.material, args.variant, args.size, group, args.used)
    if args.json:
        print(json.dumps(hits[:args.limit], indent=1))
    else:
        query = ' '.join(f'"{w}"' for w in words) or 'the filters'
        print('\n'.join(object_lines(hits, args.limit, query)))
    if args.render and hits:
        from mapworkshop.render import items
        slug = re.sub(r'[^a-z0-9]+', '-', ' '.join(words + [v for v in (args.type, args.region, args.material) if v]).lower()).strip('-')
        return items.main([o['name'] for o in hits[:args.limit] if o['model']]
                          + ['--out', str(RENDERS/'items'/f'find-{slug or "results"}.png')])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
