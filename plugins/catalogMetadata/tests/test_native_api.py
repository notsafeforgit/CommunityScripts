import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from stashInterface import StashInterface


class NativeAPIClientTests(unittest.TestCase):
    def setUp(self):
        self.interface = StashInterface.__new__(StashInterface)
        self.interface._path_rewrite = None

    def call(self, response):
        return patch.object(self.interface, '_StashInterface__gql_call', return_value=response)

    def test_reload_uses_tag_ast_and_never_retries_an_empty_selection_unfiltered(self):
        for entity, plural in [('Scene', 'scenes'), ('Image', 'images')]:
            with self.subTest(entity=entity), self.call({'find' + entity + 's': {'count': 0, plural: []}}) as call:
                result = getattr(self.interface, 'gql_find' + entity + 's')('42')
                self.assertEqual(result, {'count': 0, plural: []})
                call.assert_called_once()
                query, variables = call.call_args.args
                self.assertIn(entity.lower() + '_filter_ast: $ast', query)
                self.assertNotIn(entity + 'FilterType', query)
                self.assertEqual(variables['ast'], {'root': {'condition': {
                    'field': 'tags', 'value': {'value': ['42'], 'modifier': 'INCLUDES'},
                }}})

    def test_native_group_lookup_actually_applies_its_name_filter(self):
        with self.call({'findGroups': {'groups': [{'id': '7', 'name': 'Album'}]}}) as call:
            result = self.interface.gql_findGroups('Album')
            self.assertEqual(result['groups'][0]['id'], '7')
            query, variables = call.call_args.args
            self.assertIn('findGroups(group_filter_ast: $ast', query)
            self.assertEqual(variables['ast']['root']['condition'], {
                'field': 'name', 'value': {'value': 'Album', 'modifier': 'INCLUDES'},
            })
            self.assertNotIn('studio_filter', variables)

    def test_studio_alias_alternative_is_an_explicit_or_group(self):
        with self.call({'findStudios': {'studios': []}}) as call:
            self.interface.gql_findStudios('Alias')
            root = call.call_args.args[1]['ast']['root']['group']
            self.assertEqual(root['operator'], 'OR')
            self.assertEqual([c['condition']['field'] for c in root['children']], ['name', 'aliases'])

    def test_tag_lookup_keeps_its_name_scope_and_returns_aliases(self):
        with self.call({'findTags': {'tags': []}}) as call:
            self.interface.gql_findTags('Reload')
            query, variables = call.call_args.args
            self.assertIn('id name aliases', query)
            self.assertEqual(variables['ast']['root']['condition']['field'], 'name')
            self.interface.gql_findTags()
            self.assertIsNone(call.call_args.args[1]['ast'])

    def test_scene_reads_and_writes_use_native_groups(self):
        with self.call({'findScene': {'id': '1'}}) as call:
            self.interface.gql_findScene('1')
            query = call.call_args.args[0]
            self.assertIn('groups { group { id name director } scene_index }', query)
            self.assertNotIn('movies {', query)
        fields = dict.fromkeys(('title', 'details', 'date', 'rating', 'urls', 'studio_id', 'code', 'performer_ids', 'tag_ids', 'cover_image'))
        fields.update(movie_id='7', scene_index=3)
        with patch.object(config, 'dry_mode', False), self.call({'sceneUpdate': {'id': '1'}}) as call:
            self.interface.gql_updateScene('1', fields)
            payload = call.call_args.args[1]['input']
            self.assertEqual(payload['groups'], [{'group_id': '7', 'scene_index': 3}])
            self.assertNotIn('movies', payload)

    def test_catalog_movie_creates_a_group_with_all_urls_and_handles_no_urls(self):
        for urls in [None, ['https://example.test/1', 'https://example.test/2']]:
            with self.subTest(urls=urls), patch.object(config, 'blacklist', []), self.call({'groupCreate': {'id': '7'}}) as call:
                self.assertEqual(self.interface.gql_groupCreate({'movie': 'Album', 'date': None, 'director': None}, None, {'urls': urls}), {'id': '7'})
                query, variables = call.call_args.args
                self.assertIn('GroupCreateInput!', query)
                self.assertIn('groupCreate(input: $input)', query)
                self.assertEqual(variables['input']['urls'], urls or [])
                self.assertNotIn('url', variables['input'])


if __name__ == '__main__':
    unittest.main()
