"""Adapters loaded after catalogReader configures the shared library path."""


def account_keys(account):
    from scrape_catalog.accounts import account_keys as shared_keys
    return shared_keys(account)


def canonical_key(accounts, key):
    from scrape_catalog.accounts import canonical_key as shared_key
    return shared_key(accounts, key)


def project_state(state, accounts):
    from scrape_catalog.accounts import project_state as shared_state
    return shared_state(state, accounts)
