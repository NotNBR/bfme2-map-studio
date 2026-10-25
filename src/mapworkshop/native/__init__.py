"""Start BFME2 or ROTWK on a project; BFME2 also supports native pathfinding
and screenshot capture.

Everything runs on an isolated copy of the game in local/runtime/
(native.runtime), under this package's debugger (native.debugger, ported
from openbfme2): the game starts straight in a skirmish on the map, gets its
own profile, so your normal game and its options are untouched, and needs
no administrator rights.

- play(): a test game (mw play, the viewer's Play in game). The launcher,
  play_game.py, runs as its own process and stays as the game's debugger
  until the game closes.
- pathfind(): the pathfinding grid (mw walkable --native), kept next to the
  build as pathfind.npz and pathfind.json with the map's hash
  (mapkit.walkable). Headless.
- capture(): screenshots from the game's render target (native.capture).
  Headless unless asked to show the game.

Headless runs put the game on a hidden desktop and render through DXVK, so
no window appears and your focus stays put (native.runtime).
"""
import hashlib
import json
import os
import subprocess
import sys

from mapworkshop.config import ROOT, PROFILE, GAME_LABEL
from mapworkshop.native import runtime

EVENT = 'mapworkshop: '                 # play_game.py's event lines


def ready(progress=print):
    """Prepare the runtime (quick once it exists); RuntimeError if the game
    is missing or its engine is unsupported by the selected profile."""
    return runtime.prepare(progress)


def check(project, graphics='Medium', timeout=180, progress=print):
    """Run a hidden skirmish until ten logic frames, save evidence, and exit."""
    from mapworkshop.native import debugger
    game = runtime.start(project, graphics=graphics, headless=True, progress=progress)
    def tick(game):
        frame, mode = game.logic()
        if mode == debugger.SKIRMISH and frame is not None and frame >= 10:
            game.res['gameplay'] = dict(frame=frame, mode=mode, seconds=game.seconds())
            return 'verified-gameplay'
    result = game.run(timeout, tick=tick)
    result.update(profile=PROFILE, map_sha256=hashlib.sha256(project.map_file.read_bytes()).hexdigest())
    report = runtime.LOGS/f'check-{project.id}.json'
    report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    if result['stopped'] != 'verified-gameplay':
        raise RuntimeError(f'The game did not reach gameplay ({result["stopped"]}); see {report}')
    progress(f'{GAME_LABEL}: reached logic frame {result["gameplay"]["frame"]} in '
             f'{result["gameplay"]["seconds"]:.1f} s; test game closed. Report: {report}')
    return result


def pathfind(project, progress=print):
    """Read the game's pathfinding grid for the project's current build;
    returns its info."""
    if PROFILE == 'rotwk':
        raise RuntimeError('Native pathfinding capture currently supports BFME2 1.06 only')
    import numpy as np
    from mapworkshop.native import pathgrid
    ready(progress)
    progress(f'Starting a skirmish on {project.title} to read its pathfinding grid...')
    arrays, info = pathgrid.run(runtime.start(project, graphics='Low', headless=True, progress=progress))
    info['map'] = f'maps\\{project.native_name}.map'
    info['map_sha256'] = hashlib.sha256(project.map_file.read_bytes()).hexdigest()
    np.savez_compressed(project.build_dir/'pathfind.npz', **arrays)
    (project.build_dir/'pathfind.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    progress(f'Read the grid at logic frame {info["frame"]}.')
    return info


def play(project, graphics='Medium', progress=print, fog=False):
    """Start the selected game in a skirmish on the project's current build,
    you against an easy AI, in a 1600 x 1200 window. BFME2 reveals the map
    unless `fog`; ROTWK keeps its normal fog. Both profiles enable the free
    camera. Returns once the game reports
    that the skirmish is playable: the launcher process (for watch(); close
    its stdout if you do not watch it) and the seconds the start took. Raises
    RuntimeError when the launcher ends before that."""
    ready(progress)
    log = runtime.LOGS/f'play-{project.id}.log'
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    process = subprocess.Popen([sys.executable, '-m', 'mapworkshop.native.play_game', project.id, str(log),
                                '--graphics', graphics] + (['--fog'] if fog else []), cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    progress(f'Starting {GAME_LABEL} and loading {project.title}...')
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
