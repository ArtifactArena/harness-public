"""Cheap fail-closed checks; no simulation or compiled dependencies required."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.run = root / 'run'
        self.release = root / 'release'
        name = 'mjarena/envs/sumo.py'
        self.target = self.run / 'harness' / name
        self.source = self.release / 'harness' / name
        for path, text in ((self.target, 'baseline'), (self.source, 'patched')):
            path.parent.mkdir(parents=True)
            path.write_text(text)
        sha = lambda text: hashlib.sha256(text.encode()).hexdigest()
        manifest = {'baseline': {name: sha('baseline')},
                    'files': {'harness/' + name: sha('patched')}}
        (self.release / 'manifest.json').write_text(json.dumps(manifest))

    def install(self):
        return subprocess.run([sys.executable,
            str(Path(__file__).with_name('install_release.py')),
            str(self.release), str(self.run)], capture_output=True)

    def test_valid_overlay_can_be_installed_twice(self):
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.target.read_text(), 'patched')

    def test_modified_baseline_rejected_before_mutation(self):
        self.target.write_text('different physics rules')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(self.target.read_text(), 'different physics rules')
        self.assertFalse((self.run / 'cpu-acceleration-manifest.json').exists())

    def test_corrupt_release_rejected_before_mutation(self):
        self.source.write_text('corrupt')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(self.target.read_text(), 'baseline')
        self.assertFalse((self.run / 'cpu-acceleration-manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
