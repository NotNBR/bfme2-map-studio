"""Format-level checks independent of retail BFME files."""
import math
import pathlib
import struct
import sys
import tempfile
import unittest
import numpy as np

from mapworkshop.formats.w3d import chunks, decode_delta, interpolate, matrix, recoil_pose


class NativeFormats(unittest.TestCase):
    def test_truncated_chunk_is_rejected(self):
        with self.assertRaises(ValueError):
            list(chunks(struct.pack('<II', 1, 5)+b'bad'))

    def test_delta4_signed_nibbles(self):
        # Initial 10; scale 1; table entry 8 = 1. Deltas +1,-2,+7,-8.
        encoded=struct.pack('<ffB',1,10,8)+bytes([0xe1,0x87,0,0,0,0,0,0])
        np.testing.assert_allclose(decode_delta(encoded,5,1,4)[:,0],[10,11,9,16,8])

    def test_delta8_bias(self):
        encoded=struct.pack('<ffB',16,0,8)+bytes([128,129,127]+[128]*13)
        np.testing.assert_allclose(decode_delta(encoded,4,1,8)[:,0],[0,0,1,0])

    def test_quaternion_shortest_arc(self):
        out=interpolate(np.array([0,2]),np.array([[0.,0,0,1],[0,0,0,-1.]]),3,True)
        np.testing.assert_allclose(out,[[0,0,0,1]]*3)

    def test_native_euler_roundtrip(self):
        rng=np.random.default_rng(43)
        for _ in range(100):
            original=matrix([1,2,3],rng.normal(size=4))
            x,y,z=recoil_pose(original)[3:]
            rx=matrix([0,0,0],[math.sin(x/2),0,0,math.cos(x/2)])
            ry=matrix([0,0,0],[0,math.sin(y/2),0,math.cos(y/2)])
            rz=matrix([0,0,0],[0,0,math.sin(z/2),math.cos(z/2)])
            np.testing.assert_allclose((ry@rx@rz)[:3,:3],original[:3,:3],atol=1e-6)


if __name__=='__main__': unittest.main()
