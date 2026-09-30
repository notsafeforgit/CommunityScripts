import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_plugin
import catalogReview as review
import test_performers
from test_performers import performer
from stashInterface import StashInterface


class ReviewTests(unittest.TestCase):
    setUp = test_plugin.CatalogPluginTests.setUp
    capture = test_performers.PerformerIdentityTests.capture
    hashes = test_performers.PerformerIdentityTests.hashes

    def stash(self, profiles, settings=None):
        values = copy.deepcopy(settings or {})
        writes = []

        def save(links):
            values['performer_account_links'] = dict(links)
            writes.append(dict(links))

        return SimpleNamespace(gql_allPerformers=lambda: copy.deepcopy(profiles),
                               gql_pluginSettings=lambda: copy.deepcopy(values),
                               gql_savePerformerLinks=save, clear_performer_cache=lambda: None,
                               values=values, writes=writes)

    def test_list_and_preview_never_open_writer_or_save_settings(self):
        a = self.capture()
        self.capture('reddit', 't2_20', 'account', 'other.jpg')
        stash = self.stash([performer(1, 'account'), performer(2, 'Other', ['account'])])
        before = self.hashes()
        with patch('scrape_catalog.store.Store', side_effect=AssertionError('Writer opened')):
            report = review.dispatch(self.reader, stash, 'list_reviews', 'query', {})
            self.assertEqual(report['counts'], {'candidate': 2})
            self.assertEqual(report['catalogs'][0]['candidate_ids'], ['1', '2'])
            self.assertEqual(report['catalogs'][0]['accounts'][0]['evidence'][0]['kind'], 'name_only')
            proposal = review.dispatch(self.reader, stash, 'review_link', 'query', {'catalog_id': a, 'performer_id': '2'})
            self.assertEqual(len(proposal['catalogs']), 1)
            self.assertEqual(proposal['explicit_links'], {'twitter:id:10': '2'})
        self.assertEqual(self.hashes(), before)
        self.assertEqual(stash.writes, [])

    def test_conflicts_show_profile_evidence_and_duplicate_name_disambiguation(self):
        self.capture()
        stash = self.stash([performer(1, 'Same', urls=['https://x.com/account'], disambiguation='One'),
                            performer(2, 'Same', urls=['https://twitter.com/account'], disambiguation='Two')])
        report = review.list_reviews(self.reader, stash)
        self.assertEqual(report['counts'], {'conflict': 1})
        self.assertEqual(report['catalogs'][0]['candidate_ids'], ['1', '2'])
        self.assertEqual(len(report['catalogs'][0]['accounts'][0]['evidence']), 2)
        self.assertEqual(report['performers'][1]['disambiguation'], 'Two')

    def test_reviewed_reused_handle_stops_blocking_the_resolved_account(self):
        a = self.capture()
        b = self.capture('twitter', '20', 'account', 'other.mp4')
        stash = self.stash([performer(1, 'Canonical', urls=['https://x.com/account'])],
                           {'performer_account_links': {'twitter:id:10': '1'}})
        report = review.list_reviews(self.reader, stash)
        by_id = {row['catalog_id']: row for row in report['catalogs']}
        self.assertEqual(by_id[a]['status'], 'proposed')
        self.assertEqual(by_id[b]['status'], 'conflict')

    def test_background_sync_reloads_choices_saved_while_it_waited(self):
        import catalogPerformers
        self.capture()
        stash = self.stash([performer(1, 'One'), performer(2, 'Two')],
                           {'performer_account_links': {'twitter:id:10': '2'}})
        report = catalogPerformers.sync_links(self.reader, stash, {'performer_account_links': {'twitter:id:10': '1'}})
        self.assertEqual(report['links'][0]['performer_id'], '2')

    def test_apply_only_reviewed_identity_preserves_evidence_and_other_choices(self):
        a = self.capture()
        b = self.capture('reddit', 't2_20', 'elsewhere', 'other.jpg')
        c = self.capture('twitter', '30', 'unrelated', 'unrelated.mp4')
        profiles = [performer(1, 'Canonical', urls=['https://reddit.com/user/elsewhere']),
                    performer(2, 'Unrelated', urls=['https://x.com/unrelated'])]
        stash = self.stash(profiles, {'performer_account_links': {'twitter:id:30': '2'}, 'filename_title_fallback': False})
        request = {'catalog_id': a, 'performer_id': '1'}
        report, _, _ = review.review_link(self.reader, stash, request)
        self.assertEqual({row['id'] for row in report['catalogs']}, {a, b})
        result = review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
        self.assertEqual(result['merged_catalogs'], 1)
        self.assertEqual(self.store.resolve(a), self.store.resolve(b))
        self.assertEqual(self.store.resolve(c), c)
        self.assertEqual(stash.values['performer_account_links'], {'twitter:id:10': '1', 'twitter:id:30': '2'})
        self.assertFalse(stash.values['filename_title_fallback'])
        self.assertEqual(self.store.db(self.store.resolve(a)).execute('SELECT count(*) FROM observations').fetchone()[0], 2)
        self.assertEqual(review.list_reviews(self.reader, stash)['counts']['linked'], 1)

    def test_joined_catalog_is_previewed_and_bound_as_a_whole(self):
        a = self.capture()
        b = self.capture('reddit', 't2_20', 'elsewhere', 'other.jpg')
        self.store.link(b, a, 'Prior explicit link')
        stash = self.stash([performer(1, 'Canonical')])
        report, _, _ = review.review_link(self.reader, stash, {'catalog_id': a, 'performer_id': '1'})
        self.assertEqual(set(report['explicit_links']), {'twitter:id:10', 'reddit:id:t2_20'})
        self.assertEqual(len(report['catalogs']), 1)

    def test_stale_performers_settings_or_accounts_require_new_preview(self):
        a = self.capture()
        profiles = [performer(1, 'Canonical')]
        stash = self.stash(profiles)
        request = {'catalog_id': a, 'performer_id': '1'}
        for change in (lambda: profiles[0].update(name='Changed'),
                       lambda: stash.values.update(performer_link_namespace='other'),
                       lambda: self.capture('twitter', '20', 'new', 'new.mp4')):
            report, _, _ = review.review_link(self.reader, stash, request)
            change()
            before = self.hashes()
            with patch('scrape_catalog.store.Store', side_effect=AssertionError('Writer opened')):
                with self.assertRaisesRegex(ValueError, 'out of date'):
                    review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
            self.assertEqual(self.hashes(), before)
        self.assertEqual(stash.writes, [])

    def test_rechecks_after_obtaining_writer_lock(self):
        a = self.capture()
        profiles = [performer(1, 'Canonical')]
        stash = self.stash(profiles)
        request = {'catalog_id': a, 'performer_id': '1'}
        report, _, _ = review.review_link(self.reader, stash, request)
        stash.clear_performer_cache = lambda: profiles[0].update(name='Changed while waiting')
        with self.assertRaisesRegex(ValueError, 'out of date'):
            review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
        self.assertEqual(stash.writes, [])

    def test_dry_run_direction_and_identity_setting_block_apply_only(self):
        a = self.capture()
        for setting in ({'dry_mode': True}, {'sync_direction': 'import'}, {'sync_performer_catalogs': False}):
            stash = self.stash([performer(1, 'Canonical')], setting)
            request = {'catalog_id': a, 'performer_id': '1'}
            report, _, _ = review.review_link(self.reader, stash, request)
            self.assertTrue(report['blocked_reason'])
            with patch('scrape_catalog.store.Store', side_effect=AssertionError('Writer opened')):
                with self.assertRaises(ValueError):
                    review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
            self.assertEqual(stash.writes, [])

    def test_failed_copy_can_be_previewed_and_retried(self):
        a = self.capture()
        b = self.capture('reddit', 't2_20', 'elsewhere', 'other.jpg')
        stash = self.stash([performer(1, 'Canonical', urls=['https://reddit.com/user/elsewhere'])])
        request = {'catalog_id': a, 'performer_id': '1'}
        report, _, _ = review.review_link(self.reader, stash, request)
        with patch('scrape_catalog.store.Store.link', side_effect=RuntimeError('Interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'Interrupted'):
                review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
        self.assertEqual(stash.values['performer_account_links'], {'twitter:id:10': '1'})
        self.assertNotEqual(self.store.resolve(a), self.store.resolve(b))
        report, _, _ = review.review_link(self.reader, stash, request)
        review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
        self.assertEqual(self.store.resolve(a), self.store.resolve(b))

    def test_invalid_or_changed_catalog_performer_and_operation_are_rejected(self):
        a = self.capture()
        stash = self.stash([performer(1, 'Canonical')])
        for request in ({}, {'catalog_id': a, 'performer_id': '99'}, {'catalog_id': 'missing', 'performer_id': '1'}):
            with self.assertRaises(ValueError):
                review.review_link(self.reader, stash, request)
        with self.assertRaises(ValueError):
            review.dispatch(self.reader, stash, 'apply_link', 'query', {})
        with self.assertRaises(ValueError):
            review.dispatch(self.reader, stash, 'sync_performer_links', 'mutation', {})
        with self.assertRaisesRegex(ValueError, 'Preview'):
            review.apply_link(self.reader, stash, {'catalog_id': a, 'performer_id': '1'})

    def test_graphql_client_prohibits_writes_from_query_operations(self):
        stash = StashInterface({'args': {'mode': 'operation', 'operation_type': 'query'}, 'server_connection': {'PluginDir': '.'}})
        with patch('requests.post', side_effect=AssertionError('Network request')):
            with self.assertRaisesRegex(RuntimeError, 'mutations are disabled'):
                stash.gql_savePerformerLinks({'twitter:id:10': '1'})


if __name__ == '__main__':
    unittest.main()
