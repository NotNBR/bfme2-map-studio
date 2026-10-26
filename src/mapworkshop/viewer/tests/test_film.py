import unittest
from pathlib import Path

from mapworkshop.native import openbfme
from mapworkshop.viewer import film


class FilmTest(unittest.TestCase):
    def test_films_resolve_in_the_viewer_project(self):
        self.assertIn('wall_dance', film.films())
        self.assertEqual(film.script('wall_dance'), 'res://films/wall_dance.gd')
        with self.assertRaises(SystemExit):
            film.script('no_such_film')

    def test_video_command(self):
        args = film.command('godot.exe', Path('s/scene.json'), 'res://films/x.gd', Path('f.log'), 60, out=Path('x.avi'))
        self.assertEqual(args, ['godot.exe', '--path', str(openbfme.VIEWER), '--log-file', 'f.log', '--fixed-fps', '60',
                                '--write-movie', 'x.avi', '--script', 'res://films/x.gd', '--',
                                f'--scene={Path("s/scene.json")}', '--fps=60'])

    def test_music(self):
        args = film.command('godot.exe', 'scene.json', 'res://films/x.gd', 'f.log', 60, out=Path('x.avi'),
                            music=Path('song.mp3'), music_start=1.25)
        self.assertEqual(args[-2:], [f'--music={Path("song.mp3").resolve().as_posix()}', '--music-start=1.25'])

    def test_stills_command(self):
        args = film.command('godot.exe', 'scene.json', 'res://films/x.gd', 'f.log', 30, stills=Path('out/stills'),
                            at=[1.5, 12.0])
        self.assertNotIn('--write-movie', args)
        self.assertEqual(args[-2:], [f'--stills={Path("out/stills").resolve().as_posix()}', '--at=1.5,12'])


if __name__ == '__main__':
    unittest.main()
