"""render.effects: emitter and particle-system evaluation, without a GPU or game data."""
import struct
import unittest

import numpy as np

from mapworkshop.render.effects import (_integrate, _interp, emitter_particles, motion, parse_emitter, parse_systems,
                                        particle_bones, prepare_system, system_particles)

CAMPFIRE = """
FXParticleSystem Embers
  System
    Priority = MEDIUM_OR_ABOVE
    ParticleName = EXEmbersLight.tga
    Lifetime = 35 50
    Size = 1 1
    BurstDelay = 5 10
    BurstCount = 1 1
  End
  Color = DefaultColor
    Color1 = R:255 G:185 B:79 0
    Color2 = R:0 G:0 B:0 100
  End
  Update = DefaultUpdate
    SizeRate = 4 8
    SizeRateDamping = 0.65 0.8
  End
  Physics = DefaultPhysics
    Gravity = 0.008
    VelocityDamping = 0.95 0.99
    DriftVelocity = X:0 Y:0 Z:0.64
  End
  EmissionVelocity = OrthoEmissionVelocity
    Z = -0.4 0.4
  End
  EmissionVolume = LineEmissionVolume
    StartPoint = X:0 Y:0 Z:3
    EndPoint = X:0 Y:0 Z:3
  End
  Draw = DefaultDraw
  End
End

FXParticleSystem Flare
  System
    ParticleName = EXexplo01.tga
    Lifetime = 45 50
    SystemLifetime = 50
  End
End

FXParticleSystem Streaks
  System
    ParticleName = EXStreak.tga
  End
  Draw = StreakDraw
  End
End
"""


def emitter_chunk(rate=10.0, lifetime=2.0, colors=((0.0, (255, 0, 0)), (1.0, (0, 0, 255)))):
    """A version-2 W3D_CHUNK_EMITTER with additive blending and an 8x8 frame grid."""
    def chunk(kind, payload):
        return struct.pack('<II', kind, len(payload)) + payload
    header = chunk(0x501, struct.pack('<I', 0x20000) + b'E_Test'.ljust(16, b'\0'))
    info = bytearray(260 + 64)
    info[:13] = b'e_master.tga\0'
    struct.pack_into('<10f', info, 260, 0, 0, lifetime, rate, 0, 0, 0, 0, 0, 0)
    struct.pack_into('<3f', info, 300, 0, 0, 5)             # velocity: up 5 units/s
    shader = bytes([3, 0, 0, 1, 0, 0, 0, 1, 1] + [0]*7)       # ONE, ONE
    v2 = struct.pack('<I', 1) + struct.pack('<I3f16x', 0, 0, 0, 0) + struct.pack('<I3f16x', 0, 0, 0, 0)
    v2 += struct.pack('<2f', 0, 0) + shader + struct.pack('<2I', 0, 3) + bytes(24)
    props = struct.pack('<3I', len(colors), 1, 1) + bytes(4) + struct.pack('<2f', 0, 0) + bytes(16)
    for t, rgb in colors:
        props += struct.pack('<f', t) + bytes(rgb) + b'\0'
    props += struct.pack('<2f', 0, 1) + struct.pack('<2f', 0, 2)
    frames = struct.pack('<If2I', 0, 0, 0, 0) + struct.pack('<2f', 0, 5)
    body = header + chunk(0x503, bytes(info)) + chunk(0x504, v2) + chunk(0x505, props) + chunk(0x50b, frames)
    return chunk(0x500, body)


class KeyframeTests(unittest.TestCase):
    def test_interp_is_constant_outside_the_keys(self):
        x = np.array([-1.0, 0.0, 5.0, 10.0, 20.0])
        out = _interp(x, [0, 10], [[0.0], [1.0]])[:, 0]
        np.testing.assert_allclose(out, [0, 0, .5, 1, 1])

    def test_integrate_piecewise_linear_rate(self):
        # Rate 1 until t=2, then rising to 3 at t=4, constant after.
        x = np.array([1.0, 2.0, 4.0, 5.0])
        np.testing.assert_allclose(_integrate(x, [0, 2, 4], [1, 1, 3]), [1, 2, 6, 9])


