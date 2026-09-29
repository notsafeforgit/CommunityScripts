"""Exercise title selection through the plugin and its real mutation builders."""
import copy
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import test_plugin
from test_mappings import SETTINGS, evaluate
import catalogMappings
from catalogMappings import IMPORT_MARKER
import catalogMetadata
import config
from scrape_catalog.edits import edit
from stashInterface import StashInterface


@unittest.skipUnless(os.environ.get('STASH_JQ_EVALUATOR') or shutil.which('jq'), 'A jq evaluator is required')
class TitleFallbackTests(unittest.TestCase):
    setUp = test_plugin.CatalogPluginTests.setUp
    capture = test_plugin.CatalogPluginTests.capture

    def make_plugin(self, kind='scene', path=None, title=None, organized=False, mode='normal', **settings):
        for key in SETTINGS:
            if hasattr(config, key):
                self.addCleanup(setattr, config, key, getattr(config, key))
        path = path or self.path
        self.item = {'id': '42', 'title': title, 'details': 'Existing details', 'organized': organized,
                     'files': [{'path': str(path)}], 'visual_files': [{'path': str(path)}],
                     'tags': [], 'performers': [], 'movies': [], 'urls': []}
        self.updates = []
        interface = StashInterface({'server_connection': {'PluginDir': str(Path(__file__).resolve().parents[1])},
                                    'args': {'mode': mode, 'hookContext': {'type': kind.capitalize() + '.Create.Post', 'id': '42'}}})

        def request(query, variables=None):
            if 'pluginSettingsV3' in query:
                return {'pluginSettingsV3': {'values': {**SETTINGS, 'reload_tag': '', **settings}}}
            if 'pluginEvaluateMappings' in query:
                return {'pluginEvaluateMappings': evaluate(variables['mappings'], variables['input'])}
            if 'findScene(' in query or 'findImage(' in query:
                return {'find' + kind.capitalize(): copy.deepcopy(self.item)}
            mutation = kind + 'Update'
            if mutation + '(' in query:
                payload = copy.deepcopy(variables['input'])
                self.updates.append(payload)
                self.item.update({key: value for key, value in payload.items() if key != 'clientMutationId'})
                return {mutation: {'id': '42'}}
            self.fail(f'Unexpected GraphQL request: {query}')

        p = patch.object(interface, '_StashInterface__gql_call', side_effect=request)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(catalogMappings, 'get_reader', return_value=self.reader)
        p.start()
        self.addCleanup(p.stop)
        plugin = catalogMetadata.CatalogMetadataPlugin(interface)
        self.relation_lookups = []
        for field, result in (('performers', []), ('studio', None), ('movie', None), ('tags', [])):
            p = patch.object(plugin, '_CatalogMetadataPlugin__find_create_' + field, return_value=result)
            self.relation_lookups.append(p.start())
            self.addCleanup(p.stop)
        return plugin

    def test_unmatched_media_gets_only_a_title_inside_and_outside_catalog(self):
        for kind in ('scene', 'image'):
            for parent in (self.media, self.root / 'outside'):
                with self.subTest(kind=kind, parent=parent):
                    plugin = self.make_plugin(kind, parent / 'A name.字幕.2026.mp4', title=' \t')
                    plugin.process()
                    self.assertEqual(self.updates, [{'id': '42', 'title': 'A name.字幕.2026', 'clientMutationId': IMPORT_MARKER}])
                    for lookup in self.relation_lookups:
                        lookup.assert_not_called()

    def test_existing_title_is_preserved_without_metadata(self):
        for kind in ('scene', 'image'):
            plugin = self.make_plugin(kind, title='Handwritten title')
            plugin.process()
            self.assertEqual(self.updates, [])

    def test_native_metadata_without_title_preserves_existing_then_uses_filename(self):
        self.capture()
        self.assertNotIn('title', self.reader.metadata(self.path))
        for kind in ('scene', 'image'):
            for existing, expected in (('Handwritten title', 'Handwritten title'), (None, 'example'), (' \t', 'example')):
                with self.subTest(kind=kind, existing=existing):
                    plugin = self.make_plugin(kind, title=existing)
                    plugin.process()
                    self.assertEqual(self.updates[0]['title'], expected)
                    self.assertEqual(self.updates[0]['details'], 'Hola')

    def test_catalog_title_and_explicit_mapping_take_precedence(self):
        self.capture()
        edit(self.store, self.path, {'title': 'Catalog title'})
        for kind in ('scene', 'image'):
            for mappings, expected in (({}, 'Catalog title'), ({'title': '"Mapped title"'}, 'Mapped title')):
                plugin = self.make_plugin(kind, title='Previous title', **{kind + '_import_mappings': mappings})
                plugin.process()
                self.assertEqual(self.updates[0]['title'], expected)

    def test_preserved_xml_without_title_does_not_displace_existing_title(self):
        nfo = self.path.with_suffix('.nfo')
        nfo.write_text('<movie><plot>Preserved details</plot></movie>')
        self.store.import_nfo('Manual/example.nfo', ['Manual/example.mp4'])
        nfo.unlink()
        plugin = self.make_plugin(title='Existing title')
        plugin.process()
        self.assertEqual(self.updates[0]['title'], 'Existing title')
        self.assertEqual(self.updates[0]['details'], 'Preserved details')

    def test_explicit_title_mapping_can_omit_clear_or_blank_the_title(self):
        for kind in ('scene', 'image'):
            for expression, expected in (('empty', 'absent'), ('null', None), ('""', ''), ('"  "', '  ')):
                with self.subTest(kind=kind, expression=expression):
                    plugin = self.make_plugin(kind, **{kind + '_import_mappings': {'title': expression}})
                    plugin.process()
                    if expected == 'absent':
                        self.assertNotIn('title', self.updates[0])
                    else:
                        self.assertEqual(self.updates[0]['title'], expected)

    def test_other_import_mapping_does_not_disable_title_fallback(self):
        plugin = self.make_plugin(scene_import_mappings={'details': '"Mapped details"'})
        plugin.process()
        self.assertEqual(self.updates[0]['title'], 'example')
        self.assertEqual(self.updates[0]['details'], 'Mapped details')

    def test_fallback_setting_and_title_exclusion_apply_with_and_without_metadata(self):
        for has_metadata in (False, True):
            if has_metadata:
                self.capture()
            for settings in ({'filename_title_fallback': False}, {'blacklist': json.dumps(['title'])}):
                with self.subTest(metadata=has_metadata, settings=settings):
                    plugin = self.make_plugin(**settings)
                    plugin.process()
                    if has_metadata:
                        self.assertNotIn('title', self.updates[0])
                        self.assertEqual(self.updates[0]['details'], 'Hola')
                    else:
                        self.assertEqual(self.updates, [])

    def test_fallback_respects_dry_run_direction_and_organized_policy(self):
        for settings in ({'dry_mode': True}, {'sync_direction': 'export'}, {'organized': True}):
            plugin = self.make_plugin(**settings)
            plugin.process()
            self.assertEqual(self.updates, [])
        plugin = self.make_plugin(organized=True, mode='reload')
        plugin._CatalogMetadataPlugin__process_item('42', 'scene')
        self.assertEqual(self.updates, [{'id': '42', 'title': 'example', 'clientMutationId': IMPORT_MARKER}])

    def test_media_without_a_file_does_not_use_delivery_urls_as_filenames(self):
        for kind in ('scene', 'image'):
            plugin = self.make_plugin(kind)
            self.item.update({'files': [], 'visual_files': [], 'paths': {'image': 'https://stash.example/image/42/image'}})
            plugin.process()
            self.assertEqual(self.updates, [])

    def test_fallback_notification_does_not_create_catalog_override(self):
        self.capture()
        for kind in ('scene', 'image'):
            plugin = self.make_plugin(kind)
            plugin.process()
            payload = self.updates[0]
            self.assertEqual(payload['title'], 'example')
            plugin._stash._fragment['args']['hookContext'] = {
                'type': kind.capitalize() + '.Update.Post', 'id': '42',
                'inputFields': ['title'], 'input': payload,
            }
            with patch.object(catalogMappings, 'get_reader', side_effect=AssertionError('Automatic titles must not be exported')):
                plugin.process()
            self.assertEqual(self.reader.overrides(self.path), {})


if __name__ == '__main__':
    unittest.main()
