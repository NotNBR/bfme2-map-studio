import struct
import unittest

from mapworkshop.formats.castles import decode, encode
from mapworkshop.formats.map import string


class CastleTests(unittest.TestCase):
    def test_all_versions_nonempty_and_ignored_fields_preserved(self):
        for version in range(1,6):
            with self.subTest(version=version):
                data=b'\3\1\0\0'+struct.pack('<I',1)+string('Tower')+string('GondorBattleTower')
                data+=struct.pack('<4f',-12,34,7,.25)
                if version>=4: data+=struct.pack('<2i',40,2)
                if version>=2:
                    data+=struct.pack('<I',1)
                    if version>=5: data+=string('Approach')
                    data+=struct.pack('<I',2)
                    data+=struct.pack('<4f',-20,30,20,30) if version>=3 else struct.pack('<6i',-20,30,7,20,30,8)
                parsed=decode(data,{1:'FactionMen'},version)
                self.assertEqual(parsed['buildings'][0]['position'],(-12,34,7))
                self.assertEqual(encode(parsed,lambda name:1,version),data)
                with self.assertRaises(ValueError): decode(data[:-1],{1:'FactionMen'},version)
        self.assertEqual(parsed['paths'][0]['name'],'Approach')
        self.assertEqual(parsed['buildings'][0]['phase'],2)

    def test_bad_version_or_coordinates_rejected(self):
        with self.assertRaises(ValueError): decode(b'',{},6)
        value=dict(faction='Men',buildings=[dict(building_name='x',template='x',position=(1,2,float('nan')),angle=0)],paths=[])
        with self.assertRaises(ValueError): encode(value,lambda name:1,1)


if __name__=='__main__':unittest.main()
