"""Static W3D models for preview rendering (native Z-up coordinates).

Meshes are placed in their bind pose using the HLOD's highest-detail LOD and
its hierarchy (embedded or the referenced skeleton file). Skinned vertices are
stored relative to their primary bone and are transformed by that bone.
Animation is not applied; this is a still preview.

Each part carries what the game's fixed-function path needs (vertex material,
colour sources after MeshMatDescClass::Post_Load_Process, ShaderClass render
states) or the FX material constants. `ModelCache.load_tree` gives the single
mesh the tree and shrub buffers copy into their vertex buffers.
"""

import struct

import numpy as np

from mapworkshop.formats.w3d import cstr, matrix

MESH, VERTICES, NORMALS, INFLUENCES, TRIANGLES = 0x0, 0x2, 0x3, 0xe, 0x20
SHADERS, TEXTURES, PASS, STAGE, FX_SHADERS = 0x29, 0x30, 0x38, 0x48, 0x50
TANGENTS, BINORMALS = 0x60, 0x61
HIERARCHY, HLOD = 0x100, 0x700
HIDDEN, TWO_SIDED, CAST_SHADOW, SKIN = 0x1000, 0x2000, 0x8000, 0x20000
GEOMETRY_TYPE = 0x00FF0000
# W3D_MESH_FLAG_GEOMETRY_TYPE_CAMERA_ALIGNED / _CAMERA_ORIENTED -> 1 / 2.
CAMERA_MODES = {0x00010000: 1, 0x00060000: 2}


def chunks(data):
    """Tolerant chunk walker; the high bit only marks container chunks."""
    pos = 0
    while pos + 8 <= len(data):
        kind, size = struct.unpack_from('<II', data, pos)
        size &= 0x7fffffff
        yield kind, data[pos+8:pos+8+size]
        pos += 8 + size


def bones_of(data):
    named = named_bones(data)
    return None if named is None else named[1]


def named_bones(data):
    """(names, model-space matrices) of the hierarchy, or None."""
    parts = dict(chunks(data))
    if HIERARCHY not in parts:
        return None
    items = dict(chunks(parts[HIERARCHY]))
    count = struct.unpack_from('<I', items[0x101], 20)[0]
    pivots = items[0x102]
    names, bones = [], []
    for i in range(count):
        p = pivots[i*60:(i+1)*60]
        names.append(p[:16].split(b'\0', 1)[0].decode('latin-1').lower())
        parent = struct.unpack_from('<i', p, 16)[0]
        local = matrix(struct.unpack_from('<3f', p, 20), struct.unpack_from('<4f', p, 44))
        bones.append(bones[parent] @ local if 0 <= parent < i else local)
    return names, bones


def fx_constants(payload):
    """FX material constants: type 1 texture, 2 float, 5 float4, 7 bool."""
    values = {}
    for kind, chunk in chunks(payload):
        for k2, p2 in chunks(chunk):
            if k2 == 0x52:
                # FXShaderSetup::Load_W3D: version byte, 32-byte effect name,
                # then the technique index into the effect.
                values['__shader__'] = cstr(p2[1:33])
                if len(p2) >= 37:
                    values['__technique__'] = struct.unpack_from('<i', p2, 33)[0]
            if k2 != 0x53:
                continue
            ctype, length = struct.unpack_from('<II', p2)
            name = p2[8:8+length].split(b'\0')[0].decode('ascii', 'replace')
            rest = p2[8+length:]
            if ctype == 1:
                n = struct.unpack_from('<I', rest)[0]
                values[name] = rest[4:4+n].split(b'\0')[0].decode('ascii', 'replace')
            elif ctype in (2, 3, 4, 5):
                values[name] = struct.unpack_from(f'<{len(rest)//4}f', rest)
            elif ctype == 7:
                values[name] = bool(rest[0]) if rest else False
    return values




