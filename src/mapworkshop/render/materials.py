"""Textures and compiled effects for the renderer (MaterialsMixin): the texture
cache, alpha bleeding before mipmapping, the terrain's texture array and .fxo
effects. Part of render.engine.MapRenderer, whose state it shares.
"""
from collections import OrderedDict
import struct

from PIL import Image
import numpy as np


class TextureCache(OrderedDict):
    """Bound cached texture ownership; live batches retain their own references."""
    def __init__(self, budget=256*1024*1024):
        super().__init__()
        self.budget, self.bytes = budget, 0

    @staticmethod
    def cost(texture):
        return int(texture.width*texture.height*texture.components*4/3) if texture is not None else 0

    def __getitem__(self, key):
        texture = super().__getitem__(key)
        self.move_to_end(key)
        return texture

    def __setitem__(self, key, texture):
        if key in self:
            self.bytes -= self.cost(super().__getitem__(key))
        super().__setitem__(key, texture)
        self.move_to_end(key)
        self.bytes += self.cost(texture)
        while len(self) > 1 and (self.bytes > self.budget or len(self) > 1024):
            _, evicted = self.popitem(last=False)
            self.bytes -= self.cost(evicted)

def bleed_alpha(image):
    """Fill transparent texels with nearby opaque colour before mipmapping.

    Retail DDS files ship their own mip chains; regenerating mips from the top
    level would otherwise average hidden (often white) texels into foliage.
    """
    alpha = image[..., 3]
    if alpha.min() >= 250:
        return image
    rgb = image[..., :3].astype(np.float32)
    weight = (alpha > 127).astype(np.float32)
    if weight.sum() == 0:
        return image
    out = image.copy()
    filled = rgb*weight[..., None]
    total = weight.copy()
    for radius in (1, 2, 4, 8, 16, 32, 64):
        blur = lambda a: sum(np.roll(np.roll(a, dy, 0), dx, 1) for dy in (-radius, 0, radius) for dx in (-radius, 0, radius))
        filled, total = blur(filled), blur(total)
        missing = (weight == 0) & (total > 0)
        out[..., :3][missing] = (filled[missing]/total[missing, None]).astype(np.uint8)
        weight = np.maximum(weight, (total > 0).astype(np.float32))
        filled = out[..., :3].astype(np.float32)*weight[..., None]
        total = weight.copy()
        if weight.min() > 0:
            break
    return out

ARRAY_SIZE = 512


class MaterialsMixin:
    """MapRenderer's textures and compiled effects: images read once with their alpha bled
    (bleed_alpha), mipmapped object textures, the terrain's texture array, .fxo effects."""

    # Terrain ----------------------------------------------------------------
    @staticmethod
    def _texture_pixels(images):
        layers = []
        for image in images:
            # Resize colour and alpha separately: Pillow premultiplies RGBA,
            # which would turn texels with zero alpha black.
            rgb = Image.fromarray(np.ascontiguousarray(image[..., :3])).resize((ARRAY_SIZE, ARRAY_SIZE), Image.Resampling.LANCZOS)
            alpha = Image.fromarray(np.ascontiguousarray(image[..., 3])).resize((ARRAY_SIZE, ARRAY_SIZE), Image.Resampling.LANCZOS)
            layers.append(np.dstack([np.asarray(rgb), np.asarray(alpha)]))
        return np.stack(layers).astype(np.uint8)

    def _texture_array(self, data):
        texture = self.ctx.texture_array((ARRAY_SIZE, ARRAY_SIZE, len(data)), 4, data.tobytes())
        texture.build_mipmaps()
        texture.filter = (self.moderngl.LINEAR_MIPMAP_LINEAR, self.moderngl.LINEAR)
        texture.repeat_x = texture.repeat_y = True
        texture.anisotropy = 16.0
        return texture

    def _prepare_image(self, name):
        if name and name.lower() not in self._images:
            image = self.assets.image(name)
            self._images[name.lower()] = bleed_alpha(image) if image is not None else None

    def _plain_texture(self, name, fallback=None, raw=False):
        """A mipmapped texture. `raw` keeps the colour under transparent
        texels (additive materials draw it), skipping bleed_alpha."""
        if raw:
            image = self.assets.image(name) if name else None
        else:
            self._prepare_image(name)
            image = self._images.get(name.lower()) if name else None
        if image is None:
            return fallback
        texture = self.ctx.texture((image.shape[1], image.shape[0]), 4, np.ascontiguousarray(image).tobytes())
        texture.build_mipmaps()
        texture.filter = (self.moderngl.LINEAR_MIPMAP_LINEAR, self.moderngl.LINEAR)
        texture.anisotropy = 8.0
        texture.repeat_x = texture.repeat_y = True
        return texture

    # Objects ----------------------------------------------------------------
    def _object_texture(self, name, raw=False):
        key = ('raw:' if raw else '') + name.lower()
        if key not in self.textures:
            texture = self._plain_texture(name, raw=raw)
            if texture is None and name:
                self.report['missing_textures'].append(name)
            self.textures[key] = texture
        return self.textures[key]

    def _effect(self, name):
        """Compiled effect (Shaders/Compiled/<name>o) parsed by formats.fxo."""
        from mapworkshop.formats.fxo import Effect
        if not name:
            return None
        key = 'shaders/compiled/' + name.lower() + 'o'
        if key in self._effects:
            return self._effects[key]
        if not self.assets.exists(key):
            self._effects[key] = None
            return None
        try:
            effect = Effect(self.assets.read(key))
        except (ValueError, struct.error):
            effect = None
        self._effects[key] = effect
        return effect
