"""Distinct synthetic values catch field-order bugs hidden by uniform lighting."""

import struct
import unittest

from mapworkshop.formats.lighting import decode, encode


class LightingTests(unittest.TestCase):
    def fixture(self, version, shadow=True):
        n = 2 + (2 if version >= 2 else 0) + (2 if version >= 3 else 0) + (3 if version >= 4 else 0)
        data = struct.pack('<I', 4) + struct.pack('<'+'f'*(4*n*9), *range(4*n*9))
        if version >= 5: data += struct.pack('<f', 2.)
        if version >= 6: data += struct.pack('<I3f', 1, .1, .2, .3)
        if version >= 7: data += struct.pack('<6f', .4, .5, .6, .7, .8, .9)
        if shadow: data += struct.pack('<I', 0xff123456)
        if version >= 8: data += struct.pack('<3f', .25, .5, .75)
        return data

    def test_field_order_and_all_version_roundtrips(self):
        for version in range(1, 9):
            data = self.fixture(version)
            result = decode(data, version)
            self.assertEqual(encode(result, version), data)
            self.assertEqual(result['shadow_color_raw'], 0xff123456)
            if version >= 5: self.assertEqual(result['overbright_value'], 2.)
        value = decode(self.fixture(8), 8)
        self.assertEqual([(v['target'], v['light_index']) for v in value['configurations'][0]],
                         [('terrain',0),('objects',0),('objects',1),('objects',2),
                          ('terrain',1),('terrain',2),('third',0),('third',1),('third',2)])
        self.assertEqual(value['configurations'][0][4]['ambient'], (36.,37.,38.))
        self.assertEqual(value['final_values'], (.25,.5,.75))

    def test_optional_old_shadow_and_reject_bad_payload(self):
        for version in range(1, 8):
            data = self.fixture(version, shadow=False)
            self.assertEqual(encode(decode(data, version), version), data)
        with self.assertRaises(ValueError): decode(self.fixture(8, shadow=False), 8)
        with self.assertRaises(ValueError): decode(self.fixture(8)[:-1], 8)
        with self.assertRaises(ValueError): decode(self.fixture(8)+b'\0', 8)
        with self.assertRaises(ValueError): decode(self.fixture(8), 9)
        value = decode(self.fixture(8), 8)
        value['configurations'][0].reverse()
        with self.assertRaises(ValueError): encode(value)

    def test_native_comparison_fails_for_missing_or_swapped_data(self):
        from mapworkshop.mapkit.checks.lighting_check import differences
        value = decode(self.fixture(8), 8)
        native = dict(value)
        native['overbright_enabled'] = True
        native.pop('overbright_value')
        self.assertEqual(differences(value,native),[])
        self.assertEqual(differences(value,None),['lighting'])
        native['shadow_color_raw'] = 0
        self.assertEqual(differences(value,native),['lighting.shadow_color_raw'])


if __name__ == '__main__': unittest.main()
