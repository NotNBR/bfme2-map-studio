"""`mw test`: the unit tests, then repository checks.

Checks: every Python file parses; imports respect the layers below; every
relative link in the Markdown files resolves, anchors included; no page outside
docs/history/ gives bfme-workshop's commands as this repository's;
maps/README.md lists every map project; the guides (docs/guide/) show every
`mw` command.

Layers, bottom up; a package imports only from its own layer or below.
mapkit and render share a layer: the renderer reads mapkit's weather
presets and mapkit reads the game assets through render.assets. Command
entry points (`cli.py`, `__main__.py`) may import from any layer. Nothing in
src/ imports the map projects (maps/) or misc/.
"""
import ast
import os
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote

from mapworkshop.config import ROOT

LAYERS = dict(config=0, formats=1, mapkit=2, render=2, video=2, game=3, project=3, templates=3, selftest=3, native=3,
              viewer=4, cli=5, __main__=5)


def _units(node):
    """The mapworkshop packages (or maps/misc) an import statement uses."""
    if isinstance(node, ast.Import):
        names = [a.name for a in node.names]
    elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        names = [f'{node.module}.{a.name}' for a in node.names] if node.module == 'mapworkshop' else [node.module]
    else:
        return []
    found = []
    for name in names:
        parts = name.split('.')
        if parts[0] in ('maps', 'misc'):
            found.append(parts[0])
        elif parts[0] == 'mapworkshop' and len(parts) > 1:
            found.append(parts[1])
    return found


def check_layers():
    problems = []
    for path in sorted((ROOT/'src/mapworkshop').rglob('*.py')):
        rel = path.relative_to(ROOT/'src/mapworkshop')
        if 'tests' in rel.parts:
            continue
        unit = rel.parts[0].removesuffix('.py')
        entry = path.name in ('cli.py', '__main__.py')
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            for target in _units(node):
                if target in ('maps', 'misc'):
                    problems.append(f'{rel.as_posix()}: imports {target}/ (map projects and misc sit above src/)')
                elif target != unit and not entry and LAYERS.get(target, 0) > LAYERS.get(unit, 0):
                    problems.append(f'{rel.as_posix()}: {unit} imports {target}, a higher layer')
    return problems


def check_syntax():
    problems = []
    for base in ('src', 'maps', 'misc'):
        for path in (ROOT/base).rglob('*.py'):
            if '__pycache__' in path.parts:
                continue
            try:
                ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            except SyntaxError as error:
                problems.append(f'{path.relative_to(ROOT).as_posix()}: {error}')
    return problems


def documents():
    """The repository's Markdown files, without local/ and the submodules (other repositories)."""
    modules = [ROOT/line.split('=', 1)[1].strip() for line in (ROOT/'.gitmodules').read_text().splitlines()
               if line.strip().startswith('path')] if (ROOT/'.gitmodules').exists() else []
    return [p for p in ROOT.rglob('*.md') if not ({'local', '.git', '.claude', 'node_modules'} & set(p.relative_to(ROOT).parts))
            and not any(m in p.parents for m in modules)]


def _prose(text):
    """The text outside fenced code blocks."""
    return re.sub(r'^```.*?^```', '', text, flags=re.M | re.S)


def anchors(text):
    """The link anchors of a Markdown page, as GitHub makes them from its headings."""
    found, seen = set(re.findall(r'<a (?:id|name)="([^"]+)"', text)), {}
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', _prose(text), flags=re.M):
        heading = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', heading)      # a link keeps its text
        slug = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
        found.add(slug if slug not in seen else f'{slug}-{seen[slug]}')
        seen[slug] = seen.get(slug, 0) + 1
    return found


def check_links(pages):
    """Every relative link resolves, and every #anchor names a heading of its page."""
    problems, count, cache = [], 0, {}
    for path in pages:
        for target in re.findall(r'\]\(([^)\s]+)\)', _prose(path.read_text(encoding='utf-8'))):
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('<'):
                continue
            count += 1
            file, _, anchor = unquote(target).partition('#')
            linked = (path.parent/file).resolve() if file else path
            if not linked.exists():
                problems.append(f'{path.relative_to(ROOT).as_posix()}: broken link {target}')
            elif anchor and linked.suffix == '.md':
                if linked not in cache:
                    cache[linked] = anchors(linked.read_text(encoding='utf-8'))
                if anchor not in cache[linked]:
                    problems.append(f'{path.relative_to(ROOT).as_posix()}: no heading for {target}')
    return problems, count


# Commands and paths of bfme-workshop, the repository this one grew out of. Only the
# pages that record its history (docs/history/) and the license notices may name them.
FOREIGN = [r'scripts/workshop\.py', r'workshop\.py play', r'src/host/', r'host\.launch', r'src/strategic/',
           r'src/scenarios/', r'examples[/.](maps|showcases|scenarios)', r'python -m mapkit\.', r'tools/\w+_smoke',
           r'local/artifacts/', r'bfme-host', r'scripts/launchers/']


def check_foreign(pages):
    problems = []
    for path in pages:
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(('docs/history/', 'docs/licenses/')):
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            for pattern in FOREIGN:
                if re.search(pattern, line):
                    problems.append(f'{rel}:{number}: names bfme-workshop\'s {re.search(pattern, line)[0]} '
                                    '(not in this repository; history goes in docs/history/)')
    return problems


def check_index():
    """maps/README.md links every map project; the guides name every mw command."""
    problems = []
    index = (ROOT/'maps/README.md').read_text(encoding='utf-8') if (ROOT/'maps/README.md').exists() else ''
    for project in sorted(p.parent.name for p in (ROOT/'maps').glob('*/map.toml')):
        if f']({project}/' not in index:
            problems.append(f'maps/README.md: no entry for the project maps/{project}/')
    tree = ast.parse((ROOT/'src/mapworkshop/cli.py').read_text(encoding='utf-8'))
    commands = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'add_parser'
                and n.args and isinstance(n.args[0], ast.Constant)}
    commands |= {t.elts[0].value for n in ast.walk(tree) if isinstance(n, ast.For) and isinstance(n.iter, ast.Tuple)
                 for t in n.iter.elts if isinstance(t, ast.Tuple) and isinstance(t.elts[0], ast.Constant)}
    guides = ' '.join(p.read_text(encoding='utf-8') for p in (ROOT/'docs/guide').glob('*.md'))
    for command in sorted(commands):
        if not re.search(rf'\bmw {command}\b', guides):
            problems.append(f'docs/guide/: no page shows `mw {command}`')
    return problems


def main(argv=()):
    if '--corpus' in argv:
        os.environ['MW_CORPUS'] = '1'   # also round-trip every stock map (needs the game data; slow)
    print('Unit tests')
    suite = unittest.defaultTestLoader.discover(str(ROOT/'src'), pattern='test_*.py', top_level_dir=str(ROOT/'src'))
    result = unittest.TextTestRunner(verbosity=1 if '-v' not in argv else 2).run(suite)
    pages = documents()
    links, count = check_links(pages)
    problems = check_syntax() + check_layers() + links + check_foreign(pages) + check_index()
    print(f'\nChecks: Python syntax, import layers, {count} links in {len(pages)} documents, the map and command indexes')
    for problem in problems:
        print('  ' + problem)
    ok = result.wasSuccessful() and not problems
    print('All tests and checks passed.' if ok else f'{len(problems)} check problems.' if result.wasSuccessful() else 'Tests failed.')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
