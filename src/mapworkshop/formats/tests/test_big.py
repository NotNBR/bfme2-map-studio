import pathlib
import struct
import sys
import tempfile
import unittest
from mapworkshop.formats.big import BigArchive, number


class ImportTests(unittest.TestCase):
    def archive(self, content):
        name=b'data\\ini\\test.ini\0'
        end=16+8+len(name)
        return b'BIG4'+struct.pack('<I',end+len(content))+struct.pack('>II',1,end)+struct.pack('>II',end,len(content))+name+content

    def test_rejects_bad_signature_and_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            p=pathlib.Path(folder)/'bad.big';p.write_bytes(b'nope'+bytes(20))
            with self.assertRaises(ValueError):BigArchive(p)
            data=bytearray(self.archive(b'hello'));data[16:20]=struct.pack('>I',999999);p.write_bytes(data)
            with self.assertRaises(ValueError):BigArchive(p)

    def test_directory_entries_and_unterminated_paths(self):
        names=[b'Art\\A.tga\0',b'data\\b.ini\0']
        end=16+sum(8+len(n) for n in names)
        directory=b''.join(struct.pack('>II',end+i*3,3)+n for i,n in enumerate(names))
        data=b'BIG4'+struct.pack('<I',end+6)+struct.pack('>II',2,end)+directory+b'abcdef'
        with tempfile.TemporaryDirectory() as folder:
            p=pathlib.Path(folder)/'two.big';p.write_bytes(data)
            a=BigArchive(p)
            self.assertEqual(a.entries,{'art/a.tga':(end,3),'data/b.ini':(end+3,3)})
            self.assertEqual(a.read_bytes('data/b.ini'),b'def')
            p=pathlib.Path(folder)/'open.big'
            p.write_bytes(data[:end-1]+b'x'+data[end:])      # the last path runs into the payload
            with self.assertRaises(ValueError):BigArchive(p)

    def test_constants_are_not_executed_and_cycles_rejected(self):
        self.assertEqual(number('A',{'A':'B','B':'30'}),30)
        self.assertIsNone(number('A',{'A':'B','B':'A'}))
        self.assertIsNone(number('__import__("os")',{}))

if __name__=='__main__':unittest.main()
