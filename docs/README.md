# Documentation

## Using the workshop

- [Getting started](getting-started.md): install, open a map, the `mw` command
- [Making maps](making-maps.md): map projects, builds and the toolkit
- [The viewer](viewer.md): navigation, live reload, marks for agents
- [Rendering](rendering.md): headless renders, and what the renderer reproduces of the game

## Designing maps

- [Map workflow](map-workflow.md), from rough composition to finished landscape
- [Worked example](map-workflow-example.md)

## Reference

- [Mapping reference](reference/mapping/README.md): the native map format, terrain,
  navigation, players and AI, scripts
- [Native map-file specification](reference/mapping/file-structure/specification.md)
- [Map graphics and terrain plans](reference/mapping/terrain-and-presentation/graphics.md)
- [Licenses and provenance](reference/licenses/README.md)

## Research

- [The Ashen March](research/ashen-march.md): the first map built from an empty
  native document
- [Water that runs downhill](research/water.md): waterfalls, stepped rivers,
  particle water, and what a map's `map.ini` may define

Reference and research pages record measured behavior and what remains
uncertain. Much of it was measured in the game with
[bfme-workshop](https://github.com/NotNBR/bfme-workshop)'s native host and
capture tools. This repository now has its own game runtime for test games,
the pathfinding grid and screenshots (`mw play`, `mw walkable --native`,
`mw capture`; see [testing in-game](making-maps.md#testing-in-game)).
