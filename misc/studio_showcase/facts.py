"""The real record of Brightwater Fold's making, for the showcase.

    python -m misc.studio_showcase.facts

Reads the step snapshots in local/videos/studio-showcase/steps/ (each the
project's map.py, map.toml, build and output at that step) and writes
facts.json next to them: for every step the map changes against the step
before (mapkit.mapdiff, as `mw diff` prints them), the lines of map.py it
added, and the marks and command output recorded at the time.
"""
import difflib
import json
from pathlib import Path

from mapworkshop.config import VIDEOS
from mapworkshop.mapkit import mapdiff

ROOT = VIDEOS/'studio-showcase'
STEPS = ['00-new', '01-shape', '02-paint', '03-populate', '04-creek', '05-paddock', '06-polish', '07-walls']
MAP = 'map mp brightwater fold.map'


def read(path):
    return path.read_text(encoding='utf-8') if path.exists() else ''


def added_lines(before, after):
    """The lines of `after` that `before` lacks, with their line numbers."""
    a, b = before.splitlines(), after.splitlines()
    out = []
    for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ('insert', 'replace'):
            out += [(j+1, b[j]) for j in range(j1, j2)]
    return out


def collect():
    facts = {}
    for i, step in enumerate(STEPS):
        folder = ROOT/'steps'/step
        entry = dict(step=step, map=str(folder/MAP))
        if i:
            prev = ROOT/'steps'/STEPS[i-1]
            result = mapdiff.compare_files(prev/MAP, folder/MAP)
            entry['changes'] = mapdiff.lines(result, limit=8)
            added = added_lines(read(prev/'map.py'), read(folder/'map.py'))
            entry['added'] = added
            entry['added_count'] = len(added)
            entry['lines'] = len(read(folder/'map.py').splitlines())
        for name in ('marks.txt', 'walkable.txt', 'build.txt'):
            if (folder/name).exists():
                entry[name.split('.')[0]] = read(folder/name).splitlines()
        if (folder/'marks.json').exists():
            entry['marks_json'] = json.loads(read(folder/'marks.json'))
        facts[step] = entry
    facts['00-new']['output'] = read(ROOT/'steps'/'00-new.txt').splitlines()
    (ROOT/'facts.json').write_text(json.dumps(facts, indent=1), encoding='utf-8')
    return facts


if __name__ == '__main__':
    for step, entry in collect().items():
        print(f'== {step}: +{entry.get("added_count", 0)} lines, map.py {entry.get("lines", "?")} lines')
        for line in entry.get('changes', []):
            print('   ', line[:150])
