import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_plugin
import catalogMetadata
import catalogPerformers as identities
import config
from stashInterface import StashInterface
from test_mappings import SETTINGS
from scrape_catalog.store import Store
from scrape_catalog.identities import read_state, transaction


def performer(pid, name, aliases=(), urls=(), disambiguation=''):
    return {'id': str(pid), 'name': name, 'alias_list': list(aliases), 'urls': list(urls), 'disambiguation': disambiguation}


class PerformerIdentityTests(unittest.TestCase):
    setUp = test_plugin.CatalogPluginTests.setUp

    def capture(self, platform='twitter', aid='10', handle='account', filename='example.mp4'):
        path = self.path.parent / filename
        path.write_bytes(b'same content across accounts is not identity evidence')
        if platform == 'twitter':
            data = {'category': 'twitter', 'tweet_id': aid, 'author': {'id': aid, 'name': handle}, 'content': 'Source caption'}
        else:
            data = {'category': 'reddit', 'id': aid, 'author_fullname': aid, 'author': handle, 'title': 'Reddit caption'}
        return self.store.capture(data, 'Manual/' + filename)

    def match(self, name, performers, settings=None, path=None):
        return identities.match_performer(name, performers, self.reader, path or self.path, settings or {})

    def sync(self, performers, settings=None, hook=None, preview=False):
        return identities.sync_links(self.reader, SimpleNamespace(gql_allPerformers=lambda: performers,
                                     gql_pluginSettings=lambda: settings or {}), settings or {}, hook, preview)

    def hashes(self):
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (self.root / 'catalog').rglob('*')
                if path.is_file() and not path.name.endswith('-shm')}

    def test_canonical_and_all_aliases_are_exact_unicode_matches(self):
        profiles = [performer(1, 'Canonical', ['SingleWord', 'SingleWord', 'CAFÉ', 'Straße'])]
        for name in (' CANONICAL ', 'singleword', 'cafe\u0301', 'STRASSE'):
            self.assertEqual(self.match(name, profiles)[0], '1')
        for name in ('Canon', 'SinglesWord', '@SingleWord', ''):
            self.assertIsNone(self.match(name, profiles)[0])

    def test_canonical_alias_and_duplicate_canonical_collisions_do_not_pick_first(self):
        for profiles in ([performer(1, 'Sam'), performer(2, 'Someone', ['Sam', 'Sam'])],
                         [performer(1, 'Sam', disambiguation='A'), performer(2, 'Sam', disambiguation='B')]):
            selected, candidates = self.match('sam', profiles)
            self.assertIsNone(selected)
            self.assertEqual({p['id'] for p in candidates}, {'1', '2'})
            self.assertIsNone(self.match('sam', list(reversed(profiles)))[0])

    def test_ambiguous_import_neither_creates_nor_adds_a_performer(self):
        profiles = [performer(1, 'Sam'), performer(2, 'Other', ['Sam'])]
        plugin = catalogMetadata.CatalogMetadataPlugin.__new__(catalogMetadata.CatalogMetadataPlugin)
        plugin._stash = SimpleNamespace(gql_allPerformers=lambda: profiles,
                                        gql_performerCreate=lambda _: self.fail('Created an ambiguous performer'))
        plugin._mappings = SimpleNamespace(settings={})
        plugin._file_data = {'actors': ['Sam']}
        plugin._item_id, plugin._item_type = '42', 'scene'
        plugin._item = {'files': [{'path': str(self.path)}], 'performers': [{'id': '9'}]}
        with patch.object(config, 'create_missing_performers', True), patch.object(config, 'dry_mode', False), \
                patch.object(catalogMetadata.log, 'LogWarning') as warning:
            self.assertEqual(plugin._CatalogMetadataPlugin__find_create_performers(), [])
        self.assertEqual(plugin._item['performers'], [{'id': '9'}])
        self.assertIn('ambiguous', warning.call_args.args[0])
        self.assertIn('"id": "2"', warning.call_args.args[0])

    def test_explicit_links_disambiguate_only_the_relevant_accounts(self):
        self.capture()
        self.capture('reddit', 't2_20', 'account', 'other.jpg')
        profiles = [performer(1, 'One', ['Sam']), performer(2, 'Two', ['Sam'])]
        settings = {'performer_account_links': {'twitter:id:10': '1', 'reddit:id:t2_20': '2'}}
        self.assertEqual(self.match('Sam', profiles, settings)[0], '1')
        self.assertEqual(self.match('Sam', profiles, settings, self.path.parent / 'other.jpg')[0], '2')
        # Two author identities on one file are still ambiguous for this name.
        self.capture('reddit', 't2_20', 'account')
        self.assertIsNone(self.match('Sam', profiles, settings)[0])

    def test_merge_links_cross_service_and_same_service_accounts_preserving_evidence(self):
        cids = [self.capture(), self.capture('reddit', 't2_20', 'elsewhere', 'reddit.jpg'),
                self.capture('twitter', '30', 'another', 'other.mp4')]
        before_payloads = {r[0] for cid in cids for r in self.store.db(cid).execute('SELECT payload_json FROM observations')}
        dest = performer(1, 'Canonical', ['account', 'elsewhere'])
        hook = {'type': 'Performer.Merge.Post', 'id': 1, 'input': {
            'destination': dest,
            'previous_destination': performer(1, 'account', urls=['https://x.com/account']),
            'sources': [performer(2, 'elsewhere', ['Lost alias'], ['https://reddit.com/user/elsewhere']),
                        performer(3, 'another', urls=['https://twitter.com/another'])]}}
        report = self.sync([dest], hook=hook)
        self.assertEqual(report['conflicts'], [])
        self.assertEqual(len(report['links']), 1)
        self.assertEqual(len(report['links'][0]['accounts']), 3)
        target = self.store.resolve(cids[0])
        self.assertTrue(all(self.store.resolve(cid) == cid for cid in cids))
        self.assertEqual({r[0] for cid in cids for r in self.store.db(cid).execute('SELECT payload_json FROM observations')}, before_payloads)
        state = read_state(self.store.registry)
        self.assertEqual(len({row['identity_id'] for row in state['accounts'].values()}), 1)
        uid = report['links'][0]['identity_id']
        self.assertEqual(state['identities'][uid]['profile']['name'], 'Canonical')
        self.assertTrue(all((self.root / 'catalog/catalogs' / (cid + '.sqlite3')).exists() for cid in cids))
        self.assertEqual(self.match('Lost alias', [dest], path=self.path.parent / 'reddit.jpg')[0], '1')
        # Retry is idempotent, including source ID redirects and captured posts.
        self.sync([dest], hook=hook)
        self.assertEqual(sum(self.store.db(cid).execute('SELECT count(*) FROM observations').fetchone()[0] for cid in cids), 3)
        self.assertEqual(self.store.registry.execute('SELECT count(*) FROM links').fetchone()[0], 0)
        self.assertEqual(read_state(self.store.registry)['accounts']['twitter:id:10']['identity_id'], uid)

    def test_names_and_shared_content_only_produce_review_candidates(self):
        cids = [self.capture(), self.capture('reddit', 't2_20', 'account', 'reddit.jpg')]
        profiles = [performer(1, 'account')]
        report = self.sync(profiles)
        self.assertEqual(report['links'], [])
        self.assertEqual(len(report['name_only_candidates']), 2)
        self.assertTrue(all(self.store.resolve(cid) == cid for cid in cids))

    def test_conflicting_profile_urls_require_an_explicit_account_link(self):
        self.capture()
        profiles = [performer(1, 'One', urls=['https://x.com/account']),
                    performer(2, 'Two', urls=['https://twitter.com/account'])]
        report = self.sync(profiles)
        self.assertEqual(report['links'], [])
        self.assertEqual(report['conflicts'][0]['performer_ids'], ['1', '2'])
        report = self.sync(profiles, {'performer_account_links': {'twitter:id:10': '2'}})
        self.assertEqual(report['conflicts'], [])
        self.assertEqual(report['links'][0]['performer_id'], '2')

    def test_reused_handles_do_not_join_distinct_account_ids(self):
        cids = [self.capture(), self.capture('twitter', '20', 'account', 'reused.mp4')]
        profiles = [performer(1, 'Canonical', urls=['https://x.com/account'])]
        report = self.sync(profiles)
        self.assertEqual(report['links'], [])
        self.assertIn('multiple account IDs', report['conflicts'][0]['reason'])
        report = self.sync([performer(1, 'Canonical', urls=['https://x.com/i/user/10'])])
        self.assertEqual(report['links'][0]['accounts'], ['twitter:id:10'])
        self.assertTrue(all(self.store.resolve(cid) == cid for cid in cids))

    def test_preview_and_dry_run_never_open_writer_or_change_catalog(self):
        self.capture()
        profiles = [performer(1, 'Canonical', urls=['https://x.com/account'])]
        before = self.hashes()
        with patch('scrape_catalog.store.Store', side_effect=AssertionError('Writer opened')):
            self.assertEqual(len(self.sync(profiles, preview=True)['links']), 1)
            self.assertEqual(len(self.sync(profiles, {'dry_mode': True})['links']), 1)
        self.assertEqual(self.hashes(), before)

    def test_persisted_binding_resolves_ambiguity_and_namespace_isolated(self):
        self.capture()
        profiles = [performer(1, 'Same', urls=['https://x.com/account']), performer(2, 'Same')]
        self.sync(profiles)
        self.assertEqual(self.match('Same', profiles)[0], '1')
        self.assertIsNone(self.match('Same', profiles, {'performer_link_namespace': 'other-library'})[0])

    def test_linked_account_handle_is_scoped_history_without_becoming_an_uploader_tag(self):
        self.capture()
        self.capture('reddit', 't2_20', 'account', 'unrelated.jpg')
        profiles = [performer(1, 'Canonical', urls=['https://x.com/account'])]
        self.sync(profiles)
        self.assertEqual(self.match('account', profiles)[0], '1')
        self.assertIsNone(self.match('account', profiles, path=self.path.parent / 'unrelated.jpg')[0])
        self.assertIsNone(self.match('Another person', profiles)[0])
        self.assertEqual(profiles[0]['alias_list'], [])

    def test_accounts_in_a_previously_joined_catalog_can_have_separate_identities(self):
        a = self.capture()
        b = self.capture('reddit', 't2_20', 'elsewhere', 'reddit.jpg')
        self.store.link(b, a, 'Previously explicitly joined')
        profiles = [performer(1, 'One', urls=['https://x.com/account']),
                    performer(2, 'Two', urls=['https://reddit.com/user/elsewhere'])]
        report = self.sync(profiles)
        self.assertEqual(report['conflicts'], [])
        self.assertEqual(len({row['identity_id'] for row in report['links']}), 2)
        self.assertEqual(self.store.resolve(b), a)

    def test_synchronization_never_calls_physical_catalog_link(self):
        cids = [self.capture(), self.capture('reddit', 't2_20', 'elsewhere', 'reddit.jpg')]
        profiles = [performer(1, 'Canonical', urls=['https://x.com/account', 'https://reddit.com/user/elsewhere'])]
        with patch.object(Store, 'link', side_effect=AssertionError('Physical catalog merge')):
            first = self.sync(profiles)
            second = self.sync(profiles)
        self.assertEqual(first['links'][0]['identity_id'], second['links'][0]['identity_id'])
        self.assertTrue(all(self.store.resolve(cid) == cid for cid in cids))

    def test_late_merge_notification_follows_an_already_merged_destination(self):
        self.capture()
        self.capture('reddit', 't2_20', 'elsewhere', 'reddit.jpg')
        first = performer(1, 'First', urls=['https://x.com/account'])
        second = performer(2, 'Second', urls=['https://reddit.com/user/elsewhere'])
        final = performer(3, 'Final', aliases=['First', 'Second'])
        later = {'type': 'Performer.Merge.Post', 'id': 3, 'input': {
            'destination': final, 'previous_destination': final, 'sources': [second]}}
        self.sync([final], hook=later)
        earlier = {'type': 'Performer.Merge.Post', 'id': 2, 'input': {
            'destination': second, 'previous_destination': second, 'sources': [first]}}
        report = self.sync([final], hook=earlier)
        self.assertEqual(report['links'][0]['performer_id'], '3')
        self.assertEqual(len(report['links'][0]['accounts']), 2)
        self.assertEqual(self.match('First', [final])[0], '3')

    def test_merge_into_unbound_stash_destination_keeps_existing_catalog_uuid(self):
        self.capture()
        first = performer(1, 'First', urls=['https://x.com/account'])
        uid = self.sync([first])['links'][0]['identity_id']
        final = performer(2, 'Final')
        hook = {'type': 'Performer.Merge.Post', 'id': 2, 'input': {
            'destination': final, 'previous_destination': final, 'sources': [first]}}
        report = self.sync([final], hook=hook)
        self.assertEqual(report['links'][0]['identity_id'], uid)
        self.assertEqual(len(read_state(self.store.registry)['identities']), 1)

    def test_concurrent_merge_keeps_deleted_profiles_when_live_query_becomes_stale(self):
        a = self.capture()
        b = self.capture('reddit', 't2_20', 'elsewhere', 'reddit.jpg')
        first = performer(1, 'First', urls=['https://x.com/account'])
        second = performer(2, 'Second', urls=['https://reddit.com/user/elsewhere'])
        final = performer(3, 'Final')
        later = {'type': 'Performer.Merge.Post', 'id': 3, 'input': {
            'destination': final, 'previous_destination': final, 'sources': [second]}}
        self.sync([final], hook=later)
        earlier = {'type': 'Performer.Merge.Post', 'id': 2, 'input': {
            'destination': second, 'previous_destination': second, 'sources': [first]}}
        # This older invocation queried Stash before the later merge committed,
        # then waited for its catalog lock. Neither source URL survives in Stash.
        report = self.sync([second], hook=earlier)
        self.assertTrue(any('destination changed' in c['reason'] for c in report['conflicts']))
        self.sync([final])
        self.assertNotEqual(self.store.resolve(a), self.store.resolve(b))
        state = read_state(self.store.registry)
        self.assertEqual(state['accounts']['twitter:id:10']['identity_id'], state['accounts']['reddit:id:t2_20']['identity_id'])
        self.assertEqual(self.match('First', [final])[0], '3')

    def test_captured_profile_evidence_matches_any_extractor_and_rejects_reused_urls(self):
        self.store.capture({'category': 'example-site', 'id': 'post', 'author': {'id': '10', 'name': 'Name',
                            'profile_url': 'https://site.example/profile/10'}}, 'Manual/example.mp4')
        report = self.sync([performer(1, 'Canonical', urls=['https://site.example/profile/10'])])
        self.assertEqual(report['links'][0]['accounts'], ['example-site:id:10'])

    def test_elizabeth_legacy_link_and_instagram_url_share_one_uuid(self):
        self.capture('twitter', '742448640', 'ImElizabethTran')
        self.store.capture({'category': 'instagram', 'owner_id': 'instagram123', 'username': 'elizabethtran626',
                            'post_id': 'photo'}, 'Instagram/example.jpg')
        profiles = [performer(721, 'Elizabeth Tran', ['ImElizabethTran', 'elizabethtran626'],
                              ['https://x.com/i/user/742448640', 'https://www.instagram.com/elizabethtran626'])]
        first = self.sync(profiles)
        self.assertEqual(len(first['links'][0]['accounts']), 2)
        self.assertEqual(first['conflicts'], [])
        profiles[0]['name'] = 'Renamed'
        second = self.sync(profiles)
        self.assertEqual(first['links'][0]['identity_id'], second['links'][0]['identity_id'])

    def test_profile_url_parser_excludes_posts_subreddits_and_untrusted_hosts(self):
        self.assertEqual(identities.profile_ref('https://www.x.com/Account?lang=en'), ('twitter', 'handle', 'account'))
        self.assertEqual(identities.profile_ref('https://old.reddit.com/u/Some-Name/'), ('reddit', 'handle', 'some-name'))
        for url in ('https://x.com/account/status/123', 'https://reddit.com/r/example',
                    'https://reddit.com/user/name/comments/123', 'https://x.com.evil.test/account',
                    'https://x.com@evil.test/account', 'https://x.com/%61ccount', 'file:///account', 'https://x.com/home'):
            self.assertIsNone(identities.profile_ref(url), url)

    def test_real_hook_dispatch_honors_import_only_and_dry_run_without_stash_mutations(self):
        for key in SETTINGS:
            if hasattr(config, key):
                self.addCleanup(setattr, config, key, getattr(config, key))
        a = self.capture()
        b = self.capture('reddit', 't2_20', 'elsewhere', 'reddit.jpg')
        dest = performer(1, 'Canonical', ['account', 'elsewhere'])
        hook = {'type': 'Performer.Merge.Post', 'id': 1, 'input': {
            'destination': dest, 'previous_destination': performer(1, 'account', urls=['https://x.com/account']),
            'sources': [performer(2, 'elsewhere', urls=['https://reddit.com/user/elsewhere'])]}}
        for settings in ({'sync_direction': 'import'}, {'dry_mode': True}, {'sync_performer_catalogs': False}, {}):
            interface = StashInterface({'args': {'hookContext': hook},
                                        'server_connection': {'PluginDir': '.', 'Host': 'localhost', 'Port': 1, 'Scheme': 'http'}})
            def response(_url, **kwargs):
                query = kwargs['json']['query'].strip()
                self.assertTrue(query.startswith('query'), 'Performer sync attempted a Stash mutation')
                if 'pluginSettingsV3' in query:
                    data = {'pluginSettingsV3': {'values': {**SETTINGS, **settings}}}
                elif 'findPerformers(' in query:
                    data = {'findPerformers': {'performers': [{**dest, 'aliases': [{'alias': a} for a in dest['alias_list']]}]}}
                else:
                    self.fail('Hook dispatched to an unexpected entity query: ' + query)
                return SimpleNamespace(status_code=200, json=lambda: {'data': data})
            with patch('requests.post', side_effect=response):
                catalogMetadata.CatalogMetadataPlugin(interface).process()
            if settings:
                self.assertNotEqual(self.store.resolve(a), self.store.resolve(b))
        self.assertNotEqual(self.store.resolve(a), self.store.resolve(b))
        state = read_state(self.store.registry)
        self.assertEqual(state['accounts']['twitter:id:10']['identity_id'], state['accounts']['reddit:id:t2_20']['identity_id'])


if __name__ == '__main__':
    unittest.main()
