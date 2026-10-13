"""`mw test`: the unit tests, then repository checks.

Checks: every Python file parses; imports respect the layers below; every
relative link in the Markdown files resolves.

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


def check_links():
    problems, count = [], 0
    documents = [p for p in ROOT.rglob('*.md') if not ({'local', '.git', '.claude', 'node_modules'} & set(p.relative_to(ROOT).parts))]
    for path in documents:
        for target in re.findall(r'\]\(([^)\s]+)\)', path.read_text(encoding='utf-8')):
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith(('#', '<')):
                continue
            count += 1
            if not (path.parent/unquote(target.split('#', 1)[0])).exists():
                problems.append(f'{path.relative_to(ROOT).as_posix()}: broken link {target}')
    return problems, len(documents), count


def main(argv=()):
    if '--corpus' in argv:
        os.environ['MW_CORPUS'] = '1'   # also round-trip every stock map (needs the game data; slow)
    print('Unit tests')
    suite = unittest.defaultTestLoader.discover(str(ROOT/'src'), pattern='test_*.py', top_level_dir=str(ROOT/'src'))
    result = unittest.TextTestRunner(verbosity=1 if '-v' not in argv else 2).run(suite)
    problems = check_syntax() + check_layers()
    links, documents, count = check_links()
    problems += links
    print(f'\nChecks: Python syntax, import layers, {count} links in {documents} documents')
    for problem in problems:
        print('  ' + problem)
    ok = result.wasSuccessful() and not problems
    print('All tests and checks passed.' if ok else f'{len(problems)} check problems.' if result.wasSuccessful() else 'Tests failed.')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
