import unittest
from threading import Event, get_ident
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from mapworkshop.viewer.loading import LatestTask, Upload, map_title


class LoadingTests(unittest.TestCase):
    def test_newest_request_replaces_pending_and_cancels_running(self):
        worker = LatestTask()
        entered, release = Event(), Event()
        calls = []

        def slow(request):
            entered.set()
            self.assertTrue(release.wait(2))
            request.report(.5, 'Still working')
            return 'obsolete'

        try:
            first = worker.submit(slow)
            self.assertTrue(entered.wait(2))
            second = worker.submit(lambda request: calls.append('obsolete pending'))
            last = worker.submit(lambda request: ('latest', get_ident()))
            release.set()
            self.assertTrue(last.done.wait(2))
            self.assertTrue(first.cancelled.is_set())
            self.assertTrue(second.cancelled.is_set())
            self.assertTrue(second.done.is_set())
            self.assertIsNone(first.result)
            self.assertEqual(calls, [])
            value, thread = last.take()
            self.assertEqual(value, 'latest')
            self.assertNotEqual(thread, get_ident())
            self.assertIsNone(last.result)
        finally:
            release.set()
            worker.close()

    def test_failure_does_not_poison_the_next_load(self):
        worker = LatestTask()
        try:
            def fail(request):
                raise ValueError('bad map')
            failed = worker.submit(fail)
            self.assertTrue(failed.done.wait(2))
            self.assertIsInstance(failed.error, ValueError)
            good = worker.submit(lambda request: 'scene')
            self.assertTrue(good.done.wait(2))
            self.assertEqual(good.take(), 'scene')
        finally:
            worker.close()

    def test_close_returns_without_waiting_for_cpu_work(self):
        worker = LatestTask()
        entered, release = Event(), Event()
        def slow(request):
            entered.set()
            release.wait(2)
            request.report()
        request = worker.submit(slow)
        self.assertTrue(entered.wait(2))
        worker.close()
        self.assertTrue(request.cancelled.is_set())
        with self.assertRaises(RuntimeError):
            worker.submit(slow)
        release.set()
        self.assertTrue(request.done.wait(2))

    def test_upload_yields_and_runs_only_on_caller_thread(self):
        calls = []
        def steps(ctx, shared):
            for i in range(3):
                calls.append((i, get_ident()))
                yield
        upload = Upload(SimpleNamespace(upload=steps), None, {})
        for i in range(3):
            self.assertFalse(upload.advance(budget=0))
            self.assertEqual(len(calls), i+1)
        self.assertTrue(upload.advance(budget=0))
        self.assertTrue(all(thread == get_ident() for _, thread in calls))

    def test_titles_do_not_touch_filesystem(self):
        path = Path('map mp my valley.map')
        with patch.object(Path, 'resolve', side_effect=AssertionError('disk lookup')):
            self.assertEqual(map_title(path, {}), 'My Valley')
            self.assertEqual(map_title(path, {path: SimpleNamespace(title='Custom')}), 'Custom')


if __name__ == '__main__':
    unittest.main()
