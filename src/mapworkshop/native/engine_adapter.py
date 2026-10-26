"""Studio's adapter for the pinned OpenBFME fork (no upstream modifications).

Only this packaging adapter knows the fork's resource layout. Runtime consumers
read the resulting bundle manifest. Update this contract and its integration
tests together when advancing the engine pin.
"""
import re
from pathlib import Path

from mapworkshop.native import engine_bundle

DLL = 'bin/openbfme.windows.template_debug.x86_64.dll'
SHADERS = ('terrain', 'water_standing', 'road', 'river', 'ground_cover')
RESOURCES = ('scripts/ground_cover.gd', 'scripts/pro_lens.gd', 'scripts/pro_lens_effect.gd',
             'assets/ground_cover/profiles.json')


def viewer_resources(godot):
    """Resolve the pinned fork's runtime resources, failing on missing dependencies."""
    godot = Path(godot)
    pending = ['openbfme.gdextension', *RESOURCES, *(f'shaders/{s}.gdshader' for s in SHADERS)]
    # Older pinned runtimes have no object-shadow renderer. Carry its controller
    # whenever the selected engine supplies it, alongside its shader includes.
    if (godot/'scripts/object_shadows.gd').is_file():
        pending.append('scripts/object_shadows.gd')
    if (godot/'scripts/animation/w3d_unit_rig.gd').is_file():
        pending += ['scripts/animation/w3d_unit_rig.gd', 'scripts/animation/uruk_pike_stomp.gd']
    files = {}
    while pending:
        name = engine_bundle.relative(pending.pop())
        if name in files:
            continue
        path = engine_bundle.contained(godot, name)
        if not path.is_file():
            raise RuntimeError(f'Pinned engine lacks runtime resource {name}; update its Studio adapter')
        files[name] = path
        if path.suffix in ('.gdshader', '.gdshaderinc'):
            pending += re.findall(r'#include\s+"res://([^"]+)"', path.read_text(encoding='utf-8'))
    return files


def package(source, project, peer, executables, game_files, cache, *, revision, source_stamp, destination=None):
    """Create the runtime from one built source revision and its matching Godot."""
    source, project = Path(source), Path(project)
    game = {name.removeprefix('godot/'): source/name for name in game_files if name.startswith('godot/')}
    game[DLL] = project/DLL
    viewer = viewer_resources(source/'godot') | {DLL: project/DLL}
    metadata = {f'{policy}-english-archives.json': source/f'engine/data/retail-archives/{policy}-english-archives.json'
                for policy in ('rotwk-201', 'bfme2-106')}
    metadata['aio_pins.gd'] = source/'launcher/scripts/core/aio_pins.gd'
    groups = dict(game=game, viewer=viewer,
                  tools={'godot.exe': executables[0], 'godot.console.exe': executables[1], 'openbfme_peer.exe': peer},
                  metadata=metadata, licenses={'OpenBFME-LICENSE': source/'LICENSE'})
    return engine_bundle.create(cache, groups, revision=revision, source_stamp=source_stamp,
                                methods=engine_bundle.METHODS, destination=destination)
