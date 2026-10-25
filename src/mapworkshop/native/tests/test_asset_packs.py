"""Cosmetic packs resolve once for both viewer scenes and game launches."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mapworkshop.native import openbfme


class AssetPackTests(unittest.TestCase):
    def test_relative_folders_resolve_from_the_workspace_in_configured_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('first', 'second'):
                (root/name).mkdir()
            with mock.patch.object(openbfme, 'ROOT', root), \
                    mock.patch.object(openbfme, 'setting', return_value=['second', 'first']):
                self.assertEqual(openbfme.asset_packs(), [str((root/name).resolve()) for name in ('second', 'first')])

    def test_invalid_or_missing_packs_fail_instead_of_silently_using_retail(self):
        for value in ('a/folder', [7], ['folder-that-does-not-exist']):
            with self.subTest(value=value), mock.patch.object(openbfme, 'setting', return_value=value):
                with self.assertRaises(ValueError):
                    openbfme.asset_packs()

    def test_game_launch_uses_the_same_packs_as_the_viewer(self):
        packs = ['C:/Art packs/First', 'D:/Second']
        with mock.patch.object(openbfme, 'prepare', return_value=('godot', 'console', {}, None)), \
                mock.patch.object(openbfme, 'asset_packs', return_value=packs), \
                mock.patch.object(openbfme.subprocess, 'Popen') as spawn:
            openbfme.play(None)
        self.assertEqual(spawn.call_args.args[0][-2:], [f'--asset-pack={p}' for p in packs])
