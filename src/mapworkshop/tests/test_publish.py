"""project._publish: swapping a new build into local/build/<id>/."""
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


if __name__ == '__main__':
    unittest.main()
