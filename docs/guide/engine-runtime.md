# The OpenBFME runtime

Studio is a separate Python toolkit and Godot application. It consumes the
existing OpenBFME fork through a Studio-owned adapter. This integration needs
no changes to the official Godot port, and does not modify the source submodule.

## Source or bundle

The default is a build of the pinned source submodule. The viewer packages that
build into `local/openbfme/runtimes/<content hash>/` and consumes its manifest.
An unchanged payload reuses the same directory. Game assets, map projects,
settings, compiler output and Godot import caches are excluded.

To prepare a complete runtime explicitly:

```powershell
mw engine package
mw engine package --out local/packages/openbfme-runtime
```

`--out` must name a new directory. The bundle contains the game project, compiled
extension, matching shaders and resources, the matching Godot executables,
the headless battle runner, archive policy metadata and the engine license.
The manifest records the engine revision, source build fingerprint, platform,
Godot version, Studio adapter API, capabilities and SHA-256 of every payload file.
It describes a Studio integration contract, not an SDK supported by upstream.

To use a bundle, including on a machine without the engine source or compiler:

```powershell
mw config openbfme_bundle local/packages/openbfme-runtime
mw engine check
```

Relative paths resolve from the Studio checkout. The runtime must match Studio's
recorded engine commit, Godot 4.7.2 and Windows x64. A source ZIP has no Git pin;
there the adapter version, capabilities and file integrity are checked, and Git
is not required. Missing files, changed hashes,
missing capabilities or a different engine pin stop before launch with an error.
The normal viewer, `mw render`, `mw play --godot` and `mw battle` use this selection.
Retail assets are still supplied separately by the user. Python remains needed
for Studio; the bundle removes the engine compilation requirement.

`mw engine check` verifies the bundle and starts Godot headlessly to check the
actual extension classes and methods, including Test mode and path inspection.
It requires no retail assets. Rendering and simulation checks still require
the matching game installations; API availability alone does not prove parity.

Switch back to source builds with:

```powershell
mw config openbfme_bundle source
```

The next run restores the binaries from the selected source build. Bundles remain
immutable; Godot runs copies in `local/openbfme/project/` and
`local/openbfme/viewer/`. Copy a bundle directory as a whole when moving it.
There is no automatic runtime download or publication service.

## Ownership

| Component | Responsibility |
|---|---|
| OpenBFME fork, pinned submodule | Engine code, rendering and simulation |
| [engine_adapter.py](../../src/mapworkshop/native/engine_adapter.py) | Knowledge of that fork's source paths and resource dependencies; builds the runtime payload |
| [engine_bundle.py](../../src/mapworkshop/native/engine_bundle.py) | Bundle format, required capabilities and methods, integrity and compatibility checks |
| [openbfme.py](../../src/mapworkshop/native/openbfme.py) | Source build or bundle selection, game assets, map installation and process launch |
| [engine_runtime.gd](../../src/mapworkshop/viewer/godot/scripts/engine_runtime.gd) | Loaded-engine method checks and adaptation of internal rendering nodes/materials |
| Studio Python and viewer | Map authoring, analysis, marks, project management and editor controls |
| OpenBFME2 | Recovered behavior and source references; not a runtime dependency |

The resource list lives in the packaging adapter. The viewer consumes the bundle's
`viewer` projection and never assembles a shader dependency list itself. Game and
viewer projections share the same extension bytes and resources.

Map preview, embedded Test mode and the full game remain different sessions.
Preview loads user maps directly; simulation currently needs extra archives
mounted at process startup. Embedded Test mode uses the Uber profile and human
slots for controlling both armies. Bundling does not change these semantics or
claim to add native simulation reload support.

## Updating the pin

The gitlink is authoritative:

```powershell
git ls-files --stage src/mapworkshop/native/openbfme-godot
```

Update the adapter when the fork's resources or API change. Keep required
capabilities specific: user-map preview and user-map simulation are different.
The current adapter requires preview builders, archive-backed games, object-path
inspection, battle logging and optional grass rendering. It does not rely on an
upstream merge schedule.

After a dependency update, build a new bundle and run `mw engine check` and
`mw test`. With retail assets installed, also verify map rendering, live reload,
embedded Test mode and a short battle log. Some integration tests skip without
an engine or assets, so inspect the skipped tests before calling a pin verified.

Existing bundles retain their old revision and are rejected by a checkout whose
pin has changed. Update the configured bundle path explicitly. Keep fork changes
grouped by purpose and retire them only when the selected engine supplies the
needed capability.
