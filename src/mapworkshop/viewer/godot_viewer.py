"""The viewer: `mw view MAP` shows a map in the studio's own Godot project
(viewer/godot/, docs/viewer.md) on OpenBFME's library, which draws the map as
the game does, units animated.

render.godot prepares what the viewer reads (the map in the user maps folder,
the scene) and takes pictures with it; this adds the marks to the scene and
starts the viewer, with its companion (viewer/godot_link.py) while it is open:
the marks, the marks panel and Copy for agent, live reload, the toolbar's
jobs, Preview, the overlays and the saved views. --view starts at a view
resolved as mw render resolves it (render.godot.resolve), --probe prints where
map points land, --screenshot saves the view unseen and closes.
"""

import subprocess
import time
from pathlib import Path

from mapworkshop import project
from mapworkshop.native import openbfme
from mapworkshop.render.godot import SIZE, remove_copies, scene, unseen
from mapworkshop.viewer import godot_link
from mapworkshop.viewer import marks as marklib


def prepare(name, view=None, **options):
    """A map ready for the viewer, its marks in the scene (render.godot.scene's options); what scene() returns. The
    companion prepares the map again for a new build, another map or another preview."""
    prepared = scene(name, view, marks=lambda path, surface: godot_link.marks_state(marklib.Marks(path), surface),
                     **options)
    if prepared[2] is not None:
        openbfme.install_user_map(prepared[2])
    return prepared


def run(name, view=None, probes=(), screenshot=None, size=SIZE, check=False, progress=print, timeout=None,
        drive=None, views=None, preview=None, fps='60'):
    """Prepare and start the viewer on map `name`. With a screenshot or check, wait for it and return
    (exit code, the viewer's output lines); otherwise serve it as its companion until it closes and return its exit
    code. `drive` (tests): scripted input the viewer plays headless, with the companion, before it closes. `views`:
    View switches to start with ({'grid': True, ...}); `preview` the weather and sun ({weather, sun}, OWN's keys);
    `fps` the frame rate cap ('60', 'vsync', 'unlimited', ...)."""
    started = time.perf_counter()
    openbfme.assets(progress)
    remove_copies()                     # any a viewer stopped before it could
    gui, console = openbfme.assemble(progress)
    interactive = not (screenshot or check)
    link = godot_link.Link() if interactive else None
    port = link.port if link else None
    shots = [dict(path=screenshot, size=size)] if screenshot else []
    prepared = prepare(name, view, probes=probes, shots=shots, size=size, check=check, port=port, drive=drive,
                       views=views, preview=preview, fps=fps)
    path, data = prepared[:2]
    headless = (check and not screenshot) or (drive and not any(step['do'] == 'screenshot' for step in drive))
    args = [str(gui if interactive and not drive else console), *(['--headless'] if headless else []),
            '--path', str(openbfme.VIEWER), '--', f'--scene={path}']
    progress(f'Opening {data["title"]} in the Godot viewer ({time.perf_counter() - started:.1f} s to prepare)...')
    if not interactive:
        try:
            return unseen(args, path.parent, headless, timeout)
        finally:
            remove_copies()
    # driven (tests): the viewer's output kept out of the caller's, and a hung viewer stopped after `timeout`
    quiet = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) if drive else {}
    companion = godot_link.Companion(
        prepared, lambda other, preview=None, **more: prepare(other, size=size, port=port, preview=preview, **more),
        progress)
    try:
        while True:
            # the map shown packed for Test mode, mounted as the viewer starts (openbfme.pack_for_test)
            env = openbfme.environment(companion.pack_for_test())
            process = subprocess.Popen(args, env=env, cwd=openbfme.HOME, **quiet)
            companion.serve(link, process)
            code = process.wait(timeout=(timeout or 600) if drive else None)
            if companion.restart is None:
                return code
            args[-1] = f'--scene={companion.relaunch()}'      # Test mode on a map changed since: start again
            progress('Starting the Godot viewer again for Test mode...')
    except subprocess.TimeoutExpired:
        process.kill()
        raise RuntimeError(f'the Godot viewer did not finish its scripted input within {timeout or 600} s')
    finally:
        link.close()
        remove_copies()


FPS_LIMITS = ('30', '60', '90', '120', '144', 'vsync', 'unlimited')    # the toolbar's (toolbar.gd)


def parse_args(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog='mw view', description='Open a map in the viewer (docs/viewer.md).')
    parser.add_argument('map', nargs='?', help='Map project, stock map or .map file (default: open the map picker)')
    parser.add_argument('--map', dest='map_option', help=argparse.SUPPRESS)
    parser.add_argument('--size', default='1600x1000', help='The window size, WIDTHxHEIGHT (1600x1000)')
    parser.add_argument('--weather', default='map', help="Preview's weather: 'map' (the map's own) or clear, haze, "
                                                         "rain, snow, dusk")
    parser.add_argument('--sun', default='own', help="Preview's sun: 'own' (the weather's) or ember, copper, blood, "
                                                     "sulphur, ash, violet")
    parser.add_argument('--fps', default='60', choices=FPS_LIMITS, help='The frame rate cap (60)')
    parser.add_argument('--view', help='Start at this view: the key=value words of `mw render --view`')
    parser.add_argument('--probe', action='append', metavar='X,Y[,Z]',
                        help='With --view: print where this map point lands in the picture, in the viewer and as '
                             'mw render projects it (repeatable)')
    parser.add_argument('--screenshot', type=Path, help='Save the view (or --view) as this PNG, unseen, and close')
    return parser.parse_args(argv)


def main(argv=None):
    """mw view [MAP] [--view WORDS] [--probe X,Y[,Z] ...] [--screenshot PATH] [--size WxH] [--weather W] [--sun S]
    [--fps F]."""
    args = parse_args(argv)
    size = tuple(int(v) for v in args.size.lower().split('x'))
    probes = [tuple(float(v) for v in p.split(',')) for p in (args.probe or [])]
    if probes and not args.view:
        raise SystemExit('--probe needs --view: the points are projected through that view')
    name = args.map or args.map_option
    preview = dict(weather=args.weather, sun=args.sun)
    try:
        if not name and not (args.screenshot or probes):
            from mapworkshop.viewer.startup import choose_map
            name = choose_map()
            if name is None:
                return 0
        if not (args.screenshot or probes):
            owner = project.for_map_file(project.map_path(name))
            if owner is not None:
                project.remember(owner)                  # Preselect it in the startup picker next time.
            else:
                from mapworkshop.config import save_setting
                if Path(name).is_file():
                    save_setting('viewer_map_file', str(Path(name).resolve()))
            return run(name, args.view, size=size, preview=preview, fps=args.fps)
        code, lines = run(name, args.view, probes, args.screenshot, size, check=not args.screenshot, preview=preview)
    except (LookupError, RuntimeError, ValueError) as error:
        raise SystemExit(f'mw view: {error}')
    for line in lines:
        if line.startswith('VIEWER'):
            print(line)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
