import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'select-xcode.sh'


def run(apps: Path, major: str = '27') -> subprocess.CompletedProcess:
    env = {**os.environ, 'XCODE_APPS_DIR': str(apps), 'XCODE_MAJOR': major, 'XCODE_SELECT_DRY_RUN': '1'}
    return subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True)


class SelectXcodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.apps = Path(self.temp.name)

    def install(self, name: str) -> Path:
        app = self.apps / name
        app.mkdir()
        return app

    def test_a_release_candidate_behind_a_plain_symlink_is_refused(self):
        # The hosted image on 2026-10-26: 27.2 RC linked as Xcode_27.2.app; 27.1 released.
        rc = self.install('Xcode_27.2_Release_Candidate.app')
        (self.apps / 'Xcode_27.2.app').symlink_to(rc)
        (self.apps / 'Xcode_27.2.0.app').symlink_to(rc)
        released = self.install('Xcode_27.1.app')
        (self.apps / 'Xcode_27.1.0.app').symlink_to(released)
        self.install('Xcode_27.app')
        result = run(self.apps)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f'selected={released.resolve()}')

    def test_the_newest_released_version_wins(self):
        self.install('Xcode_27.app')
        self.install('Xcode_27.0.1.app')
        newest = self.install('Xcode_27.1.app')
        self.install('Xcode_27.1_beta.app')
        self.assertEqual(run(self.apps).stdout.strip(), f'selected={newest.resolve()}')

    def test_only_betas_or_candidates_fails_loud(self):
        rc = self.install('Xcode_27.2_Release_Candidate.app')
        (self.apps / 'Xcode_27.2.app').symlink_to(rc)
        self.install('Xcode_27.3_beta.app')
        result = run(self.apps)
        self.assertEqual(result.returncode, 1)
        self.assertIn('No released Xcode 27.x', result.stdout + result.stderr)

    def test_another_major_is_ignored(self):
        self.install('Xcode_26.4.app')
        self.assertEqual(run(self.apps).returncode, 1)


if __name__ == '__main__':
    unittest.main()
