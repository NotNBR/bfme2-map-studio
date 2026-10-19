"""Shadow volumes as BFME2 (game.dat 1.06) builds them at Medium detail.

Which objects cast what: W3DShadowManager::addShadow (0x0009A8D3). INI
Shadow names are bits in this order: SHADOW_DECAL 1, SHADOW_VOLUME 2,
SHADOW_VOLUME_NEW 4, SHADOW_DYNAMIC_PROJECTION 8, SHADOW_DIRECTIONAL_PROJECTION
0x10, SHADOW_ALPHA_DECAL 0x20, SHADOW_ADDITIVE_DECAL 0x40,
SHADOW_VOLUME_NON_SELF_1..3 0x80..0x200, SHADOW_ALPHA_DECAL_DYNAMIC 0x400,
SHADOW_ADDITIVE_DECAL_DYNAMIC 0x800, SHADOW_MERGE_DECAL 0x1000,
SHADOW_DECAL_TERRAIN_CLAIM 0x2000, SHADOW_VOLUME_OR_DECAL 0x4000,
SHADOW_VOLUME_NEW_OR_DECAL 0x8000. The *_OR_DECAL types become volumes when
GameLOD UseShadowVolumes is on, else decals. SHADOW_VOLUME and NON_SELF go to
W3DVolumetricShadowManager ('classic'), SHADOW_VOLUME_NEW to the V2 manager
('v2'), decal types to the projected-shadow manager.

Geometry: the top LOD's meshes with CAST_SHADOW (assets.models 'shadow'). V2
skips a hidden mesh unless its name contains SHADOW (0x00107E76).

Extrusion (the light is TheW3DShadowManager light 0: the time of day's
terrain light 0 direction, reversed and placed 10,000,000 units away, so
effectively directional):

- classic: W3DVolumetricShadow::Update (0x000F4017) and
  updateOptimalExtrusionPadding (0x000F1212): from the four top corners of
  the object's world box, march along the light ray in 20-unit steps up to
  5120, keeping the lowest terrain sampled (stopping a corner where the ray
  dips under the terrain but is above it again 200 units further); the floor
  is that height - 0.1 (objects 2 or more units above ground use the
  terrain's minimum height instead). updateMeshVolume extrudes every
  silhouette vertex of a mesh by the distance from the mesh box top to that
  floor along the light ray.
- v2: W3DVolumetricShadowV2 update (0x001074D5): offset = normalized
  (position - light) scaled so that its z is -(height above ground +
  object box top + 20 + 0.1); every silhouette vertex moves by it.
"""

import math

import numpy as np

SHADOW_BITS = ('SHADOW_DECAL', 'SHADOW_VOLUME', 'SHADOW_VOLUME_NEW', 'SHADOW_DYNAMIC_PROJECTION',
               'SHADOW_DIRECTIONAL_PROJECTION', 'SHADOW_ALPHA_DECAL', 'SHADOW_ADDITIVE_DECAL',
               'SHADOW_VOLUME_NON_SELF_1', 'SHADOW_VOLUME_NON_SELF_2', 'SHADOW_VOLUME_NON_SELF_3',
               'SHADOW_ALPHA_DECAL_DYNAMIC', 'SHADOW_ADDITIVE_DECAL_DYNAMIC', 'SHADOW_MERGE_DECAL',
               'SHADOW_DECAL_TERRAIN_CLAIM', 'SHADOW_VOLUME_OR_DECAL', 'SHADOW_VOLUME_NEW_OR_DECAL')
SHADOW_EXTRUSION_BUFFER = 0.1
AIRBORNE_UNIT_GROUND_DELTA = 2.0
SAMPLING_INTERVAL, SAMPLING_LOOKAHEAD, SAMPLING_LENGTH = 20.0, 200.0, 5120.0


