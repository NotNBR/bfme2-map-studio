"""Read facts from the running game through bfme-workshop's native host.

bfme-workshop (a separate checkout, by default next to this one; setting
`bfme_workshop`) keeps an isolated BFME2 1.06 runtime with hooks that start a
skirmish and read the game's memory. pathfind() installs a project's build into
that runtime's mod, starts a short skirmish on it, reads the game's
pathfinding grid (pathfind_dump.py) and keeps it next to the build as
pathfind.npz and pathfind.json, with the map's hash (mapkit.walkable).
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from mapworkshop.config import CACHE, ROOT, setting

DRIVER = Path(__file__).with_name('pathfind_dump.py')


def workshop():
    """bfme-workshop's checkout, its Python and its runtime's mod folder."""
    root = Path(setting('bfme_workshop') or ROOT.parent/'bfme-workshop')
    python = root/'local/venv/Scripts/python.exe'
    manifest = root/'local/runtime/bfme-host/manifest.json'
    if not python.is_file() or not manifest.is_file():
        raise RuntimeError(f'Reading the game needs bfme-workshop with a prepared runtime ({root}); '
                           'set its folder with `mw config bfme_workshop <folder>`')
    mod = Path(json.loads(manifest.read_text(encoding='utf-8'))['mod'])
    return root, python, mod


def _run(python, root, args, timeout):
    env = dict(os.environ, PYTHONPATH=str(root/'src'), PYTHONIOENCODING='utf-8')
    return subprocess.run([str(python), *args], cwd=root, env=env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout)


def install(project, root, python, mod):
    """Copy the build into the runtime's mod and register it in its map cache."""
    target = mod/'maps'/project.native_name
    target.mkdir(parents=True, exist_ok=True)
    for path in project.build_dir.iterdir():
        if path.suffix.lower() in ('.map', '.tga') or path.name == 'map.ini':
            shutil.copy2(path, target/path.name)
    register = ('import sys\nfrom pathlib import Path\nfrom formats.map import Map\nfrom mapkit.cache import cache_entry\n'
                'p = Path(sys.argv[1])\ncache_entry(p, Map(p.read_bytes()), sys.argv[2], sys.argv[3], sys.argv[4])\n')
    result = _run(python, root, ['-c', register, str(target/(project.native_name + '.map')), project.native_name,
                                 project.title, project.description or project.title], 120)
    if result.returncode:
        raise RuntimeError('Registering the map in the runtime failed:\n' + result.stderr[-1500:])


def pathfind(project, progress=print):
    """Read the game's pathfinding grid for the project's current build; returns its info."""
    if not project.map_file.exists():
        raise LookupError(f'{project.title} has not been built yet: run `mw build {project.id}`')
    root, python, mod = workshop()
    progress(f'Installing {project.title} into the bfme-workshop runtime...')
    install(project, root, python, mod)
    out = CACHE/'pathfind'/project.id
    shutil.rmtree(out, ignore_errors=True)
    progress('Starting a skirmish to read the pathfinding grid (about a minute)...')
    result = _run(python, root, [str(DRIVER), f'maps\\{project.native_name}.map', str(out)], 900)
    meta = out/'pathfind.json'
    if result.returncode or not meta.is_file():
        raise RuntimeError('The game run did not return a pathfinding grid:\n' + (result.stdout + result.stderr)[-2000:])
    info = json.loads(meta.read_text(encoding='utf-8'))
    info['map_sha256'] = hashlib.sha256(project.map_file.read_bytes()).hexdigest()
    shutil.copy2(out/'pathfind.npz', project.build_dir/'pathfind.npz')
    (project.build_dir/'pathfind.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    return info
