"""Exact performer matching and explicit, auditable creator account links.

Catalog-owned UUIDs and account associations live in the shared registry. Source
catalogs, routes and media stay separate. Import and preview paths use Reader.
"""
from collections import defaultdict
from contextlib import closing
import json
import re
import unicodedata

import log
import catalogAccountAliases as account_aliases

PROFILES = 'catalog_metadata_performers'
BINDINGS = 'catalog_metadata_accounts'


def name_key(value):
    return unicodedata.normalize('NFC', value.strip()).casefold()


def names(profile):
    return {name_key(value) for value in [profile.get('name', ''), *profile.get('alias_list', [])]
            if isinstance(value, str) and value.strip()}


def profile_ref(url):
    from scrape_catalog.profiles import profile_ref as resolve_profile
    return resolve_profile(url)


def profile_refs(url):
    from scrape_catalog.profiles import profile_refs as resolve_profiles
    return resolve_profiles(url)


def namespace(settings):
    value = settings.get('performer_link_namespace', 'stash').strip()
    if not value:
        raise ValueError('Performer link namespace must not be blank')
    return value


def registry_state(reader):
    from scrape_catalog.identities import read_state
    return read_state(reader.registry)


def saved_links(reader, settings, state=None, accounts=None):
    from scrape_catalog.identities import binding_ids, resolve
    state = registry_state(reader) if state is None else state
    if state['migrated']:
        ns = namespace(settings)
        profiles = {}
        for row in state['bindings']:
            if row['namespace'] == ns:
                identity_id = resolve(row['identity_id'], state)
                profiles[row['performer_id']] = {
                    'profile': merged_profile(row['profile'], [state['identities'][identity_id]['profile']]),
                    'redirect': row['redirect_to'], 'identity_id': identity_id}
        bindings = {}
        for key, row in state['accounts'].items():
            if row['identity_id']:
                ids = binding_ids(state, ns, row['identity_id'])
                if len(ids) == 1:
                    bindings[key] = next(iter(ids))
        return profiles, bindings
    tables = {r[0] for r in reader.registry.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    profiles, bindings = {}, {}
    if PROFILES in tables:
        for row in reader.registry.execute(f'SELECT * FROM {PROFILES} WHERE namespace=?', (namespace(settings),)):
            profiles[row['performer_id']] = {'profile': json.loads(row['profile_json']), 'redirect': row['redirect_to']}
    if BINDINGS in tables:
        bindings = {r['account_key']: r['performer_id'] for r in reader.registry.execute(
            f'SELECT * FROM {BINDINGS} WHERE namespace=?', (namespace(settings),))}
    if accounts is not None:
        bindings = {account_aliases.canonical_key(accounts, key): pid for key, pid in bindings.items()}
    return profiles, bindings


def resolve_id(pid, profiles, redirects=None):
    seen = set()
    while pid:
        if pid in seen:
            raise ValueError('Catalog performer redirect cycle')
        seen.add(pid)
        target = (redirects or {}).get(pid) or profiles.get(pid, {}).get('redirect')
        if not target:
            return pid
        pid = target
    return None


def file_accounts(reader, path):
    rel = reader.relpath(path)
    result = set()
    for db in reader.catalogs(rel):
        result.update(row[0] for row in db.execute('''SELECT DISTINCT p.account_key
            FROM files f JOIN appearances a USING(asset_id) JOIN posts p USING(post_key)
            WHERE f.relpath=? AND p.account_key IS NOT NULL''', (rel,)))
    return result


def match_performer(name, performers, reader, path, settings):
    """Return an ID and candidates. Multiple matches never select the first row."""
    live = {str(p['id']): p for p in performers}
    candidates = {pid for pid, p in live.items() if name_key(name) in names(p)}
    keys = file_accounts(reader, path)
    catalog_ids = [db.execute("SELECT value FROM catalog_info WHERE key='id'").fetchone()[0]
                   for db in reader.catalogs(reader.relpath(path))]
    accounts = catalog_accounts(reader, keys, catalog_ids)
    state = account_aliases.project_state(registry_state(reader), accounts)
    profiles, bindings = saved_links(reader, settings, state=state, accounts=accounts)
    linked = {resolve_id(bindings.get(key), profiles)
              for key in {account_aliases.canonical_key(accounts, key) for key in keys}}
    linked.discard(None)
    # Historical names from a merge only apply to explicitly linked accounts.
    for pid, record in profiles.items():
        target = resolve_id(pid, profiles)
        if target in linked and target in live and name_key(name) in names(record['profile']):
            candidates.add(target)
    linked_matches = candidates & linked
    selected = next(iter(linked_matches)) if len(linked_matches) == 1 else None
    if selected is None and len(candidates) == 1:
        selected = next(iter(candidates))
    return selected, [live[pid] for pid in sorted(candidates)]


def catalog_accounts(reader, account_keys=None, catalog_ids=(), state=None):
    """Read all accounts, or locate selected accounts through registry routes.

    Catalog IDs from the review list are location hints for legacy imports that
    lack an owner route. They never establish account ownership: the requested
    key must exist in the catalog. Redirects keep old joined catalogs readable.
    """
    selected = None if account_keys is None else set(account_keys)
    if selected is not None and not selected:
        return {}
    if selected is None:
        catalogs = list(reader.registry.execute("SELECT * FROM catalogs WHERE kind='creator' AND redirect_to IS NULL ORDER BY id"))
    else:
        ids = set(catalog_ids)
        for key in selected:
            ids.update(row[0] for row in reader.registry.execute(
                'SELECT catalog_id FROM routes WHERE route=? UNION SELECT id FROM catalogs WHERE owner_key=?',
                ('owner:creator:' + key, 'creator:' + key)))
        resolved = {}
        for cid in sorted(ids):
            seen = set()
            while cid:
                if not isinstance(cid, str) or not re.fullmatch(r'c_[a-f0-9]{32}', cid):
                    raise ValueError('Invalid creator catalog identifier')
                if cid in seen:
                    raise ValueError('Catalog redirect cycle')
                seen.add(cid)
                catalog = reader.registry.execute('SELECT * FROM catalogs WHERE id=?', (cid,)).fetchone()
                if not catalog or catalog['kind'] != 'creator':
                    break
                if not catalog['redirect_to']:
                    resolved[cid] = catalog
                    break
                cid = catalog['redirect_to']
        catalogs = [resolved[cid] for cid in sorted(resolved)]
    result = {}
    profile_urls = defaultdict(list)
    has_urls = reader.registry.execute("SELECT 1 FROM sqlite_master WHERE name='account_profile_urls'").fetchone()
    if has_urls:
        if selected is None:
            for row in reader.registry.execute('SELECT account_key,url FROM account_profile_urls ORDER BY url'):
                profile_urls[row['account_key']].append(row['url'])
    directories = defaultdict(set)
    for route in reader.registry.execute("SELECT route,catalog_id FROM routes WHERE route LIKE 'directory:%'"):
        suffix = ':' + route['catalog_id']
        if route['route'].endswith(suffix):
            directories[route['catalog_id']].add(route['route'][len('directory:'):-len(suffix)])
    for catalog in catalogs:
        cid = catalog['id']
        if not re.fullmatch(r'c_[a-f0-9]{32}', cid):
            raise ValueError('Invalid creator catalog identifier')
        with closing(reader._open(reader.root / 'catalogs' / (cid + '.sqlite3'))) as db:
            source_accounts = [dict(row) for row in db.execute('SELECT * FROM accounts ORDER BY account_key')]
            # Inventory-only source folders have a registry owner but no posts
            # (and therefore no accounts row). Keep that provisional owner
            # reviewable without fabricating post authors or writing on read.
            if not source_accounts and catalog['owner_key'].startswith('creator:'):
                key = catalog['owner_key'][len('creator:'):]
                separator = ':id:' if ':id:' in key else ':handle:'
                platform, found, value = key.partition(separator)
                if found and platform and value:
                    source_accounts.append({'account_key': key, 'platform': platform,
                                            'source_id': value if separator == ':id:' else None,
                                            'identity_basis': 'catalog-owner', 'created_at': catalog['created_at']})
            for row in source_accounts:
                key = row['account_key']
                if key in result:
                    raise ValueError(f'Account {key} belongs to multiple active creator catalogs')
                handles = [r[0] for r in db.execute('SELECT handle FROM handles WHERE account_key=? ORDER BY handle', (key,))]
                if row['identity_basis'] == 'catalog-owner' and ':handle:' in key:
                    handles = [key.partition(':handle:')[2]]
                if selected is not None and has_urls:
                    profile_urls[key] = [r[0] for r in reader.registry.execute(
                        'SELECT url FROM account_profile_urls WHERE account_key=? ORDER BY url', (key,))]
                result[key] = {**row, 'catalog_id': cid, 'catalog_label': catalog['label'],
                               'directories': sorted(directories[cid]), 'profile_urls': profile_urls[key], 'handles': handles}
            # Preserve a reviewed inventory-only Reddit owner after the first
            # source-ID capture. Its old owner route is still a valid locator.
            owner = catalog['owner_key'].removeprefix('creator:')
            owner_name = owner.removeprefix('reddit:handle:')
            known_owner = any(row['platform'] == 'reddit' and row['source_id']
                              and owner_name.casefold() in {h.casefold() for h in result[row['account_key']]['handles']}
                              for row in source_accounts)
            if owner.startswith('reddit:handle:') and owner not in result and known_owner:
                result[owner] = {'account_key': owner, 'platform': 'reddit', 'source_id': None,
                                 'identity_basis': 'catalog-owner', 'catalog_id': cid, 'catalog_label': catalog['label'],
                                 'directories': sorted(directories[cid]), 'profile_urls': profile_urls[owner],
                                 'handles': [owner.removeprefix('reddit:handle:')]}
    state = registry_state(reader) if state is None else state
    legacy = []
    if not state['migrated'] and reader.registry.execute("SELECT 1 FROM sqlite_master WHERE name=?", (BINDINGS,)).fetchone():
        legacy = list(reader.registry.execute('SELECT * FROM ' + BINDINGS))
    result = account_aliases.group_accounts(result, state, legacy)
    return {key: row for key, row in result.items()
            if selected is None or selected.intersection(account_aliases.account_keys(row))}


def merged_profile(current, previous):
    ret = dict(current)
    aliases, urls = set(current.get('alias_list', [])), set(current.get('urls', []))
    for profile in previous:
        aliases.update([profile.get('name', ''), *profile.get('alias_list', [])])
        urls.update(profile.get('urls', []))
    ret['alias_list'] = sorted(value for value in aliases if value and name_key(value) != name_key(ret['name']))
    ret['urls'] = sorted(urls)
    return ret


def plan_links(reader, performers, settings, merge=None, focus=None, accounts=None):
    """Pure plan: profile URLs or registry associations establish ownership."""
    from scrape_catalog.identities import resolve, binding_ids
    namespace(settings)
    accounts = catalog_accounts(reader) if accounts is None else accounts
    state = account_aliases.project_state(registry_state(reader), accounts)
    profiles, bindings = saved_links(reader, settings, state=state, accounts=accounts)
    suppressed = {key for key, value in state['accounts'].items() if not value['identity_id']}
    reviewed = {key for key, value in state['accounts'].items() if value['source'] in ('review', 'migration')}
    live = {str(p['id']): p for p in performers}
    redirects = {}
    previous = []
    if merge:
        destination = str(merge['destination']['id'])
        previous = [merge['previous_destination'], *merge['sources']]
        redirects = {str(p['id']): destination for p in merge['sources']}
        destination = resolve_id(destination, profiles)
        focus = {destination}
    else:
        focus = set(focus) if focus is not None else set(live)
    histories = defaultdict(list)
    for pid, record in profiles.items():
        histories[resolve_id(pid, profiles, redirects)].append(record['profile'])
    for profile in previous:
        histories[resolve_id(str(profile['id']), profiles, redirects)].append(profile)
    combined = {pid: merged_profile(profile, histories[pid]) for pid, profile in live.items()}
    references = defaultdict(set)
    handles = defaultdict(set)
    for key, account in accounts.items():
        if account['source_id']:
            references[(account['platform'], 'id', str(account['source_id']))].add(key)
        for url in account['profile_urls']:
            from scrape_catalog.profiles import canonical_url
            references[('url', 'profile', canonical_url(url))].add(key)
        for handle in account['handles']:
            references[(account['platform'], 'handle', name_key(handle))].add(key)
            handles[name_key(handle)].add(key)
    owners = defaultdict(set)
    conflicts = list({tuple(account['alias_conflict']['accounts']): account['alias_conflict']
                      for account in accounts.values() if account.get('alias_conflict')}.values())
    alias_conflicts = {key for key, account in accounts.items() if account.get('alias_conflict')}
    if merge and not focus <= live.keys():
        conflicts.append({'performer_ids': sorted(focus - live.keys()),
                          'reason': 'Merge destination changed during sync; identity history is retained. Run sync again.'})
    for key, pid in bindings.items():
        if key in accounts:
            owners[key].add(resolve_id(pid, profiles, redirects))
    for key, association in state['accounts'].items():
        if key in accounts and association['identity_id']:
            ids = binding_ids(state, namespace(settings), association['identity_id'])
            if len(ids) > 1:
                owners[key].update(resolve_id(pid, profiles, redirects) for pid in ids)
    for pid, profile in combined.items():
        for url in profile.get('urls', []):
            keys = set().union(*(references.get(ref, set()) for ref in profile_refs(url)))
            if len(keys) == 1:
                key = next(iter(keys))
                if key not in suppressed | reviewed:
                    owners[key].add(pid)
            elif len(keys) > 1 and pid in focus:
                unresolved = keys - bindings.keys() - suppressed - reviewed
                if unresolved:
                    conflicts.append({'performer_id': pid, 'url': url, 'accounts': sorted(unresolved),
                                      'reason': 'Handle refers to multiple account IDs; choose an association in Catalog review'})
    groups = defaultdict(list)
    for key, account in accounts.items():
        if key in suppressed or key in alias_conflicts:
            continue
        choices = owners[key]
        if not choices:
            continue
        if len(choices) != 1 or not choices <= live.keys():
            if choices & focus or key in bindings:
                conflicts.append({'catalog_id': account['catalog_id'], 'accounts': [key], 'performer_ids': sorted(choices),
                                  'performers': [{'id': pid, 'name': live.get(pid, {}).get('name'),
                                                  'disambiguation': live.get(pid, {}).get('disambiguation')}
                                                 for pid in sorted(choices)],
                                  'reason': 'Conflicting or missing performers; this account needs an explicit association'})
            continue
        pid = next(iter(choices))
        if pid in focus:
            groups[pid].append(key)
    links = []
    for pid, keys in sorted(groups.items()):
        cids = sorted({accounts[key]['catalog_id'] for key in keys})
        identity_id = profiles.get(pid, {}).get('identity_id')
        existing_ids = {resolve(state['accounts'][key]['identity_id'], state) for key in keys
                        if key in state['accounts'] and state['accounts'][key]['identity_id']}
        if not identity_id and existing_ids:
            if len(existing_ids) != 1:
                conflicts.append({'performer_id': pid, 'accounts': sorted(keys),
                                  'reason': 'Accounts already belong to different catalog performers. Review the individual associations.'})
                continue
            identity_id = next(iter(existing_ids))
        # Account handles are historical identity names only within this
        # explicit association, never global Stash aliases or uploader tags.
        combined[pid] = merged_profile(combined[pid], [{'alias_list': [
            handle for key in keys for handle in accounts[key]['handles']]}])
        links.append({'performer_id': pid, 'name': live[pid]['name'], 'accounts': sorted(keys),
                      'catalogs': cids, 'identity_id': identity_id})
    candidates = []
    for pid in sorted(focus & live.keys()):
        possible = set().union(*(handles[value] for value in names(combined[pid])))
        for key in sorted(possible):
            account = accounts[key]
            if not owners[key] and key not in suppressed | alias_conflicts and key not in state['accounts']:
                candidates.append({'performer_id': pid, 'name': live[pid]['name'], 'account_key': key,
                                   'catalog_id': account['catalog_id'], 'handles': account['handles']})
    return {'links': links, 'conflicts': conflicts, 'name_only_candidates': candidates,
            'account_keys': {key: account_aliases.account_keys(account) for key, account in accounts.items()},
            'profiles': {pid: combined[pid] for pid in focus & live.keys()}, 'redirects': redirects,
            'history': {str(p['id']): merged_profile(p, [profiles.get(str(p['id']), {}).get('profile', {})])
                        for p in previous}}


def apply_plan(store, plan, settings):
    """One atomic registry transaction; no source catalog copies or redirects."""
    from scrape_catalog.identities import transaction
    ns = namespace(settings)
    with transaction(store) as registry:
        initial = registry.state()
        current = {row['performer_id'] for row in initial['bindings'] if row['namespace'] == ns}
        linked = {link['performer_id']: link for link in plan['links']}
        # If a Stash merge destination has no catalog UUID yet, keep a source's
        # existing UUID instead of replacing a known person with a fresh one.
        for source, target in plan['redirects'].items():
            source_binding = next((row for row in initial['bindings'] if row['namespace'] == ns and row['performer_id'] == source), None)
            if source_binding and target not in current:
                profile = plan['profiles'].get(target) or plan['history'].get(target)
                registry.ensure_binding(ns, target, profile, identity_id=source_binding['identity_id'])
                current.add(target)
        for pid, profile in plan['history'].items():
            registry.ensure_binding(ns, pid, profile, historical=True)
        for pid, profile in plan['profiles'].items():
            preferred = linked.get(pid, {}).get('identity_id')
            if pid not in current and preferred:
                registry.bind_existing(ns, pid, preferred, profile)
            elif pid in current or pid in linked or pid in plan['redirects'].values():
                registry.ensure_binding(ns, pid, profile)
        for source, target in plan['redirects'].items():
            registry.redirect_binding(ns, source, target)
        for link in plan['links']:
            identity_id = registry.ensure_binding(ns, link['performer_id'], plan['profiles'][link['performer_id']])
            link['identity_id'] = identity_id
            for key in link['accounts']:
                keys = plan.get('account_keys', {}).get(key, [key])
                existing = [store.registry.execute('SELECT * FROM performer_account_associations WHERE account_key=?', (k,)).fetchone() for k in keys]
                if any(row and row['source'] in ('review', 'migration') for row in existing):
                    continue
                for member in keys:
                    registry.associate(member, identity_id, 'sync', f"Stash profile association {ns}:{link['performer_id']}")


def sync_links(reader, stash, settings, hook=None, preview=False):
    """No Stash mutations. Preview/dry run never opens a Store or creates tables."""
    performers = stash.gql_allPerformers()
    merge = (hook or {}).get('input') if (hook or {}).get('type') == 'Performer.Merge.Post' else None
    focus = {str(hook['id'])} if hook else None
    if preview or settings.get('dry_mode', False):
        plan = plan_links(reader, performers, settings, merge, focus)
    else:
        from scrape_catalog.reader import Reader
        from scrape_catalog.store import Store
        with Store(reader.root, reader.media_root) as store, store.lock():
            # Recheck sync controls and registry associations after waiting for
            # the writer lock, including decisions made in Catalog review.
            settings = stash.gql_pluginSettings()
            if settings.get('sync_direction', 'both') not in ('both', 'export') or not settings.get('sync_performer_catalogs', True):
                return {'links': [], 'conflicts': [], 'name_only_candidates': []}
            with Reader(reader.root, reader.media_root) as fresh:
                plan = plan_links(fresh, performers, settings, merge, focus)
            if not settings.get('dry_mode', False):
                apply_plan(store, plan, settings)
    report = {key: value for key, value in plan.items() if key not in ('profiles', 'redirects', 'history', 'account_keys')}
    log.LogInfo(('Preview performer catalog links: ' if preview or settings.get('dry_mode', False) else 'Synchronized performer catalog links: ') + json.dumps(report))
    return report
