"""Headless BFME2 map renderer.

An offscreen OpenGL reimplementation of the game's terrain, water and object
drawing, ported from the retail effect files (Shaders.big) and the EA/openbfme2
height-map source. Assets are read directly from the installed game archives.
It is an independent preview, not the game's renderer: check important
conclusions in the game itself (`mw play`).
"""
