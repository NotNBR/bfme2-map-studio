"""Placed objects for the renderer (ObjectsMixin): templates resolved to models,
batches of instances per model part, units, spanned bridges, and each pass's
uniform binding. Part of render.engine.MapRenderer, whose state it shares.
"""
import math
import re

import numpy as np

from mapworkshop.render import shaders
from mapworkshop.render.shadows import shadow_kind


SKIP_TEMPLATES = ('*waypoints', 'amb_', 'animalwanderpoint', 'waterripplespawn')

_UNSENT = object()            # MapRenderer._put: no value sent yet in this pass


class ObjectsMixin:
    """MapRenderer's placed objects: templates to models and batches (instances per
    model part), units in their idle pose, spanned bridges, the object options that
    reload them, and binding a batch's uniforms each pass (only what changes)."""

    def _show_props(self):
        """GameLOD.ini ShowProps of the imitated preset (GlobalData +0x1C):
        without it the shrub buffer and the prop buffer stay empty."""
        current, values = None, {}
        for line in self.assets.ini_text('gamelod.ini').splitlines():
            line = line.split(';')[0].strip()
            match = re.match(r'(?i)StaticGameLOD\s*=\s*(\w+)', line)
            if match:
                current = match.group(1).lower()
                continue
            match = re.match(r'(?i)ShowProps\s*=\s*(\w+)', line)
            if match and current:
                values.setdefault(current, match.group(1).lower() == 'yes')
        return values.get(self.options['lod'], self.options['lod'] not in ('verylow', 'low'))

    def _vertex_array(self, vertices, indices, inst, scales, sway):
        ctx = self.ctx
        vbo = ctx.buffer(np.ascontiguousarray(vertices, dtype='f4').tobytes())
        ibo = ctx.buffer(np.ascontiguousarray(indices, dtype='u4').tobytes())
        vao = ctx.vertex_array(self.object_program,
                               [(vbo, '3f 3f 2f 4f 3f 3f 2f', 'in_position', 'in_normal', 'in_uv', 'in_color',
                                 'in_tangent', 'in_binormal', 'in_uv2'),
                                (inst, '4f/i', 'in_place'), (scales, 'f/i', 'in_scale'), (sway, 'f/i', 'in_sway')],
                               index_buffer=ibo, index_element_size=4)
        self._object_resources += [vao, vbo, ibo]
        return vao

    def set_vegetation_limits(self, value):
        """Keep the game's tree and shrub buffer limits (True) or draw every
        tree and shrub (False). Rebuilds only the objects, their tree shadow
        decals and shadow volumes; terrain, water and weather stay."""
        self._set_object_option('vegetation_limits', value)

    def set_editor_markers(self, value):
        """Draw the editor markers (True), the WorldBuilder-only models the
        game does not show (GameAssets.template_model's `editor`), or leave
        them out as the game does (False). Rebuilds only the objects."""
        self._set_object_option('editor_markers', value)

    def set_units(self, value):
        """Draw the units (True): hordes as their members, every unit in the
        pose of its idle animation; or leave every unit out (False). Rebuilds
        only the objects."""
        self._set_object_option('units', value)

    def _set_object_option(self, name, value):
        value = bool(value)
        changed = value != self.options[name]
        self.options[name] = value
        if not changed or not self.options['objects']:
            return
        for item in getattr(self, '_object_resources', []):
            item.release()
        for attr in ('volume_vao', 'volume_buffer', 'volume_program', 'decal_tex', 'object_program'):
            item = getattr(self, attr, None)
            if item is not None:
                item.release()
            if hasattr(self, attr):
                delattr(self, attr)
        self.report.update(missing_models=[], unreadable_models={}, objects_drawn=0, objects_skipped=0,
                           editor_markers=0, units=dict(hidden=0, hordes=0, members=0, crew=0, posed=0))
        self.batches = []
        self._objects_gpu()

    def _object_groups(self):
        """Batches for map objects, as the game sorts them into draw paths.

        `KindOf TREE` and `KindOf SHRUB` templates with a W3DTreeDraw go to
        the tree and shrub buffers with the map angle and the template's
        Scale (a new game creates each one's drawable, whose W3DTreeDraw adds
        it; only a loaded savegame re-adds them with an identity matrix,
        GameLogic 0x00246422). addTree 0x000ECF79 keeps 1,200 trees, the shrub
        add 0x000E91CE 2,000 shrubs and only with ShowProps; they are drawn
        with vegetation.fx.
        Everything else is a W3D render object: fixed-function materials or
        FX materials (normalmapped.fx). Units stand in the first frame of
        their idle animation, hordes replaced by their members (_placed_units).
        """
        show_props = self._show_props()
        limits = self.options.get('vegetation_limits', False)
        self._effect_objects = []
        counts = dict(tree=0, shrub=0)
        dropped = dict(tree=0, shrub=0, prop=0)
        types = dict(tree=set(), shrub=set())
        groups = {}
        volumes = {}
        objects = self.map.objects()
        for o in self._placed_units(objects):
            name = o['template']
            if o['flags'] & 0x30:
                continue                     # bridge endpoints: _bridges_gpu
            if name.lower().startswith(SKIP_TEMPLATES) or o['flags'] & 6:
                self.report['objects_skipped'] += 1
                continue
            resolved = self.assets.template_model(name)
            if resolved is None:
                self.report['missing_models'].append(name)
                continue
            if resolved['editor'] and not self.options.get('editor_markers', False):
                self.report['editor_markers'] += 1
                continue                     # WorldBuilder-only: the game draws nothing
            kinds = resolved['kinds']
            model = resolved['model']
            animation = o.get('animation') or (self.assets.unit_animation(name)
                                               if resolved['unit'] and not resolved['tree'] else None)
            if animation:
                model = f'{model}+{animation}'           # ModelCache.load: posed at its first frame
                self.report['units']['posed'] += 1
            hidden = self.assets.hidden_subobjects(name) if not resolved['tree'] else ()
            if hidden:
                # Hidden as the object is created (a unit's OnCreated script:
                # the upgrades' forged blades, fire arrows, shields; an idle
                # state's BeginScript).
                model = f'{model}|{",".join(sorted(hidden))}'   # ModelCache.load: those meshes left out
            buffer = None
            if resolved['tree']:
                buffer = 'tree' if 'TREE' in kinds else 'shrub' if 'SHRUB' in kinds else 'tree'
            if buffer == 'shrub' and not show_props:
                dropped['shrub'] += 1
                continue
            if buffer is None and resolved.get('prop') and not show_props:
                dropped['prop'] += 1
                continue
            z = float(self.terrain.height_at(o['x'], o['y'])) + o['z']
            from_map = buffer is not None and ('TREE' in kinds or 'SHRUB' in kinds)
            if buffer is not None:
                type_key = (resolved['model'], (resolved['texture'] or '').lower())
                if limits and (counts[buffer] >= (1200 if buffer == 'tree' else 2000)
                               or (type_key not in types[buffer] and len(types[buffer]) >= 64)):
                    dropped[buffer] += 1
                    continue
                counts[buffer] += 1
                types[buffer].add(type_key)
            if from_map:
                # A new game creates the tree's drawable at the map angle and
                # its W3DTreeDraw adds it to the buffer with that orientation
                # and the drawable's scale. The buffer rotates positions only
                # (0x000E7DF3 keeps model-space normals). Zero Hour and BFME1
                # zero the scale randomness there (InstanceScaleFuzziness is
                # applied by WorldBuilder); BFME2's W3DTreeDraw is unmatched.
                angle, scale = o['angle'], resolved['scale']
            else:
                # Deterministic per-object scale variation (InstanceScaleFuzziness).
                fuzz = resolved['fuzziness']
                jitter = ((o['index']*2654435761) % 1000)/999.0*2-1 if fuzz else 0.0
                angle, scale = o['angle'], resolved['scale']*(1+fuzz*jitter)
            # Object::updateObjValuesFromMapProperties: the map's
            # objectPrototypeScale multiplies the drawable's instance scale.
            scale *= self._prototype_scale(o)
            # addTree/addShrub: sway type GetGameClientRandomValue(1, 10), 0
            # for TaintedTree (stand-in: a hash of the object index).
            sway = 0.0 if (buffer is None or resolved['tainted']) else float(1 + (o['index']*2246822519 >> 7) % 10)
            shadow = resolved['shadow']
            kind = shadow_kind(shadow, self.options['shadows'] == 'volume')
            # Shadow maps (High): every object with a Shadow type casts.
            caster = self.options['shadows'] == 'map' and shadow not in ('SHADOW_NONE', 'NONE')
            # KindOf OPTIMIZED_PROP map objects go to the terrain's prop buffer
            # (W3DTerrainVisual::addProp 0x0009257A), which casts no shadow.
            if kind in ('classic', 'v2') and not resolved['tree'] and not self._template_has(name, 'KindOf', 'OPTIMIZED_PROP'):
                volumes.setdefault((model, kind), []).append(
                    dict(x=o['x'], y=o['y'], z=z, angle=angle, scale=scale, ground=z-o['z'],
                         length_scale=self._template_float(name, 'ShadowSizeX')))
            # Optimized trees and shrubs (W3DTreeDraw) draw the template's
            # ShadowTexture when their Shadow is SHADOW_DECAL (addTreeType:
            # doShadow = shadowKind == 1). Without one they draw the default
            # decal, as native captures show: the shadow managers take
            # "shadow" for a name of one character or less (Zero Hour
            # createDecalShadow, BFME2 addShadow); the tree buffer's own
            # decal draw is unmatched.
            decal = None
            if resolved['tree'] and shadow == 'SHADOW_DECAL':
                decal = self._template_value(name, 'ShadowTexture') or 'shadow'
                if self.assets.texture_key(decal) is None:
                    decal = 'shadow'
            sky = 'SKYBOX' in kinds
            # The water reflection draws the tree buffer and KindOf
            # CAN_CAST_REFLECTIONS objects (sky domes have it), not the
            # shrub buffer, the terrain or other objects (Reflection Lab
            # game screenshots at High, 15 October 2026).
            reflects = buffer == 'tree' or 'CAN_CAST_REFLECTIONS' in kinds
            key = (model, resolved['texture'], caster, decal, buffer, bool(resolved.get('prop')), sky, reflects)
            groups.setdefault(key, []).append((o['x'], o['y'], z, angle, scale, sway))
            if buffer is None and not resolved.get('prop'):
                # A drawable in the scene runs its emitters and particle
                # systems; the prop buffer (W3DPropDraw) never adds its
                # render objects to a scene, so their emitters stay idle.
                self._effect_objects.append((name, model, o['x'], o['y'], z, angle, scale, o['index']))
        self.report['vegetation'] = dict(trees=counts['tree'], shrubs=counts['shrub'],
                                         trees_dropped=dropped['tree'], shrubs_dropped=dropped['shrub'],
                                         props_hidden=dropped['prop'], show_props=show_props, limits=limits,
                                         technique='Default' if self.options['lod'] in ('high', 'ultrahigh') else 'Default_L')
        return groups, volumes, objects

    def _placed_units(self, objects):
        """The map's objects as a new game creates them: a horde replaced by
        its members (GameAssets.horde_members), each at its RankInfo position
        facing the horde's way, and a template with BuildVariations by one of
        them (a hash of the object stands in for the game's random pick). A
        siege engine gets its crew (GameAssets.siege_crew: a battering ram's
        Uruks), each on its bone of the engine's model in the pose for that
        side. Members stand on the ground, or level with a horde raised above
        it (on a wall). With the units option off, every unit is left out."""
        show, report = self.options.get('units', True), self.report['units']
        for o in objects:
            name = o['template']
            resolved = None if o['flags'] & 0x30 else self.assets.template_model(name)
            if resolved is None or not resolved['unit']:
                yield o
                continue
            if not show:
                report['hidden'] += 1
                continue
            members = self.assets.horde_members(name)
            if members:
                report['hordes'] += 1
                report['members'] += len(members)
            c, s = math.cos(o['angle']), math.sin(o['angle'])
            ground = float(self.terrain.height_at(o['x'], o['y']))
            for k, (member, x, y) in enumerate(members or [(name, 0.0, 0.0)]):
                variations = self.assets.build_variations(member)
                if variations:
                    member = variations[(o['index']*2654435761 + k*40503) % len(variations)]
                mx, my = o['x'] + c*x - s*y, o['y'] + s*x + c*y
                z = ground + o['z'] - float(self.terrain.height_at(mx, my)) if o['z'] else 0.0
                yield dict(o, template=member, x=mx, y=my, z=z)
            crew = self.assets.siege_crew(name)
            if crew:
                loaded = self.model_cache.load(resolved['model'])
                bones = (loaded or {}).get('bones', {})
                for member, bone, animation in crew:
                    if bone not in bones:
                        continue
                    x, y = (float(v)*resolved['scale'] for v in bones[bone][:2, 3])
                    mx, my = o['x'] + c*x - s*y, o['y'] + s*x + c*y
                    z = ground + o['z'] - float(self.terrain.height_at(mx, my)) if o['z'] else 0.0
                    report['crew'] += 1
                    yield dict(o, template=member, x=mx, y=my, z=z, animation=animation)

    def _objects_gpu(self):
        self._prepared_objects = self._object_groups()
        self._prepare_models()
        self._prepare_volumes(self._prepared_objects[1])
        self._prepared_volume_triangles = self._volume_triangles()
        for _ in self._objects_steps():
            pass
        self._draw_batches = sorted(self.batches, key=lambda b: (not b['vegetation'], b['blend'] is not None and not b['depth_mask']))

    def _prepare_models(self):
        """Decode models and their texture pixels before any GPU work begins."""
        groups, _, objects = self._prepared_objects
        names = set()

        def textures(model):
            for part in (model or {}).get('parts', []):
                names.update((part.get('texture'), part.get('detail_texture')))
                fx = part.get('fx') or {}
                names.update(value for key, value in fx.items()
                             if ('texture' in key.lower() or key == 'NormalMap') and isinstance(value, str))
                if fx.get('__shader__', '').lower() == 'normalmapped.fx':
                    self._effect('normalmapped.fx')

        for index, (model, override, caster, decal, buffer, prop, sky, _) in enumerate(groups):
            self._progress(0.38 + 0.25*index/max(len(groups), 1), f'Preparing models {index+1}/{len(groups)}: {model}')
            names.update((override, decal))
            if buffer is not None:
                tree = self.model_cache.load_tree(model)
                if tree:
                    names.add(tree.get('texture'))
            else:
                textures(self.model_cache.load(model))
        from mapworkshop.mapkit.bridges import bridge_types
        from mapworkshop.mapkit.bridges import endpoint_pairs
        pairs = endpoint_pairs(objects)
        if pairs:
            types = {k.lower(): v for k, v in bridge_types(self.assets.ini_text('roads.ini')+'\n'+self.map_ini).items()}
            for a, _ in pairs:
                kind = types.get(a['template'].lower())
                if kind and kind['model']:
                    textures(self.model_cache.load(kind['model'].lower()))
                    names.add(kind['texture'])
        from mapworkshop.mapkit.weather import sky as preset_sky, sky_texture
        sky = preset_sky(self.weather_preset, self.sun)
        if sky:
            names.add(sky_texture(sky))
        for name in names:
            self._progress(0.64, 'Preparing object textures')
            self._prepare_image(name)
        self._prepare_effects()

    def _objects_steps(self):
        ctx = self.ctx
        self._object_resources = []
        self.sky_horizon = None
        self.object_program = ctx.program(vertex_shader=shaders.OBJECT_VS, fragment_shader=shaders.OBJECT_FS)
        self._object_uniforms = frozenset(self.object_program)
        self.object_program['clip_z'].value = -1e30
        self._object_lighting()
        groups, volumes, objects = self._prepared_objects
        decals = {}
        fx_report = {}
        for index, ((model, texture_override, caster, decal, buffer, prop, sky, reflects), instances) in enumerate(groups.items()):
            self._progress(0.80+0.18*index/max(len(groups), 1), f'Uploading objects {index+1}/{len(groups)}: {model}')
            yield
            inst = ctx.buffer(np.array([i[:4] for i in instances], 'f4').tobytes())
            scales = ctx.buffer(np.array([i[4] for i in instances], 'f4').tobytes())
            sway = ctx.buffer(np.array([i[5] for i in instances], 'f4').tobytes())
            self._object_resources += [inst, scales, sway]
            if buffer is not None:
                tree = self.model_cache.load_tree(model)
                if tree is None:
                    self.report['missing_models'].append(model)
                    continue
                n = len(tree['positions'])
                zeros = np.zeros((n, 3), np.float32)
                vertices = np.hstack([tree['positions'], tree['normals'], tree['uv'], tree['colors'], zeros, zeros, tree['uv']])
                # TextureName (+ '.tga') replaces the model texture in the atlas.
                name_t = texture_override or tree['texture']
                self.batches.append(dict(
                    vao=self._vertex_array(vertices, tree['indices'], inst, scales, sway),
                    caster=caster, texture=self._object_texture(name_t), count=len(instances),
                    technique=2 if self.options['lod'] in ('high', 'ultrahigh') else 1,
                    vegetation=True, cull=True, depth_mask=True, alpha_ref=96/255,
                    # Vegetation.IsAlphaBlendEnabled: trees blend (slot 4 of the
                    # tree buffer returns false), shrubs do not.
                    blend=('src_alpha', 'one_minus_src_alpha') if buffer == 'tree' else None,
                    mode='alphatest', uniforms={}, scaled=True, reflects=reflects))
                self.report['objects_drawn'] += len(instances)
                if decal:
                    # W3DTreeBuffer: one size per tree type, the sum of the model's
                    # half extents; the decal is centred on the tree.
                    lo, hi = tree['bounds']
                    size = float((hi[0]-lo[0])/2+(hi[1]-lo[1])/2)
                    decals.setdefault(decal, []).extend((i[0], i[1], size) for i in instances)
                continue
            loaded = self.model_cache.load(model)
            if loaded is None:
                self.report['missing_models'].append(model)
                continue
            for part in loaded['parts']:
                yield
                n = len(part['positions'])
                tangents = part['tangents'] if part['tangents'] is not None else np.zeros((n, 3), np.float32)
                binormals = part['binormals'] if part['binormals'] is not None else np.zeros((n, 3), np.float32)
                vertices = np.hstack([part['positions'], part['normals'], part['uv'], part['colors'], tangents, binormals,
                                      part.get('uv2', part['uv'])])
                batch = self._material_batch(part, texture_override, fx_report)
                batch.update(vao=self._vertex_array(vertices, part['indices'], inst, scales, sway),
                             caster=caster, count=len(instances), vegetation=False, scaled=not prop, sky=sky,
                             reflects=reflects,
                             camera=part.get('camera', 0), pivot=tuple(float(v) for v in part.get('pivot', (0, 0, 0))),
                             grid=part['material'].get('grid'))
                self.batches.append(batch)
                if sky:
                    z = part['positions'][:, 2]
                    batch['sky_own'] = (batch['texture'], (part.get('fx') or {}).get('Texture_0') or part['texture'])
                    batch['sky_rim_uv'] = part['uv'][z <= z.min() + 1.0]
                    if self.sky_horizon is None:
                        self.sky_horizon = self._horizon_color(batch['sky_own'][1], batch['sky_rim_uv'])
                    z = part['positions'][:, 2]
                    lowest = min(i[2] + float(z.min())*i[4] for i in instances)
                    span = float(z.max() - z.min())*max(i[4] for i in instances)
                    batch['uniforms'].update(sky_horizon=self.sky_horizon or (0.0, 0.0, 0.0),
                                             sky_rim=(lowest, 0.18*span if self.sky_horizon else 0.0))
                elif batch['technique'] == 5:
                    batch['uniforms']['sky_rim'] = (0.0, 0.0)
            self.report['objects_drawn'] += len(instances)
        yield
        yield from self._bridges_steps(objects, fx_report)
        self.report['fx_materials'] = fx_report
        self.decal_count = sum(len(v) for v in decals.values())
        if decals and self.options['decals']:
            self._bake_decals(decals)
        yield
        self._upload_volumes(self._prepared_volume_triangles)
        # Models the game has but that would not parse are a reader problem, not missing ones.
        unreadable = self.model_cache.unreadable
        self.report['unreadable_models'] = {m: unreadable[m] for m in sorted(set(self.report['missing_models']))
                                            if m in unreadable}
        self.report['missing_models'] = sorted(set(self.report['missing_models']) - set(unreadable))
        self._apply_sky()
        self._effects_gpu()

    def _bridges_steps(self, objects, fx_report):
        """Bridges the game spans between two map objects flagged 0x10 and
        0x20 (mapkit.bridges): their Bridge type (roads.ini or the map's
        map.ini) names the model, texture and BridgeScale. Drawn as lit
        objects; the game lights them like terrain (doTheLight), and their
        damaged states are not drawn."""
        from mapworkshop.mapkit.bridges import bridge_types
        from mapworkshop.mapkit.bridges import FLOAT, endpoint_pairs, layout, pieces, place
        pairs = endpoint_pairs(objects)
        self.report['bridges'] = []
        if not pairs:
            return
        types = {k.lower(): v for k, v in bridge_types(self.assets.ini_text('roads.ini') + chr(10) + self.map_ini).items()}
        identity = self.ctx.buffer(np.zeros(4, 'f4').tobytes())
        one = self.ctx.buffer(np.ones(1, 'f4').tobytes())
        still = self.ctx.buffer(np.zeros(1, 'f4').tobytes())
        self._object_resources += [identity, one, still]
        for a, b in pairs:
            yield
            entry = dict(type=a['template'], start=[round(a['x']), round(a['y'])], end=[round(b['x']), round(b['y'])])
            self.report['bridges'].append(entry)
            kind = types.get(a['template'].lower())
            model = self.model_cache.load(kind['model'].lower()) if kind and kind['model'] else None
            plan = None
            if model is not None:
                ends = [(o['x'], o['y'], float(self.terrain.height_at(o['x'], o['y'])) + o['z'] + FLOAT) for o in (a, b)]
                found = pieces(model)
                plan = layout(found, ends[0], ends[1], kind['scale'])
            if plan is None:
                entry['drawn'] = False
                self.report['missing_models'].append(f"bridge {a['template']}")
                continue
            entry.update(drawn=True, model=kind['model'], spans=plan['spans'])
            texture = kind['texture']
            for piece, offset in plan['draw']:
                for part in found[piece]:
                    yield
                    positions, normals = place(part, offset, plan, ends[0])
                    n = len(positions)
                    zeros = np.zeros((n, 3), np.float32)
                    vertices = np.hstack([positions, normals, part['uv'], part['colors'], zeros, zeros, part['uv']])
                    batch = self._material_batch(dict(part, fx=None), texture, fx_report)
                    batch.update(vao=self._vertex_array(vertices, part['indices'], identity, one, still),
                                 caster=False, count=1, vegetation=False, scaled=True, sky=False, cull=False)
                    self.batches.append(batch)
            self.report['objects_drawn'] += 2

    def _material_batch(self, part, texture_override, fx_report):
        """Render states and uniforms of one W3D material."""
        fx = part['fx']
        state = part['state']
        lod = self.options['lod']
        if fx is not None and fx.get('__shader__', '').lower() == 'normalmapped.fx':
            from mapworkshop.render.water import technique as pick
            effect = self._effect('normalmapped.fx')
            names = [t['name'] for t in effect.techniques] if effect else []
            lod_index = dict(verylow=0, low=0, medium=1, high=2, ultrahigh=3).get(lod, 1)
            name = pick(names, fx.get('__technique__', 0), lod_index) if names else None
            one = lambda key, default: float((fx.get(key) or (default,))[0])
            vec = lambda key, default, n: tuple(float(v) for v in (tuple(fx.get(key) or ()) + default[len(fx.get(key) or ()):])[:n])
            entry = fx_report.setdefault('normalmapped.fx', dict(technique=name, meshes=0))
            entry['meshes'] += 1
            if name not in ('Default_M', 'Default_L'):
                entry['approximated'] = f'{name} drawn with the Default_M port'
            opacity = one('OpacityOverride', 1.0)
            normal = fx.get('NormalMap')
            return dict(texture=self._object_texture(fx.get('DiffuseTexture') or part['texture'],
                                                     raw=not fx.get('AlphaTestEnable') and opacity >= 1),
                        normal=self._object_texture(normal) if isinstance(normal, str) else None,
                        technique=4 if name == 'Default_L' else 3, cull=True, depth_mask=True,
                        alpha_ref=96/255 if fx.get('AlphaTestEnable') else None,
                        blend=('src_alpha', 'one_minus_src_alpha') if opacity < 1 else None,
                        mode='alphatest' if fx.get('AlphaTestEnable') else 'opaque',
                        uniforms=dict(fx_ambient_color=vec('AmbientColor', (0.4, 0.4, 0.4), 3),
                                      fx_diffuse=vec('DiffuseColor', (1.0, 1.0, 1.0, 1.0), 4),
                                      fx_specular=vec('SpecularColor', (0.8, 0.8, 0.8), 3),
                                      fx_exponent=one('SpecularExponent', 50.0), fx_bump=one('BumpScale', 1.0),
                                      fx_opacity=opacity))
        if fx is not None and fx.get('__shader__', '').lower() == 'simple.fx':
            # simple.fx Default (sky domes): texture x ColorEmissive, unlit,
            # fogged only with FogEnable; UV = uv x TexCoordTransform_0.xy
            # (+ Time x zw, not animated here).
            fx_report.setdefault('simple.fx', dict(meshes=0))['meshes'] += 1
            emissive = tuple(float(v) for v in (tuple(fx.get('ColorEmissive') or ()) + (1.0, 1.0, 1.0))[:3])
            transform = tuple(fx.get('TexCoordTransform_0') or (1.0, 1.0, 0.0, 0.0))
            blend = fx.get('AlphaBlendingEnable')
            return dict(texture=self._object_texture(fx.get('Texture_0') or part['texture'], raw=not blend), normal=None,
                        technique=5, cull=True, depth_mask=bool(fx.get('DepthWriteEnable', True)),
                        alpha_ref=None, blend=('src_alpha', 'one_minus_src_alpha') if blend else None,
                        mode='blend' if blend else 'opaque',
                        uniforms=dict(fx_emissive=emissive, fx_fog=int(bool(fx.get('FogEnable', True))),
                                      fx_uv_scale=(float(transform[0]), float(transform[1]))))
        if fx is not None:
            # Other effects are drawn as a lit, textured fixed-function material.
            name = fx.get('__shader__', '?').lower()
            fx_report.setdefault(name, dict(meshes=0, approximated='fixed-function stand-in'))['meshes'] += 1
        material, sources = part['material'], part['sources']
        texture = texture_override or part['texture']
        # Texture stage 1 (DetailColorFunc), drawn for the functions the
        # fragment shader knows; others leave stage 0 as it is.
        detail = state.get('detail', 0) if part.get('detail_texture') and state['texturing'] else 0
        # Without alpha blending or testing the texture's alpha is unused, and
        # additive glows keep their colour under zero alpha: draw it as stored.
        raw = state['alpha_ref'] is None and (state['blend'] is None or state['blend'][0] != 'src_alpha')
        return dict(texture=self._object_texture(texture, raw) if state['texturing'] and texture else None,
                    detail=self._object_texture(part['detail_texture'], raw) if detail else None,
                    normal=None, technique=0, cull=not part['two_sided'], depth_mask=state['depth_mask'],
                    alpha_ref=None if state['alpha_ref'] is None else state['alpha_ref']/255,
                    blend=state['blend'], mode=part['mode'],
                    uniforms=dict(mat_ambient=tuple(material['ambient']), mat_diffuse=tuple(material['diffuse']),
                                  mat_emissive=tuple(material['emissive']), mat_opacity=float(material['opacity']),
                                  ambient_from_vertex=int(sources['ambient']),
                                  diffuse_from_vertex=int(sources['diffuse']), lighting=int(sources['lighting']),
                                  gradient=state['gradient'] if state['gradient'] in (0, 1, 2) else 1,
                                  texturing=int(state['texturing']), detail_func=detail))

    @staticmethod
    def _prototype_scale(o):
        for name, _, value in o.get('properties') or ():
            if name == 'objectPrototypeScale':
                try:
                    return float(value) if float(value) > 0 else 1.0
                except (TypeError, ValueError):
                    return 1.0
        return 1.0

    def _template_value(self, template, key):
        """The first word of a template's own (top-level) INI value for `key`,
        inherited through ObjectReskin/ChildObject (assets.ini)."""
        value = self.assets.template_value(template, key)
        return value.split()[0] if value and value.split() else None

    def _template_has(self, template, key, word):
        """Whether a template's own (inherited) `key` line lists `word`."""
        return word.upper() in (self.assets.template_value(template, key) or '').upper().split()

    def _template_float(self, template, key):
        try:
            return float(self._template_value(template, key) or 0.0)
        except ValueError:
            return 0.0

    def _begin_batches(self):
        """Start a pass over the object batches: forget what _put has sent, so
        whatever was written to the object program before counts as unknown."""
        self._sent = {}

    def _put(self, op, name, value):
        """Write an object-program uniform, unless this pass has already sent
        that very value (the same object, or an equal number or tuple)."""
        sent = self._sent.get(name, _UNSENT)
        if sent is value or (type(sent) is type(value) and not isinstance(value, np.ndarray) and sent == value):
            return
        op[name].value = value
        self._sent[name] = value

    def _use(self, texture, unit):
        """Bind a texture to a unit, unless this pass has bound it there already."""
        if self._sent.get(('unit', unit)) is not texture:
            texture.use(unit)
            self._sent[('unit', unit)] = texture

    def _bind_batch(self, op, batch):
        """Per-material uniforms and textures of an object batch. Values the
        batch shares with the one before are not sent again (_put), which is
        most of them: four passes bind every batch each frame."""
        if batch['texture'] is not None:
            self._use(batch['texture'], 0)
        if batch.get('detail') is not None:
            self._use(batch['detail'], 3)
        if batch.get('normal') is not None:
            self._use(batch['normal'], 9)
        known = self._object_uniforms
        binding = batch.get('_binding')
        if binding is None or binding[0] is not known:
            # Its uniforms, worked out once (_apply_sky drops them when it changes the batch).
            uniforms = batch['uniforms']
            # Camera-facing meshes and Grid-mapped textures (assets.models): camera_mode, pivot, uv_grid.
            values = [('tex', 0), ('has_texture', int(batch['texture'] is not None)), ('technique', batch['technique']),
                      ('alpha_ref', -1.0 if batch['alpha_ref'] is None else float(batch['alpha_ref'])), ('texturing', 1),
                      ('camera_mode', batch.get('camera', 0)), ('pivot', batch.get('pivot', (0.0, 0.0, 0.0))),
                      ('uv_grid', tuple(float(v) for v in batch.get('grid') or (0, 0, 0))),
                      ('detail_func', uniforms.get('detail_func', 0))]
            if batch.get('detail') is not None:
                values.append(('detail_tex', 3))
            if batch.get('normal') is not None:
                values.append(('normal_tex', 9))
            values += [(key, value) for key, value in uniforms.items() if key in known]
            binding = batch['_binding'] = (known, values)
        # _put, inline: this runs some 4,000 times a frame.
        sent = self._sent
        for name, value in binding[1]:
            old = sent.get(name, _UNSENT)
            if old is value or (type(old) is type(value) and not isinstance(value, np.ndarray) and old == value):
                continue
            op[name].value = value
            sent[name] = value
        if batch.get('scaled', True) != getattr(self, '_bound_scaled', True):
            # W3DPropBuffer::drawProps builds its own light environment from
            # the object lights without the ShaderLOD scale.
            self._bind_light_environment(op, batch.get('scaled', True))

    def _blend_func(self, factors):
        mgl = self.moderngl
        table = dict(zero=mgl.ZERO, one=mgl.ONE, src_alpha=mgl.SRC_ALPHA, one_minus_src_alpha=mgl.ONE_MINUS_SRC_ALPHA,
                     src_color=mgl.SRC_COLOR, one_minus_src_color=mgl.ONE_MINUS_SRC_COLOR, dst_color=mgl.DST_COLOR)
        return table[factors[0]], table[factors[1]]

    def _sway_offsets(self, time):
        """Vegetation.SwayOffsets (0x000E68C5) for the default breeze
        (ScriptEngine::reset: direction PI/3, intensity 0.035 PI/4, lean
        0.02 PI/4, period 300 logic frames, randomness 0.2). The vegetation
        sway update (0x000E6406) tabulates 100 offsets of
        (dirX sin a, dirY sin a, cos a - 1) with a = lean + intensity
        cos(i x 0.0622) and advances ten sway types by 100 / period per
        frame, each step and amplitude scaled by a random factor in
        [0.9, 1.1] (fixed stand-ins here). Index 0 never sways."""
        direction, intensity, lean, period, randomness = math.pi/3, 0.035*math.pi/4, 0.02*math.pi/4, 300.0, 0.2
        dx, dy = math.sin(direction), math.cos(direction)
        table = []
        for i in range(100):
            a = lean + intensity*math.cos(i*0.06220976)
            table.append((dx*math.sin(a), dy*math.sin(a), math.cos(a)-1.0))
        offsets = [(0.0, 0.0, 0.0)]
        frames = time*30.0
        for k in range(10):
            step_factor = 1.0 + randomness*0.5*math.sin(12.9898*(k+1))
            amp_factor = 1.0 + randomness*0.5*math.sin(78.233*(k+1))
            position = (frames*100.0/period*step_factor) % 100.0
            lo = int(math.floor(position))
            hi = min(lo+1, 99)
            f = position - lo
            offsets.append(tuple(amp_factor*((1-f)*table[lo][j] + f*table[hi][j]) for j in range(3)))
        return offsets
