"""Test In-Game's choice of game (viewer.jobs.play), without starting one."""
import unittest
from types import SimpleNamespace
from unittest import mock

from mapworkshop.viewer import jobs


class Inline:
    """threading.Thread that runs its target at start()."""
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


class PlayTests(unittest.TestCase):
    def test_openbfme_is_started_with_the_project_and_reports_its_close(self):
        status = jobs.Status()
        owner = SimpleNamespace(title='Glacial Crossroads')
        process = mock.Mock()
        with mock.patch('mapworkshop.native.openbfme.play', return_value=process) as play, \
                mock.patch.object(jobs.threading, 'Thread', Inline), mock.patch('mapworkshop.native.play') as native:
            jobs.play(owner, status, 'openbfme')
        self.assertIs(play.call_args.args[0], owner)
        native.assert_not_called()
        process.wait.assert_called_once()
        self.assertEqual(status.current(), 'OpenBFME has closed')

    def test_an_openbfme_failure_shows_in_the_status(self):
        status = jobs.Status()
        with mock.patch('mapworkshop.native.openbfme.play', side_effect=RuntimeError('needs 3 game files')), \
                mock.patch.object(jobs.threading, 'Thread', Inline):
            jobs.play(None, status, 'openbfme')
        self.assertEqual(status.current(), 'OpenBFME: needs 3 game files')


if __name__ == '__main__':
    unittest.main()
