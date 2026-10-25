"""Versioned OpenBFME runtime bundles, independent of a source checkout or compiler.

A bundle is a directory with runtime.json and explicitly inventoried files. Game,
viewer, tools and metadata are separate projections of the same immutable payload.
The source adapter owns engine-specific paths; consumers use these projections.
"""
import hashlib
import json
import platform
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

FORMAT = 1
API = 1                         # Studio adapter contract, not an upstream SDK promise
GODOT_VERSION = '4.7.2'
PLATFORM = 'windows-x86_64'
MANIFEST = 'runtime.json'
CAPABILITIES = ('map_preview', 'user_map_preview', 'archive_game', 'object_paths',
                'battle_log', 'ground_cover')
METHODS = {
    'RetailFileSystem': ['mount_retail', 'get_user_map_folder'],
    'MapTerrainBuilder': ['build_map', 'get_report'],
    'MapObjectBuilder': ['setup', 'build_objects', 'get_report', 'advance'],
    'PathfindView': [],
    'GameWorld': ['setup', 'set_simulation_profile', 'load_map', 'set_shroud_drawn', 'advance',
                  'get_object', 'get_object_ids', 'get_object_path', 'order_move', 'order_attack', 'order_stop'],
}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative(name):
    """A portable, contained payload path (including when consumed on Windows)."""
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise RuntimeError(f'Invalid runtime path: {name!r}')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise RuntimeError(f'Invalid runtime path: {name!r}')
    return name


def contained(root, name):
    path = root/relative(name)
    if not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError(f'Runtime file escapes its bundle: {name}')
    return path


class Bundle:
    """A validated manifest and its payload. Validation never executes bundle code."""
    def __init__(self, root, data):
        self.root, self.data = Path(root), data

    def files(self, group):
        return {name: contained(self.root, entry['path'])
                for name, entry in self.data['groups'][group].items()}

    def file(self, group, name):
        try:
            return self.files(group)[name]
        except KeyError as error:
            raise RuntimeError(f'Runtime lacks {group}/{name}') from error

    @property
    def revision(self):
        return self.data['engine']['revision']


def load(root, *, expected_revision=None, check_host=True):
    """Reject incompatible, incomplete or mixed bundles before launching Godot."""
    root = Path(root).expanduser().resolve()
    try:
        data = json.loads((root/MANIFEST).read_text(encoding='utf-8'))
        if data['format'] != FORMAT or data['adapter_api'] != API:
            raise RuntimeError('Unsupported OpenBFME runtime format or Studio adapter API; rebuild the bundle')
        if data['godot'] != GODOT_VERSION or data['platform'] != PLATFORM:
            raise RuntimeError(f'Runtime requires Godot {GODOT_VERSION} on {PLATFORM}')
        if check_host and (platform.system() != 'Windows' or platform.machine().lower() not in ('amd64', 'x86_64')):
            raise RuntimeError(f'This runtime supports {PLATFORM}')
        revision = data['engine']['revision']
        if not re.fullmatch('[0-9a-f]{40}', revision):
            raise RuntimeError('Runtime has no valid engine revision')
        if expected_revision and revision != expected_revision:
            raise RuntimeError(f'Runtime engine {revision[:8]} differs from Studio\'s pin {expected_revision[:8]}; '
                               'use a matching bundle or set openbfme_bundle to source')
        missing = set(CAPABILITIES) - set(data['capabilities'])
        if missing:
            raise RuntimeError('Runtime lacks capabilities: ' + ', '.join(sorted(missing)))
        for group in ('game', 'viewer', 'tools', 'metadata', 'licenses'):
            entries = data['groups'][group]
            if not isinstance(entries, dict) or not entries:
                raise RuntimeError(f'Runtime has no {group} payload')
            seen = set()
            for name, entry in entries.items():
                relative(name)
                if name.casefold() in seen:
                    raise RuntimeError(f'Case-colliding runtime path: {name}')
                seen.add(name.casefold())
                path = contained(root, entry['path'])
                if not path.is_file() or path.stat().st_size != entry['size'] or digest(path) != entry['sha256']:
                    raise RuntimeError(f'Runtime file missing or changed: {entry["path"]}; rebuild or replace the bundle')
        bundle = Bundle(root, data)
        for name in ('godot.exe', 'godot.console.exe', 'openbfme_peer.exe'):
            bundle.file('tools', name)
        for name in ('openbfme.gdextension', 'bin/openbfme.windows.template_debug.x86_64.dll'):
            for group in ('game', 'viewer'):
                bundle.file(group, name)
            if data['groups']['game'][name] != data['groups']['viewer'][name]:
                raise RuntimeError(f'Game and viewer use different runtime files: {name}')
        bundle.file('game', 'project.godot')
        for name in ('rotwk-201-english-archives.json', 'bfme2-106-english-archives.json', 'aio_pins.gd'):
            bundle.file('metadata', name)
        if not isinstance(data['methods'], dict) or not data['methods']:
            raise RuntimeError('Runtime lacks the Godot method contract')
        for cls, required in METHODS.items():
            if cls not in data['methods'] or not isinstance(data['methods'][cls], list) or set(required) - set(data['methods'][cls]):
                raise RuntimeError(f'Runtime lacks the {cls} method contract')
        return bundle
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError(f'Invalid OpenBFME runtime at {root}: {error}') from error


def create(cache, groups, *, revision, source_stamp, methods, destination=None):
    """Publish a complete bundle into a content-addressed cache or a new destination.

    Inputs are {group: {logical name: source Path}}. Viewer files alias the game
    payload, so the extension and resources are stored once. No game assets, user
    settings, import cache or source build directory are included.
    """
    payload, entries = {}, {}
    for group, files in groups.items():
        entries[group] = {}
        for name, path in sorted(files.items()):
            name, path = relative(name), Path(path)
            # Godot's Windows console launcher locates the GUI executable by
            # its original basename; logical tool names need not rename files.
            target = f'{"game" if group == "viewer" else group}/{path.name if group == "tools" else name}'
            if not path.is_file():
                raise RuntimeError(f'Cannot package missing runtime file: {path}')
            record = dict(path=target, size=path.stat().st_size, sha256=digest(path))
            if target in payload and digest(payload[target]) != record['sha256']:
                raise RuntimeError(f'Conflicting runtime payload: {target}')
            payload[target] = path
            entries[group][name] = record
    data = dict(format=FORMAT, adapter_api=API, godot=GODOT_VERSION, platform=PLATFORM,
                engine=dict(revision=revision, source_stamp=source_stamp),
                capabilities=list(CAPABILITIES), methods=methods, groups=entries)
    encoded = json.dumps(data, indent=2, sort_keys=True) + '\n'
    identifier = hashlib.sha256(encoded.encode()).hexdigest()
    target = Path(destination).resolve() if destination else Path(cache).resolve()/identifier
    if target.exists():
        if destination:
            raise RuntimeError(f'Runtime destination already exists: {target}; choose a new directory')
        if (target/MANIFEST).read_text(encoding='utf-8') != encoded:
            raise RuntimeError(f'Cached runtime manifest changed: {target}; remove that generated bundle and rebuild it')
        return load(target, check_host=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.runtime-', dir=target.parent) as temporary:
        staging = Path(temporary)/'bundle'
        staging.mkdir()
        for name, source in payload.items():
            output = contained(staging, name)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output)
        (staging/MANIFEST).write_text(encoded, encoding='utf-8')
        load(staging, check_host=False)  # also detects source files changed during the copy
        staging.rename(target)
    return Bundle(target, data)
