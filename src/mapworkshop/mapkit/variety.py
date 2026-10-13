"""Per-object variety that stays put when the rest of the map changes.

Drawing every object's size and rotation from one shared random stream makes
each object's look depend on how many objects were placed before it: an edit
that adds or skips one placement re-rolls everything after it. spot_random
instead seeds a generator from the map's seed and the object itself (template
and position), so an object keeps its look as long as it keeps its place.

    local = spot_random(SEED, template, x, y)
    angle = local.random() * math.tau
    scale = local.triangular(.8, 1.25, 1.)
"""
import hashlib
import random


def spot_random(seed, template, x, y):
    """A random.Random for one object: the same seed, template and position
    (to 0.1 map units) always give the same numbers, in any process."""
    key = f'{seed}:{template}:{float(x):.1f}:{float(y):.1f}'.encode()
    return random.Random(int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), 'little'))
