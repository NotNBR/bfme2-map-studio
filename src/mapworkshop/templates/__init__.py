"""Project templates: `mw new` copies new_map/ into maps/<folder>/."""
import random
import re
from pathlib import Path

from mapworkshop.config import MAPS

TEMPLATE = Path(__file__).parent/'new_map'


def slug(title):
    words = re.sub(r'[^a-z0-9]+', ' ', title.lower()).split()
    if len(words) > 1 and words[0] == 'the':
        words = words[1:]
    return '-'.join(words)


def create(title, players=2, size=(600, 600), project_id=None, description=None):
    """Create a buildable map project; returns its mapworkshop.project.Project."""
    from mapworkshop import project
    title = title.strip()
    project_id = project_id or slug(title)
    if not re.fullmatch(r'[a-z][a-z0-9]*(-[a-z0-9]+)*', project_id or ''):
        raise RuntimeError(f'Choose an id of lowercase letters, digits and hyphens (from "{title}": "{project_id}")')
    if not 2 <= players <= 8:
        raise RuntimeError('A map has 2 to 8 players')
    width, height = size
    if not (200 <= width <= 1900 and 200 <= height <= 1900):
        raise RuntimeError('Size is 200 to 1900 cells per side (600x600 is a medium map)')
    folder = MAPS/project_id.replace('-', '_')
    taken = {p.id for p in project.projects()}
    if project_id in taken or folder.exists():
        raise RuntimeError(f'A project "{project_id}" already exists ({folder}); choose another title or --id')
    values = dict(ID=project_id, TITLE=title.replace('"', "'"), PLAYERS=str(players), WIDTH=str(width),
                  HEIGHT=str(height), SEED=str(random.randrange(10_000, 1_000_000)),
                  NATIVE_NAME='map mp ' + re.sub(r'[^a-z0-9 ]+', '', title.lower()).strip(),
                  DESCRIPTION=(description or f'A {players}-player map.').replace('"', "'"))
    folder.mkdir(parents=True)
    for source in sorted(TEMPLATE.glob('*.tmpl')):
        text = source.read_text(encoding='utf-8')
        for key, value in values.items():
            text = text.replace('{{' + key + '}}', value)
        (folder/source.stem).write_text(text, encoding='utf-8', newline='\n')
    (folder/'__init__.py').write_text('', encoding='utf-8')
    return project.find(project_id)
