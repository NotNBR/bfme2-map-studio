"""mw: build, view and play Battle for Middle-earth II maps made from code.

Maps are named by their project id or any unique start of it ("grey" for
greywater-marches); commands without a map use the one you worked on last.
"""
import argparse
from pathlib import Path
import sys
import time

USAGE = """
  mw                         open the viewer on your last map
  mw setup [--game DIR]      find BFME2 and extract its data (once)
  mw doctor                  check that everything is in place
  mw maps                    list your map projects
  mw new "Misty Vale"        start a new map project
  mw dev [MAP]               rebuild on every save, with the viewer open
  mw build [MAP] [--install] build a map (--install: also into the game's maps)
  mw view [MAP]              open the viewer
  mw play [MAP]              test it in-game: start BFME2 straight in a skirmish on it
  mw marks [MAP] [--json]    print the viewer's marks, for an agent
  mw history [MAP]           earlier builds
  mw diff [MAP] [OTHER]      what the last build changed, or what differs between two maps
  mw walkable [MAP] [--native] estimate walking routes locally (--native: read the game instead)
  mw capture [MAP] --shot NAME X Y HEIGHT   screenshots from the game itself, headless (--graphics High, --show)
  mw rivers [MAP] [--json]   which way each river strip flows
  mw find WORDS...           search the game's objects: "stone bridge", --type tree --region shire
                             (--textures, --roads, --sounds, --effects: those instead)
  mw item TEMPLATE           render one object on its own (--info: what the game says about it)
  mw items PATTERN...        a labelled collage of objects: "*bridge*", --from-map MAP [--layer L]
  mw render | graphics | workspace ...   render images, map graphics, hand-edit workspaces
  mw config [KEY [VALUE]]    show or change settings (game, last_map)
  mw test [--corpus]         run the tests and checks (--corpus: also on every stock map)
"""


