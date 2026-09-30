import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, os.environ.get('SCRAPE_CATALOG_CODE', '/opt/scrape-catalog'))

import catalogMetadata
import catalogReader
import config
from reParser import RegExParser
import xmlParser
from scrape_catalog.edits import edit
from scrape_catalog.reader import Reader
from scrape_catalog.store import Store


class CatalogPluginTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.media = self.root / 'media'
        self.path = self.media / 'Manual' / 'example.mp4'
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'fixture')
        self.store = Store(self.root / 'catalog', self.media)
        self.addCleanup(self.store.close)
        self.reader = Reader(self.root / 'catalog', self.media)
        self.addCleanup(self.reader.close)
        for module in (catalogMetadata, xmlParser):
            p = patch.object(module, 'get_reader', return_value=self.reader)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(config, 'blacklist', [*config.blacklist, 'cover_image'])
        p.start()
        self.addCleanup(p.stop)
        p = patch('requests.get', side_effect=AssertionError('External network forbidden'))
        p.start()
        self.addCleanup(p.stop)

    def plugin(self, mode='reload'):
        plugin = catalogMetadata.CatalogMetadataPlugin.__new__(catalogMetadata.CatalogMetadataPlugin)
        plugin._stash = SimpleNamespace(get_mode=lambda: mode)
        return plugin

    def capture(self):
        return self.store.capture({
            'category': 'twitter', 'tweet_id': '1',
            'author': {'id': '10', 'name': 'account'}, 'content': 'Hola',
        }, 'Manual/example.mp4')

    def test_native_translation_and_manual_edit_with_preserved_folder_defaults(self):
        folder = self.path.parent / 'folder.nfo'
        folder.write_text('<movie><actor><name>Handcrafted performer</name></actor><studio>Studio</studio></movie>')
        self.store.import_nfo('Manual/folder.nfo')
        folder.unlink()
        cid = self.capture()
        self.store.add_translation(cid, 'twitter:post:1', {
            'original_text': 'Hola', 'translated_text': 'Hello', 'target_language': 'en',
        })
        edit(self.store, 'Manual/example.mp4', {'title': 'Handcrafted title'})
        data = self.plugin()._CatalogMetadataPlugin__parse(str(self.path), organized=True)
        self.assertEqual(data['title'], 'Handcrafted title')
        self.assertEqual(data['details'], 'Hello')
        self.assertEqual(data['actors'], ['Handcrafted performer'])
        self.assertEqual(data['studio'], 'Studio')
        self.assertEqual(data['source'], 'catalog')
        self.assertTrue(data['urls'])
        self.assertFalse(list(self.media.rglob('*.nfo')))

    def test_handcrafted_xml_is_read_after_sidecar_removal(self):
        nfo = self.path.with_suffix('.nfo')
        nfo.write_text('<movie><title>Manual title</title><plot>English caption</plot><original-plot>Original caption</original-plot><uniqueid>custom-code</uniqueid><url>https://example.test/post</url></movie>')
        self.store.import_nfo('Manual/example.nfo', ['Manual/example.mp4'])
        nfo.unlink()
        data = self.plugin()._CatalogMetadataPlugin__parse(str(self.path))
        self.assertEqual(data['title'], 'Manual title')
        self.assertEqual(data['details'], 'English caption')
        self.assertEqual(data['uniqueid'], 'custom-code')
        self.assertIn('https://example.test/post', data['urls'])

    def test_creation_skips_organized_but_explicit_refresh_applies(self):
        self.capture()
        self.assertIsNone(self.plugin('normal')._CatalogMetadataPlugin__parse(str(self.path), organized=True))
        self.assertEqual(self.plugin()._CatalogMetadataPlugin__parse(str(self.path), organized=True)['details'], 'Hola')

    def test_outside_catalog_source_is_skipped(self):
        self.assertIsNone(self.plugin()._CatalogMetadataPlugin__parse(str(self.root / 'other.mp4')))

    def test_startup_configures_backend_path_before_loading_shared_accounts(self):
        import subprocess
        code = "import sys; sys.path.insert(0, " + repr(str(Path(__file__).resolve().parents[1])) + "); import catalogMetadata; from catalogReader import get_reader; reader=get_reader(); print(len(reader.accounts()))"
        env = {**os.environ, 'SCRAPE_CATALOG_CODE': os.environ.get('SCRAPE_CATALOG_CODE', '/opt/scrape-catalog'),
               'SCRAPE_CATALOG_ROOT': str(self.store.root), 'SCRAPE_MEDIA_ROOT': str(self.media)}
        result = subprocess.run([sys.executable, '-I', '-c', code], env=env, cwd='/tmp', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().endswith('0'), result.stdout)

    def test_unconfigured_catalog_fails_visibly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'SCRAPE_CATALOG_ROOT'):
                catalogReader.get_reader()

    def test_filename_rules_are_separate_with_optional_legacy_fallback(self):
        legacy = self.path.parent / 'nfoFileParser.json'
        legacy.write_text(json.dumps({'regex': '(?P<title>.+)\\.mp4$', 'scope': 'filename'}))
        self.assertEqual(RegExParser(str(self.path)).parse()['title'], 'example')
        with patch.object(config, 'legacy_regex_fallback', False):
            self.assertEqual(RegExParser(str(self.path)).parse(), {})
        modern = self.path.parent / 'catalogMetadata.json'
        modern.write_text(json.dumps({'regex': '(?P<title>example).*', 'scope': 'filename'}))
        data = RegExParser(str(self.path)).parse()
        self.assertEqual(data['file'], str(modern))
        self.assertEqual(data['title'], 'example')


if __name__ == '__main__':
    unittest.main()