def shadow_kind(name, volumes):
    """'classic', 'v2', 'decal' or None for an INI Shadow value, as
    W3DShadowManager::addShadow routes it (volumes = UseShadowVolumes)."""
    name = (name or '').upper()
    if name == 'SHADOW_VOLUME_OR_DECAL':
        name = 'SHADOW_VOLUME' if volumes else 'SHADOW_DECAL'
    elif name == 'SHADOW_VOLUME_NEW_OR_DECAL':
        name = 'SHADOW_VOLUME_NEW' if volumes else 'SHADOW_DECAL'
    if name in ('SHADOW_VOLUME', 'SHADOW_VOLUME_NON_SELF_1', 'SHADOW_VOLUME_NON_SELF_2', 'SHADOW_VOLUME_NON_SELF_3'):
        return 'classic' if volumes else None
    if name == 'SHADOW_VOLUME_NEW':
        return 'v2' if volumes else None
    if name in ('SHADOW_DECAL', 'SHADOW_ALPHA_DECAL', 'SHADOW_ADDITIVE_DECAL', 'SHADOW_ALPHA_DECAL_DYNAMIC',
                'SHADOW_ADDITIVE_DECAL_DYNAMIC', 'SHADOW_MERGE_DECAL'):
        return 'decal'
    return None


def shadow_geometry(positions, triangles):
    """Welded shadow mesh with polygon neighbours, as W3DShadowGeometry builds it.

    Vertices at identical positions are merged (initFromMesh folds
    duplicates). buildPolygonNeighbors: the neighbour across edge k of a
    triangle (tri[k] -> tri[k+1]) is the first triangle that runs that edge
    the other way, unless its normal is exactly opposite (a back-to-back
    face); -1 when there is none. Returns dict(vertices [n, 3],
    triangles [m, 3], neighbours [m, 3], normals [m, 3])."""
    unique, inverse = np.unique(np.asarray(positions, np.float32), axis=0, return_inverse=True)
    vertices = unique.astype(np.float64)
    tris = inverse.reshape(-1)[np.asarray(triangles, np.int64)]
    tris = tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 2] != tris[:, 0])]
    p = vertices[tris]
    normals = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    unit = normals/np.where(length > 0, length, 1)
    runs = {}
    for t, (a, b, c) in enumerate(tris):
        for edge in ((a, b), (b, c), (c, a)):
            runs.setdefault(edge, []).append(t)
    neighbours = np.full((len(tris), 3), -1, np.int64)
    for t, tri in enumerate(tris):
        for k in range(3):
            a, b = tri[k], tri[(k+1) % 3]
            for other in runs.get((b, a), ()):
                if abs(float(unit[other] @ unit[t]) + 1.0) > 0.01:
                    neighbours[t, k] = other
                    break
    return dict(vertices=vertices, triangles=tris, neighbours=neighbours, normals=normals)


def silhouette_quads(geometry, place, scale, extrude):
    """World-space shadow volume triangles [k, 3, 3] of a shadow mesh's instances.

    W3DVolumetricShadow::buildSilhouette marks each polygon lit once
    (dot(light->vertex, normal) < 0; the light is effectively directional,
    so the light vector is the instance's extrusion direction). A silhouette
    edge is an edge of a lit polygon whose neighbour is unlit, or that has
    no neighbour (addNeighborlessEdges). constructVolume extrudes it into a
    quad from the edge to the edge moved by the extrusion vector, wound
    outwards so that its front face adds to the stencil count.

    place: [i, 4] x, y, z, angle; scale: [i]; extrude: [i, 3]."""
    place = np.asarray(place, np.float64).reshape(-1, 4)
    scale = np.asarray(scale, np.float64).reshape(-1)
    extrude = np.asarray(extrude, np.float64).reshape(-1, 3)
    if not len(place) or not len(geometry['triangles']):
        return np.zeros((0, 3, 3), np.float32)
    c, s = np.cos(place[:, 3]), np.sin(place[:, 3])
    rot = np.zeros((len(place), 3, 3))
    rot[:, 0, 0], rot[:, 0, 1], rot[:, 1, 0], rot[:, 1, 1], rot[:, 2, 2] = c, -s, s, c, 1.0
    world = np.einsum('iab,vb->iva', rot, geometry['vertices'])*scale[:, None, None] + place[:, None, :3]
    lit = np.einsum('iab,mb,ia->im', rot, geometry['normals'], extrude) < 0
    tris, neighbours = geometry['triangles'], geometry['neighbours']
    owner = np.repeat(np.arange(len(tris)), 3)
    start = tris.reshape(-1)
    end = tris[:, [1, 2, 0]].reshape(-1)
    across = neighbours.reshape(-1)
    other_lit = np.where(across >= 0, lit[:, np.maximum(across, 0)], False)
    instance, edge = np.nonzero(lit[:, owner] & ~other_lit)
    a = world[instance, start[edge]]
    b = world[instance, end[edge]]
    e = extrude[instance]
    quads = np.stack([np.stack([a, a + e, b], 1), np.stack([b, a + e, b + e], 1)], 1)
    return quads.reshape(-1, 3, 3).astype(np.float32)


