"""The map the viewer shows: which map, with which options, and loading it.

The scene is prepared on a worker (viewer.loading), uploaded to the GPU a
few milliseconds per frame and installed between frames, so the previous
scene stays usable meanwhile. The session watches the map file and its
map.ini and reloads when they stop changing; a load that fails keeps the
last good scene and the options it was loaded with.
"""

import time
from pathlib import Path

from mapworkshop import project
from mapworkshop.viewer.loading import LatestTask, Upload, map_title
from mapworkshop.viewer.marks import Marks

TOAST_DELAY = 0.25        # s a load runs before its toast shows, so quick ones do not flash
WATCH_INTERVAL = 0.25     # s between looks at the watched files
SETTLE = 0.5              # s the files must stay unchanged before a reload


class Session:
    def __init__(self, source, status, lod='medium', weather='map', sun='own'):
        self.status = status
        self.source = self.requested = source
        # What the next load uses; a failed load puts back the shown scene's.
        self.options = dict(lod=lod, weather=weather, sun=sun, limits=False, markers=False, units=True, normal_maps=None,
                            clouds=True)
        self.owners = {}
        self.refresh_owners()
        self.renderer = None
        self.marks = Marks(source)
        self.loader = LatestTask()
        self.base_assets = []     # owned by the single preparation worker
        self.cpu_shared, self.gpu_shared = {}, {}
        self.request = self.upload = None
        self.loading = False
        self.load_started = 0.0
        self.load_title = ''
        self.load_signature = None
        self.toast = None         # how the last load ended: dict(kind, title, detail, until)
        self.reload = False       # load again at the next frame
        self.watched = self._watch_list(source)
        self.signature = self._signature()
        self.changed_at = None
        self.watch_time = 0.0

    # The map --------------------------------------------------------------------
    def refresh_owners(self):
        """Re-read the map projects (a new one may have appeared)."""
        self.owners.clear()
        self.owners.update((p.map_file.resolve(), p) for p in project.projects())

    @property
    def owner(self):
        """The project the shown map is built from, or None for a game map."""
        return self.owners.get(self.source)

    def title(self, path=None):
        return map_title(path or self.source, self.owners)

    def open_map(self, path):
        self.requested = Path(path).resolve()
        self.watched = self._watch_list(self.requested)
        self.signature = self._signature()
        self.changed_at = None
        self.reload = True

    @staticmethod
    def _watch_list(path):
        return [path, path.parent/'map.ini']

    def _signature(self):
        result = []
        for path in self.watched:
            try:
                info = path.stat()
                result.append((info.st_mtime_ns, info.st_size))
            except OSError:
                result.append(None)
        return tuple(result)

    def poll(self, now):
        """Watch for map changes; reload once the files stop changing (a
        writer may still be busy)."""
        if now-self.watch_time <= WATCH_INTERVAL:
            return
        self.watch_time = now
        current = self._signature()
        if current != self.signature:
            self.signature = current
            self.changed_at = now
            self.status.set('map changed - reloading...', 2)
        elif self.changed_at is not None and now-self.changed_at > SETTLE:
            self.changed_at = None
            self.reload = True

    # Loading ----------------------------------------------------------------------
    def start_load(self):
        from mapworkshop.render.assets import GameAssets
        from mapworkshop.render.engine import MapRenderer
        self.reload = False
        if self.request:
            self.request.cancelled.set()
        if self.upload:
            self.upload.close()
            self.upload = None
        source = self.requested
        o = self.options
        options = dict(lod=o['lod'], weather=o['weather'], sun=o['sun'], vegetation_limits=o['limits'],
                       editor_markers=o['markers'], units=o['units'],
                       normal_maps=o['normal_maps'], clouds=o['clouds'])
        self.load_signature = self._signature()
        self.load_started = time.perf_counter()
        self.loading = True
        self.load_title = self._load_title(source)
        self.toast = None
        base_assets, cpu_shared = self.base_assets, self.cpu_shared

        def prepare(request):
            if not base_assets:
                request.report(0.0, 'Indexing game assets')
                base_assets.append(GameAssets())
            request.report(0.08, 'Reading map')
            return MapRenderer.prepare(source, assets=base_assets[0], shared=cpu_shared,
                                       progress=request.report, **options)
        self.request = self.loader.submit(prepare)

    def _load_title(self, source):
        """What the loading toast calls this load: the map, or the settings
        that changed on it."""
        r = self.renderer
        if r is None or source != self.source:
            return self.title(source)
        o = self.options
        changed = []
        if o['lod'] != r.options['lod']:
            changed.append(f'Detail {o["lod"].title()}')
        if o['weather'] != (r.weather_preset or 'map'):
            changed.append('Weather')
        if o['sun'] != (r.sun or 'own'):
            changed.append('Sun')
        if o['limits'] != r.options['vegetation_limits']:
            changed.append('Object limits')
        if o['markers'] != r.options['editor_markers']:
            changed.append('Editor markers')
        if o['units'] != r.options['units']:
            changed.append('Units')
        return 'Applying ' + ', '.join(changed) if changed else f'Reloading {self.title(source)}'

    def toast_shown(self, now=None):
        """Whether the loading toast is up: the load has run long enough not
        to flash."""
        return self.loading and (now or time.perf_counter())-self.load_started >= TOAST_DELAY

    def advance(self, ctx):
        """Move a finished preparation on: upload a slice of it to the GPU,
        and when that is done, install the new scene. Returns
        dict(changed_map, first) on the frame a scene is installed, else None."""
        request = self.request
        if request is None or not request.done.is_set():
            return None
        installed = None
        try:
            if request.error:
                raise request.error
            if request.cancelled.is_set():
                return None
            if self.upload is None:
                self.upload = Upload(request.take(), ctx, self.gpu_shared)
            if not self.upload.advance():
                return None
            new = self.upload.renderer
            self.upload = None
            # Do not install an obsolete snapshot if a writer changed files
            # while the worker or GPU upload was in progress.
            if self._signature() != self.load_signature:
                self.reload = True
                self.request = None
                return None
            installed = self._install(new)
        except Exception as error:
            self._failed(error)
        self.loading = False
        self.request = None
        return installed

    def _install(self, new):
        old = self.renderer
        shown = self.toast_shown()
        new.defer_walkability = True
        if old:
            new.visible.update(old.visible)
        if self.options['normal_maps'] is not None:
            new.set_option('normal_maps', self.options['normal_maps'])
        new.set_option('clouds', self.options['clouds'])
        changed_map = self.source != self.requested
        if changed_map:
            self.marks = Marks(self.requested)
        self.source = self.requested
        self.renderer = new
        for mark in self.marks.items:
            mark.pop('_world', None)
        owner = self.owner
        if owner:
            try:
                project.remember(owner)
            except OSError as error:
                print('Could not remember last map:', error)
        seconds = time.perf_counter()-self.load_started
        self.status.set(f'Loaded {self.title()} ({seconds:.1f} s)', 5)
        if shown:
            self.toast = dict(kind='done', title=self.load_title, detail=f'Done in {seconds:.1f} s',
                              until=time.perf_counter()+1.6)
        print(f'Loaded {self.source.name} in {seconds:.2f} s')
        return dict(changed_map=changed_map, first=old is None)

    def _failed(self, error):
        self.toast = dict(kind='failed', title=self.load_title, detail=str(error), until=time.perf_counter()+6.0)
        if self.upload:
            self.upload.close()
            self.upload = None
        self.requested = self.source
        self.watched = self._watch_list(self.source)
        self.signature = self._signature()
        active = self.renderer
        if active:
            self.options.update(lod=active.options['lod'], weather=active.weather_preset or 'map',
                                sun=active.sun or 'own', limits=active.options['vegetation_limits'],
                                markers=active.options['editor_markers'], units=active.options['units'],
                                normal_maps=active.options['normal_maps'], clouds=active.options['clouds'])
        self.status.set(f'Load failed: {str(error)[:120]}', 15)
        print('Load failed:', error)

    def close(self):
        self.loader.close()
        if self.upload:
            self.upload.close()
