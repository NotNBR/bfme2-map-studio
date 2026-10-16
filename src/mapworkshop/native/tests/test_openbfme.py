"""OpenBFME's parts that need neither the engine nor the game: the archives
it mounts, the merged map cache, the launcher's pins and gathering game files."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from mapworkshop.formats.big import BigArchive
from mapworkshop.native import openbfme


def md5(data):
    return hashlib.md5(data).hexdigest()


class BigTests(unittest.TestCase):
    def test_written_archive_reads_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'map.ini'
            source.write_bytes(b'Weather\nEnd\n')
            path = openbfme.write_big(Path(tmp)/'a.big', [('maps/mapcache.ini', b'; cache\r\n'),
                                                           ('maps/m/map.ini', source)])
            archive = BigArchive(path)
            self.assertEqual(set(archive.entries), {'maps/mapcache.ini', 'maps/m/map.ini'})
            self.assertEqual(archive.read_bytes('maps/mapcache.ini'), b'; cache\r\n')
            self.assertEqual(archive.read_bytes('maps/m/map.ini'), b'Weather\nEnd\n')
            self.assertEqual(path.read_bytes()[:4], b'BIG4')
            self.assertFalse((Path(tmp)/'a.big.part').exists())


class CacheTests(unittest.TestCase):
    def test_entries_replace_their_key_and_keep_the_rest(self):
        retail = ('; FILE\r\nMapCache maps_5Ca\r\n  numPlayers = 2\r\nEND\r\n\r\n'
                  'MapCache maps_5Cb\r\n  numPlayers = 4\r\nEND\r\n')
        merged = openbfme.merged_cache(retail, ['MapCache maps_5Cb\n  numPlayers = 8\nEND\n',
                                                'MapCache maps_5Cc\n  numPlayers = 2\nEND\n'])
        self.assertNotIn('\r', merged)
        self.assertIn('MapCache maps_5Ca\n  numPlayers = 2\nEND', merged)
        self.assertEqual(merged.count('MapCache maps_5Cb'), 1)
        self.assertIn('MapCache maps_5Cb\n  numPlayers = 8\nEND', merged)
        self.assertTrue(merged.rstrip().endswith('MapCache maps_5Cc\n  numPlayers = 2\nEND'))


class PinTests(unittest.TestCase):
    def test_packages_owner_and_files(self):
        text = ('const PACKAGES := [\n'
                '\t{"key": "rotwk", "guid": "original-RotWK", "owner": "bdc6bc60-73f9-4833-9069-3076aff26418", "files": [\n'
                '\t\t["Data1.big", "ee5c0791c75a55a5123d0c21b5fd680f", 625668],\n'
                '\t\t["data/cursors/Beam.ani", "bc39ef7ee099e6815ca867b166737e9d", 3458],\n'
                '\t]},\n'
                '\t{"key": "bfme2", "guid": "original-BFME2", "owner": "0000aaaa-0000-0000-0000-000000000000", "files": [\n'
                '\t\t["INI.big", "2f24887ba2b0c1d210bc7bc2d6c62c31", 29034678],\n'
                '\t]},\n]\n')
        found = openbfme.pins(text)
        self.assertEqual(found['rotwk'][0], 'bdc6bc60-73f9-4833-9069-3076aff26418')
        self.assertEqual(found['rotwk'][1][1], ('data/cursors/Beam.ani', 'bc39ef7ee099e6815ca867b166737e9d', 3458))
        self.assertEqual(found['bfme2'][1], [('INI.big', '2f24887ba2b0c1d210bc7bc2d6c62c31', 29034678)])


class GatherTests(unittest.TestCase):
    def test_links_matching_files_and_reports_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            modded, clean, target = tmp/'modded', tmp/'clean', tmp/'assets'
            for folder, data in ((modded, b'mod'), (clean, b'retail')):
                (folder/'apt').mkdir(parents=True)
                (folder/'Data1.big').write_bytes(data)
                (folder/'apt'/'x.big').write_bytes(data)
            files = [('Data1.big', md5(b'retail'), 6), ('apt/x.big', md5(b'retail'), 6), ('Gone.big', md5(b'gone'), 4)]
            hashes = openbfme.Hashes(tmp/'md5.json')
            missing = openbfme.gather(files, target, [modded, clean], hashes)
            self.assertEqual(missing, [('Gone.big', md5(b'gone'), 4)])
            self.assertEqual((target/'Data1.big').read_bytes(), b'retail')
            self.assertEqual((target/'apt'/'x.big').read_bytes(), b'retail')
            fetched = []
            def fetch(path, digest, destination):
                fetched.append(path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b'gone')
            self.assertEqual(openbfme.gather(files, target, [modded], hashes, fetch, progress=lambda *_: None), [])
            self.assertEqual(fetched, ['Gone.big'])              # the others are kept
            hashes.save()
            self.assertEqual(openbfme.Hashes(tmp/'md5.json').known, hashes.known)


if __name__ == '__main__':
    unittest.main()
