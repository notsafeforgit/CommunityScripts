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

Version 1.1 requires the Stash fork's plugin settings and jq APIs
(`pluginSettings`, `pluginEvaluateMappings`, `updatePluginSettings`). Upgrade
Stash before installing this version: older Stash builds reject the extended
manifest. There is no `ui.entry`; native v3 settings and backend hooks provide
this plugin's interface. No Python jq package or jq executable is needed at runtime.

Enable **Catalog Metadata**. When replacing the legacy integration, disable
**nfoFileParser** in Stash and replace its ID with `catalogMetadata` in any custom
hook order. This avoids two plugins updating the same item. The original plugin
can still be enabled independently wherever its NFO behavior is wanted.

## Metadata and refreshes

Scene and image creation hooks apply captured post data, stored English
translations, URLs, and manual catalog edits. Handcrafted NFO fields and folder
defaults remain available from the exact XML preserved in the databases. No NFO
files need to exist. Physical sidecars are still accepted when present for legacy
compatibility. Imports do not change the catalog or invoke online translation.

To refresh an existing scene or image, apply the **`_CATALOG_RELOAD`** tag and run
**Refresh tagged items from catalog**. Explicit refreshes include organized
items; ordinary creation hooks honor `skip_organized`. A successful update removes
the marker. The old `_NFO_RELOAD` tag belongs to the original NFO plugin.

Use `scrape-catalog edit` to make durable metadata edits and then run the tagged
refresh. With **Sync direction → Both directions** (the default), successful
Stash scene/image edits are also written to the catalog's append-only manual
metadata layer. Exports do not change captured evidence, call translation APIs,
or write sidecars. The catalog directory must be writable for exports; catalog
code remains mounted read-only. Creation/import and export can be enabled
independently with the direction setting.

Exports operate on the item's primary media path, matching the import behavior.
Default expressions export only fields named by the update hook. Imports carry
a `clientMutationId` marker so their notifications never become manual edits.
Updates descended from scene/image creation hooks are also skipped, so Title
From Filename initialization cannot become a manual catalog override. Unchanged
values do not append duplicate edits. Failures are logged as plugin
errors after the successful Stash operation; hooks do not veto or roll it back.

Expand **Settings → Plugins → Catalog Metadata** to configure sync direction,
dry run, import exclusions, entity creation, organized policy, name tolerance,
refresh tag and the four mapping settings. Save changes to persist them in Stash.
Declared settings use manifest defaults and saved values; `config.py` remains
the fallback for preferences that are not exposed. Existing declared defaults
match the previous installation. Preserved XML is interpreted as before.

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


## Field mappings

Each mapping setting is a JSON object whose keys are target fields and whose
values are jq expressions. **Scene import**, **Image import**, **Scene export**,
and **Image export** are separate settings. Use the sample-data preview in v3
before saving expressions. Its input is the complete context object below.

Import mappings override the standard importer; an empty object keeps its
existing behavior. Target any supported `SceneUpdateInput` or `ImageUpdateInput`
field except `id` and `clientMutationId`. Relation targets such as `studio_id`
and `performer_ids` expect Stash IDs. Standard imports still resolve names using
the matching/creation settings. Explicit mappings take precedence over the
standard import blacklist.

Example import overrides:

```json
{
  "title": ".catalog.title // empty",
  "details": ".observations[-1].payload.content // empty",
  "director": ".catalog.director // empty",
  "custom_fields": "{partial: {catalog_author: .observations[-1].payload.author.name}}",
  "organized": "false"
}
```

Export targets are the catalog's supported manual fields: `title`, `details`,
`date`, `director`, `studio`, `movie`, `actors`, `tags`, `urls`. Relation values
are names rather than Stash IDs. Any queried Stash field, including
`custom_fields`, can provide a value for these targets.

Example export overrides (replace the setting's map, so keep other entries if
wanted):

```json
{
  "title": "select(.fields | index(\"title\")) | .stash.title",
  "details": "select(.fields | index(\"custom_fields\")) | .stash.custom_fields.catalog_caption // empty",
  "actors": "select(.fields | index(\"performer_ids\")) | [.stash.performers[].name]"
}
```

Both directions receive:

- `.stash`: current scene/image, including editable scalar fields, custom fields,
  files and related entity IDs/names. This is the plugin's queried snapshot,
  not an arbitrary recursive GraphQL projection.
- `.catalog`: resolved metadata. Imports include preserved XML/filename defaults;
  exports use the catalog reader projection and manual overrides.
- `.observations`: captured source rows ordered by capture time and observation
  ID; each has `.payload` containing the original JSON. `[-1]` selects the last.
- `.path` and `.relative_path`: selected media pathname.

Exports additionally receive `.fields` (hook input field names), `.input`
(original mutation input, or `{}` for specialized updates) and `.settings`.
Custom export expressions should check `.fields` when only particular edits
should cause a write. Defaults do this, omit blank values, and exclude the
configured refresh tag from exported tags.

An expression must yield zero or one value. `empty` leaves the destination
untouched, including disabling an import field's standard mapping. `null` clears
a Stash field on import; on export it **removes the manual override and inherits
captured metadata**. Catalog text/list fields require nonempty strings/lists;
blank Stash values are skipped by export defaults. This does not mirror blank
values as permanent empty catalog fields. Use an explicit null mapping to
restore inheritance. Dates require ISO dates. `false`, zero, arrays and objects
are preserved where the destination accepts them. Mapping errors fail the
whole mapping before its entity update/manual edit.

The shared backend interpreter has bounded execution time and serialized data
sizes; oversized source payloads return an error. Expressions cannot access the
server filesystem, environment, or network. Plugin updates themselves use the
normal Stash and catalog APIs.

## Validation

With the catalog code and development-only PyYAML/jq available, run the offline integration tests:

```sh
SCRAPE_CATALOG_CODE=/path/to/scrape-catalog python3 -m unittest discover -s tests -v
```

Set `STASH_JQ_EVALUATOR` to a JSON stdin/stdout adapter around Stash's
`plugin.EvaluateMappings` to test the exact backend interpreter instead of jq.
Mapping tests skip if neither evaluator is available.

Tests use temporary media/catalogs and mock Stash. They do not change the live
database or contact external services.

The implementation inherits the repository's AGPL-3.0-only license and credits
the `nfoFileParser` contributors for the Stash mapping and XML/filename parsers.
