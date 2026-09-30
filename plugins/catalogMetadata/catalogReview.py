"""Read-only identity reviews and explicit, narrowly scoped apply operations."""
from collections import defaultdict
import hashlib
import json

import catalogPerformers as identities


def blocked_reason(settings):
    if settings.get('dry_mode', False):
        return 'Dry run is enabled. Turn it off in Catalog Metadata settings to apply links.'
    if settings.get('sync_direction', 'both') not in ('both', 'export'):
        return 'Stash-to-catalog sync is disabled. Choose Both directions or Stash to catalog in settings.'
    if not settings.get('sync_performer_catalogs', True):
        return 'Performer identity synchronization is disabled in Catalog Metadata settings.'
    return None


def snapshot(reader, stash):
    settings = stash.gql_pluginSettings()
    performers = stash.gql_allPerformers()
    accounts = identities.catalog_accounts(reader)
    return settings, performers, accounts


def account_view(account):
    return {key: account[key] for key in ('account_key', 'platform', 'source_id', 'handles', 'catalog_id')}


def list_reviews(reader, stash):
    settings, performers, accounts = snapshot(reader, stash)
    plan = identities.plan_links(reader, performers, settings, accounts=accounts)
    profiles, bindings = identities.saved_links(reader, settings)
    explicit = identities.explicit_links(settings)
    labels = {r['id']: r['label'] for r in reader.registry.execute('SELECT id, label FROM catalogs WHERE redirect_to IS NULL')}
    rows = {}
    by_ref = defaultdict(set)
    evidence = defaultdict(list)
    for key, account in accounts.items():
        cid = account['catalog_id']
        rows.setdefault(cid, {'catalog_id': cid, 'label': labels[cid], 'accounts': [], 'conflicts': [],
                              'candidate_ids': set(), 'status': 'unmatched', 'performer_id': None})
        rows[cid]['accounts'].append({**account_view(account), 'evidence': evidence[key]})
        if account['source_id']:
            by_ref[(account['platform'], 'id', str(account['source_id']))].add(key)
        for handle in account['handles']:
            by_ref[(account['platform'], 'handle', identities.name_key(handle))].add(key)
        for kind, mapping in (('saved_link', bindings), ('explicit_link', explicit)):
            if key in mapping:
                pid = identities.resolve_id(mapping[key], profiles)
                evidence[key].append({'kind': kind, 'performer_id': pid})
                rows[cid]['candidate_ids'].add(pid)
    for performer in performers:
        pid = str(performer['id'])
        for url in performer.get('urls', []):
            keys = by_ref.get(identities.profile_ref(url), set())
            for key in keys:
                evidence[key].append({'kind': 'profile_url', 'performer_id': pid, 'url': url, 'ambiguous': len(keys) > 1})
                rows[accounts[key]['catalog_id']]['candidate_ids'].add(pid)
    for candidate in plan['name_only_candidates']:
        key = candidate['account_key']
        evidence[key].append({'kind': 'name_only', 'performer_id': candidate['performer_id']})
        row = rows[candidate['catalog_id']]
        row['candidate_ids'].add(candidate['performer_id'])
        row['status'] = 'candidate'
    for link in plan['links']:
        for cid in link['catalogs']:
            row = rows[cid]
            row['performer_id'] = link['performer_id']
            row['candidate_ids'].add(link['performer_id'])
            complete = len(link['catalogs']) == 1 and row['label'] == link['name'] and all(
                identities.resolve_id(bindings.get(a['account_key']), profiles) == link['performer_id'] for a in row['accounts'])
            row['status'] = 'linked' if complete else 'proposed'
    unattached = []
    for conflict in plan['conflicts']:
        keys = conflict.get('accounts', []) + ([conflict['account_key']] if conflict.get('account_key') else [])
        cids = {accounts[key]['catalog_id'] for key in keys if key in accounts}
        if conflict.get('catalog_id') in rows:
            cids.add(conflict['catalog_id'])
        if not cids:
            unattached.append(conflict)
        for cid in cids:
            rows[cid]['status'] = 'conflict'
            rows[cid]['conflicts'].append(conflict)
            rows[cid]['candidate_ids'].update(conflict.get('performer_ids', []))
            if conflict.get('performer_id'):
                rows[cid]['candidate_ids'].add(conflict['performer_id'])
    counts = defaultdict(int)
    for row in rows.values():
        row['candidate_ids'] = sorted(row['candidate_ids'])
        counts[row['status']] += 1
    return {'catalogs': list(rows.values()), 'performers': performers, 'counts': dict(counts),
            'unattached_conflicts': unattached, 'blocked_reason': blocked_reason(settings)}


