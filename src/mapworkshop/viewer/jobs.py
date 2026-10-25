"""The viewer's background work, run by its companion (viewer.godot_link):
building the project, Test In-Game and the marks panel's summary. Each runs
on its own thread and reports to the status line (Status).
"""

import json
import threading
import time


class Status:
    """The status line's text: the latest message, shown for its time. Jobs
    set it from their threads."""

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
        self.outcome = None       # the last build: (succeeded, seconds, time.time() it ended)

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
            seconds = time.perf_counter()-self.started
            self.outcome = (not code, seconds, time.time())
            self.running = False
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


TEST_GAMES = ('original', 'openbfme')     # the toolbar's choice for Test In-Game (setting test_game)


def play(owner, status, test_game='original', events=lambda event: None, settings=None):
    """Test In-Game: BFME2 straight in a skirmish on the project (native.play),
    or, when that cannot run (no BFME2 1.06) or for a game map (owner None),
    the normal game at its menu. With test_game 'openbfme', OpenBFME starts
    a skirmish on the project's map (native.openbfme).
    `events` hears 'started' once the game is up and 'closed' when a game it
    can watch has ended, from a worker thread."""
    from mapworkshop import game
    from mapworkshop.config import GAME_LABEL, PROFILE
    if test_game == 'openbfme':
        return play_openbfme(owner, status, events, settings)

    def normal_game(note=''):
        if owner:
            game.install(owner.build_dir, owner.native_name)
        game.launch()
        status.set(note + (f'{owner.title} installed in the game\'s maps; ' if owner else '') + f'starting {GAME_LABEL}...', 10)
        events('started')

    def work():
        try:
            from mapworkshop import native
            try:
                native.ready(progress=lambda line: status.set(line[:140], 600))
            except RuntimeError as error:
                if PROFILE == 'rotwk':
                    raise
                normal_game(f'{error}: ')
                return
            # Each step holds the status until the next: the game says
            # when the skirmish is playable and when it has closed.
            process, seconds = native.play(owner, progress=lambda line: status.set(line[:140], 600))
            status.set(f'{owner.title} is playable in {GAME_LABEL} ({seconds:.0f} s to start)', 600)
            events('started')
            native.watch(process)
            status.set(f'the test game on {owner.title} has closed', 8)
            events('closed')
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


def play_openbfme(owner, status, events=lambda event: None, settings=None):
    """OpenBFME in a skirmish (mw play --godot); the first time also builds it,
    which the status follows. With no project (owner None), open its main menu instead.
    `events` as for play()."""
    def work():
        try:
            from mapworkshop.native import openbfme
            process = openbfme.play(owner, progress=lambda line: status.set(line.strip()[:140], 600), settings=settings)
            status.set(f'OpenBFME test round on {owner.title} is starting' if owner else 'OpenBFME is open', 600)
            events('started')
            process.wait()
            status.set('OpenBFME has closed', 8)
            events('closed')
        except Exception as error:
            status.set(f'OpenBFME: {str(error)[:130]}', 20)

    status.set('preparing OpenBFME' + (f' with {owner.title}...' if owner else '...'), 600)
    threading.Thread(target=work, daemon=True).start()


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