def world_box(bounds, x, y, z, angle, scale):
    """World AABB (lo, hi) of a model box rotated about Z, scaled and placed."""
    lo, hi = (np.asarray(b, float)*scale for b in bounds)
    corners = np.array([[px, py, pz] for px in (lo[0], hi[0]) for py in (lo[1], hi[1]) for pz in (lo[2], hi[2])])
    c, s = math.cos(angle), math.sin(angle)
    rotated = np.column_stack([c*corners[:, 0] - s*corners[:, 1], s*corners[:, 0] + c*corners[:, 1], corners[:, 2]])
    rotated += (x, y, z)
    return rotated.min(0), rotated.max(0)


def classic_floor(box, z, ground, height_at, direction, min_height):
    """Floor z of a classic volume (updateOptimalExtrusionPadding + updateVolumes).
    `direction` is the unit vector from the light towards the scene."""
    if abs(z - ground) >= AIRBORNE_UNIT_GROUND_DELTA:
        return z - (abs(z - min_height) + SHADOW_EXTRUSION_BUFFER)
    lo, hi = box
    base = z
    d = np.asarray(direction, float)
    for cx, cy in ((hi[0], hi[1]), (lo[0], hi[1]), (lo[0], lo[1]), (hi[0], lo[1])):
        corner = np.array([cx, cy, hi[2]])
        steps = np.arange(1, int(math.ceil(SAMPLING_LENGTH/SAMPLING_INTERVAL)))
        points = corner + np.outer(steps*SAMPLING_INTERVAL, d)
        terrain = np.asarray(height_at(points[:, 0], points[:, 1]), float)
        ahead = points + d*SAMPLING_LOOKAHEAD
        above_again = ahead[:, 2] > np.asarray(height_at(ahead[:, 0], ahead[:, 1]), float)
        stop = np.nonzero((terrain > points[:, 2]) & above_again)[0]
        end = stop[0] if len(stop) else len(points)
        if end:
            base = min(base, float(terrain[:end].min()))
    return base - SHADOW_EXTRUSION_BUFFER


def classic_extrusion(mesh_top, floor, direction):
    """Extrusion vector of one mesh: the top of its box to the floor along the ray."""
    d = np.asarray(direction, float)
    return d*abs((mesh_top - floor)/d[2]) if abs(d[2]) > 1e-6 else d*SAMPLING_LENGTH


def v2_offset(z, ground, box_top, direction, length_scale=0.0, padding=0.1):
    """W3DVolumetricShadowV2's light offset (0x001074D5); box_top is the
    object-space box top (the constructor adds 20 units)."""
    d = np.asarray(direction, float).copy()
    if length_scale > 0.0:
        horizontal = (d[0]*d[0] + d[1]*d[1])*length_scale*length_scale
        if horizontal > d[2]:
            d[2] = math.sqrt(horizontal)
    if not d[2] > -0.01:
        height = box_top + 20.0
        d *= (z + height - ground + padding)*(-1.0/d[2])
    return d
