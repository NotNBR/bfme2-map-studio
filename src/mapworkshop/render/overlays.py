"""Overlays the renderer draws over the map (OverlaysMixin): the local walkability
estimate (mapkit.pathing, mapkit.walkable). Part of render.engine.MapRenderer,
whose state it shares.
"""
import numpy as np

from mapworkshop.assets.models import ModelCache


class OverlaysMixin:
    """MapRenderer's walkability overlay: computed on a worker (CPU only), installed
    as a texture on the thread that owns the context."""

    def walkable_overlay(self):
        """Local walkability as an overlay texture and its world extent.
        self.walkable holds the analysis: categories and cut-off areas."""
        if not hasattr(self, '_walk'):
            self.install_walkability(self.compute_walkability())
        return self._walk

    def compute_walkability(self):
        """CPU-only analysis; do not mutate the live renderer on a worker."""
        from mapworkshop.mapkit import pathing, walkable
        models = ModelCache(self.pathing_assets)
        models.cache = dict(self.model_cache.cache)
        grid = pathing.compute(self.map, assets=self.pathing_assets, map_ini=self.map_ini, models=models)
        result = walkable.analyse(grid, self.map)
        result['info'] = grid['info']
        return result, np.ascontiguousarray(walkable.overlay(result))

    def walkability_task(self):
        """Capture CPU data only; a worker must never own live GPU resources."""
        from functools import partial
        from types import SimpleNamespace
        data = SimpleNamespace(map=self.map, pathing_assets=self.pathing_assets,
                               map_ini=self.map_ini, model_cache=self.model_cache)
        return partial(OverlaysMixin.compute_walkability, data)

    def install_walkability(self, prepared):
        """Install a worker result on the context-owning thread."""
        from mapworkshop.mapkit import walkable
        self.walkable, rgba = prepared
        h, w = rgba.shape[:2]
        texture = self.ctx.texture((w, h), 4, rgba.tobytes())
        texture.filter = (self.moderngl.NEAREST, self.moderngl.NEAREST)
        texture.repeat_x = texture.repeat_y = False
        self._walk = (texture, (w*walkable.CELL, h*walkable.CELL))
