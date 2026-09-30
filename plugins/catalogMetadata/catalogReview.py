"""Read-only account reviews and atomic catalog identity associations."""
from collections import defaultdict
import hashlib
import json

import catalogPerformers as performers_api


def blocked_reason(settings):
    if settings.get('dry_mode', False):
        return 'Dry run is enabled. Turn it off in Catalog Metadata settings to apply links.'
    if settings.get('sync_direction', 'both') not in ('both', 'export'):
        return 'Stash-to-catalog sync is disabled. Choose Both directions or Stash to catalog in settings.'
    if not settings.get('sync_performer_catalogs', True):
        return 'Performer identity synchronization is disabled in Catalog Metadata settings.'
    return None


def snapshot(reader, stash):
    return stash.gql_pluginSettings(), stash.gql_allPerformers(), performers_api.catalog_accounts(reader)


def account_view(account):
    return {key: account[key] for key in ('account_key', 'platform', 'source_id', 'identity_basis',
                                         'handles', 'catalog_id', 'catalog_label', 'directories', 'profile_urls')}


def identity_views(state, accounts, live, namespace):
    from scrape_catalog.identities import resolve
    groups = {}
    for uid, item in state['identities'].items():
        if not item['redirect_to']:
            groups[uid] = {'id': uid, **item['profile'], 'accounts': [], 'stash_bindings': [], 'merged_ids': []}
    for uid, item in state['identities'].items():
        if item['redirect_to']:
            groups[resolve(uid, state)]['merged_ids'].append(uid)
    for key, association in state['accounts'].items():
        if association['identity_id']:
            view = account_view(accounts[key]) if key in accounts else {'account_key': key, 'missing': True}
            groups[resolve(association['identity_id'], state)]['accounts'].append(view)
    for binding in state['bindings']:
        groups[resolve(binding['identity_id'], state)]['stash_bindings'].append({
            'namespace': binding['namespace'], 'performer_id': binding['performer_id'],
            'name': binding['profile'].get('name'), 'redirect_to': binding['redirect_to'],
            'available': binding['namespace'] == namespace and binding['performer_id'] in live and not binding['redirect_to']})
    return sorted(groups.values(), key=lambda item: (item.get('name', '').casefold(), item['id']))


