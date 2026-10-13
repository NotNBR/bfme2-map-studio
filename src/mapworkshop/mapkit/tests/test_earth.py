import unittest
import numpy as np
from mapworkshop.mapkit.earth import fbm, thermal_erosion


class EarthTests(unittest.TestCase):
    def test_noise_repeatable_and_seed_changes_landscape(self):
        y,x=np.indices((49,63));x=x*10.;y=y*10.
        a=fbm(x,y,seed=32)
        np.testing.assert_array_equal(a,fbm(x,y,seed=32))
        self.assertGreater(np.std(a-fbm(x,y,seed=33)),.01)
        self.assertTrue(np.isfinite(a).all())

    def test_talus_relaxation_conserves_mass_and_does_not_wrap_edges(self):
        z=np.full((51,57),100.);z[24:27,26:29]=400
        eroded=thermal_erosion(z,12)
        self.assertAlmostEqual(float(eroded.sum()),float(z.sum()),places=6)
        self.assertLess(float(eroded.max()),400)
        self.assertGreater(float(eroded[23,27]),100)
        self.assertEqual(float(eroded[0,0]),100)
        self.assertGreaterEqual(float(eroded.min()),100)

    def test_flat_ground_stays_flat(self):
        z=np.full((20,30),137.)
        np.testing.assert_array_equal(z,thermal_erosion(z))
