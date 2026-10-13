"""Latest-request-only CPU work. GPU resources never enter this worker."""
from threading import Condition, Event, Thread


class Cancelled(Exception):
    pass


class Request:
    def __init__(self):
        self.cancelled = Event()
        self.done = Event()
        self.progress = (0.0, 'Starting')
        self.result = None
        self.error = None

    def report(self, fraction=0.0, step='Working'):
        if self.cancelled.is_set():
            raise Cancelled()
        self.progress = (fraction, step)

    def take(self):
        """Transfer ownership to the UI, including any later GPU resources."""
        result, self.result = self.result, None
        return result


class LatestTask:
    """One running task and at most one pending replacement, never a backlog."""
    def __init__(self):
        self._condition = Condition()
        self._pending = self._running = None
        self._closed = False
        self._thread = Thread(target=self._run, name='viewer-prepare', daemon=True)
        self._thread.start()

    def submit(self, work):
        request = Request()
        with self._condition:
            if self._closed:
                raise RuntimeError('Loader is closed')
            if self._running:
                self._running.cancelled.set()
            if self._pending:
                self._pending[0].cancelled.set()
                self._pending[0].done.set()
            self._pending = request, work
            self._condition.notify()
        return request

    def close(self):
        with self._condition:
            self._closed = True
            if self._running:
                self._running.cancelled.set()
            if self._pending:
                self._pending[0].cancelled.set()
                self._pending[0].done.set()
            self._pending = None
            self._condition.notify()

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._pending is not None)
                if self._closed:
                    return
                request, work = self._pending
                self._pending = None
                self._running = request
            try:
                request.report()
                request.result = work(request)
                request.report(1.0, 'Ready')
            except Cancelled:
                request.result = None
            except Exception as error:
                # Do not retain the preparation stack (potentially large arrays).
                request.error = error.with_traceback(None)
            finally:
                request.done.set()
                with self._condition:
                    self._running = None
                request = work = None


class Upload:
    """Advance GPU stages on the UI thread, yielding to the next frame."""
    def __init__(self, renderer, ctx, shared):
        self.renderer = renderer
        self.steps = renderer.upload(ctx, shared)

    def advance(self, budget=0.006):
        from time import perf_counter
        deadline = perf_counter() + budget
        while True:
            try:
                next(self.steps)
            except StopIteration:
                return True
            if perf_counter() >= deadline:
                return False

    def close(self):
        self.steps.close()


def map_title(path, owners):
    """No filesystem work in the frame loop or for each stock-map title."""
    from pathlib import Path
    path = Path(path)
    owner = owners.get(path)
    if owner:
        return owner.title
    words = path.stem.split()
    for prefix in (['map', 'mp'], ['bfmexbar']):
        if [w.lower() for w in words[:len(prefix)]] == prefix and len(words) > len(prefix):
            words = words[len(prefix):]
    return ' '.join(w[:1].upper()+w[1:] for w in words)
