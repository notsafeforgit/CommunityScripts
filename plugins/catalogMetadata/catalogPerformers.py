"""Exact performer matching and explicit, auditable creator account links.

Plugin-owned tables live in the catalog registry, so catalog snapshots include
them. Raw accounts/posts keep their identities; Store.link copies their evidence
and redirects future writes. Import and preview paths only use Reader.
"""
from collections import defaultdict
from contextlib import closing
import json
import re
import unicodedata
from urllib.parse import urlsplit

import log

PROFILES = 'catalog_metadata_performers'
BINDINGS = 'catalog_metadata_accounts'


def name_key(value):
    return unicodedata.normalize('NFC', value.strip()).casefold()


def names(profile):
    return {name_key(value) for value in [profile.get('name', ''), *profile.get('alias_list', [])]
            if isinstance(value, str) and value.strip()}


def profile_ref(url):
    """Accept profile URLs only; a post URL or shared username proves nothing."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.port:
            return None
    except ValueError:
        return None
    host = re.sub(r'^(www|mobile|old|new)\.', '', host)
    path = parsed.path.rstrip('/')
    if host in ('twitter.com', 'x.com'):
        match = re.fullmatch(r'/i/user/(\d+)', path)
        if match:
            return 'twitter', 'id', match[1]
        match = re.fullmatch(r'/([A-Za-z0-9_]{1,15})', path)
        if match and match[1].lower() not in ('home', 'search', 'explore', 'settings', 'messages', 'notifications', 'intent', 'share', 'login', 'logout', 'signup', 'i'):
            return 'twitter', 'handle', match[1].lower()
    if host == 'reddit.com':
        match = re.fullmatch(r'/(?:user|u)/([A-Za-z0-9_-]{1,32})', path)
        if match:
            return 'reddit', 'handle', match[1].lower()
    return None


def namespace(settings):
    value = settings.get('performer_link_namespace', 'stash').strip()
    if not value:
        raise ValueError('Performer link namespace must not be blank')
    return value


def explicit_links(settings):
    value = settings.get('performer_account_links', {})
    if not isinstance(value, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v.isdecimal() for k, v in value.items()):
        raise ValueError('Performer account links must map catalog account keys to Stash performer ID strings')
    return value


def saved_links(reader, settings):
    tables = {r[0] for r in reader.registry.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    profiles, bindings = {}, {}
    if PROFILES in tables:
        for row in reader.registry.execute(f'SELECT * FROM {PROFILES} WHERE namespace=?', (namespace(settings),)):
            profiles[row['performer_id']] = {'profile': json.loads(row['profile_json']), 'redirect': row['redirect_to']}
    if BINDINGS in tables:
        bindings = {r['account_key']: r['performer_id'] for r in reader.registry.execute(
            f'SELECT * FROM {BINDINGS} WHERE namespace=?', (namespace(settings),))}
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
    profiles, bindings = saved_links(reader, settings)
    explicit = explicit_links(settings)
    linked = {resolve_id(explicit.get(key, bindings.get(key)), profiles)
              for key in file_accounts(reader, path)}
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


def catalog_accounts(reader):
    """Only creator catalogs may join; subreddit/collection catalogs stay separate."""
    result = {}
    for catalog in reader.registry.execute("SELECT id FROM catalogs WHERE kind='creator' AND redirect_to IS NULL ORDER BY id"):
        cid = catalog['id']
        if not re.fullmatch(r'c_[a-f0-9]{32}', cid):
            raise ValueError('Invalid creator catalog identifier')
        with closing(reader._open(reader.root / 'catalogs' / (cid + '.sqlite3'))) as db:
            for row in db.execute('SELECT * FROM accounts ORDER BY account_key'):
                key = row['account_key']
                if key in result:
                    raise ValueError(f'Account {key} belongs to multiple active creator catalogs')
                result[key] = {**dict(row), 'catalog_id': cid, 'handles': [r[0] for r in db.execute(
                    'SELECT handle FROM handles WHERE account_key=? ORDER BY handle', (key,))]}
    return result


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
    """Pure plan: profile URLs or explicit stable account keys establish ownership."""
    namespace(settings)
    explicit = explicit_links(settings)
    profiles, bindings = saved_links(reader, settings)
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
    accounts = catalog_accounts(reader) if accounts is None else accounts
    references = defaultdict(set)
    handles = defaultdict(set)
    for key, account in accounts.items():
        if account['source_id']:
            references[(account['platform'], 'id', str(account['source_id']))].add(key)
        for handle in account['handles']:
            references[(account['platform'], 'handle', name_key(handle))].add(key)
            handles[name_key(handle)].add(key)
    owners = defaultdict(set)
    conflicts = []
    if merge and not focus <= live.keys():
        conflicts.append({'performer_ids': sorted(focus - live.keys()),
                          'reason': 'Merge destination changed during sync; identity history is retained. Run sync again.'})
    for key, pid in bindings.items():
        if key in accounts:
            owners[key].add(resolve_id(pid, profiles, redirects))
    for pid, profile in combined.items():
        for url in profile.get('urls', []):
            ref = profile_ref(url)
            keys = references.get(ref, set())
            if len(keys) == 1:
                owners[next(iter(keys))].add(pid)
            elif len(keys) > 1 and pid in focus:
                unresolved = keys - explicit.keys() - bindings.keys()
                if unresolved:
                    conflicts.append({'performer_id': pid, 'url': url, 'accounts': sorted(unresolved),
                                      'reason': 'Handle refers to multiple account IDs; specify an explicit account link'})
    for key, pid in explicit.items():
        target = resolve_id(pid, profiles, redirects)
        if key not in accounts or target not in live:
            conflicts.append({'account_key': key, 'performer_id': pid, 'reason': 'Explicit link references an unknown creator account or performer'})
            continue
        owners[key] = {target}
    # A catalog is already an explicitly joined creator identity. Do not split
    # it between conflicting performers, or silently absorb someone else's link.
    catalogs = defaultdict(list)
    for key, account in accounts.items():
        catalogs[account['catalog_id']].append(key)
    groups = defaultdict(list)
    for cid, keys in catalogs.items():
        choices = set().union(*(owners[key] for key in keys))
        if not choices:
            continue
        if len(choices) != 1 or not choices <= live.keys():
            if choices & focus or any(key in explicit for key in keys):
                conflicts.append({'catalog_id': cid, 'accounts': keys, 'performer_ids': sorted(choices),
                                  'performers': [{'id': pid, 'name': live.get(pid, {}).get('name'),
                                                  'disambiguation': live.get(pid, {}).get('disambiguation')}
                                                 for pid in sorted(choices)],
                                  'reason': 'Conflicting or missing performers; no accounts in this catalog were linked'})
            continue
        pid = next(iter(choices))
        if pid in focus:
            groups[pid].extend(keys)
    links = []
    for pid, keys in sorted(groups.items()):
        cids = sorted({accounts[key]['catalog_id'] for key in keys})
        # Account handles are historical identity names only within this
        # explicit association, never global Stash aliases or uploader tags.
        combined[pid] = merged_profile(combined[pid], [{'alias_list': [
            handle for key in keys for handle in accounts[key]['handles']]}])
        links.append({'performer_id': pid, 'name': live[pid]['name'], 'accounts': sorted(keys),
                      'catalogs': cids, 'target_catalog': cids[0]})
    candidates = []
    for pid in sorted(focus & live.keys()):
        possible = set().union(*(handles[value] for value in names(combined[pid])))
        for key in sorted(possible):
            account = accounts[key]
            if not owners[key]:
                candidates.append({'performer_id': pid, 'name': live[pid]['name'], 'account_key': key,
                                   'catalog_id': account['catalog_id'], 'handles': account['handles']})
    return {'links': links, 'conflicts': conflicts, 'name_only_candidates': candidates,
            'profiles': {pid: combined[pid] for pid in focus & live.keys()}, 'redirects': redirects,
            'history': {str(p['id']): merged_profile(p, [profiles.get(str(p['id']), {}).get('profile', {})])
                        for p in previous}}


def apply_plan(store, plan, settings):
    """Caller holds Store.lock; intent is durable before retryable catalog copies."""
    ns = namespace(settings)
    store.registry.executescript(f'''
        CREATE TABLE IF NOT EXISTS {PROFILES} (
            namespace TEXT NOT NULL, performer_id TEXT NOT NULL, profile_json TEXT NOT NULL,
            redirect_to TEXT, PRIMARY KEY(namespace, performer_id));
        CREATE TABLE IF NOT EXISTS {BINDINGS} (
            namespace TEXT NOT NULL, account_key TEXT NOT NULL, performer_id TEXT NOT NULL,
            PRIMARY KEY(namespace, account_key));
    ''')
    store.registry.execute('BEGIN IMMEDIATE')
    try:
        # Retain the event even if another Stash merge invalidated our live
        # query while we waited for the catalog lock. A later sync can replay
        # the association from these profiles without the deleted Stash rows.
        for pid, profile in plan['history'].items():
            store.registry.execute(f'''INSERT INTO {PROFILES} VALUES (?,?,?,NULL)
                ON CONFLICT(namespace, performer_id) DO UPDATE SET profile_json=excluded.profile_json''',
                (ns, pid, json.dumps(profile)))
        for pid, profile in plan['profiles'].items():
            store.registry.execute(f'INSERT OR REPLACE INTO {PROFILES} VALUES (?,?,?,NULL)', (ns, pid, json.dumps(profile)))
        for source, target in plan['redirects'].items():
            store.registry.execute(f'''INSERT INTO {PROFILES} VALUES (?,?,?,?)
                ON CONFLICT(namespace, performer_id) DO UPDATE SET redirect_to=excluded.redirect_to''',
                (ns, source, '{}', target))
            store.registry.execute(f'UPDATE {BINDINGS} SET performer_id=? WHERE namespace=? AND performer_id=?', (target, ns, source))
        for link in plan['links']:
            for key in link['accounts']:
                store.registry.execute(f'INSERT OR REPLACE INTO {BINDINGS} VALUES (?,?,?)', (ns, key, link['performer_id']))
        store.registry.commit()
    except BaseException:
        store.registry.rollback()
        raise
    for link in plan['links']:
        reason = f"Stash performer {ns}:{link['performer_id']} ({link['name']}): explicit profile/account association"
        for cid in link['catalogs']:
            if cid != link['target_catalog']:
                store.link(cid, link['target_catalog'], reason)
        target = store.resolve(link['target_catalog'])
        with store.transaction(target) as db:
            db.execute("UPDATE catalog_info SET value=? WHERE key='label' AND value<>?", (link['name'], link['name']))
        store.registry.execute('UPDATE catalogs SET label=? WHERE id=? AND label<>?', (link['name'], target, link['name']))


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
            # A review may have saved a newer explicit choice while this hook
            # waited. Never overwrite it using the invocation's stale settings.
            settings = stash.gql_pluginSettings()
            if settings.get('sync_direction', 'both') not in ('both', 'export') or not settings.get('sync_performer_catalogs', True):
                return {'links': [], 'conflicts': [], 'name_only_candidates': []}
            with Reader(reader.root, reader.media_root) as fresh:
                plan = plan_links(fresh, performers, settings, merge, focus)
            if not settings.get('dry_mode', False):
                apply_plan(store, plan, settings)
    report = {key: value for key, value in plan.items() if key not in ('profiles', 'redirects', 'history')}
    log.LogInfo(('Preview performer catalog links: ' if preview or settings.get('dry_mode', False) else 'Synchronized performer catalog links: ') + json.dumps(report))
    return report
