"""mw film: a scripted film of a map, filmed by the Godot viewer through OpenBFME's pro camera.

A film is a GDScript in the viewer project's films/ folder (src/mapworkshop/viewer/godot/films/<name>.gd) that extends
res://scripts/film.gd: it turns on what it shows and moves the camera, frame by frame, with the map's clock following
it. Godot's movie writer records it at a fixed frame rate (an MJPEG .avi), or --stills saves PNGs at chosen seconds.
docs/guide/rendering.md, "Films", describes writing one.
"""
import argparse
import time
from pathlib import Path

from mapworkshop.config import RENDERS
from mapworkshop.native import openbfme
from mapworkshop.native.debugger import run_hidden
from mapworkshop.viewer import godot_viewer

FILMS = Path(__file__).resolve().parent/'godot'/'films'


def films():
    return sorted(p.stem for p in FILMS.glob('*.gd'))


def script(name):
    """The film's script as Godot loads it."""
    if not (FILMS/f'{name}.gd').is_file():
        raise SystemExit(f'No film {name!r} in {FILMS}: {", ".join(films()) or "none yet"}')
    return f'res://films/{name}.gd'


def command(console, scene, film, log, fps, out=None, stills=None, at=(), music=None, music_start=0.0):
    """Godot's command line: the viewer project, the movie writer (or stills) at `fps`, the film on `scene`, with
    `music` from `music_start` seconds."""
    args = [str(console), '--path', str(openbfme.VIEWER), '--log-file', str(log), '--fixed-fps', str(fps)]
    if out is not None:
        args += ['--write-movie', str(out)]
    args += ['--script', film, '--', f'--scene={scene}', f'--fps={fps}']
    if music is not None:
        args += [f'--music={Path(music).resolve().as_posix()}', f'--music-start={music_start:g}']
    if stills is not None:
        args += [f'--stills={Path(stills).resolve().as_posix()}', '--at=' + ','.join(f'{t:g}' for t in at)]
    return args


def main(argv=None):
    parser = argparse.ArgumentParser(prog='mw film', description=__doc__.split('\n\n')[0])
    parser.add_argument('map', help='Map project, stock map or .map file')
    parser.add_argument('film', help=f'A film of the viewer project ({", ".join(films())})')
    parser.add_argument('--out', type=Path, help='The video, an .avi (default: the renders folder, films/<film>.avi)')
    parser.add_argument('--fps', type=int, default=60, help='Frames a second (60)')
    parser.add_argument('--size', default='1920x1080', help='Picture size (1920x1080)')
    parser.add_argument('--music', type=Path, help='A soundtrack (MP3, Ogg or WAV), recorded with the picture')
    parser.add_argument('--music-start', type=float, default=0.0, help='Seconds into the soundtrack the film starts at (0)')
    parser.add_argument('--stills', type=Path, help='Save PNGs into this folder at the --at seconds instead of a video')
    parser.add_argument('--at', default='', help='With --stills: seconds into the film, comma separated')
    parser.add_argument('--timeout', type=float, default=3600, help='Seconds before giving up (3600)')
    args = parser.parse_args(argv)
    film = script(args.film)
    width, height = (int(v) for v in args.size.lower().split('x'))
    at = [float(t) for t in args.at.split(',') if t.strip()]
    if args.stills is not None and not at:
        parser.error('--stills needs --at')
    out = None if args.stills is not None else (args.out or RENDERS/'films'/f'{args.film}.avi').resolve()
    if args.music is not None and not args.music.is_file():
        parser.error(f'no file {args.music}')
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
    openbfme.assets()
    godot_viewer.remove_copies()
    _, console = openbfme.assemble()
    openbfme.LOGS.mkdir(parents=True, exist_ok=True)
    log = openbfme.LOGS/f'film-{time.time_ns()}.log'
    try:
        scene = godot_viewer.prepare(args.map, size=(width, height))[0]
        print(f'Filming {args.film} on {args.map} at {width}x{height}, {args.fps} fps...', flush=True)
        code = run_hidden(command(console, scene, film, log, args.fps, out, args.stills, at, args.music, args.music_start),
                          openbfme.environment(openbfme.archives()), openbfme.HOME, args.timeout)
    finally:
        godot_viewer.remove_copies()
    text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
    for line in text.splitlines():
        if line.startswith(('FILM', 'SCRIPT ERROR')) or 'Parse Error' in line:
            print(line)
    if code:
        print(f'The film stopped with code {code}; see {log}')
    elif out is not None:
        print(f'Film: {out}')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
