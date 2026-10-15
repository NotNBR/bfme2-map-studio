"""The viewer's background work: building the project, Test In-Game, the
walkability estimate and the marks panel's summary. Each runs on its own
thread and reports to the toolbar's status text (Status); none touches the
GL context, so the 3D view keeps drawing while they run.
"""

import json
import threading
import time

from mapworkshop.viewer.loading import LatestTask


class Status:
    """The toolbar's status text: the latest message, shown for its time.
    Jobs set it from their threads."""

    def __init__(self):
        self.text, self.until = '', 0.0

    def set(self, text, seconds):
        self.text = text
        self.until = time.perf_counter()+seconds

    def current(self, now=None):
        """The message while it lasts, else None."""
        return self.text if (now or time.perf_counter()) < self.until else None


class Build:
    """Rebuild a project in the background (project.run). The viewer
    reloads the result through its file watch; a failed build leaves the
    previous one in place. `show_toast(toast)` puts up how a build ended:
    dict(kind 'done' or 'failed', title, detail, until)."""

    def __init__(self, status, show_toast):
        self.status, self.show_toast = status, show_toast
        self.running = False
        self.line = ''            # the build's latest output line, for the status text and the toast
        self.started = 0.0
        self.title = ''           # the toast's title while it runs

    def start(self, owner):
        from mapworkshop import project
        if owner is None:
            self.status.set("a game map: nothing to build (start your own with `mw new`)", 5)
            return
        if self.running:
            # The build toast is up; say why nothing new starts.
            self.status.set('already building - the build will reload the map', 4)
            return
        self.running, self.line = True, 'Starting'
        self.started, self.title = time.perf_counter(), f'Building {owner.title}'
        lines = []

        def on_line(line):
            lines.append(line)
            if line.strip():
                self.line = line.strip()[:100]

        def work():
            code = project.run(owner, on_line=on_line)
            self.running = False
            seconds = time.perf_counter()-self.started
            if code:
                print('\n'.join(lines[-40:]))
                error = next((l.strip() for l in reversed(lines) if l.strip()), 'see the terminal')
                self.status.set(f'build failed: {error[:120]}', 15)
                self.show_toast(dict(kind='failed', title=f'{owner.title}: build failed', detail=error,
                                     until=time.perf_counter()+15.0))
            else:
                # The reload that follows replaces this with its own toast.
                self.show_toast(dict(kind='done', title=f'Built {owner.title}', detail=f'Done in {seconds:.0f} s',
                                     until=time.perf_counter()+3.0))
                # The build ends with what it changed since the previous build (mapkit.mapdiff).
                start = next((i for i, l in enumerate(lines) if l.startswith('Changes since')), len(lines))
                changes = [l.strip() for l in lines[start + 1:] if l.strip()]
                if changes:
                    print('\n'.join(lines[start:]))
                self.status.set('built - reloading' + (f': {changes[0][:110]}' if changes else '...'),
                                6 if changes else 3)
        threading.Thread(target=work, daemon=True).start()


def play(owner, status):
    """Test In-Game: BFME2 straight in a skirmish on the project (native.play),
    or, when that cannot run (no BFME2 1.06) or for a game map (owner None),
    the normal game at its menu."""
    from mapworkshop import game

    def normal_game(note=''):
        if owner:
            game.install(owner.build_dir, owner.native_name)
        game.launch()
        status.set(note + (f'{owner.title} installed in the game\'s maps; ' if owner else '') + 'starting BFME2...', 10)

    def work():
        try:
            from mapworkshop import native
            try:
                native.ready(progress=lambda line: status.set(line[:140], 600))
            except RuntimeError as error:
                normal_game(f'{error}: ')
                return
            # Each step holds the status until the next: the game says
            # when the skirmish is playable and when it has closed.
            process, seconds = native.play(owner, progress=lambda line: status.set(line[:140], 600))
            status.set(f'{owner.title} is playable in BFME2 ({seconds:.0f} s to start)', 600)
            native.watch(process)
            status.set(f'the test game on {owner.title} has closed', 8)
        except Exception as error:
            status.set(str(error)[:140], 15)

    try:
        if owner is None:
            normal_game()
        else:
            status.set(f'installing {owner.title} for a test game...', 10)
            threading.Thread(target=work, daemon=True).start()
    except Exception as error:
        status.set(str(error)[:140], 10)


class Walkability:
    """The walkability estimate of the scene shown, computed in the
    background when View > Walkable is on and installed between frames."""

    def __init__(self, status):
        self.status = status
        self.loader = LatestTask()
        self.pending = None       # (renderer, request)

    def request(self, renderer):
        """Compute it for `renderer` if its layer is on and it has none yet;
        a request for an earlier scene is cancelled."""
        if self.pending:
            self.pending[1].cancelled.set()
            self.pending = None
        if renderer is None or not renderer.visible['walkable'] or hasattr(renderer, '_walk'):
            return
        calculate = renderer.walkability_task()
        self.pending = renderer, self.loader.submit(lambda request: calculate())
        self.status.set('Computing walkability...', 60)

    def advance(self, current):
        """Install a finished result, if it is still for the scene shown."""
        if not self.pending or not self.pending[1].done.is_set():
            return
        renderer, request = self.pending
        self.pending = None
        if request.cancelled.is_set() or renderer is not current or not renderer.visible['walkable']:
            return
        if request.error:
            renderer.visible['walkable'] = False
            self.status.set(f'Walkability failed: {request.error}', 10)
            return
        renderer.install_walkability(request.take())
        self.status.set(f'Walkability ready: {len(renderer.walkable["cut_off"])} cut-off areas', 5)

    def close(self):
        self.loader.close()


class MarksSummary:
    """What each mark covers (marks.describe), for the marks panel: worked
    out in the background whenever the marks or the scene change."""

    def __init__(self):
        self.result = None        # (key, describe() result)
        self.key = None           # the key last worked out
        self.busy = False

    @staticmethod
    def key_for(renderer, marks):
        return (id(renderer), str(marks.path), json.dumps(marks.plain()))

    def invalidate(self):
        self.key = None

    def update(self, renderer, marks, map_path):
        from mapworkshop.viewer import marks as marklib
        key = self.key_for(renderer, marks)
        if key == self.key or self.busy or not marks.items:
            return
        self.busy = True
        data = json.loads(json.dumps(dict(map_path=str(map_path), map=map_path.stem, marks=marks.plain())))
        assets, m, terrain = renderer.assets, renderer.map, renderer.terrain

        def work():
            try:
                self.result = (key, marklib.describe(data, assets=assets, m=m, terrain=terrain))
            except Exception as error:
                print('Marks summary failed:', error)
            finally:
                self.key, self.busy = key, False
        threading.Thread(target=work, daemon=True).start()

    def get(self, renderer, marks):
        """The summary of the marks as they are now, or None while it is worked out."""
        if self.result and self.result[0] == self.key_for(renderer, marks):
            return self.result[1]
        return None