def list_reviews(reader, stash):
    from scrape_catalog.identities import resolve, binding_ids
    settings, performers, accounts = snapshot(reader, stash)
    plan = performers_api.plan_links(reader, performers, settings, accounts=accounts)
    profiles, bindings = performers_api.saved_links(reader, settings)
    state = performers_api.registry_state(reader)
    namespace = performers_api.namespace(settings)
    live = {str(p['id']): p for p in performers}
    rows, references = {}, defaultdict(set)
    for key, account in accounts.items():
        row = rows[key] = {**account_view(account), 'label': ', '.join(account['handles']) or account['source_id'] or key,
                           'evidence': [], 'conflicts': [], 'candidate_ids': set(), 'status': 'unmatched',
                           'performer_id': None, 'identity_id': None, 'identity_name': None}
        if account['source_id']:
            references[(account['platform'], 'id', str(account['source_id']))].add(key)
        for url in account['profile_urls']:
            from scrape_catalog.profiles import canonical_url
            references[('url', 'profile', canonical_url(url))].add(key)
        for handle in account['handles']:
            references[(account['platform'], 'handle', performers_api.name_key(handle))].add(key)
        association = state['accounts'].get(key)
        if association:
            if not association['identity_id']:
                row['status'] = 'conflict' if association['source'] == 'migration_conflict' else 'unlinked'
                if row['status'] == 'conflict':
                    row['conflicts'].append({'reason': association['reason']})
            else:
                uid = resolve(association['identity_id'], state)
                row.update(identity_id=uid, identity_name=state['identities'][uid]['profile']['name'], status='linked')
                ids = binding_ids(state, namespace, uid) & live.keys()
                row['candidate_ids'].update(ids)
                if len(ids) == 1:
                    row['performer_id'] = next(iter(ids))
        if key in bindings:
            pid = performers_api.resolve_id(bindings[key], profiles)
            row['evidence'].append({'kind': 'saved_link', 'performer_id': pid})
            row['candidate_ids'].add(pid)
    for performer in performers:
        pid = str(performer['id'])
        for url in performer.get('urls', []):
            keys = set().union(*(references.get(ref, set()) for ref in performers_api.profile_refs(url)))
            for key in keys:
                rows[key]['evidence'].append({'kind': 'profile_url', 'performer_id': pid, 'url': url, 'ambiguous': len(keys) > 1})
                rows[key]['candidate_ids'].add(pid)
    for candidate in plan['name_only_candidates']:
        row = rows[candidate['account_key']]
        row['evidence'].append({'kind': 'name_only', 'performer_id': candidate['performer_id']})
        row['candidate_ids'].add(candidate['performer_id'])
        row['status'] = 'candidate'
    for link in plan['links']:
        for key in link['accounts']:
            row = rows[key]
            row['performer_id'] = link['performer_id']
            row['candidate_ids'].add(link['performer_id'])
            if not row['identity_id']:
                row['status'] = 'proposed'
    unattached = []
    for conflict in plan['conflicts']:
        keys = conflict.get('accounts', []) + ([conflict['account_key']] if conflict.get('account_key') else [])
        keys = [key for key in keys if key in rows]
        if not keys:
            unattached.append(conflict)
        for key in keys:
            rows[key]['status'] = 'conflict'
            rows[key]['conflicts'].append(conflict)
            rows[key]['candidate_ids'].update(conflict.get('performer_ids', []))
            if conflict.get('performer_id'):
                rows[key]['candidate_ids'].add(conflict['performer_id'])
    counts = defaultdict(int)
    for row in rows.values():
        row['candidate_ids'] = sorted(row['candidate_ids'])
        counts[row['status']] += 1
    return {'accounts': list(rows.values()), 'performers': performers, 'counts': dict(counts),
            'identities': identity_views(state, accounts, live, namespace), 'namespace': namespace,
            'unattached_conflicts': unattached, 'blocked_reason': blocked_reason(settings)}


def review_link(reader, stash, request):
    """Preview one account decision or a Stash binding to an existing UUID."""
    from scrape_catalog.identities import resolve, binding_ids
    settings, performers, accounts = snapshot(reader, stash)
    state = performers_api.registry_state(reader)
    profiles, _ = performers_api.saved_links(reader, settings)
    live = {str(p['id']): p for p in performers}
    namespace = performers_api.namespace(settings)
    action = request.get('action', 'link')
    key, pid, uid = request.get('account_key'), request.get('performer_id'), request.get('identity_id')
    if action not in ('link', 'unlink', 'bind'):
        raise ValueError('Choose a supported association action')
    account = None
    if action != 'bind':
        if not isinstance(key, str) or key not in accounts:
            raise ValueError('Choose an individual source account. Refresh the review list if it changed.')
        account = account_view(accounts[key])
    if action == 'unlink':
        if pid or uid:
            raise ValueError('An unlink cannot also choose a performer')
    else:
        if action == 'bind' and (not pid or not uid):
            raise ValueError('Choose a catalog performer and a Stash performer')
        if action == 'link' and bool(pid) == bool(uid):
            raise ValueError('Choose either a Stash performer or a catalog performer')
        if pid:
            if not isinstance(pid, str) or not pid.isdecimal() or pid not in live:
                raise ValueError('This Stash performer no longer exists. Refresh the review list.')
            if performers_api.resolve_id(pid, profiles) != pid:
                raise ValueError('This performer ID has a merge redirect. Check the library namespace before linking it.')
        if uid:
            if not isinstance(uid, str):
                raise ValueError('Choose a catalog performer UUID')
            uid = resolve(uid, state)
        if action == 'bind':
            existing = profiles.get(pid, {}).get('identity_id')
            if existing and existing != uid:
                raise ValueError('This Stash performer already belongs to another catalog UUID. Review its account associations or merge the performers in Stash.')
            others = (binding_ids(state, namespace, uid) & live.keys()) - {pid}
            if others:
                raise ValueError('This catalog performer is already bound to another current Stash performer in this library.')
        if pid and not uid:
            uid = profiles.get(pid, {}).get('identity_id')
    previous = state['accounts'].get(key, {}) if key else {}
    previous_id = resolve(previous.get('identity_id'), state)
    group = state['identities'].get(uid)
    choice = {'action': action, 'account_key': key, 'performer_id': pid, 'identity_id': request.get('identity_id')}
    material = {'settings': settings, 'performers': sorted(performers, key=lambda p: str(p['id'])),
                'accounts': accounts, 'state': state, 'legacy_profiles': profiles, 'choice': choice}
    token = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    return {'review_token': token, 'action': action, 'account': account, 'choice': choice,
            'performer': live.get(pid), 'identity_id': uid,
            'identity_name': group['profile']['name'] if group else (live[pid]['name'] if pid else None),
            'creates_identity': action == 'link' and bool(pid) and not uid,
            'previous_identity_id': previous_id,
            'previous_identity_name': state['identities'][previous_id]['profile']['name'] if previous_id else None,
            'associated_accounts': [account_view(accounts[k]) for k, association in state['accounts'].items()
                                    if k in accounts and uid and resolve(association['identity_id'], state) == uid and k != key],
            'blocked_reason': blocked_reason(settings)}, settings


