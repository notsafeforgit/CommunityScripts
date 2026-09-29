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
        from scrape_catalog.reader import Reader
        _reader = Reader(root, os.environ.get('SCRAPE_MEDIA_ROOT', '/media/porn'))
        atexit.register(_reader.close)
    return _reader
