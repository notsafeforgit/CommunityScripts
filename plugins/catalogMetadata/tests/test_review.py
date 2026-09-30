import copy
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_plugin
import catalogReview as review
import catalogPerformers
import test_performers
from test_performers import performer
from scrape_catalog.identities import read_state, transaction, Identities
from scrape_catalog.store import Store
from stashInterface import StashInterface


class ReviewTests(unittest.TestCase):
    setUp = test_plugin.CatalogPluginTests.setUp
    capture = test_performers.PerformerIdentityTests.capture
    hashes = test_performers.PerformerIdentityTests.hashes

    def stash(self, profiles, settings=None):
        values = copy.deepcopy(settings or {})
        writes = []
        def update(*args):
            writes.append(args)
            self.fail('Catalog review must not mutate Stash entities')
        return SimpleNamespace(gql_allPerformers=lambda: copy.deepcopy(profiles),
                               gql_performersByIDs=lambda ids: copy.deepcopy([p for p in profiles if str(p['id']) in ids]),
                               gql_pluginSettings=lambda: copy.deepcopy(values),
                               gql_updateTitle=update, clear_performer_cache=lambda: None,
                               values=values, writes=writes)

    def apply(self, stash, **choice):
        report, _ = review.review_link(self.reader, stash, choice)
        return review.apply_link(self.reader, stash, {**choice, 'review_token': report['review_token']})

    def test_list_and_preview_never_open_writer_or_save_settings(self):
        self.capture()
        self.capture('reddit', 't2_20', 'account', 'other.jpg')
        stash = self.stash([performer(1, 'account'), performer(2, 'Other', ['account'])])
        before = self.hashes()
        with patch('scrape_catalog.store.Store', side_effect=AssertionError('Writer opened')):
            report = review.dispatch(self.reader, stash, 'list_reviews', 'query', {})
            self.assertEqual(report['counts'], {'candidate': 2})
            self.assertEqual(report['accounts'][0]['candidate_ids'], ['1', '2'])
            self.assertEqual(report['accounts'][0]['evidence'][0]['kind'], 'name_only')
            proposal = review.dispatch(self.reader, stash, 'review_link', 'query', {'account_key': 'twitter:id:10', 'performer_id': '2'})
            self.assertTrue(proposal['creates_identity'])
            self.assertEqual(proposal['account']['account_key'], 'twitter:id:10')
        self.assertEqual(self.hashes(), before)
        self.assertEqual(stash.writes, [])

    def test_inventory_only_creator_folder_is_reviewable_without_inventing_posts(self):
        path = self.media / 'elizabethtran626, instagram' / 'image.jpg'
        path.parent.mkdir()
        path.write_bytes(b'inventoried media')
        cid = self.store.inventory_file('elizabethtran626, instagram/image.jpg')
        stash = self.stash([performer(721, 'Elizabeth Tran', urls=['https://www.instagram.com/elizabethtran626'])])
        report = review.list_reviews(self.reader, stash)
        row = next(row for row in report['accounts'] if row['catalog_id'] == cid)
        self.assertEqual(row['account_key'], 'instagram:handle:elizabethtran626')
        self.assertEqual(row['identity_basis'], 'catalog-owner')
        self.assertEqual(row['performer_id'], '721')
        self.apply(stash, account_key=row['account_key'], performer_id='721')
        self.assertEqual(self.store.db(cid).execute('SELECT count(*) FROM posts').fetchone()[0], 0)
        self.assertEqual(self.store.db(cid).execute('SELECT count(*) FROM accounts').fetchone()[0], 0)

    def test_conflicts_show_profile_evidence_and_duplicate_name_disambiguation(self):
        self.capture()
        stash = self.stash([performer(1, 'Same', urls=['https://x.com/account'], disambiguation='One'),
                            performer(2, 'Same', urls=['https://twitter.com/account'], disambiguation='Two')])
        report = review.list_reviews(self.reader, stash)
        self.assertEqual(report['counts'], {'conflict': 1})
        self.assertEqual(report['accounts'][0]['candidate_ids'], ['1', '2'])
        self.assertEqual(len(report['accounts'][0]['evidence']), 2)
        self.assertEqual(report['performers'][1]['disambiguation'], 'Two')

    def test_reviewed_reused_handle_stops_blocking_only_the_resolved_account(self):
        self.capture()
        self.capture('twitter', '20', 'account', 'other.mp4')
        stash = self.stash([performer(1, 'Canonical', urls=['https://x.com/account'])])
        self.apply(stash, account_key='twitter:id:10', performer_id='1')
        rows = {row['account_key']: row for row in review.list_reviews(self.reader, stash)['accounts']}
        self.assertEqual(rows['twitter:id:10']['status'], 'linked')
        self.assertEqual(rows['twitter:id:20']['status'], 'conflict')

    def test_background_sync_reloads_registry_choices_before_planning(self):
        self.capture()
        profiles = [performer(1, 'One', urls=['https://x.com/account']), performer(2, 'Two')]
        stash = self.stash(profiles)
        self.assertEqual(catalogPerformers.plan_links(self.reader, profiles, {})['links'][0]['performer_id'], '1')
        original_lock, reviewed = Store.lock, False
        @contextmanager
        def lock_after_review(store):
            nonlocal reviewed
            if not reviewed:
                reviewed = True
                with transaction(self.store) as registry:
                    uid = registry.ensure_binding('stash', '2', profiles[1])
                    registry.associate('twitter:id:10', uid, 'review', 'Reviewed while sync waited')
            with original_lock(store):
                yield
        with patch.object(Store, 'lock', lock_after_review):
            report = catalogPerformers.sync_links(self.reader, stash, {})
        self.assertEqual(report['links'][0]['performer_id'], '2')

    def test_background_sync_rechecks_current_sync_controls(self):
        self.capture()
        stash = self.stash([performer(1, 'One', urls=['https://x.com/account'])], {'sync_direction': 'import'})
        report = catalogPerformers.sync_links(self.reader, stash, {'sync_direction': 'both'})
        self.assertEqual(report['links'], [])
        self.assertEqual(read_state(self.store.registry)['accounts'], {})

    def test_legacy_json_is_not_review_evidence(self):
        self.capture()
        stash = self.stash([performer(1, 'One')], {'performer_account_links': {'twitter:id:10': '1'}})
        row = review.list_reviews(self.reader, stash)['accounts'][0]
        self.assertEqual(row['status'], 'unmatched')
        self.assertEqual(row['evidence'], [])
        self.assertEqual(row['candidate_ids'], [])

    def test_apply_changes_only_the_reviewed_account_with_no_catalog_copies(self):
        a = self.capture()
        b = self.capture('reddit', 't2_20', 'elsewhere', 'other.jpg')
        stash = self.stash([performer(1, 'Canonical', urls=['https://reddit.com/user/elsewhere'])])
        with patch('scrape_catalog.store.Store.link', side_effect=AssertionError('Physical merge')):
            result = self.apply(stash, account_key='twitter:id:10', performer_id='1')
        self.assertEqual(result['linked_accounts'], 1)
        self.assertEqual(set(read_state(self.store.registry)['accounts']), {'twitter:id:10'})
        self.assertEqual(self.store.resolve(a), a)
        self.assertEqual(self.store.resolve(b), b)
        self.assertEqual(review.list_reviews(self.reader, stash)['counts'], {'proposed': 1, 'linked': 1})
        self.assertEqual(stash.writes, [])

    def test_individual_accounts_inside_a_previously_joined_catalog_can_be_reassigned(self):
        a = self.capture()
        b = self.capture('reddit', 't2_20', 'elsewhere', 'other.jpg')
        self.store.link(b, a, 'Prior explicit catalog merge')
        stash = self.stash([performer(1, 'One'), performer(2, 'Two')])
        first = self.apply(stash, account_key='twitter:id:10', performer_id='1')
        second = self.apply(stash, account_key='reddit:id:t2_20', performer_id='2')
        self.assertNotEqual(first['identity_id'], second['identity_id'])
        self.assertEqual(len(review.list_reviews(self.reader, stash)['accounts']), 2)
        self.assertEqual(self.store.resolve(b), a)  # Existing evidence stays readable.

    def test_reviewed_unlink_persists_across_profile_url_sync(self):
        self.capture()
        profiles = [performer(1, 'One', urls=['https://x.com/account'])]
        stash = self.stash(profiles)
        uid = self.apply(stash, account_key='twitter:id:10', performer_id='1')['identity_id']
        self.apply(stash, account_key='twitter:id:10', action='unlink')
        catalogPerformers.sync_links(self.reader, stash, stash.values)
        state = read_state(self.store.registry)
        self.assertIsNone(state['accounts']['twitter:id:10']['identity_id'])
        self.assertIn(uid, state['identities'])
        self.assertEqual(review.list_reviews(self.reader, stash)['counts'], {'unlinked': 1})
        self.apply(stash, account_key='twitter:id:10', performer_id='1')
        self.assertEqual(read_state(self.store.registry)['accounts']['twitter:id:10']['identity_id'], uid)

    def test_reassigning_one_account_preserves_other_accounts_and_both_uuids(self):
        self.capture()
        self.capture('reddit', 't2_20', 'elsewhere', 'other.jpg')
        stash = self.stash([performer(1, 'One'), performer(2, 'Two')])
        first = self.apply(stash, account_key='twitter:id:10', performer_id='1')['identity_id']
        self.apply(stash, account_key='reddit:id:t2_20', identity_id=first)
        second = self.apply(stash, account_key='twitter:id:10', performer_id='2')['identity_id']
        state = read_state(self.store.registry)
        self.assertNotEqual(first, second)
        self.assertEqual(state['accounts']['reddit:id:t2_20']['identity_id'], first)
        self.assertEqual(state['accounts']['twitter:id:10']['identity_id'], second)
        self.assertTrue(all(not r['redirect_to'] for r in state['identities'].values()))

    def test_catalog_uuid_can_exist_without_stash_and_bind_to_a_rebuilt_library(self):
        self.capture()
        with transaction(self.store) as registry:
            uid = registry.create({'name': 'Catalog performer', 'alias_list': ['Old name']})
        stash = self.stash([performer(12, 'Current name')], {'performer_link_namespace': 'rebuilt'})
        self.apply(stash, account_key='twitter:id:10', identity_id=uid)
        self.apply(stash, action='bind', identity_id=uid, performer_id='12')
        view = review.list_reviews(self.reader, stash)['identities'][0]
        self.assertEqual(view['id'], uid)
        self.assertEqual(view['name'], 'Current name')
        self.assertEqual(view['stash_bindings'][0]['performer_id'], '12')
        self.assertEqual(view['accounts'][0]['account_key'], 'twitter:id:10')

    def test_bind_rejects_conflicting_current_performers_and_reused_ids(self):
        self.capture()
        stash = self.stash([performer(1, 'One'), performer(2, 'Two')])
        uid = self.apply(stash, account_key='twitter:id:10', performer_id='1')['identity_id']
        with self.assertRaisesRegex(ValueError, 'already bound'):
            review.review_link(self.reader, stash, {'action': 'bind', 'identity_id': uid, 'performer_id': '2'})

    def test_stale_performers_settings_accounts_or_associations_require_new_preview(self):
        self.capture()
        profiles = [performer(1, 'Canonical')]
        stash = self.stash(profiles)
        request = {'account_key': 'twitter:id:10', 'performer_id': '1'}
        for change in (lambda: profiles[0].update(name='Changed'),
                       lambda: stash.values.update(performer_link_namespace='other'),
                       lambda: self.capture('twitter', '10', 'renamed', 'new.mp4'),
                       lambda: self.apply(stash, account_key='twitter:id:10', action='unlink')):
            report, _ = review.review_link(self.reader, stash, request)
            change()
            before = self.hashes()
            with patch('scrape_catalog.store.Store', side_effect=AssertionError('Writer opened')):
                with self.assertRaisesRegex(ValueError, 'out of date'):
                    review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
            self.assertEqual(self.hashes(), before)

    def test_unrelated_scrapes_performers_settings_and_associations_do_not_stale_preview(self):
        self.capture()
        profiles = [performer(1, 'One'), performer(2, 'Two')]
        stash = self.stash(profiles)
        request = {'account_key': 'twitter:id:10', 'performer_id': '1'}
        report, _ = review.review_link(self.reader, stash, request)
        self.capture('twitter', '20', 'other', 'other.mp4')
        profiles[1]['name'] = 'Unrelated edit'
        stash.values['scene_import_mappings'] = {'title': '.catalog.title'}
        self.apply(stash, account_key='twitter:id:20', performer_id='2')
        result = review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
        self.assertEqual(result['performer_id'], '1')

    def test_preview_and_apply_never_scan_unrelated_catalogs_or_performers(self):
        selected = self.capture()
        unrelated = self.capture('twitter', '20', 'other', 'other.mp4')
        stash = self.stash([performer(1, 'One'), performer(2, 'Two')])
        opened = []
        from scrape_catalog.reader import Reader
        original = Reader._open
        def checked(path):
            opened.append(path.name)
            self.assertNotEqual(path.name, unrelated + '.sqlite3')
            return original(path)
        with patch.object(Reader, '_open', side_effect=checked), \
                patch.object(stash, 'gql_allPerformers', side_effect=AssertionError('Full performer scan')), \
                patch.object(stash, 'gql_performersByIDs', wraps=stash.gql_performersByIDs) as lookup:
            result = self.apply(stash, account_key='twitter:id:10', performer_id='1')
        self.assertEqual(opened.count(selected + '.sqlite3'), 4)  # Preview, two validations, changed card.
        self.assertTrue(all(call.args[0] == {'1'} for call in lookup.call_args_list))
        self.assertEqual([a['account_key'] for a in result['updates']['accounts']], ['twitter:id:10'])
        self.assertEqual(len(result['updates']['identities']), 1)
        self.assertEqual(result['updates']['identities'][0]['stash_bindings'][0]['available'], True)

    def test_legacy_account_location_is_verified_and_follows_catalog_redirects(self):
        selected = self.capture()
        target = self.capture('reddit', 't2_20', 'other', 'other.jpg')
        # Legacy imports can insert an account into an existing catalog whose
        # provisional owner has a different key and no exact owner route.
        self.store.registry.execute('DELETE FROM routes WHERE route=?', ('owner:creator:twitter:id:10',))
        self.store.registry.execute('UPDATE catalogs SET owner_key=? WHERE id=?', ('creator:twitter:handle:account', selected))
        self.store.registry.commit()
        self.store.link(selected, target, 'Historical catalog join')
        stash = self.stash([performer(1, 'One')])
        report, _ = review.review_link(self.reader, stash, {'account_key': 'twitter:id:10', 'performer_id': '1'})
        self.assertEqual(report['account']['catalog_id'], target)
        result = self.apply(stash, account_key='twitter:id:10', performer_id='1', catalog_ids=[selected])
        self.assertEqual(result['updates']['accounts'][0]['catalog_id'], target)
        with self.assertRaises(ValueError):
            review.review_link(self.reader, stash, {'account_key': 'unknown', 'performer_id': '1', 'catalog_ids': [target]})
        with self.assertRaisesRegex(ValueError, 'Invalid creator catalog identifier'):
            review.review_link(self.reader, stash, {'account_key': 'twitter:id:10', 'performer_id': '1', 'catalog_ids': ['../../secret']})

    def test_reassignment_updates_both_identity_cards_and_binding_updates_related_accounts(self):
        self.capture()
        self.capture('reddit', 't2_20', 'other', 'other.jpg')
        profiles = [performer(1, 'One'), performer(2, 'Two')]
        stash = self.stash(profiles)
        original = self.apply(stash, account_key='twitter:id:10', performer_id='1')['identity_id']
        self.apply(stash, account_key='reddit:id:t2_20', identity_id=original)
        result = self.apply(stash, account_key='twitter:id:10', performer_id='2')
        self.assertEqual({i['id'] for i in result['updates']['identities']}, {original, result['identity_id']})
        for identity in result['updates']['identities']:
            self.assertEqual(len(identity['accounts']), 1)
        profiles[:] = [performer(3, 'Rebuilt')]
        bound = self.apply(stash, action='bind', identity_id=original, performer_id='3')
        self.assertEqual(bound['updates']['accounts'][0]['performer_id'], '3')
        self.assertEqual(bound['updates']['accounts'][0]['binding_conflicts'], [])
        self.assertEqual(bound['updates']['accounts'][0]['account_key'], 'reddit:id:t2_20')

    def test_failure_building_changed_cards_rolls_back_association(self):
        self.capture()
        stash = self.stash([performer(1, 'One')])
        with patch.object(review, 'affected_cards', side_effect=RuntimeError('Cannot refresh account')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot refresh account'):
                self.apply(stash, account_key='twitter:id:10', performer_id='1')
        self.assertEqual(read_state(self.store.registry)['identities'], {})

    def test_rechecks_after_obtaining_writer_lock(self):
        self.capture()
        profiles = [performer(1, 'Canonical')]
        stash = self.stash(profiles)
        request = {'account_key': 'twitter:id:10', 'performer_id': '1'}
        report, _ = review.review_link(self.reader, stash, request)
        stash.clear_performer_cache = lambda: profiles[0].update(name='Changed while waiting')
        with self.assertRaisesRegex(ValueError, 'out of date'):
            review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
        self.assertEqual(read_state(self.store.registry)['accounts'], {})

    def test_rechecks_selected_association_changed_while_waiting_for_writer(self):
        self.capture()
        stash = self.stash([performer(1, 'One'), performer(2, 'Two')])
        request = {'account_key': 'twitter:id:10', 'performer_id': '1'}
        report, _ = review.review_link(self.reader, stash, request)
        original_lock, changed = Store.lock, False
        @contextmanager
        def lock_after_change(store):
            nonlocal changed
            if not changed:
                changed = True
                with transaction(self.store) as registry:
                    uid = registry.ensure_binding('stash', '2', performer(2, 'Two'))
                    registry.associate('twitter:id:10', uid, 'review', 'Reviewed while waiting')
            with original_lock(store):
                yield
        with patch.object(Store, 'lock', lock_after_change):
            with self.assertRaisesRegex(ValueError, 'out of date'):
                review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
        state = read_state(self.store.registry)
        uid = state['accounts']['twitter:id:10']['identity_id']
        self.assertEqual(state['identities'][uid]['profile']['name'], 'Two')

    def test_dry_run_direction_and_identity_setting_block_apply_only(self):
        self.capture()
        for setting in ({'dry_mode': True}, {'sync_direction': 'import'}, {'sync_performer_catalogs': False}):
            stash = self.stash([performer(1, 'Canonical')], setting)
            request = {'account_key': 'twitter:id:10', 'performer_id': '1'}
            report, _ = review.review_link(self.reader, stash, request)
            self.assertTrue(report['blocked_reason'])
            with patch('scrape_catalog.store.Store', side_effect=AssertionError('Writer opened')):
                with self.assertRaises(ValueError):
                    review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})

    def test_failed_apply_is_atomic_and_can_be_retried_with_same_preview(self):
        self.capture()
        stash = self.stash([performer(1, 'Canonical')])
        request = {'account_key': 'twitter:id:10', 'performer_id': '1'}
        report, _ = review.review_link(self.reader, stash, request)
        with patch.object(Identities, 'associate', side_effect=RuntimeError('Interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'Interrupted'):
                review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
        self.assertEqual(read_state(self.store.registry)['identities'], {})
        result = review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})
        self.assertEqual(result['linked_accounts'], 1)

    def test_invalid_inputs_operation_kind_and_legacy_whole_catalog_choice_are_rejected(self):
        cid = self.capture()
        stash = self.stash([performer(1, 'Canonical')])
        for request in ({}, {'catalog_id': cid, 'performer_id': '1'},
                        {'account_key': 'missing', 'performer_id': '1'},
                        {'account_key': 'twitter:id:10', 'performer_id': '99'},
                        {'account_key': 'twitter:id:10', 'performer_id': '1', 'action': 'unlink'}):
            with self.assertRaises(ValueError):
                review.review_link(self.reader, stash, request)
        with self.assertRaises(ValueError):
            review.dispatch(self.reader, stash, 'apply_link', 'query', {})
        with self.assertRaises(ValueError):
            review.dispatch(self.reader, stash, 'unknown', 'mutation', {})

    def test_graphql_client_prohibits_writes_from_query_operations(self):
        stash = StashInterface({'args': {'mode': 'operation', 'operation_type': 'query'}, 'server_connection': {'PluginDir': '.'}})
        with patch('requests.post', side_effect=AssertionError('Network request')):
            with self.assertRaisesRegex(RuntimeError, 'mutations are disabled'):
                stash.gql_updateTitle('scene', '1', 'Preview must not write')

    def test_targeted_performer_lookup_filters_ids_and_rechecks_missing_after_cache_clear(self):
        stash = StashInterface({'args': {'mode': 'operation', 'operation_type': 'query'}, 'server_connection': {'PluginDir': '.'}})
        response = {'p0': {'id': '1', 'name': 'One', 'aliases': [{'alias': 'Old'}], 'urls': []}, 'p1': None}
        with patch.object(stash, '_StashInterface__gql_call', side_effect=lambda *args: copy.deepcopy(response)) as query:
            self.assertEqual(stash.gql_performersByIDs([]), [])
            query.assert_not_called()
            self.assertEqual(stash.gql_performersByIDs({'1', '2'})[0]['alias_list'], ['Old'])
            self.assertEqual(query.call_args.args[1], {'p0': '1', 'p1': '2'})
            self.assertIn('p0: findPerformer(id: $p0)', query.call_args.args[0])
            self.assertIn('p1: findPerformer(id: $p1)', query.call_args.args[0])
            self.assertEqual(stash.gql_performersByIDs({'2'}), [])
            self.assertEqual(query.call_count, 1)
            stash.clear_performer_cache()
            stash.gql_performersByIDs({'1', '2'})
            self.assertEqual(query.call_count, 2)


if __name__ == '__main__':
    unittest.main()
