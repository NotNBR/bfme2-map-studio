"""Runtime packaging, compatibility failures and running without engine source."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mapworkshop.native import engine_adapter, engine_bundle, openbfme


def fixture(root):
    """Small synthetic runtime; no engine or game assets needed."""
    root = Path(root)
    source, project = root/'source', root/'project'
    files = {'godot/project.godot': 'config_version=5',
             'godot/openbfme.gdextension': '[configuration]',
             'godot/shaders/terrain.gdshader': '#include "res://shaders/common.gdshaderinc"',
             'godot/shaders/common.gdshaderinc': '#include "res://shaders/nested.gdshaderinc"',
             'godot/shaders/nested.gdshaderinc': '',
             **{f'godot/shaders/{s}.gdshader': '' for s in engine_adapter.SHADERS[1:]},
             **{f'godot/{name}': '' for name in engine_adapter.RESOURCES},
             'launcher/scripts/core/aio_pins.gd': 'const PACKAGES := [\n{"key": "rotwk", "owner": "abcdef", "files": []}]',
             'engine/data/retail-archives/rotwk-201-english-archives.json': '{"archives": []}',
             'engine/data/retail-archives/bfme2-106-english-archives.json': '{"archives": []}',
             'LICENSE': 'test license'}
    for name, text in files.items():
        path = source/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    (project/engine_adapter.DLL).parent.mkdir(parents=True)
    (project/engine_adapter.DLL).write_bytes(b'extension')
    for name in ('godot.exe', 'godot.console.exe', 'openbfme_peer.exe'):
        (root/name).write_bytes(name.encode())
    return engine_adapter.package(source, project, root/'openbfme_peer.exe',
                                  (root/'godot.exe', root/'godot.console.exe'), list(files), root/'cache',
                                  revision='a'*40, source_stamp='test')


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = fixture(self.root)

    def load(self, **kwargs):
        return engine_bundle.load(self.bundle.root, check_host=False, **kwargs)

    def edit_manifest(self, change):
        path = self.bundle.root/engine_bundle.MANIFEST
        data = json.loads(path.read_text(encoding='utf-8'))
        change(data)
        path.write_text(json.dumps(data), encoding='utf-8')

    def test_payload_is_complete_and_game_and_viewer_share_bytes(self):
        bundle = self.load(expected_revision='a'*40)
        self.assertEqual(bundle.file('game', engine_adapter.DLL), bundle.file('viewer', engine_adapter.DLL))
        self.assertIn('shaders/nested.gdshaderinc', bundle.files('viewer'))
        self.assertEqual(bundle.file('tools', 'openbfme_peer.exe').read_bytes(), b'openbfme_peer.exe')
        self.assertNotIn('project.godot', bundle.files('viewer'))
        self.assertFalse(any('.godot' in p.parts for p in bundle.root.rglob('*')))

    def test_repack_is_idempotent_and_export_refuses_existing_destination(self):
        groups = {g: self.bundle.files(g) for g in self.bundle.data['groups']}
        before = {p: p.stat().st_mtime_ns for p in self.bundle.root.rglob('*')}
        repacked = engine_bundle.create(self.root/'cache', groups, revision='a'*40,
                                       source_stamp='test', methods=engine_bundle.METHODS)
        self.assertEqual(repacked.root, self.bundle.root)
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in self.bundle.root.rglob('*')})
        with self.assertRaisesRegex(RuntimeError, 'already exists'):
            engine_bundle.create(self.root/'cache', groups, revision='a'*40, source_stamp='test',
                                 methods=engine_bundle.METHODS, destination=self.bundle.root)

    def test_hash_mismatch_fails_even_with_same_file_size(self):
        self.bundle.file('viewer', engine_adapter.DLL).write_bytes(b'wrong-dll')
        with self.assertRaisesRegex(RuntimeError, 'missing or changed'):
            self.load()

    def test_wrong_revision_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'differs from Studio'):
            self.load(expected_revision='b'*40)

    def test_source_archive_has_no_git_requirement_for_bundle_selection(self):
        with mock.patch.object(openbfme, 'ROOT', self.root), \
                mock.patch.object(openbfme, '_git', side_effect=AssertionError('Git used')):
            self.assertIsNone(openbfme.recorded())

    def test_switching_back_to_source_rebuilds_instead_of_reusing_bundle_binary(self):
        project, build = self.root/'switch-project', self.root/'switch-build'
        project.mkdir()
        build.mkdir()
        (project/openbfme.DLL).parent.mkdir(parents=True)
        (project/openbfme.DLL).write_bytes(b'bundled')
        (project/openbfme.BUNDLE_MARKER).write_text('{}', encoding='utf-8')
        (build/'stamp.txt').write_text('current', encoding='utf-8')
        def compile_engine(*args):
            self.assertFalse((build/'stamp.txt').exists())
            (project/openbfme.DLL).write_bytes(b'from source')
        with mock.patch.multiple(openbfme, PROJECT=project, BUILD=build, LOGS=self.root/'switch-logs',
                                 SOURCE=self.root/'source'), \
                mock.patch.object(openbfme, 'setting', return_value='source'), \
                mock.patch.object(openbfme, 'source'), \
                mock.patch.object(openbfme, 'toolchain', return_value=('llvm', 'gui', 'console')), \
                mock.patch.object(openbfme, '_stamp', return_value='current'), \
                mock.patch.object(openbfme, '_git', return_value='godot/project.godot'), \
                mock.patch.object(openbfme, '_compile', side_effect=compile_engine) as compiled, \
                mock.patch.object(openbfme, '_import'):
            self.assertFalse(openbfme.is_built())
            openbfme.build()
            compiled.assert_called_once()
            self.assertTrue(openbfme.is_built())
            self.assertFalse((project/openbfme.BUNDLE_MARKER).exists())
            self.assertEqual((project/openbfme.DLL).read_bytes(), b'from source')

    def test_incompatible_version_and_missing_capability(self):
        original = (self.bundle.root/engine_bundle.MANIFEST).read_text(encoding='utf-8')
        for key, value in [('format', 2), ('adapter_api', 2), ('godot', '4.6'),
                           ('platform', 'linux'), ('capabilities', []), ('methods', {})]:
            with self.subTest(key=key):
                (self.bundle.root/engine_bundle.MANIFEST).write_text(original, encoding='utf-8')
                self.edit_manifest(lambda data: data.update({key: value}))
                with self.assertRaises(RuntimeError):
                    self.load()

    def test_incomplete_method_contract_is_rejected(self):
        self.edit_manifest(lambda data: data['methods']['GameWorld'].remove('load_map'))
        with self.assertRaisesRegex(RuntimeError, 'GameWorld'):
            self.load()

    def test_path_escape_and_missing_file_are_rejected(self):
        for path in ('../outside', '/absolute', 'C:/absolute', 'game/../outside', 'game\\outside'):
            with self.subTest(path=path):
                with self.assertRaisesRegex(RuntimeError, 'Invalid runtime path'):
                    engine_bundle.contained(self.bundle.root, path)
        self.bundle.file('metadata', 'aio_pins.gd').unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing or changed'):
            self.load()

    def test_shader_include_missing_fails_before_publication(self):
        (self.root/'source/godot/shaders/nested.gdshaderinc').unlink()
        with self.assertRaisesRegex(RuntimeError, 'lacks runtime resource'):
            engine_adapter.viewer_resources(self.root/'source/godot')

    def test_prebuilt_path_needs_no_checkout_compiler_or_download(self):
        with mock.patch.object(openbfme, 'setting', return_value=str(self.bundle.root)), \
                mock.patch.object(openbfme, 'recorded', return_value='a'*40), \
                mock.patch.multiple(engine_bundle.platform, system=lambda: 'Windows', machine=lambda: 'AMD64'), \
                mock.patch.multiple(openbfme, SOURCE=self.root/'absent', PROJECT=self.root/'installed',
                                    LOGS=self.root/'logs', APPDATA=self.root/'appdata'), \
                mock.patch.object(openbfme, 'source', side_effect=AssertionError('source used')), \
                mock.patch.object(openbfme, 'toolchain', side_effect=AssertionError('compiler used')), \
                mock.patch.object(openbfme, '_fetch', side_effect=AssertionError('download used')), \
                mock.patch.object(openbfme, '_import') as imported:
            gui, console = openbfme.build()
            self.assertEqual(gui, self.bundle.file('tools', 'godot.exe'))
            self.assertEqual(console, self.bundle.file('tools', 'godot.console.exe'))
            self.assertEqual(openbfme.peer(), self.bundle.file('tools', 'openbfme_peer.exe'))
            self.assertEqual(openbfme.required(), dict(rotwk=[], bfme2=[]))
            self.assertEqual(openbfme.pins()['rotwk'][0], 'abcdef')
            self.assertTrue(openbfme.is_built())
            imported.assert_called_once()
            self.assertEqual((openbfme.PROJECT/engine_adapter.DLL).read_bytes(), b'extension')


if __name__ == '__main__':
    unittest.main()
