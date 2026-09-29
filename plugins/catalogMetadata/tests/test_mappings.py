"""Offline bidirectional integration tests with a real jq evaluator.

STASH_JQ_EVALUATOR may name a helper using pkg/plugin.EvaluateMappings; otherwise
the developer's jq executable is used. Neither is a runtime plugin dependency.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

import test_plugin
import catalogMappings
from catalogMappings import CatalogMappings, IMPORT_MARKER
import config
from scrape_catalog.edits import edit
from stashInterface import StashInterface

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {name: value.get('default') for name, value in yaml.safe_load((ROOT / 'catalogMetadata.yml').read_text())['settings'].items()}


def evaluate(mappings, data):
    helper = os.environ.get('STASH_JQ_EVALUATOR')
    if helper:
        result = subprocess.run([helper], input=json.dumps({'mappings': mappings, 'input': data}),
                                text=True, capture_output=True, check=True)
        output = json.loads(result.stdout)
        if output.get('error'):
            raise ValueError(output['error'])
        return output['result']
    result = {}
    for key, expression in mappings.items():
        proc = subprocess.run(['jq', '-c', expression], input=json.dumps(data), text=True, capture_output=True, check=True)
        values = [json.loads(line) for line in proc.stdout.splitlines()]
        if len(values) > 1:
            raise ValueError('Mapping emitted multiple values')
        if values:
            result[key] = values[0]
    return result


@unittest.skipUnless(os.environ.get('STASH_JQ_EVALUATOR') or shutil.which('jq'), 'Set STASH_JQ_EVALUATOR or install jq for mapping tests')
class MappingTests(unittest.TestCase):
    setUp = test_plugin.CatalogPluginTests.setUp
    capture = test_plugin.CatalogPluginTests.capture

    def mappings(self, **values):
        # Setting application changes module globals only for one invocation.
        for key in SETTINGS:
            if hasattr(config, key):
                original = getattr(config, key)
                self.addCleanup(setattr, config, key, original)
        return CatalogMappings(SimpleNamespace(
            gql_pluginSettings=lambda: {**SETTINGS, **values}, gql_evaluateMappings=evaluate))

    def reader_patch(self):
        return patch.object(catalogMappings, 'get_reader', return_value=self.reader)

    def test_custom_import_handles_raw_fields_null_false_and_custom_fields(self):
        self.capture()
        mappings = self.mappings(scene_import_mappings=json.dumps({
            'title': '.observations[-1].payload.content | ascii_upcase',
            'details': 'empty', 'date': 'null', 'organized': 'false', 'rating100': '0',
            'custom_fields': '{partial: {catalog_author: .observations[-1].payload.author.name}}',
        }))
        with self.reader_patch():
            payload = mappings.import_payload('scene', {'id': '42'}, self.path, self.reader.metadata(self.path),
                                              {'title': 'Old', 'details': 'Keep', 'date': '2020-01-01'})
        self.assertEqual(payload['title'], 'HOLA')
        self.assertNotIn('details', payload)
        self.assertIsNone(payload['date'])
        self.assertIs(payload['organized'], False)
        self.assertEqual(payload['rating100'], 0)
        self.assertEqual(payload['custom_fields'], {'partial': {'catalog_author': 'account'}})
        self.assertEqual(payload['clientMutationId'], IMPORT_MARKER)
        self.assertEqual(payload['id'], '42')

    def test_default_exports_only_changed_fields_and_does_not_repeat_edits(self):
        self.capture()
        mappings = self.mappings()
        item = {'id': '42', 'title': 'Manual title', 'details': 'Must not export'}
        with self.reader_patch():
            result = mappings.export_item('scene', item, self.path, {'inputFields': ['title']})
            self.assertEqual(result['fields'], {'title': 'Manual title'})
            self.assertEqual(self.reader.metadata(self.path)['details'], 'Hola')
            self.assertIsNone(mappings.export_item('scene', item, self.path, {'inputFields': ['title']}))
        self.assertEqual(self.reader.metadata(self.path)['title'], 'Manual title')

    def test_image_exports_relation_names_and_excludes_refresh_tag(self):
        self.capture()
        mappings = self.mappings()
        item = {'id': '42', 'performers': [{'name': 'Alice'}], 'studio': {'name': 'Studio'},
                'tags': [{'name': '_CATALOG_RELOAD'}, {'name': 'Chosen'}]}
        with self.reader_patch():
            result = mappings.export_item('image', item, self.path, {'inputFields': ['performer_ids', 'studio_id', 'tag_ids']})
        self.assertEqual(result['fields'], {'actors': ['Alice'], 'studio': 'Studio', 'tags': ['Chosen']})

    def test_custom_export_extracts_custom_fields_and_can_remove_override(self):
        self.capture()
        edit(self.store, self.path, {'details': 'Manual caption'})
        mappings = self.mappings(scene_export_mappings=json.dumps({
            'title': '.stash.custom_fields.catalog_title', 'details': 'null',
        }))
        with self.reader_patch():
            mappings.export_item('scene', {'id': '42', 'custom_fields': {'catalog_title': 'Custom title'}}, self.path,
                                 {'inputFields': ['custom_fields']})
        self.assertEqual(self.reader.metadata(self.path)['title'], 'Custom title')
        self.assertEqual(self.reader.metadata(self.path)['details'], 'Hola')

    def test_import_notification_dry_run_disabled_and_unrelated_edits_do_not_write(self):
        self.capture()
        item = {'id': '42', 'title': 'Do not write'}
        hook = {'inputFields': ['title']}
        with self.reader_patch():
            mappings = self.mappings()
            self.assertIsNone(mappings.export_item('scene', item, self.path, {**hook, 'input': {'clientMutationId': IMPORT_MARKER}}))
            self.assertIsNone(mappings.export_item('scene', item, self.path, {**hook, 'parentHooks': [{'pluginId': 'titleFromFilename', 'type': 'Scene.Create.Post'}]}))
            self.assertIsNone(mappings.export_item('scene', item, self.path, {'inputFields': ['play_count']}))
            mappings = self.mappings(sync_direction='import')
            self.assertIsNone(mappings.export_item('scene', item, self.path, hook))
            mappings = self.mappings(dry_mode=True)
            self.assertEqual(mappings.export_item('scene', item, self.path, hook), {'title': 'Do not write'})
        self.assertNotIn('title', self.reader.overrides(self.path))

    def test_bad_mapping_fails_before_any_catalog_edit(self):
        self.capture()
        mappings = self.mappings(scene_export_mappings=json.dumps({'title': '"Valid"', 'details': '1, 2'}))
        with self.reader_patch(), self.assertRaises(ValueError):
            mappings.export_item('scene', {'id': '42'}, self.path, {'inputFields': ['title']})
        self.assertEqual(self.reader.overrides(self.path), {})

    def test_import_transform_reaches_both_graphql_mutations(self):
        interface = StashInterface.__new__(StashInterface)
        fields = dict.fromkeys(('title', 'details', 'date', 'rating', 'urls', 'studio_id', 'code', 'performer_ids', 'tag_ids', 'cover_image', 'movie_id'))
        for kind in ('Scene', 'Image'):
            with patch.object(config, 'dry_mode', False), patch.object(interface, '_StashInterface__gql_call', return_value={kind.lower() + 'Update': {'id': '42'}}) as call:
                getattr(interface, 'gql_update' + kind)('42', fields, lambda payload: {**payload, 'clientMutationId': IMPORT_MARKER, 'custom_fields': {'partial': {'test': False}}})
                payload = call.call_args[0][1]['input']
                self.assertEqual(payload['clientMutationId'], IMPORT_MARKER)
                self.assertEqual(payload['custom_fields'], {'partial': {'test': False}})


if __name__ == '__main__':
    unittest.main()
