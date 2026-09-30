"""Local catalog adapter. Fail visibly if a configured catalog cannot be read."""
import atexit
import os
import sys

_reader = None


def get_reader():
    global _reader
    root = os.environ.get('SCRAPE_CATALOG_ROOT')
    if not root:
        raise RuntimeError('Catalog Metadata requires SCRAPE_CATALOG_ROOT and the scrape-catalog reader')
    if _reader is None:
        sys.path.insert(0, os.environ.get('SCRAPE_CATALOG_CODE', '/opt/scrape-catalog'))
        try:
            from scrape_catalog import identities, profiles, observations
        except ImportError as error:
            raise RuntimeError('Catalog Metadata 1.8 requires scrape-catalog 0.3.0 or later. Update the catalog backend.') from error
        from scrape_catalog.reader import Reader
        _reader = Reader(root, os.environ.get('SCRAPE_MEDIA_ROOT', '/media/porn'))
        atexit.register(_reader.close)
    return _reader


def mapping_context(reader, path, stash, metadata):
    """Expose source evidence separately from the resolved catalog projection."""
    rel = reader.relpath(path)
    return {
        'stash': stash,
        'catalog': metadata,
        'observations': reader.observations(path),
        'path': str(path),
        'relative_path': rel,
    }


def write_overrides(reader, path, fields):
    """Use the catalog writer's lock and append-only manual edit contract."""
    from scrape_catalog.edits import edit
    from scrape_catalog.store import Store
    with Store(reader.root, reader.media_root) as store:
        return edit(store, path, fields)
