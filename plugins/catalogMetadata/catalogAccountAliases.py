"""Confirmed Reddit username/ID aliases, without rewriting source evidence.

Reddit usernames are permanent. Other services can recycle or rename handles,
so sharing a folder or handle is not enough to combine their account keys.
"""
from collections import defaultdict
import re


def account_keys(account):
    return account.get('account_keys', [account['account_key']])


def canonical_key(accounts, key):
    if key in accounts:
        return key
    return next((canonical for canonical, account in accounts.items() if key in account_keys(account)), key)


def group_accounts(accounts, state, legacy_links=()):
    from scrape_catalog.identities import resolve
    result = {key: {**row, 'account_keys': [key]} for key, row in accounts.items()}
    source_ids = defaultdict(set)
    pairs = defaultdict(set)
    for key, row in accounts.items():
        if row['platform'] == 'reddit' and row['identity_basis'] == 'source-id' and re.fullmatch(r't2_[a-z0-9]+', row['source_id'] or ''):
            for handle in row['handles']:
                if re.fullmatch(r'[A-Za-z0-9_-]{1,32}', handle):
                    source_ids[(row['catalog_id'], handle.casefold())].add(key)
    for key, row in accounts.items():
        if row['platform'] != 'reddit' or not key.startswith('reddit:handle:'):
            continue
        handle = key.removeprefix('reddit:handle:')
        candidates = source_ids.get((row['catalog_id'], handle.casefold()), set())
        if len(candidates) != 1:
            continue
        canonical = next(iter(candidates))
        pairs[canonical].add(key)
    for canonical, aliases in pairs.items():
        members = {canonical, *aliases}
        decisions = {resolve(state['accounts'][member]['identity_id'], state)
                     for member in members if member in state['accounts']}
        historical = {(link['namespace'], link['performer_id']) for link in legacy_links if link['account_key'] in members}
        if len(decisions) > 1 or len(historical) > 1:
            # Never choose between explicit links/unlinks while browsing. Both
            # keys remain reviewable until their saved decisions agree.
            conflict = {'accounts': sorted(members),
                        'reason': 'This Reddit username and ID have different saved associations. Review these account keys so their decisions agree.'}
            for member in members:
                result[member]['alias_conflict'] = conflict
            continue
        target = result[canonical]
        target['account_keys'] = sorted(members)
        for key in sorted(aliases):
            row = accounts[key]
            by_name = {handle.casefold(): handle for handle in reversed(target['handles'])}
            for handle in row['handles']:
                by_name.setdefault(handle.casefold(), handle)
            target['handles'] = sorted(by_name.values(), key=str.casefold)
            for field in ('profile_urls', 'directories'):
                target[field] = sorted(set(target[field]) | set(row[field]))
            del result[key]
    return result


def project_state(state, accounts):
    """Read existing alias associations as one decision; original rows stay intact."""
    groups = defaultdict(list)
    keys = {member: key for key, account in accounts.items() for member in account_keys(account)}
    for key, association in state['accounts'].items():
        groups[keys.get(key, key)].append(association)
    projected = {}
    for key, values in groups.items():
        # group_accounts only combines keys with compatible decisions. Retain
        # every input row in the preview token so changing either stales it.
        selected = max(values, key=lambda row: (row['source'] in ('review', 'migration'), row['updated_at']))
        projected[key] = {**selected, 'account_key': key}
        if len(values) > 1 or selected['account_key'] != key:
            projected[key]['alias_associations'] = sorted(values, key=lambda row: row['account_key'])
    return {**state, 'accounts': projected}