# W3D ShaderClass blend tables as ShaderClass::Apply (ShaderClassApply.cpp)
# uses them: source ZERO, ONE, SRCALPHA, DESTCOLOR; destination ZERO, ONE,
# SRCCOLOR, INVSRCCOLOR, SRCALPHA, INVSRCALPHA.
SRC_BLEND = ('zero', 'one', 'src_alpha', 'dst_color')
DST_BLEND = ('zero', 'one', 'src_color', 'one_minus_src_color', 'src_alpha', 'one_minus_src_alpha')


def classic_shader(shader):
    """Render states of a 16-byte W3dShaderStruct, as ShaderClass::Apply sets
    them: blend factors, depth writes, alpha test (reference 0x60 for
    ALPHATEST_ENABLE; SrcAlpha/InvSrcAlpha blending also tests against 1/255)
    and the primary gradient (texture x diffuse, MODULATE2X under overbright)."""
    depth_mask, dst, gradient, src, texturing, alpha_test = (shader[1], shader[3], shader[5], shader[7],
                                                             shader[8], shader[12])
    detail = shader[9]                               # DetailColorFunc: how stage 1 combines
    src_f = SRC_BLEND[src] if src < len(SRC_BLEND) else 'one'
    dst_f = DST_BLEND[dst] if dst < len(DST_BLEND) else 'zero'
    blend = None if (src_f, dst_f) == ('one', 'zero') else (src_f, dst_f)
    if alpha_test == 1:
        reference = 0x60
    elif blend == ('src_alpha', 'one_minus_src_alpha'):
        reference = 1
    else:
        reference = None
    return dict(blend=blend, depth_mask=bool(depth_mask), alpha_ref=reference,
                gradient=int(gradient), texturing=bool(texturing), detail=int(detail))


def vertex_material(payload):
    """First W3D_CHUNK_VERTEX_MATERIAL_INFO: ambient, diffuse, emissive,
    opacity, and its stage-0 texture mapper (`grid`: frames per row, frames
    per second and frame count for the Grid mapper, else None)."""
    for kind, chunk in chunks(payload):
        if kind != 0x2b:
            continue
        parts = dict(chunks(chunk))
        info = parts.get(0x2d)
        if info and len(info) >= 32:
            rgb = lambda o: tuple(c/255 for c in info[o:o+3])
            return dict(ambient=rgb(4), diffuse=rgb(8), emissive=rgb(16),
                        opacity=struct.unpack_from('<f', info, 24)[0],
                        grid=grid_mapper(struct.unpack_from('<I', info)[0], parts.get(0x2e, b'')))
    return dict(ambient=(1.0, 1.0, 1.0), diffuse=(1.0, 1.0, 1.0), emissive=(0.0, 0.0, 0.0), opacity=1.0, grid=None)


def grid_mapper(attributes, args):
    """GridTextureMapperClass (W3DVERTMAT_STAGE0_MAPPING_GRID, 0x00070000):
    the UVs cover the first frame of a 2^Log2Width square grid, stepped
    through at FPS frames per second, row by row, wrapping after Last frames
    (all of them by default). Returns (width, fps, last) or None."""
    if attributes & 0x00FF0000 != 0x00070000:
        return None
    values = {}
    for line in args.split(b'\0', 1)[0].decode('latin-1').splitlines():
        key, _, value = line.partition('=')
        values[key.strip().lower()] = value.strip()
    try:
        width = 1 << int(values.get('log2width', '0'))
        fps = float(values.get('fps', '1'))
        last = int(values.get('last', width*width))
    except ValueError:
        return None
    return (width, fps, max(1, min(last, width*width)))


