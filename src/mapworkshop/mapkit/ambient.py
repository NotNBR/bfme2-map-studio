"""Ambient sound: a map's stream bed and its local emitters.

Stock evidence (local/game/maps, the 13 multiplayer maps, measured): each map
has one AmbStream_ object near its centre, a looping bed heard everywhere,
and 6 to 94 Amb_ emitters, each heard round where it stands: water along
rivers, creeks and lakes, birds in woods and open country, wind and falling
stones on the heights, village sounds in settlements. The same sound repeats
about 700 to 1,000 apart (median of the nearest same-sound distances 985,
lower quartile 684). The palettes below are the emitters the stock maps
place with each bed.

    from mapworkshop.mapkit.ambient import ambient, along
    ambient(m, 'rohan', centre=(2395, 2395), zones=dict(
        river=along(river_line, 600), woods=copse_centres, heights=hilltops, settlement=[hold]))
"""
import math

from mapworkshop.formats.terrain import playable_extent
from mapworkshop.mapkit.sites import spread

# Setting: the bed and, per kind of place, the emitters to cycle through.
PALETTES = {
    'rohan': dict(stream='AmbStream_PlainsOfRohan', zones=dict(
        river=['Amb_WaterRiver1Loop', 'Amb_WaterSplashFish1'], creek=['Amb_WaterCreek2Loop'],
        lake=['Amb_WaterLakeLight1'],
        open=['Amb_BirdsDesert1', 'Amb_BirdsAmonHen2', 'Amb_CritterDesert1', 'Amb_BirdsBuzzard'],
        woods=['Amb_BirdsAmonHen1', 'Amb_CreakTree1', 'Amb_BirdsAmonHen2'],
        heights=['Amb_WindMT', 'Amb_BirdsMountain1', 'Amb_BirdsFalcon1', 'Amb_DirtFall1', 'Amb_BirdsMountain2'],
        settlement=['Amb_VillageWalla1Loop', 'Amb_VillageCoals', 'Amb_ShutterWoodCreaksCracks1'],
        stable=['Amb_VillageStable'], fire=['Amb_Torch1'])),
    'grassland': dict(stream='AmbStream_EdorasGrasslands', zones=dict(
        river=['Amb_WaterRiver1Loop'], creek=['Amb_WaterCreek2Loop'], lake=['Amb_WaterLakeLight1'],
        open=['Amb_BirdsAmonHen2', 'Amb_BirdsDesert1', 'Amb_CritterDesert1', 'Amb_FlyBuzz1'],
        woods=['Amb_BirdsAmonHen1', 'Amb_CreakTree1', 'Amb_BirdsCrowMellow'],
        heights=['Amb_RockTumbleMedium', 'Amb_DirtFall1', 'Amb_WindMT'],
        coast=['Amb_OceanWaves1', 'Amb_BirdsBeach'], settlement=['Amb_VillageWalla1Loop', 'Amb_VillageChickens'],
        stable=['Amb_VillageStable'], fire=['Amb_Torch1'])),
    'forest': dict(stream='AmbStream_AmonHenForest1', zones=dict(
        river=['Amb_WaterRiver1Loop', 'Amb_WaterSplashFish1'], creek=['Amb_WaterCreek2Loop'],
        lake=['Amb_WaterLakeLight1'], open=['Amb_BirdsAmonHen2', 'Amb_BirdsDesert1', 'Amb_CritterDesert1'],
        woods=['Amb_BirdsAmonHen1', 'Amb_BirdsIthilien2Loop', 'Amb_BirdsIthilien1Loop'],
        heights=['Amb_BirdsMountain2', 'Amb_BirdsMountain1', 'Amb_BirdsFalcon1'],
        coast=['Amb_OceanWaves1', 'Amb_BirdsBeach'], settlement=['Amb_VillageWalla1Loop', 'Amb_VillageChickens'],
        stable=['Amb_VillageStable'], fire=['Amb_Torch1'])),
    'shire': dict(stream='AmbStream_Shire', zones=dict(
        river=['Amb_WaterRiver1Loop'], creek=['Amb_WaterCreek2Loop'], lake=['Amb_WaterLakeLight1'],
        open=['Amb_BirdsAmonHen2', 'Amb_CricketsBed1', 'Amb_FlyBuzz1'],
        woods=['Amb_BirdsAmonHen1', 'Amb_BirdsIthilien1Loop', 'Amb_CreakTree1'], heights=['Amb_BirdsMountain1'],
        settlement=['Amb_VillageWalla1Loop', 'Amb_VillageChickens', 'Amb_VillageBarrelMaker'],
        stable=['Amb_VillageStable'], fire=['Amb_Torch1'])),
    'winter': dict(stream='AmbStream_WinterTundra', zones=dict(
        river=['Amb_WaterRiver1Loop'], creek=['Amb_WaterCreek1Loop'], lake=['Amb_WaterLakeLight1'],
        open=['Amb_WindCold1', 'Amb_BirdsCrowSimple'], woods=['Amb_CreakTree1', 'Amb_BirdsOwl'],
        heights=['Amb_WindMountain1', 'Amb_WindCold1', 'Amb_RockTumbleMedium'],
        settlement=['Amb_VillageWalla1Loop'], fire=['Amb_Campfire1'])),
    'desert': dict(stream='AmbStream_Desert1', zones=dict(
        river=['Amb_WaterRiver1Loop'], lake=['Amb_WaterLakeLight1'],
        open=['Amb_BirdsDesert1', 'Amb_CritterDesert1', 'Amb_CritterDesert2', 'Amb_FlyBuzz1'],
        heights=['Amb_WindMT', 'Amb_DirtFall1', 'Amb_RockTumbleMedium'], coast=['Amb_OceanWaves1', 'Amb_BirdsBeach'],
        settlement=['Amb_VillageWalla1Loop'], fire=['Amb_Torch1'])),
}
SPACING = 700                   # same kind of place: emitters at least this far apart


