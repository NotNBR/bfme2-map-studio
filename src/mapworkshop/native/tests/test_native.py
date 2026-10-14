"""The launcher's parts that need no running game: the PE reader, the code
stubs it writes into the game, and the runtime's files."""
import struct
import tempfile
import unittest
from pathlib import Path, PurePath
from types import SimpleNamespace
from unittest import mock

from mapworkshop.mapkit.blank import create, starts
from mapworkshop.native import debugger, runtime
from mapworkshop.native.capture import DLL
from mapworkshop.native.pe import PE


class PETests(unittest.TestCase):
    def test_capture_dll_exports_and_imports(self):
        pe = PE(DLL)
        self.assertEqual(set(pe.exports()), {'mwCapture', 'mwPhoto', 'mwInstalled'})
        dlls = {dll for dll, _ in pe.imports()}
        self.assertEqual(dlls, {'kernel32.dll', 'msvcr71.dll'})     # the game ships msvcr71
        self.assertEqual(pe.image_base, 0x10000000)
        self.assertTrue(any(code for _, code in pe.code()))


class StubTests(unittest.TestCase):
    def test_call_stub_pushes_right_to_left_and_ends_in_int3(self):
        code = debugger.call_stub([{'call': 0x401000, 'ecx': 0x1234, 'args': [1, 2]}], 0x5000)
        self.assertEqual(code, b'\x68' + struct.pack('<I', 2) + b'\x68' + struct.pack('<I', 1)
                         + b'\xB9' + struct.pack('<I', 0x1234) + b'\xB8' + struct.pack('<I', 0x401000) + b'\xFF\xD0'
                         + b'\xA3' + struct.pack('<I', 0x5000) + b'\xCC')

    def test_appdata_stub_keeps_the_original_and_the_path(self):
        blob = debugger.appdata_stub(0x20000, 0x7654321, r'D:\sandbox\appdata')
        self.assertEqual(blob[0x80:0x84], struct.pack('<I', 0x7654321))
        self.assertEqual(blob[0x100:], 'D:\\sandbox\\appdata\0'.encode('utf-16-le'))
        with self.assertRaises(RuntimeError):
            debugger.appdata_stub(0x20000, 0, 'x' * 300)

    def test_version_stub_reports_windows_xp(self):
        blob = debugger.version_stubs(0x30000)
        self.assertEqual(blob[:6], bytes.fromhex('B8 05 01 28 0A C3'))
        self.assertEqual(struct.unpack_from('<5I', blob, 0x100), (156, 5, 1, 2600, 2))

    def test_describe(self):
        self.assertEqual(debugger.describe(dict(stopped='exit', exit_code=0x29A, fault='image+0xe10d8')),
                         'exit, exit code 0x29a, first fault at image+0xe10d8')


class RuntimeTests(unittest.TestCase):
    def test_archives_and_movies_are_linked_the_rest_copied(self):
        self.assertTrue(runtime.linked(PurePath('W3D.big')))
        self.assertTrue(runtime.linked(PurePath('data/Movies/CS01.vp6')))
        self.assertFalse(runtime.linked(PurePath('game.dat')))
        self.assertFalse(runtime.linked(PurePath('lotrbfme2.exe')))
        self.assertTrue(runtime.SKIPPED.search('Worldbuilder.exe'))
        self.assertTrue(runtime.SKIPPED.search('DUMP_12.dmp'))

    def test_options_set_the_detail_level_and_keep_other_lines(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(runtime, 'APPDATA', Path(folder)/'appdata'), \
                mock.patch.object(runtime, 'profile_leaf', lambda: 'Profile'):
            path = runtime.set_options('High')
            path.write_text(path.read_text() + 'Gamma = 50\n', encoding='latin1')
            text = runtime.set_options('Low').read_text(encoding='latin1')
            self.assertIn('StaticGameLOD = Low\n', text)
            self.assertIn('IdealStaticGameLOD = Low\n', text)
            self.assertIn('Resolution = 1600 1200\n', text)
            self.assertIn('Gamma = 50\n', text)
            self.assertNotIn('High', text)
            with self.assertRaises(ValueError):
                runtime.set_options('Ultra')

    def test_dxvk_is_checked_against_its_digest_and_only_the_32_bit_dll_kept(self):
        import hashlib, io, tarfile
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for name, data in ((f'dxvk-{runtime.DXVK_VERSION}/x32/d3d9.dll', b'32-bit'),
                               (f'dxvk-{runtime.DXVK_VERSION}/x64/d3d9.dll', b'64-bit')):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        blob = buffer.getvalue()
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(runtime, 'RUNTIME', Path(folder)):
            with self.assertRaises(RuntimeError):                  # not the published file
                runtime.dxvk(progress=lambda _: None, download=lambda url: blob)
            with mock.patch.object(runtime, 'DXVK_SHA256', hashlib.sha256(blob).hexdigest()):
                dll = runtime.dxvk(progress=lambda _: None, download=lambda url: blob)
            self.assertEqual(dll.read_bytes(), b'32-bit')
            self.assertEqual(runtime.dxvk(download=lambda url: 1/0), dll)      # kept: no second download

    def test_headless_folder_links_the_runtime_and_adds_dxvk(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game, headless, dll = root/'game', root/'game-headless', root/'d3d9.dll'
            (game/'data').mkdir(parents=True)
            (game/'game.dat').write_bytes(b'game')
            (game/'data'/'W3D.big').write_bytes(b'archive')
            dll.write_bytes(b'dxvk')
            (headless/'old').mkdir(parents=True)
            (headless/'old'/'gone.txt').write_text('stale')
            with mock.patch.object(runtime, 'GAME', game), mock.patch.object(runtime, 'HEADLESS_GAME', headless), \
                    mock.patch.object(runtime, 'prepare', lambda progress=None: game), \
                    mock.patch.object(runtime, 'dxvk', lambda progress=None, download=None: dll):
                runtime.prepare_headless()
            self.assertTrue(os.path.samefile(game/'game.dat', headless/'game.dat'))
            self.assertTrue(os.path.samefile(game/'data'/'W3D.big', headless/'data'/'W3D.big'))
            self.assertEqual((headless/'d3d9.dll').read_bytes(), b'dxvk')
            self.assertFalse((headless/'old'/'gone.txt').exists())
            self.assertFalse((game/'d3d9.dll').exists())                 # test games keep native Direct3D 9

    def test_install_copies_the_build_and_replaces_its_cache_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)/'build'
            build.mkdir()
            m = create(64, 64, 3)
            starts(m, [(100, 100), (500, 500)])
            (build/'map mp test.map').write_bytes(m.encode())
            (build/'map.ini').write_text('; test\n')
            (build/'notes.txt').write_text('not for the game')
            project = SimpleNamespace(id='test', title='Test', description='', native_name='map mp test',
                                      build_dir=build, map_file=build/'map mp test.map')
            with mock.patch.object(runtime, 'MOD', Path(folder)/'mod'):
                self.assertEqual(runtime.install(project), 'maps\\map mp test.map')
                runtime.install(project)
                maps = Path(folder)/'mod'/'maps'
                self.assertEqual(sorted(p.name for p in (maps/'map mp test').iterdir()), ['map mp test.map', 'map.ini'])
                cache = (maps/'mapcache.ini').read_text(encoding='cp1252')
                self.assertEqual(cache.count('MapCache maps_5Cmap_20mp_20test_5Cmap_20mp_20test_2Emap'), 1)
                self.assertIn('numPlayers = 2', cache)


if __name__ == '__main__':
    unittest.main()
