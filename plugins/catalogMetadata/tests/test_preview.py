"""Entity previews read real temporary catalogs; any attempted write fails."""
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_plugin
from test_mappings import SETTINGS, evaluate
import catalogMetadata
import catalogMappings
import config
from stashInterface import StashInterface


class PreviewTests(unittest.TestCase):
    setUp = test_plugin.CatalogPluginTests.setUp
    capture = test_plugin.CatalogPluginTests.capture

    def preview(self, kind, direction, item=None, **settings):
        for key in SETTINGS:
            if hasattr(config, key):
                original = getattr(config, key)
                self.addCleanup(setattr, config, key, original)
        item = item if item is not None else {
            'id': '42', 'title': 'Stash title', 'organized': True,
            'files': [{'path': str(self.path)}], 'visual_files': [{'path': str(self.path)}],
            'performers': [{'id': '7', 'name': 'Alice'}],
            'tags': [{'id': '8', 'name': '_CATALOG_RELOAD'}, {'id': '9', 'name': 'Chosen'}],
            'custom_fields': {'catalog_title': 'Custom title'}, 'urls': [],
        }
        interface = StashInterface({
            'args': {'mode': 'preview', 'setting': f'{kind}_{direction}_mappings',
                     'entity_type': kind, 'entity_id': '42'},
            'server_connection': {'PluginDir': '.', 'Port': 1, 'Host': 'localhost', 'Scheme': 'http'},
        })
        def response(_url, **kwargs):
            query = kwargs['json']['query'].lstrip()
            self.assertTrue(query.startswith('query'), 'Preview attempted a Stash mutation')
            if 'pluginSettingsV3' in query:
                data = {'pluginSettingsV3': {'values': {**SETTINGS, 'blacklist': '["cover_image"]', **settings}}}
            elif f'find{kind.capitalize()}(' in query:
                data = {f'find{kind.capitalize()}': item or None}
            else:
                raise AssertionError('Unexpected GraphQL operation: ' + query)
            return SimpleNamespace(status_code=200, json=lambda: {'data': data})
        with patch('requests.post', side_effect=response), \
                patch.object(catalogMetadata.CatalogMetadataPlugin, '_CatalogMetadataPlugin__update', side_effect=AssertionError('Import write path entered')), \
                patch.object(catalogMappings.CatalogMappings, 'export_item', side_effect=AssertionError('Export write path entered')), \
                patch.object(catalogMappings, 'write_overrides', side_effect=AssertionError('Catalog write attempted')):
            return catalogMetadata.CatalogMetadataPlugin(interface).process()

    def catalog_hashes(self):
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (self.root / 'catalog').rglob('*') if path.is_file() and not path.name.endswith('-shm')}

    def test_import_preview_reads_organized_items_and_preserved_defaults_without_writes(self):
        self.capture()
        folder = self.path.parent / 'folder.nfo'
        folder.write_text('<movie><actor><name>Folder performer</name></actor></movie>')
        self.store.import_nfo('Manual/folder.nfo')
        folder.unlink()
        before = self.catalog_hashes()
        for kind in ('scene', 'image'):
            context = self.preview(kind, 'import', sync_direction='export', create_missing_performers=True)
            self.assertNotIn('settings', context)
            self.assertEqual(context['catalog']['actors'], ['Folder performer'])
            self.assertEqual(context['catalog']['details'], 'Hola')
            self.assertEqual(context['stash']['title'], 'Stash title')
            self.assertEqual(context['observations'][-1]['payload']['author']['name'], 'account')
            self.assertEqual(evaluate({'title': '.observations[-1].payload.content | ascii_upcase'}, context), {'title': 'HOLA'})
        self.assertEqual(before, self.catalog_hashes())

    def test_export_preview_simulates_fields_without_exposing_plugin_settings_or_writing(self):
        self.capture()
        before = self.catalog_hashes()
        for kind in ('scene', 'image'):
            context = self.preview(kind, 'export', sync_direction='import')
            self.assertNotIn('settings', context)
            self.assertEqual(context['stash']['tags'], [{'id': '9', 'name': 'Chosen'}])
            self.assertEqual(context['input']['tag_ids'], ['8', '9'])
            self.assertEqual(context['input']['performer_ids'], ['7'])
            self.assertEqual(context['input']['custom_fields'], {'full': {'catalog_title': 'Custom title'}})
            self.assertIn('performer_ids', context['fields'])
            self.assertNotIn('id', context['fields'])
            result = evaluate(SETTINGS[f'{kind}_export_mappings'], context)
            self.assertEqual(result['actors'], ['Alice'])
            self.assertEqual(result['tags'], ['Chosen'])
            self.assertEqual(result['title'], 'Stash title')
            context['fields'] = ['performer_ids']
            self.assertEqual(evaluate(SETTINGS[f'{kind}_export_mappings'], context), {'actors': ['Alice']})
        self.assertEqual(before, self.catalog_hashes())

    def test_export_preview_honors_custom_refresh_tag_without_changing_the_entity(self):
        self.capture()
        item = {'id': '42', 'files': [{'path': str(self.path)}], 'visual_files': [{'path': str(self.path)}],
                'tags': [{'id': '8', 'name': 'Refresh now'}, {'id': '9', 'name': 'Chosen'}]}
        for kind in ('scene', 'image'):
            context = self.preview(kind, 'export', item=item, reload_tag='Refresh now')
            self.assertNotIn('settings', context)
            self.assertEqual(evaluate({'tags': SETTINGS[f'{kind}_export_mappings']['tags']}, context), {'tags': ['Chosen']})
            self.assertEqual(item['tags'][0]['name'], 'Refresh now')
            self.assertEqual(len(item['tags']), 2)

    def test_shared_post_preview_exposes_attachment_patches_without_repeating_body(self):
        for num in (1,2,3):
            self.store.capture({'category':'twitter','tweet_id':'123',
                'author':{'id':'1','name':'account'},'content':'Shared caption',
                'num':num,'filename':str(num),'extension':'jpg'},'Manual/example.mp4')
        before=self.catalog_hashes()
        context=self.preview('image','import')
        self.assertEqual(len(context['observations']),1)
        post=context['observations'][0]
        self.assertEqual(post['payload']['content'],'Shared caption')
        self.assertNotIn('num',post['payload'])
        self.assertEqual({c['payload_patch']['num'] for c in post['captures']},{1,2,3})
        self.assertTrue(all('content' not in c['payload_patch'] for c in post['captures']))
        self.assertEqual(evaluate({'numbers':'[.observations[].captures[].payload_patch.num] | sort'},context),
                         {'numbers':[1,2,3]})
        self.assertEqual(before,self.catalog_hashes())

    def test_first_unsaved_import_mapping_can_preview_without_projected_metadata(self):
        context = self.preview('scene', 'import')
        self.assertEqual(context['catalog']['source'], 'catalog')
        self.assertEqual(context['observations'], [])
        self.assertEqual(evaluate({'title': '.stash.title'}, context), {'title': 'Stash title'})

    def test_preview_errors_for_missing_item_path_or_outside_catalog(self):
        with self.assertRaisesRegex(ValueError, 'not found'):
            self.preview('scene', 'import', item={})
        with self.assertRaisesRegex(ValueError, 'no usable file path'):
            self.preview('image', 'export', item={'id': '42'})
        with self.assertRaises(ValueError):
            self.preview('scene', 'import', item={'id': '42', 'files': [{'path': '/outside/example.mp4'}]})

    def test_preview_rejects_unknown_setting_before_querying_entity(self):
        with self.assertRaisesRegex(ValueError, 'matching scene or image'):
            self.preview('scene', 'destroy')

    def test_preview_client_blocks_mutations_before_network(self):
        interface = StashInterface({'args': {'mode': 'preview'}, 'server_connection': {'PluginDir': '.'}})
        with patch('requests.post', side_effect=AssertionError('Network was called')):
            with self.assertRaisesRegex(RuntimeError, 'mutations are disabled'):
                interface._StashInterface__gql_call('mutation { sceneDestroy(input: {id: "42"}) }')


if __name__ == '__main__':
    unittest.main()