def parser():
    p = argparse.ArgumentParser(prog='mw', description=__doc__, usage=USAGE,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command')
    s = sub.add_parser('setup', help='Find BFME2 and extract its data')
    s.add_argument('--game', help='The BFME2 folder (with lotrbfme2.exe and INI.big)')
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
    s = sub.add_parser('build', help='Build a map')
    s.add_argument('map', nargs='?')
    s.add_argument('--install', action='store_true', help="Also copy it into the game's user maps")
    s = sub.add_parser('play', help='Test the map in-game: start BFME2 straight in a skirmish on it')
    s.add_argument('map', nargs='?')
    s.add_argument('--rebuild', action='store_true', help='Build before installing')
    s.add_argument('--normal-game', action='store_true',
                   help="Install into your own game's user maps and start it at the menu instead")
    s.add_argument('--graphics', choices=['Low', 'Medium', 'High', 'UltraHigh'], default='Medium',
                   help='Detail level of the test game (default Medium)')
    s = sub.add_parser('history', help='Earlier builds of a map')
    s.add_argument('map', nargs='?')
    s = sub.add_parser('config', help='Show or change settings')
    s.add_argument('key', nargs='?')
    s.add_argument('value', nargs='?')
    sub.add_parser('test', help='Run the tests and repository checks')
    s = sub.add_parser('walkable', help='Estimate walking routes without starting the game')
    s.add_argument('map', nargs='?', help='Map project (default: the last map)')
    s.add_argument('--native', action='store_true', help='Read the grid from the game first (starts it on the map; about 7 seconds)')
    s.add_argument('--compare', action='store_true', help='Compare the local estimate with a saved native grid; does not launch the game')
    s.add_argument('--image', type=Path, help='Also write the overlay as a top-view PNG, one pixel per 10-unit cell')
    s.add_argument('--json', action='store_true', help='Print the cut-off areas as JSON')
    s = sub.add_parser('capture', help='Screenshots from the game itself: start it on the map and save camera views')
    s.add_argument('map', nargs='?', help='Map project (default: the last map)')
    s.add_argument('--shot', nargs=4, action='append', required=True, metavar=('NAME', 'X', 'Y', 'HEIGHT'),
                   help='A view: the camera looks at the ground at X, Y (map units) from HEIGHT (the game camera; 300 is its usual zoom)')
    s.add_argument('--graphics', choices=['Low', 'Medium', 'High', 'UltraHigh'], default='Medium',
                   help='Detail level (default Medium)')
    s.add_argument('--out', type=Path, help='Folder for the PNGs (default local/renders/game/<map>)')
    s.add_argument('--settle', type=int, default=30, help='Rendered frames to wait after moving the camera (30)')
    s.add_argument('--show', action='store_true',
                   help='Show the game window and use native Direct3D 9 (default: headless, through DXVK)')
    s = sub.add_parser('rivers', help='Which way each river strip flows')
    s.add_argument('map', nargs='?', help='Project, stock map or .map file (default: the last map)')
    s.add_argument('--json', action='store_true', help='Print each strip with the middle of every cross-section')
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
    folder = game.setup(choice, force=args.force, progress=say)
    say(f'BFME2: {folder}')
    say('Next: `mw maps` to see the map projects, `mw` to open the viewer.')
    return 0


def cmd_doctor(args):
    import platform
    from mapworkshop import game, project
    from mapworkshop.config import USER_MAPS, game_dir
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
    check(bool(folder and game.is_game(folder)), f'BFME2 folder: {folder or "not set"}', 'Run `mw setup` (or `mw setup --game DIR`).')
    check(game.extracted(), 'Game data extracted (local/game)', 'Run `mw setup`.')
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
    check(USER_MAPS.parent.exists(), f"Game's user maps: {USER_MAPS}",
          'Start BFME2 once so it creates its user folder; `mw play` installs maps there.', required=False)
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


def cmd_build(args, extra):
    from mapworkshop import game, project
    p = project.find(args.map)
    code = _build(p, extra)
    if code == 0 and args.install:
        say(f'Installed: {game.install(p.build_dir, p.native_name)}')
    return code


def cmd_play(args, extra):
    from mapworkshop import game, project
    p = project.find(args.map)
    if args.rebuild or not p.map_file.exists():
        code = _build(p, extra)
        if code:
            return code
    project.remember(p)
    if not args.normal_game:
        from mapworkshop import native
        try:
            native.ready(progress=say)
        except RuntimeError as error:
            say(f'{error}\nStarting your normal game instead.')
        else:
            try:
                process, seconds = native.play(p, graphics=args.graphics, progress=say)
            except RuntimeError as error:
                say(str(error))
                return 1
            process.stdout.close()                   # the game runs on; its launcher logs to the cache
            say(f'{p.title} is playable in BFME2, {seconds:.0f} s after the start: you against an easy AI. '
                'Closing the game window ends it.')
            return 0
    target = game.install(p.build_dir, p.native_name)
    say(f'Installed {p.title} into {target}')
    game.launch()
    say(f'Starting BFME2: pick "{p.title}" under Skirmish or Multiplayer.')
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
    except ValueError:
        raise LookupError('--shot takes a name and three numbers: NAME X Y HEIGHT') from None
    if len({s[0] for s in shots}) != len(shots):
        raise LookupError('Shot names must be unique')
    native.ready(progress=say)
    out = args.out or RENDERS/'game'/p.id
    report = capture(p, shots, out, graphics=args.graphics, settle=args.settle, progress=say, headless=not args.show)
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
    save_setting(args.key, args.value)
    return 0


def cmd_dev(args, extra):
    """Build, open the viewer, then rebuild whenever the project's sources change."""
    import subprocess
    from mapworkshop import project
    from mapworkshop.config import ROOT
    p = project.find(args.map)
    project.remember(p)
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
    return selftest.main(extra)


PASSTHROUGH = {'view': 'mapworkshop.viewer.app', 'marks': 'mapworkshop.viewer.marks',
               'render': 'mapworkshop.render.cli', 'graphics': 'mapworkshop.mapkit.graphics',
               'workspace': 'mapworkshop.mapkit.workspace',
               'find': 'mapworkshop.render.catalog',
               'item': 'mapworkshop.render.items:main_item', 'items': 'mapworkshop.render.items:main'}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
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
                    config=cmd_config, diff=cmd_diff, walkable=cmd_walkable, rivers=cmd_rivers, capture=cmd_capture)
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