def review_link(reader, stash, request):
    """Choosing a performer applies to every account in the selected creator catalog."""
    cid, pid = request.get('catalog_id'), request.get('performer_id')
    if not isinstance(cid, str) or not isinstance(pid, str) or not pid.isdecimal():
        raise ValueError('Choose a creator catalog and a Stash performer')
    settings, performers, accounts = snapshot(reader, stash)
    chosen = sorted(key for key, account in accounts.items() if account['catalog_id'] == cid)
    if not chosen:
        raise ValueError('This creator catalog changed or no longer exists. Refresh the review list.')
    live = {str(p['id']): p for p in performers}
    if pid not in live:
        raise ValueError('This performer no longer exists. Refresh the review list.')
    # A saved redirect must never silently transfer a newly reused Stash ID.
    profiles, bindings = identities.saved_links(reader, settings)
    if identities.resolve_id(pid, profiles) != pid:
        raise ValueError('This performer ID has a catalog merge redirect. Check the library namespace before linking it.')
    overrides = {key: pid for key in chosen}
    proposed_settings = {**settings, 'performer_account_links': {**identities.explicit_links(settings), **overrides}}
    plan = identities.plan_links(reader, performers, proposed_settings, focus={pid}, accounts=accounts)
    link = next((item for item in plan['links'] if item['performer_id'] == pid and set(chosen) <= set(item['accounts'])), None)
    if not link:
        raise ValueError('The selected catalog still has conflicting account links. Refresh and review its accounts.')
    # Only the chosen identity is writable. Other proposals/conflicts remain untouched.
    plan['links'] = [link]
    plan['profiles'] = {pid: plan['profiles'][pid]}
    labels = {r['id']: r['label'] for r in reader.registry.execute('SELECT id, label FROM catalogs WHERE redirect_to IS NULL')}
    catalogs = [{'id': value, 'label': labels[value], 'accounts': [account_view(accounts[key]) for key in link['accounts']
                                                               if accounts[key]['catalog_id'] == value]} for value in link['catalogs']]
    material = {'settings': settings, 'performers': sorted(performers, key=lambda p: str(p['id'])),
                'accounts': accounts, 'profiles': profiles, 'bindings': bindings, 'labels': labels,
                'choice': overrides, 'link': link}
    token = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    report = {'review_token': token, 'catalog_id': cid, 'performer': live[pid], 'catalogs': catalogs,
              'target_catalog': link['target_catalog'], 'explicit_links': overrides,
              'blocked_reason': blocked_reason(settings), 'other_conflicts': plan['conflicts']}
    return report, plan, proposed_settings


def apply_link(reader, stash, request):
    if not isinstance(request.get('review_token'), str) or len(request['review_token']) != 64:
        raise ValueError('Preview the link before applying it')
    # Reject a stale/blocked request without even opening a writer.
    report, _, _ = review_link(reader, stash, request)
    if report['blocked_reason']:
        raise ValueError(report['blocked_reason'])
    if report['review_token'] != request['review_token']:
        raise ValueError('The review is out of date. Preview again before applying.')
    from scrape_catalog.reader import Reader
    from scrape_catalog.store import Store
    with Store(reader.root, reader.media_root) as store, store.lock():
        # Serialize catalog changes and re-read settings, performers and bindings
        # after acquiring the writer lock. Stash itself has no cross-store CAS.
        stash.clear_performer_cache()
        with Reader(reader.root, reader.media_root) as fresh:
            report, plan, settings = review_link(fresh, stash, request)
        if report['blocked_reason']:
            raise ValueError(report['blocked_reason'])
        if report['review_token'] != request['review_token']:
            raise ValueError('The review is out of date. Preview again before applying.')
        # Persist the explicit choice before retryable catalog copies, preserving
        # unrelated settings/links. A failed copy can be previewed and retried.
        stash.gql_savePerformerLinks(settings['performer_account_links'])
        identities.apply_plan(store, plan, settings)
    return {'performer_id': report['performer']['id'], 'catalog_id': report['target_catalog'],
            'linked_accounts': sum(len(catalog['accounts']) for catalog in report['catalogs']),
            'merged_catalogs': len(report['catalogs']) - 1}


def dispatch(reader, stash, name, kind, request):
    operations = {'list_reviews': ('query', list_reviews), 'review_link': ('query', review_link),
                  'apply_link': ('mutation', apply_link)}
    if name not in operations or operations[name][0] != kind:
        raise ValueError('Unsupported catalog review operation')
    if not isinstance(request, dict):
        raise ValueError('Operation input must be an object')
    if name == 'list_reviews':
        return list_reviews(reader, stash)
    if name == 'review_link':
        return review_link(reader, stash, request)[0]
    return apply_link(reader, stash, request)
