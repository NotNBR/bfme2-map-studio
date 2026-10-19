"""Sky domes for the renderer (SkyMixin). Part of render.engine.MapRenderer, whose
state it shares.
"""
import numpy as np


class SkyMixin:
    """MapRenderer's sky domes: their texture (the weather's or the sun's), the horizon
    colour below them, and drawing them before the terrain."""

    def _apply_sky(self):
        """Give the map's sky domes the sun's or the weather preset's sky
        texture (all WaterReflectionSkydome models share one dome), or their
        own without either."""
        from mapworkshop.mapkit.weather import PRESETS, SUNS, sky_texture
        sky = (SUNS[self.sun].get('sky') if self.sun else None) or \
              (PRESETS[self.weather_preset].get('sky') if self.weather_preset else None)
        for batch in getattr(self, 'batches', []):
            if 'sky_own' not in batch:
                continue
            texture, name = batch['sky_own']
            if sky:
                swapped = self._object_texture(sky_texture(sky))
                if swapped is not None:
                    texture, name = swapped, sky_texture(sky)
            batch['texture'] = texture
            self.sky_horizon = self._horizon_color(name, batch['sky_rim_uv']) or self.sky_horizon
            batch['uniforms']['sky_horizon'] = self.sky_horizon or (0.0, 0.0, 0.0)
            batch.pop('_binding', None)          # _bind_batch works its uniforms out again

    def _horizon_color(self, name, uv):
        """Mean colour of texture `name` along a sky dome's rim (`uv`): the
        background below the dome (seen past the map's edge) is cleared to it."""
        image = self.assets.image(name) if name else None
        if image is None:
            return None
        image = np.asarray(image)
        h, w = image.shape[:2]
        x = np.clip((uv[:, 0]*(w-1)).astype(int), 0, w-1)
        y = np.clip(((1.0-uv[:, 1])*(h-1)).astype(int), 0, h-1)
        return tuple(float(c)/255 for c in image[y, x, :3].mean(0))

    def _draw_sky(self, batches, vp, eye):
        """Sky domes (simple.fx, unlit), drawn before the terrain."""
        ctx, mgl = self.ctx, self.moderngl
        op = self.object_program
        op['view_projection'].write(vp)
        op['eye'].value = eye
        op['use_shadows'].value = 0
        ctx.enable(mgl.DEPTH_TEST)
        self._begin_batches()
        for batch in batches:
            if batch['cull']:
                ctx.enable(mgl.CULL_FACE)
            self._bind_batch(op, batch)
            if 'sky_horizon' in op:
                self._put(op, 'sky_horizon', self._horizon())
            batch['vao'].render(mgl.TRIANGLES, instances=batch['count'])
            ctx.disable(mgl.CULL_FACE)

    def _horizon(self):
        """Colour the sky dome's rim and the background below it fade to:
        the fog colour while fog is on (the fogged land fades there too),
        else the dome's own rim colour."""
        w = self.weather
        if w['hardwarefogenable'] and self.visible['weather']:
            return tuple(float(c) for c in w['hardwarefogcolor'])
        return self.sky_horizon
