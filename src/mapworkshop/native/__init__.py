"""Start BFME2 on a project and learn from the running game: test games you
play, the game's own pathfinding grid, screenshots.

Everything runs on an isolated copy of the game in local/runtime/
(native.runtime), under this package's debugger (native.debugger, ported
from openbfme2): the game starts straight in a skirmish on the map, gets its
own profile, so your normal game and its options are untouched, and needs
no administrator rights.

- play(): a test game (mw play, the viewer's Test In-Game). The launcher,
  play_game.py, runs as its own process and stays as the game's debugger
  until the game closes.
- pathfind(): the pathfinding grid (mw walkable --native), kept next to the
  build as pathfind.npz and pathfind.json with the map's hash
  (mapkit.walkable).
- capture(): screenshots from the game's render target (native.capture).
"""
import hashlib
import json
import os
import subprocess
import sys

from mapworkshop.config import ROOT
from mapworkshop.native import runtime

EVENT = 'mapworkshop: '                 # play_game.py's event lines


def ready(progress=print):
    """Prepare the runtime (quick once it exists); RuntimeError if the game
    is missing or not BFME2 1.06."""
    return runtime.prepare(progress)


def pathfind(project, progress=print):
    """Read the game's pathfinding grid for the project's current build;
    returns its info."""
    import numpy as np
    from mapworkshop.native import pathgrid
    ready(progress)
    progress(f'Starting a skirmish on {project.title} to read its pathfinding grid...')
    arrays, info = pathgrid.run(runtime.start(project, graphics='Low'))
    info['map'] = f'maps\\{project.native_name}.map'
    info['map_sha256'] = hashlib.sha256(project.map_file.read_bytes()).hexdigest()
    np.savez_compressed(project.build_dir/'pathfind.npz', **arrays)
    (project.build_dir/'pathfind.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    progress(f'Read the grid at logic frame {info["frame"]}.')
    return info


def play(project, graphics='Medium', progress=print):
    """Start BFME2 straight in a skirmish on the project's current build, you
    against an easy AI, in a 1600 x 1200 window. Returns once the game reports
    that the skirmish is playable: the launcher process (for watch(); close
    its stdout if you do not watch it) and the seconds the start took. Raises
    RuntimeError when the launcher ends before that."""
    ready(progress)
    log = runtime.LOGS/f'play-{project.id}.log'
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    process = subprocess.Popen([sys.executable, '-m', 'mapworkshop.native.play_game', project.id, str(log),
                                '--graphics', graphics], cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    progress(f'Starting BFME2 and loading {project.title}...')
    last = ''
    for line in process.stdout:
        if line.startswith(EVENT + 'loaded '):
            return process, float(line.split()[-1])
        last = line.strip() or last
    code = process.wait()
    raise RuntimeError(f'The game ended before {project.title} was playable (launcher exit {code}): '
                       + (last or 'no output')[-300:] + f'; the log is {log}')


def watch(process):
    """Wait until a test game from play() closes; returns the seconds it ran."""
    seconds = None
    for line in process.stdout:
        if line.startswith(EVENT + 'closed '):
            seconds = float(line.split()[-1])
    process.wait()
    return seconds
