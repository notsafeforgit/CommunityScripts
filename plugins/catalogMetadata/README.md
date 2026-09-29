# Catalog Metadata

Populate Stash scenes and images from the per-creator SQLite databases maintained
by `scrape-catalog`. This separate plugin, ID `catalogMetadata`, derives from
`nfoFileParser` 1.6.4. The original NFO plugin retains its own code, configuration,
marker tag, and behavior.

## Installation

Install this directory as a Stash plugin. Python 3 and `requests` are required,
along with the existing `scrape-catalog` package and databases. The reader is an
explicit dependency; this plugin does not import anything from `nfoFileParser`.

Set these environment variables for the Stash process:

```sh
SCRAPE_CATALOG_CODE=/opt/scrape-catalog
SCRAPE_CATALOG_ROOT=/media/scrape_metadata
SCRAPE_MEDIA_ROOT=/media/porn
```

The paths must exist inside the Stash runtime. Mount the catalog code read-only.
The reader uses read-only SQLite connections, but live WAL databases may require
access to their shared-memory files. Preserve the catalog mount and permissions.
Missing configuration or unreadable databases cause a visible error.

Enable **Catalog Metadata**. When replacing the legacy integration, disable
**nfoFileParser** in Stash and replace its ID with `catalogMetadata` in any custom
hook order. This avoids two plugins updating the same item. The original plugin
can still be enabled independently wherever its NFO behavior is wanted.

## Metadata and refreshes

Scene and image creation hooks apply captured post data, stored English
translations, URLs, and manual catalog edits. Handcrafted NFO fields and folder
defaults remain available from the exact XML preserved in the databases. No NFO
files need to exist. Physical sidecars are still accepted when present for legacy
compatibility. Reads do not change the catalog or invoke online translation.

To refresh an existing scene or image, apply the **`_CATALOG_RELOAD`** tag and run
**Refresh tagged items from catalog**. Explicit refreshes include organized
items; ordinary creation hooks honor `skip_organized`. A successful update removes
the marker. The old `_NFO_RELOAD` tag belongs to the original NFO plugin.

Use `scrape-catalog edit` to make durable metadata edits and then run the tagged
refresh. Edits made directly in Stash are not written back into the catalog.

`config.py` contains this plugin's independent field blacklist, matching rules,
entity-creation switches, and organized-item policy (`set_organized_catalog`).
Its defaults preserve the existing installation's choices. Preserved XML fields
are interpreted with the same rules as the previous catalog integration.

Optional filename rules are read from the nearest `catalogMetadata.json` in the
media directory or its parents. Existing `nfoFileParser.json` rules are used if no
new rule file exists. Set `legacy_regex_fallback = False` to turn that migration
compatibility off. Neither plugin writes these files.

Example filename rule:

```json
{
  "regex": "(?P<title>.+)\\.mp4$",
  "scope": "filename"
}
```

The hooks skip media outside `SCRAPE_MEDIA_ROOT`. This plugin does not delete
media, prune posts, or change backup retention.

## Validation

With the catalog code available, run the offline integration tests:

```sh
SCRAPE_CATALOG_CODE=/path/to/scrape-catalog python3 -m unittest discover -s tests -v
```

Tests use temporary media/catalogs and mock Stash. They do not change the live
database or contact external services.

The implementation inherits the repository's AGPL-3.0-only license and credits
the `nfoFileParser` contributors for the Stash mapping and XML/filename parsers.