def apply_link(reader, stash, request):
    from scrape_catalog.identities import transaction
    from scrape_catalog.reader import Reader
    from scrape_catalog.store import Store
    if not isinstance(request.get('review_token'), str) or len(request['review_token']) != 64:
        raise ValueError('Preview the association before applying it')
    report, _ = review_link(reader, stash, request)
    def check(value):
        if value['blocked_reason']:
            raise ValueError(value['blocked_reason'])
        if value['review_token'] != request['review_token']:
            raise ValueError('The review is out of date. Preview again before applying.')
    check(report)
    with Store(reader.root, reader.media_root) as store, store.lock():
        stash.clear_performer_cache()
        with Reader(reader.root, reader.media_root) as fresh:
            report, settings = review_link(fresh, stash, request)
        check(report)
        with transaction(store) as registry:
            uid = report['identity_id']
            profile = report['performer']
            ns = performers_api.namespace(settings)
            if report['action'] == 'bind':
                uid = registry.bind_existing(ns, profile['id'], uid, profile)
            elif report['action'] == 'unlink':
                registry.associate(report['account']['account_key'], None, 'review', 'Explicitly unlinked in Catalog review')
            else:
                if profile:
                    profile = performers_api.merged_profile(profile, [{'alias_list': report['account']['handles']}])
                    uid = registry.ensure_binding(ns, profile['id'], profile)
                else:
                    current = registry.state()['identities'][uid]['profile']
                    registry.update_profile(uid, performers_api.merged_profile(current, [{'alias_list': report['account']['handles']}]))
                registry.associate(report['account']['account_key'], uid, 'review', 'Explicitly linked in Catalog review')
    return {'action': report['action'], 'identity_id': uid,
            'performer_id': profile['id'] if profile else None,
            'account_key': report['account']['account_key'] if report['account'] else None,
            'linked_accounts': 1 if report['action'] == 'link' else 0}


def dispatch(reader, stash, name, kind, request):
    operations = {'list_reviews': 'query', 'review_link': 'query', 'apply_link': 'mutation'}
    if operations.get(name) != kind or name not in operations:
        raise ValueError('Unsupported catalog review operation')
    if not isinstance(request, dict):
        raise ValueError('Operation input must be an object')
    if name == 'list_reviews':
        return list_reviews(reader, stash)
    if name == 'review_link':
        return review_link(reader, stash, request)[0]
    return apply_link(reader, stash, request)
