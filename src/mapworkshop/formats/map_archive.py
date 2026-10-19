"""A .map file's container: EAR (RefPack-compressed) or plain CkMp, unpacked.

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
