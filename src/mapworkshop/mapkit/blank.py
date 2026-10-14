"""Construct a BFME2 CkMp document from typed fields, without a donor map.

GPL-3.0-only. See docs/research/ashen-march.md for format references and verification.
All spatial data is generated here. No .map file is read by this constructor.
"""

import numpy as np
from mapworkshop.formats import sections
from mapworkshop.formats.map import Map, Chunk, tile_offset
from mapworkshop.formats.terrain import encode_blend, encode_heights
from mapworkshop.formats.water import standing_water


def add_chunk(m, name, version, data):
    m.chunks.append(Chunk(m.intern(name), version, data))


def add_section(m, name, version, value):
    """Append a section written from its values (formats.sections)."""
    data = sections.encode(name, version, value, m)
    add_chunk(m, name, version, data)


def lighting():
    from mapworkshop.formats.lighting import encode, slots

    # Retail order: terrain sun, object sun/fills, terrain fills, third array.
    # Raking sunlight and restrained fill reveal terrain and model volume.
    configurations = []
    for _ in range(4):
        sources = [
            ((.18,.19,.215),(.70,.65,.56),(.64,.54,-.55)),
            ((0,0,0),(.045,.06,.085),(-.65,-.3,-.70)),
            ((0,0,0),(.015,.02,.025),(.2,-.9,-.38))]
        lights = []
        for target, index in slots(8):
            ambient, color, direction = sources[index]
            gain = 1.0 if target == 'terrain' else 1.10
            lights.append(dict(target=target, light_index=index, ambient=ambient,
                               diffuse=tuple(v*gain for v in color), direction=direction))
        configurations.append(lights)
    out = encode(dict(time_of_day=2, configurations=configurations,
                      overbright_value=1.0, chunk_flag_raw=0,
                      vector_triplets=[(.15686275,)*3, (.4980392,)*3, (.4980392,)*3],
                      shadow_color_raw=0xFFA0A0A0, final_values=(1., 1., 1.)))
    assert len(out)==1360
    return bytes(out)


def set_heights(m, values):
    t=m.heightmap(); h,w=values.shape
    assert (h,w)==(t['height'],t['width'])
    if not np.isfinite(values).all() or values.min()<0 or values.max()>2559:
        raise ValueError('Height outside native unsigned fixed-point range')
    border=t['border']
    m.chunk('HeightMapData').data=encode_heights(dict(border=border,borders=[(w-2*border,h-2*border)],
                                                      elevations=np.rint(values/.0390625)))


