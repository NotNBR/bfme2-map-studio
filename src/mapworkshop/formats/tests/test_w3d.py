"""Format-level checks independent of retail BFME files."""
import math
import pathlib
import struct
import sys
import tempfile
import unittest
import numpy as np

from mapworkshop.formats.w3d import channels, chunks, decode_delta, interpolate, matrix, pose, recoil_pose


def chunk(kind, payload):
    return struct.pack('<II', kind, len(payload)) + payload


def name(text):
    return text.encode().ljust(16, b'\0')


class Animations(unittest.TestCase):
    # Two bones: a root, and an arm 10 along X from it.
    BONES = [dict(name='root', parent=-1, local=np.eye(4)), dict(name='arm', parent=0, local=matrix([10, 0, 0], [0, 0, 0, 1]))]
    QUARTER = [0, 0, math.sin(math.pi/4), math.cos(math.pi/4)]    # 90 degrees about Z

    def compressed(self):
        header = struct.pack('<I', 1) + name('wave') + name('skel') + struct.pack('<IHH', 30, 30, 0)
        # Timecoded: count, pivot, vector length, type; time code and value pairs
        # (the top bit of a time code: no interpolation).
        rise = struct.pack('<IHBB', 2, 1, 1, 2) + struct.pack('<If', 0, 4.0) + struct.pack('<If', 0x80000000 | 10, 8.0)
        turn = struct.pack('<IHBB', 1, 0, 4, 6) + struct.pack('<I4f', 0, *self.QUARTER)
        return chunk(0x280, chunk(0x281, header) + chunk(0x282, rise) + chunk(0x282, turn))

    def test_timecoded_channels(self):
        info, motion = channels(self.compressed())
        self.assertEqual((info['name'], info['hierarchy'], info['frames'], info['fps']), ('wave', 'skel', 30, 30))
        (pivot, channel, times, values), _ = motion
        self.assertEqual((pivot, channel), (1, 2))
        np.testing.assert_array_equal(times, [0, 10])
        np.testing.assert_allclose(values[:, 0], [4, 8])

    def test_uncompressed_channels(self):
        header = struct.pack('<I', 1) + name('wave') + name('skel') + struct.pack('<II', 3, 15)
        # First and last frame, vector length, type, pivot, padding; a value per frame.
        move = struct.pack('<6H', 0, 2, 1, 0, 1, 0) + struct.pack('<3f', 1, 2, 3)
        info, motion = channels(chunk(0x200, chunk(0x201, header) + chunk(0x202, move)))
        self.assertEqual((info['frames'], info['fps']), (3, 15))
        np.testing.assert_allclose(motion[0][3][:, 0], [1, 2, 3])

    def test_pose_turns_the_root_and_moves_the_arm(self):
        bones, world = pose(self.compressed(), lambda hierarchy: self.BONES, frame=5)
        self.assertIs(bones, self.BONES)
        # The root turns a quarter: the arm's 10 along X now lies along Y,
        # raised half way from 4 to 8 at frame 5.
        np.testing.assert_allclose(world[1][:3, 3], [0, 10, 6], atol=1e-9)


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
