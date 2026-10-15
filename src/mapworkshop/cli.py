"""mw: build, view and play Battle for Middle-earth II maps made from code.

Maps are named by their project id or any unique start of it ("grey" for
greywater-marches); commands without a map use the one you worked on last.
"""
import argparse
import os
from pathlib import Path
import sys
import time

USAGE = """
  mw --profile bfme2|rotwk COMMAND   use a game profile for this command
  mw                         open the viewer on your last map
  mw setup [--game DIR]      find BFME2 and extract its data (once)
  mw doctor                  check that everything is in place
  mw maps                    list your map projects
  mw new "Misty Vale"        start a new map project
  mw dev [MAP]               rebuild on every save, with the viewer open
  mw build [MAP] [--install] build a map (--install: also into the game's maps;
                             --no-cache: make every stored calculation again)
  mw view [MAP]              open the viewer
  mw play [MAP]              test it in-game: start BFME2 straight in a skirmish on it
  mw marks [MAP] [--json]    print the viewer's marks, for an agent
  mw history [MAP]           earlier builds
  mw diff [MAP] [OTHER]      what the last build changed, or what differs between two maps
  mw walkable [MAP] [--native] estimate walking routes locally (--native: read the game instead)
  mw capture [MAP] --shot NAME X Y HEIGHT   screenshots from the game itself, headless (--graphics High, --show)
  mw patch [install|remove]  faster map loading in your normal game (status without an action)
  mw rivers [MAP] [--json]   which way each river strip flows
  mw where MAP NAME...       where objects stand (--section Z, --footprint, --bones: their outlines there)
  mw find WORDS...           search the game's objects: "stone bridge", --type tree --region shire
                             (--textures, --roads, --sounds, --effects: those instead)
  mw item TEMPLATE           render one object on its own (--info: what the game says about it)
  mw items PATTERN...        a labelled collage of objects: "*bridge*", --from-map MAP [--layer L]
  mw render | graphics | workspace ...   render images, map graphics, hand-edit workspaces
  mw config [KEY [VALUE]]    show or change settings (game, rotwk, profile, last_map)
  mw test [--corpus]         run the tests and checks (--corpus: also on every stock map)
"""


