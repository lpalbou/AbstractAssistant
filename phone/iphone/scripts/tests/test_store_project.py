import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('store_project', Path(__file__).resolve().parents[1] / 'store-project.py')
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


class StoreProjectTests(unittest.TestCase):
    def test_composition_preserves_developer_identity_and_routes_watch_to_existing_listing(self):
        phone = {'name': 'Phone', 'options': {}, 'settings': {'base': {
            'MARKETING_VERSION': '0.6.21', 'CURRENT_PROJECT_VERSION': '29'}},
            'packages': {'AssistantKit': {'path': 'Packages/AssistantKit'}}, 'targets': {
            'AbstractAssistantPhone': {'sources': ['Sources/App', 'Resources'],
                'info': {'path': 'Resources/Info.plist', 'properties': {}},
                'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': store.STORE_ID + '.iphone'}}}}}
        watch = {'options': {}, 'settings': {'base': {'MARKETING_VERSION': '0.3.0'}}, 'targets': {
            'AbstractAssistantWatch': {'sources': ['Sources/App', 'Resources'],
                'dependencies': [{'package': 'AbstractGatewayClient'}],
                'info': {'path': 'Resources/Info.plist', 'properties': {'WKWatchOnly': True}},
                'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': store.WATCH_ID}}}}}
        originals = copy.deepcopy((phone, watch))
        p, w = store.compose(phone, watch, Path('/repo'), Path('/generated'))
        self.assertEqual((phone, watch), originals)
        self.assertEqual(p['targets']['AbstractAssistantPhone']['settings']['base']['PRODUCT_BUNDLE_IDENTIFIER'], store.STORE_ID)
        props = w['targets']['AbstractAssistantWatch']['info']['properties']
        self.assertNotIn('WKWatchOnly', props)
        self.assertEqual(props['WKCompanionAppBundleIdentifier'], store.STORE_ID)
        self.assertTrue(props['WKRunsIndependentlyOfCompanionApp'])
        self.assertEqual(w['settings']['base']['MARKETING_VERSION'], '0.6.21')
        self.assertEqual(p['targets']['AbstractAssistantPhone']['sources'][1]['excludes'], ['Info.plist'])
        self.assertEqual(w['targets']['AbstractAssistantWatch']['info']['path'], '/generated/Watch.info.plist')
        self.assertNotIn('AbstractAssistant', w['targets'])

    def test_watch_package_cannot_silently_lose_swiftpm_build_behavior(self):
        package = {'targets': [{'name': 'AbstractGatewayClient', 'type': 'regular'}]}
        store.validate_watch_package(package)
        for field in ('resources', 'settings', 'dependencies', 'exclude', 'pluginUsages', 'path', 'sources'):
            changed = copy.deepcopy(package)
            changed['targets'][0][field] = ['custom']
            with self.assertRaisesRegex(ValueError, 'custom build behavior'):
                store.validate_watch_package(changed)


if __name__ == '__main__': unittest.main()
