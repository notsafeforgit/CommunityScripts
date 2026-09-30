import unittest
from unittest.mock import patch

import test_plugin
import test_review
from test_performers import performer
import catalogPerformers as performers
import catalogReview as review
from scrape_catalog.identities import Identities, read_state, transaction


HANDLE = 'reddit:handle:alice'
SOURCE = 'reddit:id:t2_20'


class RedditAliasTests(unittest.TestCase):
    setUp = test_plugin.CatalogPluginTests.setUp
    stash = test_review.ReviewTests.stash
    apply = test_review.ReviewTests.apply
    hashes = test_review.ReviewTests.hashes

    def capture(self, filename, source_id=None, handle='Alice', platform='reddit'):
        (self.path.parent / filename).write_bytes(filename.encode())
        if platform == 'reddit':
            data = {'category': platform, 'id': filename, 'author': handle, 'title': 'Caption'}
            if source_id:
                data['author_fullname'] = source_id
        else:
            data = {'category': platform, 'tweet_id': filename, 'author': {'name': handle}, 'content': 'Caption'}
            if source_id:
                data['author']['id'] = source_id
        return self.store.capture(data, 'Manual/' + filename)

    def pair(self):
        first = self.capture('old.jpg', handle='alice')
        self.assertEqual(self.capture('new.jpg', 't2_20'), first)
        return first

    def save(self, key, profile=None, source='review'):
        with transaction(self.store) as registry:
            uid = registry.ensure_binding('stash', profile['id'], profile) if profile else None
            registry.associate(key, uid, source, 'Existing account decision')
        return uid

    def test_one_read_only_card_and_profile_match_for_confirmed_pair(self):
        cid = self.pair()
        stash = self.stash([performer(1, 'Alice', urls=['https://reddit.com/user/ALICE'])])
        before = self.hashes()
        with patch('scrape_catalog.store.Store', side_effect=AssertionError('Writer opened')):
            result = review.list_reviews(self.reader, stash)
            row, = result['accounts']
            self.assertEqual(row['account_key'], SOURCE)
            self.assertEqual(row['handles'], ['Alice'])
            self.assertEqual(set(row['account_keys']), {HANDLE, SOURCE})
            self.assertEqual(row['status'], 'proposed')
            self.assertEqual(row['conflicts'], [])
            self.assertFalse(row['evidence'][0]['ambiguous'])
            preview, _ = review.review_link(self.reader, stash, {'account_key': HANDLE, 'performer_id': '1', 'catalog_ids': [cid]})
            self.assertEqual(preview['account'], review.account_view(performers.catalog_accounts(self.reader)[SOURCE]))
            self.assertEqual(preview['choice']['account_key'], SOURCE)
        self.assertEqual(before, self.hashes())
        self.assertEqual(self.store.db(cid).execute('SELECT count(*) FROM accounts').fetchone()[0], 2)

    def test_saved_handle_link_disambiguates_id_and_legacy_file_imports(self):
        self.pair()
        people = [performer(1, 'One', ['Sam']), performer(2, 'Two', ['Sam'])]
        uid = self.save(HANDLE, people[1])
        before = self.hashes()
        for filename in ('old.jpg', 'new.jpg'):
            selected, _ = performers.match_performer('Sam', people, self.reader, self.path.parent / filename, {})
            self.assertEqual(selected, '2')
        result = review.list_reviews(self.reader, self.stash(people))
        self.assertEqual(result['counts'], {'linked': 1})
        self.assertEqual(result['accounts'][0]['identity_id'], uid)
        self.assertEqual(len(result['identities'][0]['accounts']), 1)
        self.assertEqual(before, self.hashes())
        self.assertEqual(set(read_state(self.store.registry)['accounts']), {HANDLE})

    def test_reviewed_link_unlink_and_sync_cover_both_keys_as_one_account(self):
        self.pair()
        people = [performer(1, 'Alice', urls=['https://reddit.com/user/alice'])]
        stash = self.stash(people)
        result = self.apply(stash, account_key=HANDLE, performer_id='1')
        self.assertEqual(result['linked_accounts'], 1)
        self.assertEqual(len(result['updates']['accounts']), 1)
        state = read_state(self.store.registry)
        self.assertEqual({item['identity_id'] for item in state['accounts'].values()}, {result['identity_id']})
        self.assertEqual(set(state['accounts']), {HANDLE, SOURCE})
        self.apply(stash, account_key=SOURCE, action='unlink')
        performers.sync_links(self.reader, stash, {})
        self.assertEqual(review.list_reviews(self.reader, stash)['counts'], {'unlinked': 1})
        self.assertTrue(all(item['identity_id'] is None for item in read_state(self.store.registry)['accounts'].values()))

    def test_background_sync_links_pair_once(self):
        self.pair()
        stash = self.stash([performer(1, 'Alice', urls=['https://reddit.com/user/alice'])])
        report = performers.sync_links(self.reader, stash, {})
        self.assertEqual(report['links'][0]['accounts'], [SOURCE])
        self.assertEqual(set(read_state(self.store.registry)['accounts']), {HANDLE, SOURCE})
        self.assertEqual(len(review.list_reviews(self.reader, stash)['identities'][0]['accounts']), 1)

    def test_failure_writing_second_alias_rolls_back_both_associations(self):
        self.pair()
        stash = self.stash([performer(1, 'Alice')])
        original, calls = Identities.associate, []
        def interrupted(registry, key, *args):
            calls.append(key)
            if len(calls) == 2:
                raise RuntimeError('Interrupted second association')
            return original(registry, key, *args)
        with patch.object(Identities, 'associate', interrupted):
            with self.assertRaisesRegex(RuntimeError, 'Interrupted second association'):
                self.apply(stash, account_key=SOURCE, performer_id='1')
        self.assertEqual(set(calls), {HANDLE, SOURCE})
        state = read_state(self.store.registry)
        self.assertEqual(state['accounts'], {})
        self.assertEqual(state['identities'], {})

    def test_existing_handle_unlink_suppresses_matching_new_source_id(self):
        self.capture('old.jpg')
        self.save(HANDLE)
        self.capture('new.jpg', 't2_20')
        stash = self.stash([performer(1, 'Alice', urls=['https://reddit.com/user/alice'])])
        self.assertEqual(review.list_reviews(self.reader, stash)['counts'], {'unlinked': 1})
        self.assertEqual(performers.sync_links(self.reader, stash, {})['links'], [])
        self.assertEqual(set(read_state(self.store.registry)['accounts']), {HANDLE})

    def test_conflicting_saved_associations_remain_reviewable_until_they_agree(self):
        self.pair()
        people = [performer(1, 'One'), performer(2, 'Two')]
        first, second = self.save(HANDLE, people[0]), self.save(SOURCE, people[1])
        before = self.hashes()
        stash = self.stash(people)
        result = review.list_reviews(self.reader, stash)
        self.assertEqual(result['counts'], {'conflict': 2})
        self.assertTrue(all('different saved associations' in row['conflicts'][0]['reason'] for row in result['accounts']))
        self.assertEqual(performers.plan_links(self.reader, people, {})['links'], [])
        self.assertEqual(self.hashes(), before)
        changed = self.apply(stash, account_key=HANDLE, performer_id='2')
        self.assertEqual(len(changed['updates']['accounts']), 1)
        self.assertEqual(set(changed['updates']['accounts'][0]['account_keys']), {HANDLE, SOURCE})
        cards = {item['id']: item for item in changed['updates']['identities']}
        self.assertEqual(cards[first]['accounts'], [])
        self.assertEqual(len(cards[second]['accounts']), 1)
        self.assertEqual(review.list_reviews(self.reader, stash)['counts'], {'linked': 1})

    def test_link_and_explicit_unlink_disagreement_is_not_hidden(self):
        self.pair()
        self.save(HANDLE)
        self.save(SOURCE, performer(1, 'Alice'))
        stash = self.stash([performer(1, 'Alice', urls=['https://reddit.com/user/alice'])])
        self.assertEqual(review.list_reviews(self.reader, stash)['counts'], {'conflict': 2})
        self.assertEqual(performers.plan_links(self.reader, stash.gql_allPerformers(), {})['links'], [])

    def test_multiple_performers_still_conflict_after_source_key_deduplication(self):
        self.pair()
        people = [performer(1, 'One', urls=['https://reddit.com/user/alice']),
                  performer(2, 'Two', urls=['https://old.reddit.com/user/Alice'])]
        result = review.list_reviews(self.reader, self.stash(people))
        self.assertEqual(result['counts'], {'conflict': 1})
        self.assertEqual(result['accounts'][0]['candidate_ids'], ['1', '2'])

    def test_multiple_source_ids_mismatched_authors_and_mutable_handles_are_not_combined(self):
        first = self.pair()
        second = self.capture('third.jpg', 't2_30')
        self.store.link(second, first, 'Historical explicit catalog join')
        people = [performer(1, 'Alice', urls=['https://reddit.com/user/alice'])]
        self.assertEqual(review.list_reviews(self.reader, self.stash(people))['counts'], {'conflict': 3})
        bob = self.capture('bob-old.jpg', handle='Bob')
        other = self.capture('charlie.jpg', 't2_40', 'Charlie')
        self.store.link(other, bob, 'Historical explicit catalog join')
        accounts = performers.catalog_accounts(self.reader)
        self.assertIn('reddit:handle:bob', accounts)
        self.assertIn('reddit:id:t2_40', accounts)
        self.capture('twitter-old.jpg', handle='Alice', platform='twitter')
        self.capture('twitter-new.jpg', '123', handle='Alice', platform='twitter')
        accounts = performers.catalog_accounts(self.reader)
        self.assertIn('twitter:handle:alice', accounts)
        self.assertIn('twitter:id:123', accounts)

    def test_new_id_capture_invalidates_handle_only_preview(self):
        self.capture('old.jpg')
        stash = self.stash([performer(1, 'Alice')])
        request = {'account_key': HANDLE, 'performer_id': '1'}
        report, _ = review.review_link(self.reader, stash, request)
        self.capture('new.jpg', 't2_20')
        with patch('scrape_catalog.store.Store', side_effect=AssertionError('Writer opened')):
            with self.assertRaisesRegex(ValueError, 'out of date'):
                review.apply_link(self.reader, stash, {**request, 'review_token': report['review_token']})

    def test_inventory_owner_link_survives_first_source_id_capture(self):
        path = self.media / 'Alice, reddit' / 'image.jpg'
        path.parent.mkdir()
        path.write_bytes(b'Inventory')
        cid = self.store.inventory_file('Alice, reddit/image.jpg')
        uid = self.save(HANDLE, performer(1, 'Alice'))
        self.assertEqual(self.store.capture({'category': 'reddit', 'id': 'post1', 'author': 'Alice', 'author_fullname': 't2_20'},
                                           'Alice, reddit/image.jpg'), cid)
        result = review.list_reviews(self.reader, self.stash([performer(1, 'Alice')]))
        self.assertEqual(result['counts'], {'linked': 1})
        self.assertEqual(result['accounts'][0]['identity_id'], uid)
        self.assertEqual(set(result['accounts'][0]['account_keys']), {HANDLE, SOURCE})
        self.assertEqual(self.store.db(cid).execute('SELECT count(*) FROM accounts').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
