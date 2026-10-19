"""The renderer's light (LightingMixin): the map's GlobalLighting as the game
applies it to terrain and objects, the object light environment, and weather
switched in place. Part of render.engine.MapRenderer, whose state it shares.
"""
import numpy as np

from mapworkshop.formats.lighting import decode
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.render.camera import _normalize


class LightingMixin:
    """MapRenderer's light: the map's GlobalLighting (terrain, objects, fill lights,
    shadow colour), the object light environment, and set_weather switching it in place."""

    # Lighting ---------------------------------------------------------------
    def _lighting(self):
        chunk = self.map.chunk('GlobalLighting')
        value = decode(chunk.data, chunk.version)
        if self.weather_preset:
            from mapworkshop.mapkit.weather import apply_lighting
            apply_lighting(value, self.weather_preset)
        if self.sun:
            from mapworkshop.mapkit.weather import apply_sun
            apply_sun(value, self.sun)
        config = value['configurations'][max(0, min(3, value['time_of_day']-1))]
        lights = {(l['target'], l['light_index']): l for l in config}
        to_light = lambda l: tuple(-_normalize(l['direction']))
        self.terrain_ambient = lights[('terrain', 0)]['ambient']
        # As GlobalData holds them for drawRiverWater: directions as stored.
        self.terrain_lights = [(tuple(lights[('terrain', i)]['direction']), tuple(lights[('terrain', i)]['diffuse']))
                               for i in range(3)]
        self.time_of_day = value['time_of_day']
        self.sun_dir = to_light(lights[('terrain', 0)])
        self.sun_color = lights[('terrain', 0)]['diffuse']
        self.fills = [(to_light(lights[('terrain', i)]), lights[('terrain', i)]['diffuse']) for i in (1, 2)]
        # Terrain vertex lighting (getStaticDiffuse/doTheLight): rays are the
        # negated GlobalLighting directions as stored, not normalized, and the
        # diffuse colours are scaled by the v8 final values (GlobalData +0x944,
        # applied while the terrain rendering mode is 0).
        scale = value.get('final_values', (1.0, 1.0, 1.0))
        self.terrain_rays = [(tuple(-np.asarray(lights[('terrain', i)]['direction'], float)),
                              tuple(c*s for c, s in zip(lights[('terrain', i)]['diffuse'], scale))) for i in range(3)]
        self.object_ambient = lights[('objects', 0)]['ambient']
        self.object_lights = [(to_light(lights[('objects', i)]), lights[('objects', i)]['diffuse']) for i in range(3)]
        self.overbright = value['overbright_value'] > 1
        # ShaderLOD Low/Medium scale the object and vegetation light
        # environments by the chunk's last three values (1, 1, 1 by default).
        final = tuple(value.get('final_values') or (1.0, 1.0, 1.0))
        self.light_scale = final if self.options['lod'] in ('verylow', 'low', 'medium') else (1.0, 1.0, 1.0)
        self._light_environments = {}         # light_environment's results, for these lights
        raw = value.get('shadow_color_raw', 0xFFA0A0A0)
        self.shadow_color = tuple(((raw >> shift) & 255)/255 for shift in (16, 8, 0))
        try:
            self.environment = records(self.map, 'EnvironmentData')
        except ValueError:
            self.environment = {}

    def _object_lighting(self):
        """Light environment for objects and the vegetation buffers.

        The scene's fixed light environment (RTS3DScene, 0x0006E716) and the
        tree/shrub render step (0x00071A1F) build it from the three object
        lights and the object ambient, scaled at ShaderLOD Low/Medium by the
        GlobalLighting chunk's final three values (GlobalData +0x944). Sas
        colours double under overbright (`sas_scale`); the fixed-function
        path instead doubles texture x diffuse (MODULATE2X).
        """
        p = self.object_program
        self._bind_light_environment(p, scaled=True)
        p['sas_scale'].value = 2.0 if self.overbright else 1.0
        p['modulate2x'].value = int(self.overbright)

    def light_environment(self, scaled=True):
        """(ambient, [(direction, colour)] x 3) as LightEnvironmentClass holds
        them: Add_Light (0x00140770) drops lights whose diffuse is below 0.05
        in every channel and keeps the rest sorted by squared diffuse length;
        unused slots are black. Worked out once per set of lights (_lighting)."""
        known = getattr(self, '_light_environments', None)
        if known is not None and scaled in known:
            return known[scaled]
        scale = np.asarray(self.light_scale if scaled else (1.0, 1.0, 1.0), np.float32)
        lights = [(tuple(d), np.asarray(c, np.float32)*scale) for d, c in self.object_lights]
        lights = [l for l in lights if not (l[1] < 0.05).all()]
        lights.sort(key=lambda l: -float(l[1] @ l[1]))
        lights += [((0.0, 0.0, 1.0), np.zeros(3, np.float32))]*(3-len(lights))
        ambient = tuple(float(v) for v in np.asarray(self.object_ambient)*scale)
        result = ambient, [(d, tuple(float(v) for v in c)) for d, c in lights[:3]]
        if known is not None:
            known[scaled] = result
        return result

    def _bind_light_environment(self, p, scaled):
        ambient, lights = self.light_environment(scaled)
        p['ambient'].value = ambient
        p['light_dir'].value = [l[0] for l in lights]
        p['light_color'].value = [l[1] for l in lights]
        self._bound_scaled = scaled

    def set_weather(self, weather, sun=None):
        """Switch the weather preset (None or 'map' for the map's own) and the
        sun (None or 'own' for the weather's) in place: lighting uniforms, fog,
        particles and the sky dome's texture; nothing else reloads."""
        self.weather_preset = weather if weather not in (None, '', 'map') else None
        self.sun = sun if sun not in (None, '', 'own') else None
        self._apply_sky()
        self._lighting()
        self._terrain_lighting()
        if hasattr(self, 'object_program'):
            self._object_lighting()
        # The shadow light follows terrain light 0 (W3DShadowManager::setTimeOfDay).
        self._volume_extrusions()
        lights = self.object_lights
        for entry in self.water:
            u = entry['uniforms']
            u['light0_dir'] = tuple(lights[0][0])
            u['light0_color'] = tuple((2.0 if self.overbright else 1.0)*c for c in lights[0][1])
            if not entry.get('own_specular'):
                u['specular_dir'] = tuple(lights[1][0]) if len(lights) > 1 else (0.0, 0.0, 1.0)
        self._prepare_weather()
        self._weather_gpu()