def post_load_colors(material, dcg, dig, count):
    """MeshMatDescClass::Post_Load_Process (meshmatdesc.cpp) for one pass:
    the per-vertex colour array the fixed-function pipeline reads and the
    D3D material colour sources. DIG multiplies into DCG; with only a DCG
    array the material diffuse (or ambient, or emissive) is folded into it
    and the ambient/diffuse sources switch to the vertex colour."""
    amb, dif, emi, opacity = (np.array(material[k], np.float32) for k in ('ambient', 'diffuse', 'emissive', 'opacity'))
    used = dict(diffuse=bool(dif.any()), ambient=bool(amb.any()), emissive=bool(emi.any()))
    sources = dict(ambient=False, diffuse=dcg is not None, lighting=True)
    if dcg is None:
        return np.ones((count, 4), np.float32), sources
    colors = dcg.copy()
    if dig is not None:
        colors[:, :3] *= dig[:, :3]
    d, a, e = used['diffuse'], used['ambient'], used['emissive']
    if d and not a and not e:
        colors[:, :3] *= dif; colors[:, 3] *= opacity
    elif d and a and not e:
        colors[:, :3] *= dif; colors[:, 3] *= opacity
        sources['ambient'] = True
    elif a and not d and not e:
        colors[:, :3] *= amb; colors[:, 3] *= opacity
        sources.update(ambient=True, diffuse=False)
    elif e and not d and not a:
        colors[:, :3] *= emi; colors[:, 3] *= opacity
        # Lighting is switched off when every material only emits.
        sources['lighting'] = False
    return colors, sources


def parse_mesh(payload):
    parts = {}
    for kind, chunk in chunks(payload):
        parts.setdefault(kind, chunk)
    header = parts[0x1f]
    attributes = struct.unpack_from('<I', header, 4)[0]
    name = cstr(header[8:24]); container = cstr(header[24:40])
    positions = np.frombuffer(parts[VERTICES], '<f4').reshape(-1, 3).astype(np.float32)
    count = len(positions)
    vec3 = lambda kind: (np.frombuffer(parts[kind], '<f4').reshape(-1, 3).astype(np.float32)
                         if kind in parts and len(parts[kind]) == count*12 else None)
    normals = vec3(NORMALS)
    if normals is None:
        normals = np.zeros_like(positions)
    tangents, binormals = vec3(TANGENTS), vec3(BINORMALS)
    triangles = np.frombuffer(parts[TRIANGLES], '<u4').reshape(-1, 8)[:, :3].astype(np.uint32)
    textures = []
    for kind, tex in chunks(parts.get(TEXTURES, b'')):
        if kind == 0x31:
            textures.append(cstr(dict(chunks(tex)).get(0x32, b'')))
    shaders = [parts[SHADERS][i:i+16] for i in range(0, len(parts.get(SHADERS, b'')), 16)]
    uv = None; tex_ids = None; shader_ids = None; dcg = None; dig = None
    uv2 = None; detail_ids = None
    if PASS in parts:
        pass_parts = list(chunks(parts[PASS]))
        for kind, chunk in pass_parts:
            if kind == 0x3a:
                shader_ids = np.frombuffer(chunk, '<u4')
            if kind == 0x3b and dcg is None and len(chunk) == count*4:
                # DCG: per-vertex diffuse colour.
                dcg = np.frombuffer(chunk, 'u1').reshape(-1, 4).astype(np.float32)/255
            if kind == 0x3c and dig is None and len(chunk) == count*4:
                # DIG: per-vertex illumination, multiplied into DCG on load.
                dig = np.frombuffer(chunk, 'u1').reshape(-1, 4).astype(np.float32)/255
            if kind == 0x4a and uv is None:
                # FX-shader meshes keep texture coordinates directly in the pass.
                uv = np.frombuffer(chunk, '<f4').reshape(-1, 2).astype(np.float32)
            if kind == STAGE and uv is None:
                stage = dict(chunks(chunk))
                if 0x4a in stage:
                    uv = np.frombuffer(stage[0x4a], '<f4').reshape(-1, 2).astype(np.float32)
                if 0x49 in stage:
                    tex_ids = np.frombuffer(stage[0x49], '<u4')
            elif kind == STAGE and uv2 is None:
                # Texture stage 1: the detail texture and its coordinates.
                stage = dict(chunks(chunk))
                if 0x4a in stage:
                    uv2 = np.frombuffer(stage[0x4a], '<f4').reshape(-1, 2).astype(np.float32)
                if 0x49 in stage:
                    detail_ids = np.frombuffer(stage[0x49], '<u4')
    if uv is None or len(uv) != count:
        uv = np.zeros((count, 2), np.float32)
    detail_texture = ''
    if uv2 is None or len(uv2) != count:
        uv2 = uv
    elif detail_ids is not None and len(detail_ids) and int(detail_ids[0]) < len(textures):
        detail_texture = textures[int(detail_ids[0])]
    material = vertex_material(parts.get(0x2a, b''))
    colors, sources = post_load_colors(material, dcg, dig, count)
    two_sided = bool(attributes & TWO_SIDED)
    fx = fx_constants(parts[FX_SHADERS]) if FX_SHADERS in parts else None
    groups = {}
    if fx is not None:
        texture_names = [v for k, v in fx.items() if isinstance(v, str) and k != '__shader__'
                         and v.lower() != 'none' and 'texture' in k.lower()]
        diffuse = [fx[k] for k in ('DiffuseTexture', 'Texture_0', 'BaseTexture') if isinstance(fx.get(k), str)]
        textures = (diffuse or texture_names)[:1]
        mode = 'alphatest' if fx.get('AlphaTestEnable') else 'opaque'
        state = dict(blend=None, depth_mask=True, alpha_ref=0x60 if fx.get('AlphaTestEnable') else None,
                     gradient=1, texturing=True)
        groups[(textures[0] if textures else '', 0)] = triangles
        shader_list = [state]
    else:
        shader_list = [classic_shader(s) for s in shaders] or [classic_shader(bytes([3, 1, 0, 0, 0, 1, 0, 1, 1] + [0]*7))]
        per_shader = (shader_ids if shader_ids is not None and len(shader_ids) == len(triangles)
                      else np.full(len(triangles), int(shader_ids[0]) if shader_ids is not None and len(shader_ids) else 0))
        per_shader = np.minimum(per_shader, len(shader_list)-1)
        if tex_ids is None or len(tex_ids) == 0:
            tex_ids = np.zeros(1, np.uint32)
        per_texture = tex_ids if len(tex_ids) == len(triangles) else np.full(len(triangles), tex_ids[0])
        for t, s in sorted(set(zip(per_texture.tolist(), per_shader.tolist()))):
            name_t = (textures[int(t)] if int(t) < len(textures) else textures[0]) if textures else ''
            if not shader_list[s]['texturing']:
                name_t = ''
            groups[(name_t, s)] = triangles[(per_texture == t) & (per_shader == s)]
        state = shader_list[0]
        mode = 'alphatest' if state['alpha_ref'] == 0x60 else 'blend' if state['blend'] else 'opaque'
    influences = None
    if INFLUENCES in parts:
        influences = np.frombuffer(parts[INFLUENCES], '<u2').reshape(-1, 4)[:, 0].astype(int)
    return dict(name=name, container=container, attributes=attributes, positions=positions,
                normals=normals, tangents=tangents, binormals=binormals, uv=uv, uv2=uv2,
                detail_texture=detail_texture, colors=colors,
                dcg=dcg, groups=groups, shaders=shader_list, mode=mode, influences=influences,
                material=material, sources=sources, fx=fx, two_sided=two_sided,
                textures=textures, triangles=triangles)


