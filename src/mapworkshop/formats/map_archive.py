"""Camera-only edits to native BFME maps. All other decompressed bytes survive.

GPL-3.0-only. Container/RefPack layouts cross-checked with OpenSAGE Data/Map
and FileFormats.RefPack; see native/THIRD_PARTY.md.
"""

import struct


def refpack(data):
    if len(data)<5 or data[0]&0x3e!=0x10 or data[1]!=0xfb:
        raise ValueError('Invalid RefPack header')
    width=4 if data[0]&0x80 else 3
    pos=2+(width if data[0]&1 else 0)
    size=int.from_bytes(data[pos:pos+width],'big'); pos+=width
    if size>128*1024*1024: raise ValueError('Map exceeds size limit')
    out=bytearray()
    while True:
        if pos>=len(data): raise ValueError('Truncated RefPack command')
        a=data[pos];pos+=1;count=distance=0
        if a<0x80:
            b=data[pos];pos+=1
            literal=a&3;count=((a&0x1c)>>2)+3;distance=((a&0x60)<<3)+b+1
        elif a<0xc0:
            b,c=data[pos:pos+2];pos+=2
            literal=b>>6;count=(a&0x3f)+4;distance=((b&0x3f)<<8)+c+1
        elif a<0xe0:
            b,c,d=data[pos:pos+3];pos+=3
            literal=a&3;count=((a&0xc)<<6)+d+5;distance=((a&0x10)<<12)+(b<<8)+c+1
        elif a<0xfc:
            literal=((a&0x1f)+1)*4
        else:
            literal=a&3
        if pos+literal>len(data): raise ValueError('Truncated RefPack literals')
        out.extend(data[pos:pos+literal]);pos+=literal
        if count:
            if not 0<distance<=len(out): raise ValueError('Invalid RefPack distance')
            pattern=out[-distance:]
            out.extend((pattern*((count+distance-1)//distance))[:count])
        if len(out)>size: raise ValueError('RefPack output exceeds declared length')
        if a>=0xfc: break
    if len(out)!=size: raise ValueError('RefPack output size mismatch')
    return bytes(out)


def unpack(data):
    if data[:4]==b'EAR\0':
        declared=struct.unpack_from('<I',data,4)[0]
        data=refpack(data[8:])
        if len(data)!=declared: raise ValueError('EAR size mismatch')
    if data[:4]!=b'CkMp': raise ValueError('Unsupported map container')
    return data


def metadata(data):
    """Return WorldInfo properties with exact original value offsets."""
    if data[:4]!=b'CkMp': raise ValueError('Expected uncompressed map')
    count=struct.unpack_from('<I',data,4)[0]; pos=8;names={}
    if count>100000: raise ValueError('Invalid map string count')
    for expected in range(count,0,-1):
        length=shift=0
        while True:
            b=data[pos];pos+=1;length|=(b&127)<<shift;shift+=7
            if b<128:break
            if shift>28:raise ValueError('Invalid map string length')
        name=data[pos:pos+length].decode('utf-8');pos+=length
        index=struct.unpack_from('<I',data,pos)[0];pos+=4
        if index!=expected:raise ValueError('Unexpected map string index')
        names[index]=name
    while pos<len(data):
        index,version,size=struct.unpack_from('<IHI',data,pos);pos+=10
        end=pos+size
        if end>len(data):raise ValueError('Map chunk outside container')
        if names[index]!='WorldInfo':pos=end;continue
        fields={};count=struct.unpack_from('<H',data,pos)[0];pos+=2
        for _ in range(count):
            kind=data[pos];index=int.from_bytes(data[pos+1:pos+4],'little');pos+=4
            offset=pos
            if kind==0:value=bool(data[pos]);pos+=1
            elif kind in (1,2):value=struct.unpack_from('<i' if kind==1 else '<f',data,pos)[0];pos+=4
            elif kind in (3,4,5):
                length=struct.unpack_from('<H',data,pos)[0];pos+=2
                length*=2 if kind==4 else 1
                value=data[pos:pos+length].decode('utf-16-le' if kind==4 else 'cp1252');pos+=length
            else:raise ValueError('Unknown map property type')
            fields[names[index]]={'kind':kind,'offset':offset,'value':value}
        if pos!=end:raise ValueError('Unexpected WorldInfo trailing bytes')
        return fields
    raise ValueError('Missing WorldInfo')


def extend_camera(data,factor):
    original=unpack(data); fields=metadata(original)
    # GroundMin/MaxHeight describe terrain-related camera data; preserve them.
    candidates=[(k,v) for k,v in fields.items() if k=='cameraMaxHeight']
    if not candidates:
        return original,[]  # map inherits the GameData default
    result=bytearray(original)
    changes=[];allowed=set()
    for key,field in candidates:
        if field['kind']!=2 or not 50<=field['value']<=2000:
            raise ValueError('Unrecognized native camera height')
        new=field['value']*factor
        struct.pack_into('<f',result,field['offset'],new)
        allowed.update(range(field['offset'],field['offset']+4))
        changes.append({'field':key,'offset':field['offset'],'before':field['value'],'after':new})
    if any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(original,result))):
        raise AssertionError('Non-camera map content changed')
    return bytes(result),changes