def along(line, step):
    """Points every `step` along a polyline: candidates for water sounds."""
    points, carry = [], step/2
    for (ax, ay), (bx, by) in zip(line, line[1:]):
        length = math.hypot(bx-ax, by-ay)
        t = carry
        while t <= length:
            points.append((ax+(bx-ax)*t/length, ay+(by-ay)*t/length))
            t += step
        carry = t-length
    return points


def plan(palette, centre, zones, spacing=SPACING, limits=None, inside=None):
    """The emitters for a map, as (template, x, y): the palette's stream at
    `centre`, and for each kind of place in `zones` ({kind: candidate points})
    points at least `spacing` apart (sites.spread), cycling through the kind's
    sounds. `limits` caps a kind's count; `inside(x, y)` keeps points on the map."""
    p = PALETTES[palette] if isinstance(palette, str) else palette
    out = [(p['stream'], float(centre[0]), float(centre[1]))]
    for kind, candidates in zones.items():
        sounds = p['zones'].get(kind)
        if not sounds:
            raise ValueError(f'The {palette} palette has no sounds for {kind!r}; it has {", ".join(p["zones"])}')
        keep = [c for c in candidates if inside is None or inside(*c)]
        count = (limits or {}).get(kind, len(keep))
        for i, (x, y) in enumerate(spread(keep, count, apart=spacing)):
            out.append((sounds[i % len(sounds)], x, y))
    return out


def ambient(m, palette, centre, zones, spacing=SPACING, limits=None, layer='Sounds'):
    """Add plan(...)'s emitters to the map; returns them."""
    from mapworkshop.mapkit.blank import add_object
    w, h = _playable(m)
    emitters = plan(palette, centre, zones, spacing, limits, inside=lambda x, y: 0 <= x <= w and 0 <= y <= h)
    for template, x, y in emitters:
        add_object(m, template, x, y, layer=layer)
    return emitters


def _playable(m):
    return playable_extent(m.heightmap())
