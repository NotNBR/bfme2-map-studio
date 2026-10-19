"""The map-cache entry of a built map, with its player starts checked.

BFME2 writes the cache for maps in its user maps folder itself, so nothing is
written here: a build calls cache_entry to check that the map has 2 to 8
consecutive player starts (exactly `players` of them when given, as in
map.toml), and may keep the returned entry for reference.
"""
import re
import zlib


def cache_entry(path, m, name, title, description, root=None, players=None):
    def escaped(raw):
        return ''.join(chr(c) if (48<=c<=57 or 65<=c<=90 or 97<=c<=122) else f'_{c:02X}' for c in raw)
    key=escaped(('maps\\'+name+'\\'+name+'.map').encode('ascii'))
    # MapCache.ini's extent is always (W - 2B) x 10, whatever the border records say
    # (all 122 retail entries; OpenBFME test_map_cache), unlike formats.terrain.playable_extent.
    t=m.heightmap();w=(t['width']-2*t['border'])*10;h=(t['height']-2*t['border'])*10
    start_objects=[]
    for o in m.objects():
        for k,_,v in o['properties']:
            if k=='waypointName' and re.fullmatch(r'Player_\d+_Start',v):
                start_objects.append((v,o))
    expected={f'Player_{i}_Start' for i in range(1,len(start_objects)+1)}
    if not 2<=len(start_objects)<=8 or {v for v,_ in start_objects}!=expected:
        raise ValueError('Map cache requires 2..8 unique consecutive player starts')
    if players is not None and len(start_objects)!=players:
        raise ValueError(f'The map has {len(start_objects)} player starts, but map.toml says {players} players')
    lines=[f'MapCache {key}',f'  fileSize = {path.stat().st_size}',
           f'  fileCRC = {zlib.crc32(path.read_bytes())}', '  timestampLo = 0','  timestampHi = 0',
           '  isOfficial = yes','  isMultiplayer = yes','  isScenarioMP = no',f'  numPlayers = {len(start_objects)}',
           '  extentMin = X:0.00 Y:0.00 Z:0.00',f'  extentMax = X:{w:.2f} Y:{h:.2f} Z:0.00',
           '  displayName = '+escaped(title.encode('utf-16-le')),
           '  description = '+escaped(description.encode('utf-16-le'))]
    for v,o in start_objects:
        lines.append(f'  {v} = X:{o["x"]:.2f} Y:{o["y"]:.2f} Z:0.00')
    lines.append('END')
    return '\n'.join(lines)+'\n'
