"""project._publish, swapping a new build into local/build/<id>/, and
project._prune, which old runs local/history/<id>/ keeps."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from mapworkshop import project


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__('shutil').rmtree, self.root, True)
        patcher = mock.patch.object(project, 'BUILD', self.root/'build')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = SimpleNamespace(id='lab', native_name='map mp lab', build_dir=self.root/'build'/'lab')

    def run_folder(self, text):
        work = self.root/'history'/text
        (work/'map').mkdir(parents=True)
        (work/'map'/'map mp lab.map').write_text(text)
        return work

    def test_a_new_build_replaces_the_previous_one(self):
        project._publish(self.project, self.run_folder('first'))
        project._publish(self.project, self.run_folder('second'))
        self.assertEqual((self.project.build_dir/'map mp lab.map').read_text(), 'second')
        self.assertEqual(sorted(p.name for p in (self.root/'build').iterdir()), ['lab'])

    def test_a_failed_swap_puts_the_previous_build_back(self):
        project._publish(self.project, self.run_folder('first'))
        real = Path.replace

        def replace(path, target):
            if path.name.endswith('.partial'):
                raise PermissionError('in use')
            return real(path, target)

        with mock.patch.object(Path, 'replace', replace), self.assertRaises(PermissionError):
            project._publish(self.project, self.run_folder('second'))
        self.assertEqual((self.project.build_dir/'map mp lab.map').read_text(), 'first')


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__('shutil').rmtree, self.root, True)
        patcher = mock.patch.object(project, 'HISTORY', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = SimpleNamespace(id='lab')

    def runs(self, statuses):
        for i, status in enumerate(statuses):
            folder = self.root/'lab'/f'2026-10-{i+1:02d}_120000'
            folder.mkdir(parents=True)
            (folder/'build.json').write_text(json.dumps(dict(status=status)))

    def kept(self):
        return [json.loads((f/'build.json').read_text())['status'] + f.name[8:10]
                for f in sorted((self.root/'lab').iterdir())]

    def test_the_newest_runs_stay(self):
        self.runs(['built']*8)
        project._prune(self.project)
        self.assertEqual(self.kept(), ['built04', 'built05', 'built06', 'built07', 'built08'])

    def test_the_previous_success_outlives_any_number_of_failures(self):
        self.runs(['built', 'built'] + ['failed']*7 + ['built'])
        project._prune(self.project)
        self.assertEqual(self.kept(), ['built02', 'failed06', 'failed07', 'failed08', 'failed09', 'built10'])


if __name__ == '__main__':
    unittest.main()