class MotionTests(unittest.TestCase):
    def test_closed_form_matches_particle_update(self):
        p0, v0 = np.array([[1.0, 2.0, 3.0]]), np.array([[0.5, -0.2, 0.3]])
        drift, gravity = np.array([0.0, 0.1, 0.64]), 0.008
        for damping in (0.95, 1.0):
            pos, vel = p0[0].copy(), v0[0].copy()
            for n in range(1, 41):
                vel = (vel + (0, 0, gravity))*damping
                pos = pos + vel + drift
                got = motion(p0, v0, [damping], gravity, drift, [n])[0]
                np.testing.assert_allclose(got, pos, rtol=1e-9, atol=1e-9)


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.systems = parse_systems(CAMPFIRE)

    def test_parse_and_prepare(self):
        s, reason = prepare_system(self.systems['embers'])
        self.assertIsNone(reason)
        self.assertEqual(s['texture'], 'EXEmbersLight.tga')
        self.assertEqual(s['lifetime'], (35.0, 50.0))
        self.assertEqual(s['blend'], ('one', 'one'))          # ADDITIVE is the default shader
        self.assertEqual(len(s['colors']), 2)
        np.testing.assert_allclose(s['drift'], [0, 0, .64])
        self.assertEqual(prepare_system(self.systems['streaks']), (None, 'draw StreakDraw'))

    def test_steady_state_is_reproducible_and_rising(self):
        s, _ = prepare_system(self.systems['embers'])
        origins, angles, seeds = np.zeros((3, 3)), np.zeros(3), np.array([1, 2, 3])
        a = system_particles(s, origins, angles, seeds, 1.5)
        b = system_particles(s, origins, angles, seeds, 1.5)
        np.testing.assert_array_equal(a, b)
        # One particle every 8.5 frames living 35-50 frames: 4-6 per fire.
        self.assertTrue(3*4 <= len(a) <= 3*6, len(a))
        self.assertTrue((a[:, 2] >= 3 - 1).all())               # drift carries them up
        self.assertTrue(((a[:, 4:8] >= 0) & (a[:, 4:8] <= 1)).all())

    def test_stopped_systems_draw_nothing(self):
        s, _ = prepare_system(self.systems['flare'])
        self.assertIsNone(system_particles(s, np.zeros((1, 3)), np.zeros(1), np.array([1]), 0.0))


class EmitterTests(unittest.TestCase):
    def test_parse(self):
        e = parse_emitter(emitter_chunk())
        self.assertEqual(e['texture'], 'e_master.tga')
        self.assertEqual(e['blend'], ('one', 'one'))
        self.assertEqual((e['lifetime'], e['rate'], e['frame_mode']), (2.0, 10.0, 3))
        np.testing.assert_allclose(e['color']['times'], [0, 1])
        np.testing.assert_allclose(e['frame']['values'], [[5]])

    def test_particles_follow_keyframes(self):
        e = parse_emitter(emitter_chunk())
        rows = emitter_particles(e, np.zeros((1, 3)), np.eye(3)[None], np.ones(1), np.array([4]), 0.0)
        # One emission every 100 ms for 2 s.
        self.assertIn(len(rows), (19, 20, 21))
        age = rows[:, 2]/5.0                                  # rising at 5 units/s
        np.testing.assert_allclose(rows[:, 4], np.clip(1 - age, 0, 1), atol=1e-4)    # red fades by 1 s
        np.testing.assert_allclose(rows[:, 6], np.clip(age, 0, 1), atol=1e-4)
        np.testing.assert_allclose(rows[:, 3], 2.0)           # size key
        # Frame 5 of an 8x8 grid: column 5 of the top row.
        np.testing.assert_allclose(rows[0, 9:12], [5/8, 0, 1/8])


class BoneTests(unittest.TestCase):
    def test_default_and_idle_states_with_nested_blocks(self):
        body = """
  Draw = W3DScriptedModelDraw ModuleTag_01
    DefaultModelConditionState
      Model = PBonFire
      ParticleSysBone = emberBone Glow
    End
    IdleAnimationState
      Animation = Idle
        AnimationName = PBonFire.Idle
      End
      ParticleSysBone emberBone Smoke FollowBone:Yes
    End
    ModelConditionState = DAMAGED
      ParticleSysBone = Bone1 Burning
    End
  End
"""

        class Assets:
            templates = {'bonfire': dict(body=body, parent=None), 'reskin': dict(body='', parent='bonfire')}
        self.assertEqual(particle_bones(Assets, 'Bonfire'), [('emberbone', 'Glow'), ('emberbone', 'Smoke')])
        self.assertEqual(particle_bones(Assets, 'Reskin'), [('emberbone', 'Glow'), ('emberbone', 'Smoke')])


if __name__ == '__main__':
    unittest.main()