def parser():
    p = argparse.ArgumentParser(prog='mw', description=__doc__, usage=USAGE,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--profile', choices=['bfme2', 'rotwk'], help='Game assets and output profile (default: saved setting)')
    sub = p.add_subparsers(dest='command')
    s = sub.add_parser('setup', help='Find BFME2 and extract its data')
    s.add_argument('--game', help='The BFME2 folder (with lotrbfme2.exe and INI.big)')
    s.add_argument('--rotwk', help='The expansion folder (with lotrbfme2ep1.exe and INI.big); use --profile rotwk')
    s.add_argument('--force', action='store_true', help='Extract again even if up to date')
    sub.add_parser('doctor', help='Check the setup')
    sub.add_parser('maps', help='List the map projects')
    s = sub.add_parser('new', help='Start a new map project')
    s.add_argument('title')
    s.add_argument('--players', type=int, default=2, help='Player starts, 2-8 (2)')
    s.add_argument('--size', default='600x600', help='Playable size in cells, WIDTHxHEIGHT (600x600; 10 map units per cell)')
    s.add_argument('--id', help='Project id (default: from the title)')
    s = sub.add_parser('dev', help='Rebuild on every save, with the viewer open')
    s.add_argument('map', nargs='?')
    s.add_argument('--no-view', action='store_true', help="Don't open the viewer")
    s.add_argument('--no-cache', action='store_true', help="Make every calculation again instead of reusing earlier builds' results")
    s = sub.add_parser('build', help='Build a map')
    s.add_argument('map', nargs='?')
    s.add_argument('--install', action='store_true', help="Also copy it into the game's user maps")
    s.add_argument('--no-cache', action='store_true', help="Make every calculation again instead of reusing earlier builds' results")
    s = sub.add_parser('play', help='Test the map in-game: start the selected game in a skirmish on it')
    s.add_argument('map', nargs='?')
    s.add_argument('--rebuild', action='store_true', help='Build before installing')
    s.add_argument('--check', action='store_true', help='Run a hidden skirmish to ten logic frames, then close it and save a report')
    s.add_argument('--normal-game', action='store_true',
                   help="Install into the game's user maps and open its menu (isolated runtime for ROTWK)")
    s.add_argument('--graphics', choices=['Low', 'Medium', 'High', 'UltraHigh'], default='Medium',
                   help='Detail level of the test game (default Medium)')
    s.add_argument('--fog', action='store_true',
                   help='Keep the shroud and fog of war (by default the map is revealed)')
    s = sub.add_parser('history', help='Earlier builds of a map')
    s.add_argument('map', nargs='?')
    s = sub.add_parser('config', help='Show or change settings')
    s.add_argument('key', nargs='?')
    s.add_argument('value', nargs='?')
    s = sub.add_parser('test', help='Run the tests and repository checks')
    s.add_argument('--corpus', action='store_true', help='Also read and rewrite every stock map (needs the game data; slow)')
    s.add_argument('-v', '--verbose', action='store_true', help='List every test')
    s = sub.add_parser('walkable', help='Estimate walking routes without starting the game')
    s.add_argument('map', nargs='?', help='Map project (default: the last map)')
    s.add_argument('--native', action='store_true', help='Read the grid from the game first (starts it on the map; about 7 seconds)')
    s.add_argument('--compare', action='store_true', help='Compare the local estimate with a saved native grid; does not launch the game')
    s.add_argument('--image', type=Path, help='Also write the overlay as a top-view PNG, one pixel per 10-unit cell')
    s.add_argument('--json', action='store_true', help='Print the cut-off areas as JSON')
    s = sub.add_parser('capture', help='Screenshots from the game itself: start it on the map and save camera views')
    s.add_argument('map', nargs='?', help='Map project (default: the last map)')
    s.add_argument('--view', nargs=6, action='append', metavar=('NAME', 'X', 'Y', 'DISTANCE', 'PITCH', 'HEADING'),
                   help='A cinematic view: the camera DISTANCE from the ground at X, Y, PITCH degrees below the '
                        'horizon, facing HEADING degrees (0 north, 90 east); after the --shot views')
    s.add_argument('--shot', nargs=4, action='append', default=[], metavar=('NAME', 'X', 'Y', 'HEIGHT'),
                   help='A view: the camera looks at the ground at X, Y (map units) from HEIGHT (the game camera; 300 is its usual zoom)')
    s.add_argument('--at', type=int, action='append', metavar='FRAME',
                   help='With one value per --shot, in order: take that shot once the game reaches this logic frame')
    s.add_argument('--timeout', type=int, default=240, help='Seconds before the run gives up (240)')
    s.add_argument('--graphics', choices=['Low', 'Medium', 'High', 'UltraHigh'], default='Medium',
                   help='Detail level (default Medium)')
    s.add_argument('--out', type=Path, help='Folder for the PNGs (default local/renders/game/<map>)')
    s.add_argument('--settle', type=int, default=30, help='Rendered frames to wait after moving the camera (30)')
    s.add_argument('--delay', type=int, default=0, metavar='MS',
                   help='Also wait at least this many milliseconds after moving the camera before each shot')
    s.add_argument('--show', action='store_true',
                   help='Show the game window and use native Direct3D 9 (default: headless, through DXVK)')
    s = sub.add_parser('patch', help="Faster map loading in your normal game (a dinput8.dll in the game folder)")
    s.add_argument('action', nargs='?', choices=['status', 'install', 'remove'], default='status')
    s = sub.add_parser('rivers', help='Which way each river strip flows')
    s.add_argument('map', nargs='?', help='Project, stock map or .map file (default: the last map)')
    s.add_argument('--json', action='store_true', help='Print each strip with the middle of every cross-section')
    s = sub.add_parser('where', help='Where objects stand on a map, and their outlines there')
    s.add_argument('map', help='Project, stock map or .map file')
    s.add_argument('patterns', nargs='*',
                   help='Template, object or waypoint names: a wildcard ("*bridge*") or any part of one')
    s.add_argument('--layer', help='Only objects of this layer')
    s.add_argument('--near', help='Only objects within R of X,Y: X,Y,R')
    s.add_argument('--section', type=float, metavar='Z', help="Each one's model cut at the map height Z (e.g. its water)")
    s.add_argument('--footprint', action='store_true', help='The ground each one covers seen from above')
    s.add_argument('--low', type=float, help='With --footprint: only what lies above this map height')
    s.add_argument('--high', type=float, help='With --footprint: only what lies below this map height')
    s.add_argument('--bones', action='store_true', help="Each one's named points")
    s.add_argument('--step', type=float, default=1., help='Outline grid in map units (1)')
    s.add_argument('--limit', type=int, default=40, help='Objects to show (40)')
    s.add_argument('--json', action='store_true', help='Print JSON')
    s = sub.add_parser('diff', help='What the last build changed, or what differs between two maps')
    s.add_argument('map', nargs='?', help='Project, stock map or .map file (default: the last map)')
    s.add_argument('other', nargs='?', help='A second map: show what changes from MAP to OTHER')
    s.add_argument('--json', action='store_true', help='Print the full comparison as JSON')
    s.add_argument('--limit', type=int, default=12, help='Detail lines per part (12)')
    for name, text in (('view', 'Open the viewer'), ('marks', "Print the viewer's marks"),
                       ('render', 'Render map images headlessly'), ('graphics', 'Map plans and comparisons'),
                       ('workspace', 'Hand-edit workspaces for .map files'),
                       ('find', "Search the game's objects, terrain textures, roads, sounds and effects"),
                       ('item', 'Render one object on its own'), ('items', 'A labelled collage of objects')):
        sub.add_parser(name, help=text, add_help=False)
    return p


def say(text=''):
    print(text, flush=True)


# Commands ----------------------------------------------------------------------
def cmd_setup(args):
    from mapworkshop import game
    from mapworkshop.config import ROOT, GAME_LABEL, PROFILE
    if PROFILE == 'bfme2' and (ROOT/'.git').exists() and not (ROOT/'src/mapworkshop/native/loading/loading.cpp').exists():
        import subprocess
        say('Fetching the bfme2-map-quickload submodule (faster map loading)...')
        subprocess.run(['git', 'submodule', 'update', '--init'], cwd=ROOT, check=False)
    choice = args.game
    if not choice and game.find() is None:
        if not sys.stdin.isatty():
            raise RuntimeError('BFME2 not found: run `mw setup --game "<BFME2 folder>"`')
        say('BFME2 was not found in the usual places.')
        while True:
            choice = input('Drag the BFME2 folder (the one with lotrbfme2.exe) here and press Enter: ').strip().strip('"')
            if choice and game.is_game(choice):
                break
            say('That folder has no lotrbfme2.exe and INI.big; try again, or Ctrl+C to stop.')
    folder = game.setup(choice, force=args.force, progress=say, rotwk=args.rotwk)
    say(f'{GAME_LABEL}: {folder}')
    say('Next: `mw maps` to see the map projects, `mw` to open the viewer.')
    return 0


def cmd_doctor(args):
    import platform
    from mapworkshop import game, project
    from mapworkshop.config import USER_MAPS, GAME_DATA, GAME_LABEL, PROFILE, base_game_dir, game_dir
    problems = 0

    def check(ok, text, fix=None, required=True):
        nonlocal problems
        mark = 'ok ' if ok else ('!! ' if required else '-- ')
        say(f'  {mark} {text}' + ('' if ok or not fix else f'\n       {fix}'))
        if not ok and required:
            problems += 1

    say('bfme2-map-workshop doctor')
    check(sys.version_info >= (3, 11), f'Python {platform.python_version()}', 'Install Python 3.11 or newer.')
    folder = game_dir()
    check(bool(folder and game.is_game(folder, PROFILE)), f'{GAME_LABEL} folder: {folder or "not set"}', 'Run `mw setup`.')
    if PROFILE == 'rotwk':
        base = base_game_dir()
        check(bool(base and game.is_game(base)), f'Shared BFME2 assets: {base or "not set"}', 'Run `mw setup --game DIR`.')
    check(game.extracted() if base_game_dir() else False, f'Game data extracted ({GAME_DATA})', 'Run `mw setup`.')
    if PROFILE == 'rotwk':
        import hashlib
        from mapworkshop.native import rotwk
        engine = folder/'game.dat' if folder else None
        supported = bool(engine and engine.is_file() and
                         hashlib.sha256(engine.read_bytes()).hexdigest() == rotwk.SUPPORTED_SHA256)
        check(supported, 'Verified ROTWK engine for direct in-game tests',
              'Asset editing works independently; direct tests need the verified engine documented in docs/game/runtime.md.',
              required=False)
    else:
        from mapworkshop.config import ROOT
        check((ROOT/'src/mapworkshop/native/loading/bin/loading.dll').exists(),
              'bfme2-map-quickload submodule (faster map loading in test games)',
              'Run `git submodule update --init` (or `mw setup`).', required=False)
    try:
        import moderngl
        ctx = moderngl.create_standalone_context(require=430)
        renderer = ctx.info.get('GL_RENDERER', 'unknown')
        ctx.release()
        check(True, f'OpenGL 4.3: {renderer}')
    except Exception as error:
        check(False, 'OpenGL 4.3', f'The renderer and viewer need OpenGL 4.3 ({error}). Update the graphics driver.')
    try:
        import glfw
        check(bool(glfw.init()), 'Viewer windows (GLFW)', 'GLFW could not start; the viewer needs a desktop session.')
        glfw.terminate()
    except Exception as error:
        check(False, 'Viewer windows (GLFW)', str(error))
    try:
        import imageio_ffmpeg
        check(bool(imageio_ffmpeg.get_ffmpeg_exe()), 'ffmpeg (videos only)', required=False)
    except Exception:
        check(False, 'ffmpeg (videos only)', 'pip install -e ".[video]"', required=False)
    if PROFILE == 'rotwk':
        from mapworkshop.native import runtime
        user_maps = runtime.APPDATA/runtime.profile_leaf()/'Maps'
        check(user_maps.exists(), f'Isolated ROTWK user maps: {user_maps}',
              '`mw play` prepares this folder and installs the map.', required=False)
    else:
        check(USER_MAPS.parent.exists(), f"Game's user maps: {USER_MAPS}",
              f'Start {GAME_LABEL} once so it creates its user folder; `mw play` installs maps there.', required=False)
    every = project.projects()
    built = [p for p in every if p.map_file.exists()]
    check(bool(every), f'{len(every)} map projects, {len(built)} built', 'Start one with `mw new "<title>"`.')
    say('All good.' if not problems else f'{problems} problem{"s" if problems != 1 else ""} to fix.')
    return 1 if problems else 0


def cmd_maps(args):
    from mapworkshop import project
    from mapworkshop.config import setting
    last = setting('last_map')
    every = project.projects()
    if not every:
        say('No map projects yet: `mw new "<title>"` starts one.')
        return 0
    width = max(len(p.id) for p in every)
    for p in every:
        built = time.strftime('%Y-%m-%d %H:%M', time.localtime(p.map_file.stat().st_mtime)) if p.map_file.exists() else 'not built'
        players = f'{p.players} players' if p.players else ''
        say(f'{"*" if p.id == last else " "} {p.id:<{width}}  {p.title:<26} {players:<10} {built}')
    say('\n* last opened. `mw view <map>`, `mw build <map>`, `mw play <map>`.')
    return 0


def cmd_new(args):
    from mapworkshop.templates import create
    try:
        width, height = (int(v) for v in args.size.lower().split('x'))
    except ValueError:
        raise SystemExit('--size is WIDTHxHEIGHT in cells, e.g. 600x600')
    p = create(args.title, players=args.players, size=(width, height), project_id=args.id)
    say(f'Created {p.folder} ({p.id}).')
    say(f'Next: `mw dev {p.id}` builds it, opens the viewer and rebuilds whenever you save {p.folder.name}/map.py.')
    return 0


def _build(p, extra=()):
    from mapworkshop import project
    say(f'Building {p.title}...')
    code = project.run(p, extra)
    if code:
        say(f'Build failed (exit {code}); the previous build stays in place.')
    return code


def _no_cache(args):
    """--no-cache: the builds this command runs make every calculation again
    (mapkit.memo) instead of reusing earlier builds' results."""
    if args.no_cache:
        os.environ['MW_NO_CACHE'] = '1'


def cmd_build(args, extra):
    from mapworkshop import game, project
    p = project.find(args.map)
    _no_cache(args)
    code = _build(p, extra)
    if code == 0 and args.install:
        say(f'Installed: {game.install(p.build_dir, p.native_name)}')
    return code


def cmd_play(args, extra):
    from mapworkshop import game, project
    from mapworkshop.config import GAME_LABEL, PROFILE
    if args.check and args.normal_game:
        raise RuntimeError('--check cannot be combined with --normal-game')
    p = project.find(args.map)
    if args.rebuild or not p.map_file.exists():
        code = _build(p, extra)
        if code:
            return code
    project.remember(p)
    if args.check:
        from mapworkshop import native
        native.check(p, graphics=args.graphics, progress=say)
        return 0
    if not args.normal_game:
        from mapworkshop import native
        try:
            native.ready(progress=say)
        except RuntimeError as error:
            if PROFILE == 'rotwk':
                raise
            say(f'{error}\nStarting your normal game instead.')
        else:
            try:
                process, seconds = native.play(p, graphics=args.graphics, progress=say, fog=args.fog)
            except RuntimeError as error:
                say(str(error))
                return 1
            process.stdout.close()                   # the game runs on; its launcher logs to the cache
            say(f'{p.title} is playable in {GAME_LABEL}, {seconds:.0f} s after the start: you against an easy AI. '
                'Closing the game window ends it.')
            return 0
    target = game.install(p.build_dir, p.native_name)
    say(f'Installed {p.title} into {target}')
    game.launch()
    say(f'Starting {GAME_LABEL}: pick "{p.title}" under Skirmish or Multiplayer.')
    return 0


def cmd_history(args):
    from mapworkshop import project
    p = project.find(args.map)
    runs = project.history(p)
    if not runs:
        say(f'No builds of {p.title} yet.')
    for folder, record in runs:
        say(f'  {folder.name}  {record.get("status", "?"):<7} {record.get("seconds", 0):>5.0f} s  '
            f'{(record.get("map_sha256") or "")[:12]}  {record.get("error", "")}')
    return 0


def cmd_diff(args):
    """MAP's latest build against the build before it, or MAP against OTHER."""
    import json
    from mapworkshop import project
    from mapworkshop.mapkit import mapdiff
    if args.other:
        before, after = project.map_path(args.map), project.map_path(args.other)
    else:
        p = project.find(args.map)
        after = p.map_file
        if not after.exists():
            raise LookupError(f'{p.title} has not been built yet: run `mw build {p.id}`')
        before = project.previous_build(p)
        if before is None:
            raise LookupError(f'{p.title} has only one build; build it again, or name two maps')
    result = mapdiff.compare_files(before, after)
    if args.json:
        say(json.dumps(result, indent=2))
    else:
        say(f'From {before}\n  to {after}\n')
        say('\n'.join(mapdiff.lines(result, args.limit)))
    return 0


def cmd_patch(args):
    """Install, remove or report the faster-loading patch in the normal game."""
    from mapworkshop.native import patch
    if args.action == 'install':
        say(f'Installed {patch.install()}: maps load with their terrain textures built on several processor cores, '
            'and the title logo after loading is skipped. `mw patch remove` takes it out again.')
    elif args.action == 'remove':
        say(f'Removed {patch.remove()}; the game loads as it did before.')
    else:
        state = patch.status()
        say({'not installed': 'Not installed: `mw patch install` makes maps load faster in your normal game.',
             'installed': f'Installed and up to date ({patch.folder()/patch.NAME}).',
             'outdated': 'Installed, but an older build: `mw patch install` updates it.',
             'foreign': f'{patch.folder()/patch.NAME} belongs to another program; the patch cannot be installed '
                        'beside it.'}[state])
    return 0


def cmd_capture(args):
    """Screenshots of a project's current build, rendered by the game."""
    from mapworkshop import native, project
    from mapworkshop.config import RENDERS
    from mapworkshop.native.capture import capture
    p = project.find(args.map)
    if not p.map_file.exists():
        raise LookupError(f'No build of {p.title}: run `mw build {p.id}`')
    try:
        shots = [(name, float(x), float(y), float(height)) for name, x, y, height in args.shot]
        shots += [dict(name=name, x=float(x), y=float(y), height=300., distance=float(d), pitch=float(p), heading=float(h))
                  for name, x, y, d, p, h in args.view or []]
    except ValueError:
        raise LookupError('--shot takes NAME X Y HEIGHT, --view NAME X Y DISTANCE PITCH HEADING: numbers after the name') from None
    if not shots:
        raise LookupError('Give at least one --shot or --view')
    names = [s['name'] if isinstance(s, dict) else s[0] for s in shots]
    if len(set(names)) != len(shots):
        raise LookupError('Shot names must be unique')
    if args.at:
        if len(args.at) != len(shots) or args.at != sorted(args.at):
            raise LookupError('--at takes one rising logic frame per --shot and --view')
        shots = [dict(s, frame=f) if isinstance(s, dict) else s+(f,) for s, f in zip(shots, args.at)]
    native.ready(progress=say)
    out = args.out or RENDERS/'game'/p.id
    report = capture(p, shots, out, graphics=args.graphics, settle=args.settle, progress=say, headless=not args.show,
                     timeout=args.timeout, delay=args.delay)
    say(f'{len(report["shots"])} screenshot(s) in {out} ({report["seconds"]:.0f} s); capture.json has the details.')
    return 0


def cmd_walkable(args):
    """Local walkability, with optional native capture or saved-grid comparison."""
    import json
    from mapworkshop import project
    from mapworkshop.formats.map import Map
    from mapworkshop.mapkit import pathing, walkable
    p = project.find(args.map)
    if not p.map_file.exists():
        raise LookupError(f'No build of {p.title}: run `mw build {p.id}`')
    if args.native:
        from mapworkshop import native
        native.pathfind(p, progress=say)
    grid = walkable.load(p.map_file) if args.native else pathing.from_file(p.map_file)
    if grid is None:
        raise LookupError(f'No native pathfinding grid for the current build of {p.title}')
    comparison = None
    if args.compare:
        reference = walkable.load(p.map_file)
        if reference is None:
            raise LookupError('No saved native grid for this build; --compare never launches the game. '
                              'Use --native explicitly if you want a new capture.')
        estimate = pathing.from_file(p.map_file) if args.native else grid
        comparison = walkable.compare(estimate, reference)
    result = walkable.analyse(grid, Map(p.map_file.read_bytes()))
    if args.image:
        from PIL import Image
        args.image.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(walkable.overlay(result)[::-1]).save(args.image)
    if args.json:
        say(json.dumps(dict(cut_off=result['cut_off'], starts=len(result['starts']),
                            source='native' if args.native else 'computed',
                            warnings=grid['info'].get('warnings', []), comparison=comparison), indent=2))
    else:
        size = grid["ground"].shape
        source = "the game's pathfinding grid" if args.native else 'local walkability estimate'
        say(f'{p.title}: {source}, {size[1]} x {size[0]} cells of 10 units.')
        for line in walkable.summary(result, grid['info']):
            say(line)
        if comparison:
            say(f"Saved native comparison: {comparison['category_match_percent']:.2f}% of cell categories match; "
                f"{comparison['passability_differences']:,} cells differ in passability.")
    return 0


def cmd_where(args):
    """Placed objects matching the patterns, with their outlines on the map."""
    import json
    import math
    from mapworkshop import project
    from mapworkshop.formats.map import Map
    from mapworkshop.render import footprint
    if not (args.patterns or args.layer or args.near):
        raise LookupError('name a template, object or waypoint, or give --layer or --near')
    near = None
    if args.near:
        near = tuple(float(v) for v in args.near.split(','))
        if len(near) != 3:
            raise LookupError('--near takes X,Y,R')
    path = project.map_path(args.map)
    found = footprint.placed(Map(path.read_bytes()), args.patterns, args.layer, near)
    shapes = args.section is not None or args.footprint or args.bones
    for o in found[:args.limit]:
        if not shapes or o['template'].startswith('*'):
            continue
        def here(points, o=o):
            return footprint.to_world(points, o['x'], o['y'], o['angle'], o['z'])
        try:
            if args.bones:
                o['bones'] = {k: here([v])[0] for k, v in footprint.bones(o['template']).items()}
            if args.section is not None:
                o['section'] = [here(p) for p in footprint.section(o['template'], args.section - o['z'], args.step)]
            if args.footprint:
                low, high = (None if v is None else v - o['z'] for v in (args.low, args.high))
                o['footprint'] = [here(p) for p in footprint.footprint(o['template'], low, high, args.step)]
        except LookupError as error:
            o['error'] = str(error)
    if args.json:
        say(json.dumps([dict(o, angle=round(math.degrees(o['angle']), 2)) for o in found[:args.limit]], indent=1))
        return 0
    say(f'{path.stem}: {len(found)} object{" matches" if len(found) == 1 else "s match"}. Map units, x east and y north; '
        "z is the height on the map; an object's angle turns it counter-clockwise from east.")
    for o in found[:args.limit]:
        label = o['template'] + (f' "{o["name"]}"' if o['name'] else '') + (f' [{o["layer"]}]' if o['layer'] else '')
        say(f'{label} at ({o["x"]:g}, {o["y"]:g}), ground {o["ground"]:g}, origin z {o["z"]:g}, '
            f'angle {math.degrees(o["angle"]):.1f}')
        if o.get('error'):
            say(f'  {o["error"]}')
        for name, point in o.get('bones', {}).items():
            say(f'  bone {name}: ({point[0]:g}, {point[1]:g}, {point[2]:g})')
        for key, title in {'section': f'cut at z {args.section}', 'footprint': 'from above'}.items():
            if key in o:
                say(f'  {title}: {len(o[key]) or "no"} outline{"" if len(o[key]) == 1 else "s"}')
                for line in footprint.describe(o[key]):
                    say('    ' + line)
    if len(found) > args.limit:
        say(f'... {len(found) - args.limit} more (--limit)')
    return 0


def cmd_rivers(args):
    """Each river strip (RiverAreas) in flow order, as compass runs."""
    import json
    from mapworkshop import project
    from mapworkshop.formats.map import Map
    from mapworkshop.mapkit import rivers
    path = project.map_path(args.map)
    courses = rivers.courses(Map(path.read_bytes()))
    if args.json:
        say(json.dumps([dict(c, middle=[[round(x, 1), round(y, 1)] for x, y in c['middle']]) for c in courses],
                       indent=2))
        return 0
    say(f'{path.stem}: {len(courses)} river strips. Coordinates are map units, x east and y north; '
        'a strip flows from its first cross-section to its last.')
    for c in courses:
        layer = f' [{c["layer"]}]' if c['layer'] else ''
        say(f'#{c["id"]} {c["name"]}{layer}: {c["length"]:,.0f} long, {c["width"]:.0f} wide, '
            f'water {c["water_height"]}; {rivers.flow_text(c)}')
    return 0


def cmd_config(args):
    from mapworkshop import game
    from mapworkshop.config import CONFIG, save_setting, settings
    if args.key is None:
        values = settings()
        for key, value in values.items():
            say(f'{key} = {value}')
        if not values:
            say(f'No settings yet ({CONFIG}); `mw setup` sets the game folder.')
        return 0
    if args.value is None:
        say(str(settings().get(args.key, '')))
        return 0
    if args.key == 'game':
        game.setup(args.value, progress=say)
        return 0
    if args.key == 'rotwk':
        game.setup(rotwk=args.value, progress=say)
        return 0
    if args.key == 'profile':
        if args.value not in ('bfme2', 'rotwk'):
            raise RuntimeError('Profile must be bfme2 or rotwk')
        save_setting(args.key, args.value)
        say(f'Default profile: {args.value}. Restart any open viewer to switch its assets.')
        return 0
    save_setting(args.key, args.value)
    return 0


def cmd_dev(args, extra):
    """Build, open the viewer, then rebuild whenever the project's sources change."""
    import subprocess
    from mapworkshop import project
    from mapworkshop.config import ROOT
    p = project.find(args.map)
    project.remember(p)
    _no_cache(args)
    if not p.map_file.exists() or _changed_since_build(p):
        _build(p, extra)
    viewer = None
    if not args.no_view and p.map_file.exists():
        viewer = subprocess.Popen([sys.executable, '-m', 'mapworkshop.viewer.app', p.id], cwd=ROOT)
    say(f'Watching {p.folder} - save a file to rebuild, Ctrl+C to stop.')
    seen = _snapshot(p)
    try:
        while viewer is None or viewer.poll() is None:
            time.sleep(0.5)
            current = _snapshot(p)
            if current != seen:
                time.sleep(0.3)        # let the editor finish writing
                seen = _snapshot(p)
                started = time.time()
                code = _build(p, extra)
                say(f'{"Rebuilt" if code == 0 else "Failed"} after {time.time() - started:.0f} s; watching.')
                if code == 0 and viewer is None and not args.no_view:
                    viewer = subprocess.Popen([sys.executable, '-m', 'mapworkshop.viewer.app', p.id], cwd=ROOT)
    except KeyboardInterrupt:
        pass
    finally:
        if viewer and viewer.poll() is None:
            viewer.terminate()
    return 0


def _snapshot(p):
    return tuple((path, path.stat().st_mtime_ns) for path in p.sources())


def _changed_since_build(p):
    built = p.map_file.stat().st_mtime_ns
    return any(mtime > built for _, mtime in _snapshot(p))


def cmd_test(args, extra):
    from mapworkshop import selftest
    return selftest.main([*extra, *(['--corpus'] if args.corpus else []), *(['-v'] if args.verbose else [])])


PASSTHROUGH = {'view': 'mapworkshop.viewer.app', 'marks': 'mapworkshop.viewer.marks',
               'render': 'mapworkshop.render.cli', 'graphics': 'mapworkshop.mapkit.graphics',
               'workspace': 'mapworkshop.mapkit.workspace',
               'find': 'mapworkshop.render.catalog',
               'item': 'mapworkshop.render.items:main_item', 'items': 'mapworkshop.render.items:main'}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Do this before importing config (including through a passthrough module).
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument('--profile', choices=['bfme2', 'rotwk'])
    selected, argv = selector.parse_known_args(argv)
    if selected.profile:
        os.environ['MW_GAME_PROFILE'] = selected.profile
    if not argv:
        argv = ['view']
    if argv[0] in PASSTHROUGH:
        import importlib
        name, _, function = PASSTHROUGH[argv[0]].partition(':')
        entry = getattr(importlib.import_module(name), function or 'main')
        try:
            return entry(argv[1:]) or 0
        except (LookupError, RuntimeError) as error:
            say(f'mw {argv[0]}: {error}')
            return 1
    p = parser()
    args, extra = p.parse_known_args(argv)
    if extra and extra[0] == '--':
        extra = extra[1:]
    commands = dict(setup=cmd_setup, doctor=cmd_doctor, maps=cmd_maps, new=cmd_new, history=cmd_history,
                    config=cmd_config, diff=cmd_diff, walkable=cmd_walkable, rivers=cmd_rivers, where=cmd_where, capture=cmd_capture,
                    patch=cmd_patch)
    with_extra = dict(build=cmd_build, play=cmd_play, dev=cmd_dev, test=cmd_test)
    try:
        if args.command in commands:
            if extra:
                p.error('unexpected arguments: ' + ' '.join(extra))
            return commands[args.command](args)
        if args.command in with_extra:
            return with_extra[args.command](args, extra)
        p.print_help()
        return 1
    except (LookupError, RuntimeError) as error:
        say(f'mw {args.command}: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
