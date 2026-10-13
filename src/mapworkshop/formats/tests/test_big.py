import pathlib
import struct
import sys
import tempfile
import unittest
from mapworkshop.formats.big import BigArchive, block, number, convert


class ImportTests(unittest.TestCase):
    def archive(self, content):
        name=b'data\\ini\\test.ini\0'
        end=16+8+len(name)
        return b'BIG4'+struct.pack('<I',end+len(content))+struct.pack('>II',1,end)+struct.pack('>II',end,len(content))+name+content

    def test_reads_real_layout_and_converts(self):
        ini=b'''#define HP 250\nObject GondorFighter\n Body = ActiveBody ModuleTag\n  MaxHealth = HP\n End\n WeaponSet\n  Weapon = PRIMARY TestSword\n End\nEnd\nObject GondorFighterHorde\n BuildCost = 200\n BuildTime = 20\n Behavior = HordeContain ModuleTag\n  InitialPayload = GondorFighter 15\n End\nEnd\nWeapon TestSword\n AttackRange = 25\n DamageNugget\n  Damage = 40\n End\nEnd\n'''
        with tempfile.TemporaryDirectory() as folder:
            p=pathlib.Path(folder)/'INI.big';p.write_bytes(self.archive(ini));a=BigArchive(p)
            units,missing=convert(a)
            self.assertEqual(units['soldier']['health'],250)
            self.assertEqual(units['soldier']['count'],15)
            self.assertEqual(units['soldier']['damage'],40)
            self.assertIn('GondorArcher',missing)

    def test_rejects_bad_signature_and_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            p=pathlib.Path(folder)/'bad.big';p.write_bytes(b'nope'+bytes(20))
            with self.assertRaises(ValueError):BigArchive(p)
            data=bytearray(self.archive(b'hello'));data[16:20]=struct.pack('>I',999999);p.write_bytes(data)
            with self.assertRaises(ValueError):BigArchive(p)

    def test_constants_are_not_executed_and_cycles_rejected(self):
        self.assertEqual(number('A',{'A':'B','B':'30'}),30)
        self.assertIsNone(number('A',{'A':'B','B':'A'}))
        self.assertIsNone(number('__import__("os")',{}))

    def test_block_preserves_nested_ends(self):
        text='Object Test\n Body = ActiveBody\n  MaxHealth = 100\n End\n Cost = 10\nEnd\nObject Other\nEnd'
        self.assertIn('Cost = 10',block(text,'Object','Test'))
        self.assertNotIn('Other',block(text,'Object','Test'))

if __name__=='__main__':unittest.main()