class ModelCache:
    def __init__(self, assets):
        self.assets = assets
        self.cache = {}

    def load(self, model):
        if model in self.cache:
            return self.cache[model]
        key = self.assets.model_key(model)
        result = None
        if key is not None:
            try:
                result = self._build(self.assets.read(key))
            except (ValueError, KeyError, struct.error, IndexError):
                result = None
        self.cache[model] = result
        return result

    def load_tree(self, model):
        """Geometry as W3DTreeBuffer/W3DShrubBuffer take it (addTreeType
        0x000EC75D, vertex fill 0x000E7DF3): the first sub-object of the
        model (HLodClass::Get_Sub_Object(0), the first mesh of the lowest
        LOD), offset by the translation of its bone transform only, with the
        mesh's own normals, DCG colour (alpha forced to 255, else white) and
        UVs clamped to [0, 1]."""
        key = ('tree', model)
        if key in self.cache:
            return self.cache[key]
        result = None
        file_key = self.assets.model_key(model)
        if file_key is not None:
            try:
                result = self._build_tree(self.assets.read(file_key))
            except (ValueError, KeyError, struct.error, IndexError):
                result = None
        self.cache[key] = result
        return result

    def _build_tree(self, data):
        top = list(chunks(data))
        meshes = {}
        order = []
        for kind, payload in top:
            if kind == MESH:
                mesh = parse_mesh(payload)
                meshes[(mesh['container']+'.'+mesh['name']).lower()] = mesh
                meshes.setdefault(mesh['name'].lower(), mesh)
                order.append(mesh)
        if not order:
            return None
        mesh, bone = order[0], None
        bones = bones_of(data)
        for kind, payload in top:
            if kind != HLOD:
                continue
            lods = []
            hierarchy_name = None
            for k, p in chunks(payload):
                if k == 0x701:
                    hierarchy_name = cstr(p[24:40])
                if k == 0x702:
                    lods.append([(struct.unpack_from('<I', q)[0], cstr(q[4:36]))
                                 for kk, q in chunks(p) if kk == 0x704])
            if bones is None and hierarchy_name:
                skeleton = self.assets.model_key(hierarchy_name)
                if skeleton:
                    bones = bones_of(self.assets.read(skeleton))
            for lod in lods:
                if lod:
                    bone, name = lod[0]
                    mesh = meshes.get(name.lower()) or meshes.get(name.lower().split('.')[-1]) or mesh
                    break
            break
        offset = np.zeros(3, np.float32)
        if bones is not None and bone is not None and bone < len(bones):
            offset = bones[bone][:3, 3].astype(np.float32)
        colors = np.ones((len(mesh['positions']), 4), np.float32)
        if mesh['dcg'] is not None:
            colors[:, :3] = mesh['dcg'][:, :3]
        positions = (mesh['positions'] + offset).astype(np.float32)
        indices = np.concatenate([t for t in mesh['groups'].values() if len(t)]) if mesh['groups'] else np.zeros(0, np.uint32)
        return dict(positions=positions, normals=mesh['normals'], uv=np.clip(mesh['uv'], 0.0, 1.0),
                    colors=colors, indices=indices.astype(np.uint32),
                    texture=mesh['textures'][0] if mesh['textures'] else '',
                    bounds=(positions.min(0), positions.max(0)), name=mesh['name'])

    def _build(self, data):
        top = list(chunks(data))
        meshes = {}
        for kind, payload in top:
            if kind == MESH:
                mesh = parse_mesh(payload)
                meshes[(mesh['container']+'.'+mesh['name']).lower()] = mesh
                meshes.setdefault(mesh['name'].lower(), mesh)
        named = named_bones(data)
        placement = {}
        aggregates = []
        for kind, payload in top:
            if kind != HLOD:
                continue
            lods = []
            hierarchy_name = None
            for k, p in chunks(payload):
                if k == 0x701:
                    hierarchy_name = cstr(p[24:40])
                if k == 0x702:
                    lods.append([(struct.unpack_from('<I', q)[0], cstr(q[4:36]))
                                 for kk, q in chunks(p) if kk == 0x704])
                if k == 0x705:
                    # The aggregate array: further render objects on bones,
                    # such as particle emitters (render.effects draws them).
                    aggregates += [(struct.unpack_from('<I', q)[0], cstr(q[4:36]))
                                   for kk, q in chunks(p) if kk == 0x704]
            if named is None and hierarchy_name:
                key = self.assets.model_key(hierarchy_name)
                if key:
                    named = named_bones(self.assets.read(key))
            # LOD arrays are stored from lowest to highest detail.
            for bone, name in (lods[-1] if lods else []):
                placement[name.lower()] = bone
        bones = None if named is None else named[1]
        parts = []
        shadow = []
        collision = []
        used = set()
        names = placement or {k: None for k in meshes if '.' in k}
        for name, bone in names.items():
            mesh = meshes.get(name) or meshes.get(name.split('.')[-1])
            if mesh is None or id(mesh) in used:
                continue
            used.add(id(mesh))
            positions = mesh['positions']; normals = mesh['normals']
            tangents, binormals = mesh['tangents'], mesh['binormals']
            local = (positions, normals)
            # The geometry type is a field (W3D_MESH_FLAG_GEOMETRY_TYPE_MASK),
            # not bits: camera-oriented (0x60000) shares a bit with skin.
            geometry = mesh['attributes'] & GEOMETRY_TYPE
            camera = CAMERA_MODES.get(geometry, 0)
            pivot = np.zeros(3, np.float32)
            if bones is not None:
                if bone is not None and bone < len(bones):
                    pivot = bones[bone][:3, 3].astype(np.float32)
                if geometry == SKIN and mesh['influences'] is not None and len(mesh['influences']) == len(positions):
                    index = np.clip(mesh['influences'], 0, len(bones)-1)
                    stack = np.stack(bones)[index]
                    rotate = lambda v: None if v is None else np.einsum('nij,nj->ni', stack[:, :3, :3], v)
                    positions = np.einsum('nij,nj->ni', stack[:, :3, :3], positions) + stack[:, :3, 3]
                    normals, tangents, binormals = rotate(normals), rotate(tangents), rotate(binormals)
                elif bone is not None and bone < len(bones):
                    m = bones[bone]
                    rotate = lambda v: None if v is None else v @ m[:3, :3].T
                    positions = positions @ m[:3, :3].T + m[:3, 3]
                    normals, tangents, binormals = rotate(normals), rotate(tangents), rotate(binormals)
            collision.append(dict(name=mesh['name'], positions=positions.astype(np.float32, copy=False),
                                  indices=mesh['triangles']))
            if mesh['attributes'] & CAST_SHADOW and len(mesh['triangles']):
                # W3DShadowGeometry::initFromHLOD / the V2 shadow constructor:
                # top-LOD meshes whose MeshGeometry has CAST_SHADOW (the W3D
                # attribute 0x8000), hidden ones included.
                shadow.append(dict(positions=positions.astype(np.float32), indices=mesh['triangles'],
                                   name=mesh['name'], skin=geometry == SKIN,
                                   hidden=bool(mesh['attributes'] & HIDDEN)))
            if mesh['attributes'] & HIDDEN or 'shadow' in mesh['name']:
                continue
            for (texture, shader), triangles in mesh['groups'].items():
                if len(triangles) == 0:
                    continue
                state = mesh['shaders'][shader]
                mode = ('alphatest' if state['alpha_ref'] == 0x60 else
                        'additive' if state['blend'] == ('one', 'one') else
                        'blend' if state['blend'] else 'opaque')
                if camera:
                    # DX8 mesh renderer: an aligned or oriented mesh is drawn
                    # with Obj_Look_At at its bone's position instead of its
                    # transform, so it keeps its own axes and turns as a whole.
                    positions, normals = local
                    tangents = binormals = None
                parts.append(dict(positions=positions.astype(np.float32), normals=normals.astype(np.float32),
                                  tangents=None if tangents is None else tangents.astype(np.float32),
                                  binormals=None if binormals is None else binormals.astype(np.float32),
                                  uv=mesh['uv'], uv2=mesh['uv2'], detail_texture=mesh['detail_texture'],
                                  colors=mesh['colors'], indices=triangles, texture=texture,
                                  mode=mode, state=state, material=mesh['material'], sources=mesh['sources'],
                                  fx=mesh['fx'], two_sided=mesh['two_sided'], name=mesh['name'],
                                  camera=camera, pivot=pivot))
        if not parts:
            return None
        allpos = np.concatenate([p['positions'] + (p['pivot'] if p['camera'] else 0) for p in parts])
        bone_matrix = lambda i: bones[i] if bones is not None and i < len(bones) else np.eye(4)
        return dict(parts=parts, bounds=(allpos.min(0), allpos.max(0)), shadow=shadow, collision=collision,
                    bones={} if named is None else {n: m for n, m in zip(*named)},
                    aggregates=[(name, bone_matrix(bone)) for bone, name in aggregates])
