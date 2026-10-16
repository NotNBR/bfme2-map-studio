"""Authored glacier ruptures and the local scenery palette.

Rupture axes are world coordinates, independent of viewer marks. Their two
offset courses leave the middle of the ice sheet open and end before shore.
Widths are half-widths; the frost shoulders extend beyond the actual void.
"""

CREVASSES = [
    dict(name='North rupture', half_width=105., floor=8., points=[
        (12780., 14610.), (13030., 14820.), (13210., 14810.),
        (13480., 15040.), (13850., 15090.), (14170., 15310.),
        (14560., 15350.), (14850., 15290.)], branches=[
            [(13480., 15040.), (13400., 15210.), (13190., 15380.)],
            [(14170., 15310.), (14300., 15180.), (14340., 14960.)]]),
    dict(name='South rupture', half_width=120., floor=12., points=[
        (13630., 13130.), (13910., 13090.), (14200., 13200.),
        (14510., 13210.), (14760., 13400.), (15040., 13450.),
        (15260., 13690.), (15620., 13810.)], branches=[
            [(14200., 13200.), (14150., 13410.), (14220., 13570.)],
            [(15040., 13450.), (15080., 13240.), (15240., 13090.)]]),
]

# Radii encompass the inspected model silhouettes, not just their smaller
# INI collision shapes. All are stock, normal-scale winter scenery.
ROCKS = [('SnowyRock01', 55.), ('SnowyRock05', 85.),
         ('SnowyRock15', 105.), ('SnowyRock17', 45.),
         ('SnowyRock09', 45.), ('SnowyRock10', 40.),
         ('SnowyRock11', 30.), ('SnowyRock12', 28.)]
# Measured top outlines fit within 28 units of their native origins.
TREES = [('TreeSnowySpruce01', 28.), ('TreeSnowySpruce03', 28.)]

# Eight circles in 1000073095.jpg replace the old diagonal/saddle sites.
# The four inner marks follow diagonal passes; the outer four sit at the
# rear saddles. Positions are nudged within those areas to balance walking
# distance, with compact shelves and no obstacles on the through routes.
CHECKPOINTS = [
    dict(name='Northwest inner', template='SignalFire', junction=(9983., 18344.),
         position=(10248., 18587.), players=[2, 5, 13, 14], mark=(10700., 17800.)),
    dict(name='Northeast inner', template='SignalFire', junction=(18279., 18461.),
         position=(18506., 18181.), players=[3, 12, 13, 16], mark=(18770., 18550.)),
    dict(name='Southwest inner', template='SignalFire', junction=(10079., 10291.),
         position=(10310., 10015.), players=[6, 9, 14, 15], mark=(9910., 10110.)),
    dict(name='Southeast inner', template='SignalFire', junction=(18266., 10216.),
         position=(18533., 10458.), players=[8, 11, 15, 16], mark=(18550., 10600.)),
    dict(name='North saddle', template='Inn', junction=(14210., 23470.),
         position=(14460., 23390.), players=[2, 3, 13], mark=(14250., 23380.)),
    dict(name='East saddle', template='Inn', junction=(23320., 14150.),
         position=(23186., 14473.), players=[11, 12, 16], mark=(23090., 14230.)),
    dict(name='South saddle', template='Inn', junction=(14290., 5270.),
         position=(14270., 4790.), players=[8, 9, 15], mark=(14580., 5430.)),
    dict(name='West saddle', template='Inn', junction=(5130., 14270.),
         position=(5160., 14000.), players=[5, 6, 14], mark=(5080., 14210.)),
]
for checkpoint in CHECKPOINTS:
    dx, dy = (b-a for a, b in zip(checkpoint['junction'], checkpoint['position']))
    length = (dx*dx+dy*dy)**.5
    checkpoint['outward'] = (dx/length, dy/length)
    checkpoint['shelf_scale'] = 1.45 if checkpoint['template'] == 'Inn' else 1.

# Complete the short gaps between each rear access and the outer pass.
# These connections let all three surrounding bases approach the outer
# flags directly instead of giving the inner base a much shorter route.
CAPTURE_LINKS = [
    dict(name='North saddle link', points=[(14256., 23822.), (14086., 23299.)], width=220., main=False),
    dict(name='East saddle link', points=[(23392., 14146.), (22841., 14159.)], width=220., main=False),
    dict(name='South saddle link', points=[(14280., 5163.), (14504., 5697.)], width=220., main=False),
    dict(name='West saddle link', points=[(4911., 14280.), (5343., 14362.)], width=220., main=False),
]

# Unequal straight shoulders describe a cut into bedrock, not a circular
# plaza. Local coordinates are outward into the spur, then across it.
CHECKPOINT_SHELF = [(-135., -65.), (-90., -110.), (75., -100.),
                    (130., -45.), (100., 95.), (-65., 115.), (-130., 50.)]

# Four viewer circles locate fighting hollows, not their boundaries. Each
# follows its diagonal valley, with a bent axis, unequal banks and long ends.
# World centre copied from the mark; bearing is counterclockwise from east.
BATTLE_HOLLOWS = [
    dict(mark=1, name='Northwest inner', center=(10303.9, 18057.4),
         bearing=-48., length=1500., breadth=460., bend=105., bias=.12),
    dict(mark=2, name='Northeast inner', center=(18340.1, 18539.8),
         bearing=43., length=1550., breadth=500., bend=-120., bias=-.10),
    dict(mark=3, name='Southeast inner', center=(18141.8, 10401.8),
         bearing=-47., length=1450., breadth=470., bend=-100., bias=.14),
    dict(mark=4, name='Southwest inner', center=(9830.2, 10102.5),
         bearing=47., length=1500., breadth=480., bend=125., bias=-.13),
]
