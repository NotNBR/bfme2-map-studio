# Weather

How the game draws fog and falling rain and snow
([how the game draws a map](README.md)).

- Weather: the map.ini Weather block over weather.ini's. Hardware fog
  (HardwareFogEnable/Color/Start/End) reaches the effects as the WW3D `Fog`
  parameters (IsEnabled, Color, RangeStart, RangeEnd): the scene fog is set
  from TheWeatherSetting (near 0x00071F88) and bound by 0x0018BFCE. The
  effects switch fixed-function fog off and blend towards the fog colour by
  1 - clamp((|world - eye| - start) / (end - start)), per vertex (the
  studio's Python renderer evaluated it per pixel). Terrain, objects and
  water are fogged before the stencil shadows darken the frame; rain and
  snow are not fogged (their shader, bits 0x198B3, has fog off).
  With IsSnowing, falling rain or snow follows W3DSnowManager and
  renderAsQuads (0x00093CC3, read from game.dat): emitters every SnowSpacing
  units over the first of NumberTiles x NumberTiles sub-boxes of the map,
  repeated over the tiles; heights from a 64x64 table of rand() %
  SnowBoxHeight, falling from SnowBoxHeight (world height); SnowAmplitude
  wobble; drift time x SnowXYSpeed less SnowXYSpeed x box / SnowSpeed per
  completed fall. Each drop is a quad spanned by the camera's right vector
  and world Z, 0.707 x SnowQuadSize either side of its centre, alpha blended
  without depth writes, with no distance cull (only the near clip).

## Open questions

- Rain density and lean: the rain ramp (RampControl, RampSpacing,
  RampSpeed) runs through W3DSnowManager's state transition (0x00094652,
  matched) into 0x00093B5B and 0x00093349, which are not. The studio's
  Python renderer kept spacing and speed at SnowSpacing/SnowSpeed, and native
  rain looked denser than its rain, and slightly slanted. The drop brightness
  gate (0x000932E1) and lightning (LightningEnabled/Factor/Duration/Chance;
  trigger 0x0009322D matched) are not traced further.