def terrain_cell_sizes(palette):
    """Texture-class size per palette name: the file's width in 64-pixel tiles.

    WorldHeightMap::readTexClass skips a class whose file has fewer tiles than
    declared, so the declaration must not exceed the installed texture.
    """
    from mapworkshop.render.assets import GameAssets
    assets = GameAssets()
    sizes = []
    for name in palette:
        file = assets.terrain_textures.get(name.lower())
        image = assets.image(file) if file else None
        if image is None:
            raise ValueError('Terrain texture not installed: '+name)
        sizes.append(max(1, min(image.shape[0], image.shape[1])//64))
    return sizes


# Blend corner sets (0:(x,y) 1:(x+1,y) 2:(x+1,y+1) 3:(x,y+1)) to native blend
# records (direction bytes, flags bit 0 = inverted, long diagonal), following
# WorldHeightMap::getAlphaUVData.
H, V, R, L = b'\1\0\0\0', b'\0\1\0\0', b'\0\0\1\0', b'\0\0\0\1'
CORNER_BLENDS = {
    0b0110: (H, 0, 0), 0b1001: (H, 1, 0), 0b1100: (V, 0, 0), 0b0011: (V, 1, 0),
    0b0100: (R, 0, 0), 0b0010: (R, 1, 0), 0b1000: (L, 0, 0), 0b0001: (L, 1, 0),
    0b1110: (R, 0, 1), 0b0111: (R, 1, 1), 0b1101: (L, 0, 1), 0b1011: (L, 1, 1),
    # Opposite corners have no single tile; keep the larger side.
    0b0101: (R, 1, 1), 0b1010: (L, 0, 1),
}


def blend_record(tile, direction, flags, long_diagonal=0):
    """A blend record (formats.terrain): no custom edge, the retail marker."""
    return dict(tile=tile,direction=direction,flags=flags,long_diagonal=long_diagonal,
                custom_edge_class=-1,marker=0x7ada0000)


# The cells touching each corner of a cell, as (dy, dx), in corner bit order.
CORNER_CELLS = [[(-1,-1),(-1,0),(0,-1)],[(-1,0),(-1,1),(0,1)],[(0,1),(1,1),(1,0)],[(1,0),(1,-1),(0,-1)]]
# Opposite corners as two single-corner blends, one in each layer.
OPPOSITE_CORNERS = {0b0101: (0b0001,0b0100), 0b1010: (0b0010,0b1000)}


def corner_masks(labels, texture):
    """For every cell, the bit mask of its corners touched by a neighbour of
    `texture` (an array of one texture per cell, -1 for none)."""
    h,w=labels.shape
    padded=np.pad(labels,1,mode='edge').astype(np.int32)
    mask=np.zeros((h,w),dtype=np.int32)
    for bit,cells in enumerate(CORNER_CELLS):
        hit=np.zeros((h,w),bool)
        for dy,dx in cells:
            hit|=padded[1+dy:1+dy+h,1+dx:1+dx+w]==texture
        mask|=hit.astype(np.int32)<<bit
    mask[texture<0]=0
    return mask


def higher_neighbours(labels, below=None):
    """For every cell, its highest neighbouring texture above its own (and
    under `below`, when given), or -1."""
    h,w=labels.shape
    padded=np.pad(labels,1,mode='edge').astype(np.int32)
    own=labels.astype(np.int32); best=np.full((h,w),-1,np.int32)
    for dy in (-1,0,1):
        for dx in (-1,0,1):
            if dy or dx:
                n=padded[1+dy:1+dy+h,1+dx:1+dx+w]
                ok=n>own if below is None else (n>own)&(n<below)
                best=np.where(ok&(n>best),n,best)
    return best


def fill_enclosed(labels, rounds=64):
    """A cell whose four corners a higher texture touches can show no
    transition, since no blend covers the whole cell: it takes that texture
    (the highest one, if several), and its neighbours are looked at again.
    Removes lone cells and one-cell gaps that would show as sharp squares."""
    labels=labels.astype(np.int32)
    for _ in range(rounds):
        fill=np.full(labels.shape,-1,np.int32)
        for texture in np.unique(labels):
            full=(corner_masks(labels,np.full(labels.shape,texture,np.int32))==0b1111)&(labels<texture)
            fill[full]=texture
        if not (fill>=0).any():
            break
        labels=np.where(fill>=0,fill,labels)
    return labels


def corner_blend_records(labels, tile_index):
    """Up to two blends per cell from the corners its higher neighbours
    touch, as BFME 2 composites them (WorldHeightMap::getPointerToTileData
    0x000AED2E): the base tile, then the primary blend, then the three-way
    blend on top, each through one of the 64x64 alpha tiles (0x000AC6F9).

    The highest neighbouring texture goes on top, in the three-way layer, the
    next one below it in the primary layer; with a single neighbouring
    texture it alone is the primary. Opposite corners of one texture become a
    single-corner blend in each layer. Diagonal and three-corner (long
    diagonal) blends replace the stair-step edges that cardinal-only blending
    leaves along curved boundaries.

    The game draws the three-way layer only over a primary blend, and since
    each tile is composited per pixel its triangle orientation does not
    matter: no record carries WorldBuilder's forced-flip bit (2), which
    BFME 2's alpha lookup (0x000AC6A6) would read as inverted. Call
    `fill_enclosed` first: a fully enclosed cell has no blend.
    """
    h,w=labels.shape
    top=higher_neighbours(labels); top_mask=corner_masks(labels,top)
    below=higher_neighbours(labels,np.where(top<0,0,top)); below_mask=corner_masks(labels,below)
    for mask in (top_mask,below_mask):
        mask[[0,-1],:]=0; mask[:,[0,-1]]=0
    blends=np.zeros((h,w),dtype='<u4'); extra=np.zeros((h,w),dtype='<u4'); records=[]; lookup={}
    def record(texture,y,x,mask):
        direction,flags,long_diagonal=CORNER_BLENDS[mask]
        key=(int(tile_index(texture,y,x)),direction,flags,long_diagonal)
        if key not in lookup:
            records.append(blend_record(*key))
            lookup[key]=len(records)
        return lookup[key]
    for y,x in zip(*np.nonzero(top_mask)):
        t,tm,b,bm=int(top[y,x]),int(top_mask[y,x]),int(below[y,x]),int(below_mask[y,x])
        if bm:
            blends[y,x]=record(b,y,x,bm); extra[y,x]=record(t,y,x,tm)
        elif tm in OPPOSITE_CORNERS:
            first,second=OPPOSITE_CORNERS[tm]
            blends[y,x]=record(t,y,x,first); extra[y,x]=record(t,y,x,second)
        else:
            blends[y,x]=record(t,y,x,tm)
    return blends,extra,records


def set_materials(m, palette, labels, blocked=None, blend_edges=True, cell_sizes=None, corner_blends=False):
    h,w=labels.shape; yy,xx=np.indices((h,w))
    sizes=list(cell_sizes or [4]*len(palette))
    if len(sizes)!=len(palette):
        raise ValueError('One cell size per palette texture')
    counts=[size*size for size in sizes]
    cell_start=np.cumsum([0]+counts[:-1])
    # Each texture class holds size x size cells of four quarter tiles.
    tile_start=np.array(4*cell_start)
    phases=np.stack([tile_offset(xx,yy,size) for size in sorted(set(sizes))])
    phase_of={size:i for i,size in enumerate(sorted(set(sizes)))}
    label_phase=np.array([phase_of[size] for size in sizes])
    def tile_index(label,y,x):
        return tile_start[label]+phases[label_phase[label],y,x]
    if blend_edges and corner_blends:
        labels=fill_enclosed(labels)
    tiles=tile_index(labels,yy,xx).astype('<u2')
    blends=np.zeros((h,w),dtype='<u4'); records=[]; lookup={}
    zero=np.zeros((h,w),dtype='u1'); three_way=zero
    # Native directional transitions around material regions. Tile phases match
    # primary terrain and blend descriptors are interned rather than per-cell.
    if blend_edges and corner_blends:
        blends,three_way,records=corner_blend_records(labels,tile_index)
    elif blend_edges:
        for dy,dx,direction,flags in [(0,1,b'\1\0\0\0',0),(0,-1,b'\1\0\0\0',1),
                                      (1,0,b'\0\1\0\0',0),(-1,0,b'\0\1\0\0',1)]:
            other=np.roll(labels,(-dy,-dx),(0,1))
            mask=(other>labels)&(blends==0)
            mask[[0,-1],:]=False; mask[:,[0,-1]]=False
            for y,x in zip(*np.nonzero(mask)):
                key=(int(tile_index(other[y,x],y,x)),direction,flags)
                if key not in lookup:
                    records.append(blend_record(*key))
                    lookup[key]=len(records)
                blends[y,x]=lookup[key]
    blocked=zero if blocked is None else blocked.astype('u1')
    arrays=dict(tiles=tiles,blends=blends,three_way=three_way,cliffs=zero,impassable=blocked,impassable_players=zero,
                passage_widths=zero,taintable=zero,extra_passable=zero,flammability=zero,visible=np.ones((h,w),'u1'))
    textures=[dict(cell_start=int(cell_start[i]),cell_count=counts[i],cell_size=sizes[i],name=name)
              for i,name in enumerate(palette)]
    m.chunk('BlendTileData').data=encode_blend(dict(arrays=arrays,texture_cells=sum(counts),textures=textures,
        edge_texture_cells=0,edge_textures=[],blend_records=records,cliff_records=[]),18)


def add_object(m, template, x, y, angle=0, layer='', extra=(), z=0):
    index=getattr(m,'_object_count',0)+1; m._object_count=index
    fields=[('objectInitialHealth',1,100),('objectEnabled',0,1),('objectIndestructible',0,0),
            ('objectUnsellable',0,0),('objectPowered',0,1),('objectRecruitableAI',0,1),
            ('objectTargetable',0,0),('objectBasePriority',1,40),('objectBasePhase',1,1),
            ('originalOwner',3,'PlyrCivilian/teamPlyrCivilian'),('uniqueID',3,f'Ashen_{index:05d}'),
            ('objectLayer',3,layer)]
    overrides={f[0] for f in extra}; fields=[f for f in fields if f[0] not in overrides]+list(extra)
    o=dict(template=template,x=x,y=y,z=z,angle=angle,flags=0,properties=fields)
    m.chunk('ObjectsList').data+=m.encode_object(o).encode()


def set_world(m, **values):
    """Change WorldInfo properties by name, e.g. set_world(m, cameraMaxHeight=30000.)."""
    fields=sections.read(m,'WorldInfo')
    unknown=set(values)-{k for k,_,_ in fields}
    if unknown:raise KeyError(f'No WorldInfo properties {sorted(unknown)}')
    sections.write(m,'WorldInfo',[(k,kind,values.get(k,v)) for k,kind,v in fields])


def water_plane(m, name, height, points=None, uv_speed=.03, margin=300, shader='wtr_Riv03.W3D'):
    """One standing-water area at `height`: under it, the terrain is water.
    Without `points` it covers the playable area and `margin` beyond.
    `shader` is the stock water model; its WindSpeed and WindAngle scroll the
    ripples one way over the whole area. Stock maps put flowing rivers
    (mapkit.rivers) over both kinds: wtr_Riv03 in Ithilien, the nearly still
    'wtr_Riv_pond.W3D' in Fangorn."""
    if points is None:
        t=m.heightmap();w=(t['width']-2*t['border'])*10;h=(t['height']-2*t['border'])*10
        points=[(-margin,-margin),(w+margin,-margin),(w+margin,h+margin),(-margin,h+margin)]
    m.chunk('StandingWaterAreas').data=standing_water([dict(id=1,name=name,layer='Water',
        uv_speed=uv_speed,additive=0,bump_texture='WaterRippleBump.tga',sky_texture='SkyEnv.tga',
        points=points,water_height=int(height),shader=shader,depth_colors='LUTDepthTint.tga')])


def starts(m, points):
    for i,(x,y) in enumerate(points,1):
        name=f'Player_{i}_Start'
        add_object(m,'*Waypoints/Waypoint',x,y,layer='Starts',extra=[
            ('originalOwner',3,'/team'),('uniqueID',3,name),('waypointID',1,i),
            ('waypointName',3,name),('waypointTypeOption',3,'')])


def create(width=840,height=950,border=30,title='The Ashen March',elevation=100,player_count=2,
           description='A ruined frontier beneath the shadow of Mordor.'):
    if not isinstance(player_count,int) or not 2<=player_count<=8:
        raise ValueError('A skirmish map needs 2..8 player sides')
    if min(width,height)<64 or max(width+2*border,height+2*border)>2048:
        raise ValueError('Supported experimental sample dimensions: 64..2048')
    m=object.__new__(Map);m.names={};m.chunks=[];m._object_count=0
    w,h=width+2*border,height+2*border
    add_section(m,'HeightMapData',5,dict(border=border,borders=[(width,height)],
                                         elevations=np.full((h,w),round(elevation/.0390625))))
    add_chunk(m,'BlendTileData',18,b'');set_materials(m,['DirtMordor04'],np.zeros((h,w),dtype='u2'))
    # cameraMaxHeight 300, as every stock map: the game's camera starts at this
    # height, and far higher (20,000) it sees nothing but black past its draw range.
    add_section(m,'WorldInfo',1,[('cameraMaxHeight',2,300.),('cameraPitchAngle',2,37.5),('cameraYawAngle',2,0.),
            ('cameraScrollSpeedScalar',2,1.),('isLivingWorldScriptHolder',0,0),('weather',1,0),
            ('compression',1,0),('mapName',3,title),('mapDescription',3,description),
            ('cameraGroundMinHeight',2,0.),('cameraGroundMaxHeight',2,1400.),('isScenarioMultiplayer',0,0),
            ('cameraMapHeightSmoothnessScalar',2,.75)])
    add_section(m,'MPPositionList',0,[dict(chunk='MPPositionInfo',version=1,human=1,computer=1,load_ai_script=1,
                                           team=0xffffffff,side_restrictions=[])]*8)
    players=[('',''),('PlyrNeutral','Neutral'),('PlyrCivilian','Civilian'),('PlyrCreeps','Civilian')]
    players += [('Skirmish'+s,'Tutorial' if s=='Men' else s) for s in ['Men','Elves','Dwarves','Isengard','Mordor','Wild']]
    players += [(f'Player_{i}','Civilian') for i in range(1,player_count+1)]
    add_section(m,'SidesList',6,dict(unknown_boolean=1,players=[dict(build_list=[],properties=[
        ('playerName',3,name),('playerIsHuman',0,0),('playerDisplayName',4,name or 'Neutral'),
        ('playerFaction',3,'Faction'+faction if faction else ''),('playerAllies',3,''),('playerEnemies',3,'')])
        for name,faction in players]))
    add_section(m,'LibraryMapLists',1,[dict(chunk='LibraryMaps',version=1,maps=[])]*len(players))
    add_section(m,'Teams',1,[[('teamName',3,'team'+name),('teamOwner',3,name),('teamIsSingleton',0,1)]
                             for name,_ in players])
    add_section(m,'PlayerScriptsList',1,[dict(chunk='ScriptList',version=1,children=[])]*len(players))
    for name,v in [('BuildLists',1),('ObjectsList',3),('TriggerAreas',1),('StandingWaterAreas',2),('RiverAreas',2),
                   ('StandingWaveAreas',2)]:
        add_section(m,name,v,[])
    add_chunk(m,'GlobalLighting',8,lighting())
    add_section(m,'PostEffectsChunk',1,[])
    # The landscape macro texture, stretched: the game's 256px urban default
    # (TSNoiseUrb.tga) makes a coarse repeating camouflage grid.
    add_section(m,'EnvironmentData',3,dict(water_max_alpha_depth=3.,deep_water_alpha=1.,macro_texture_stretched=1,
                                           macro_texture='TSNoise2kNoGreen.tga',cloud_texture='TSCloudMed.tga'))
    for name,v in [('NamedCameras',2),('CameraAnimationList',3),('WaypointsList',1)]:
        add_section(m,name,v,[])
    return m
