import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tarfile
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('iphone_release', SCRIPTS / 'release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
SHA = 'a' * 40


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / release.ARCHIVE_NAME
        self.app = self.archive / 'Products/Applications/AbstractAssistantPhone.app'
        self.app.mkdir(parents=True)
        self.info = {'CFBundleIdentifier': release.BUNDLE_ID, 'CFBundleShortVersionString': '0.6.21',
                     'CFBundleVersion': '101.1', 'DTPlatformName': 'iphoneos',
                     'CFBundleSupportedPlatforms': ['iPhoneOS'], 'CFBundleExecutable': 'Assistant'}
        self.write_info()
        (self.app / 'Assistant').write_bytes(b'fixture executable')
        self.watch = self.app / 'Watch/AbstractAssistantWatch.app'
        self.watch.mkdir(parents=True)
        self.watch_info = {**self.info, 'CFBundleIdentifier': release.WATCH_BUNDLE_ID,
            'DTPlatformName': 'watchos', 'CFBundleSupportedPlatforms': ['WatchOS'],
            'WKApplication': True, 'WKCompanionAppBundleIdentifier': release.BUNDLE_ID,
            'WKRunsIndependentlyOfCompanionApp': True}
        self.write_watch_info()
        (self.watch / 'Assistant').write_bytes(b'watch executable')
        self.output = self.root / 'candidate'

    def write_info(self):
        (self.app / 'Info.plist').write_bytes(plistlib.dumps(self.info))

    def write_watch_info(self):
        (self.watch / 'Info.plist').write_bytes(plistlib.dumps(self.watch_info))

    def test_watch_only_missing_wrong_companion_or_version_is_refused(self):
        valid = dict(self.watch_info)
        for key, value in [('WKWatchOnly', True), ('WKCompanionAppBundleIdentifier', 'wrong.id'),
                           ('WKRunsIndependentlyOfCompanionApp', False), ('CFBundleVersion', '100'),
                           ('CFBundleIdentifier', 'another.watch'), ('DTPlatformName', 'watchsimulator')]:
            self.watch_info = {**valid, key: value}; self.write_watch_info()
            with self.assertRaises(ValueError, msg=key): self.candidate()
        (self.watch / 'Info.plist').unlink()
        with self.assertRaisesRegex(ValueError, 'include the iPhone and Watch'): self.candidate()

    def test_two_top_level_applications_are_refused(self):
        (self.archive / 'Products/Applications/OldCarrier.app').mkdir()
        with self.assertRaisesRegex(ValueError, 'one top-level'): self.candidate()

    def candidate(self, suite='full'):
        return release.candidate(self.archive, self.output, SHA, '0.6.21', '101.1', suite)

    def test_build_numbers_are_valid_unique_on_retry_and_bounded(self):
        project = self.root / 'project.yml'; project.write_text('MARKETING_VERSION: "0.6.21"\n')
        self.assertEqual(release.metadata(project, 1, 1), {'version': '0.6.21', 'build': '101.1'})
        self.assertNotEqual(release.metadata(project, 1, 1), release.metadata(project, 1, 2))
        for number, attempt in [(0, 1), (10000, 1), (1, 100), (1, 0)]:
            with self.assertRaises(ValueError): release.metadata(project, number, attempt)

    def test_verified_archive_matches_commit_identity_version_and_bytes(self):
        manifest = self.candidate()
        self.assertEqual(release.verify(self.output, self.root / 'unpack', SHA), manifest)
        self.assertEqual((self.root / 'unpack' / release.ARCHIVE_NAME /
                          'Products/Applications/AbstractAssistantPhone.app/Assistant').read_bytes(), b'fixture executable')

    def test_other_commit_or_bundle_cannot_be_uploaded(self):
        self.candidate()
        with self.assertRaisesRegex(ValueError, 'identity/source'):
            release.verify(self.output, self.root / 'wrong-commit', 'b' * 40)
        manifest = json.loads((self.output / 'candidate.json').read_text())
        manifest['bundle_id'] = 'another.app'
        (self.output / 'candidate.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'identity/source'):
            release.verify(self.output, self.root / 'wrong-app', SHA)

    def test_modified_archive_is_refused(self):
        self.candidate()
        with (self.output / 'candidate.tar.gz').open('ab') as stream: stream.write(b'tampering')
        with self.assertRaisesRegex(ValueError, 'digest'):
            release.verify(self.output, self.root / 'modified', SHA)

    def test_critical_suite_candidate_cannot_be_uploaded(self):
        self.candidate('critical')
        with self.assertRaisesRegex(ValueError, 'full native suite'):
            release.verify(self.output, self.root / 'partial', SHA)

    def test_test_host_or_mismatched_binary_metadata_is_refused(self):
        self.info['CFBundleVersion'] = '29'; self.write_info()
        with self.assertRaisesRegex(ValueError, 'CFBundleVersion'):
            self.candidate()
        self.info['CFBundleVersion'] = '101.1'; self.write_info()
        (self.app / 'PlugIns/Tests.xctest').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'Test plugins'):
            self.candidate()

    def test_archive_path_traversal_is_refused_even_with_matching_digest(self):
        manifest = self.candidate()
        path = self.output / 'candidate.tar.gz'
        with tarfile.open(path, 'w:gz') as target:
            item = tarfile.TarInfo(release.ARCHIVE_NAME + '/../../escape'); item.size = 1
            target.addfile(item, io.BytesIO(b'x'))
        manifest['archive_sha256'] = release.digest(path)
        (self.output / 'candidate.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'archive root'):
            release.verify(self.output, self.root / 'extract', SHA)
        self.assertFalse((self.root / 'escape').exists())

    def test_explicit_entitlements_require_signed_archive(self):
        settings = self.root / 'settings.json'
        settings.write_text('[{"buildSettings":{}}]'); release.validate_settings(settings)
        settings.write_text('[{"buildSettings":{"CODE_SIGN_ENTITLEMENTS":"app.entitlements"}}]')
        with self.assertRaisesRegex(ValueError, 'entitlements'):
            release.validate_settings(settings)

    def test_export_keeps_testflight_candidate_eligible_for_store_promotion(self):
        path = self.root / 'ExportOptions.plist'; release.export_options(path, 'K3R4D6HP2A')
        options = plistlib.loads(path.read_bytes())
        self.assertEqual(options['method'], 'app-store-connect')
        self.assertEqual(options['destination'], 'upload')
        self.assertFalse(options['testFlightInternalTestingOnly'])
        self.assertFalse(options['manageAppVersionAndBuildNumber'])

    def test_signed_candidate_exports_an_app_store_ipa_without_uploading(self):
        path = self.root / 'ExportOptions.plist'
        release.export_options(path, 'K3R4D6HP2A', destination='export')
        options = plistlib.loads(path.read_bytes())
        self.assertEqual((options['method'], options['destination'], options['signingStyle'], options['teamID']),
                         ('app-store-connect', 'export', 'automatic', 'K3R4D6HP2A'))
        with self.assertRaises(ValueError):
            release.export_options(path, 'K3R4D6HP2A', destination='ad-hoc')

    def test_private_key_is_removed_on_success_or_export_failure(self):
        self.candidate()
        tools = self.root / 'bin'; tools.mkdir()
        for name, text in {'openssl': '#!/bin/bash\nexit 0\n', 'xcodebuild': '''#!/bin/bash
set -eu
printf called > "$UPLOAD_MARKER"
exit "$FAKE_UPLOAD_STATUS"
'''}.items():
            path = tools / name; path.write_text(text); path.chmod(0o755)
        temp = self.root / 'runner'; temp.mkdir()
        env = {**os.environ, 'PATH': str(tools) + os.pathsep + os.environ['PATH'],
               'RUNNER_TEMP': str(temp), 'GITHUB_SHA': SHA, 'TEAM_ID': 'K3R4D6HP2A',
               'ASC_KEY_ID': 'FAKEKEY123', 'ASC_ISSUER_ID': '00000000-0000-0000-0000-000000000000',
               'ASC_KEY_P8': 'FAKE PRIVATE KEY FIXTURE', 'UPLOAD_MARKER': str(self.root / 'called')}
        for status in ['0', '1']:
            result = subprocess.run(['bash', str(SCRIPTS / 'upload-candidate.sh'), str(self.output)],
                                    env={**env, 'FAKE_UPLOAD_STATUS': status}, capture_output=True, text=True)
            self.assertEqual(result.returncode, int(status), result.stderr)
            self.assertTrue((self.root / 'called').exists())
            self.assertEqual(list(temp.iterdir()), [])
            self.assertNotIn(env['ASC_KEY_P8'], result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
