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

Version 1.5 additionally requires the host's `Performer.Merge.Post` notification.
Update Stash before updating this plugin.

Version 1.2 and later declare `apiVersion: 3` and require the Stash fork's v3 plugin API
(`pluginSettingsV3`, `pluginEvaluateMappings`, `updatePluginSettingsV3`). It has
no v2.5 plugin API or UI compatibility requirement. Upgrade Stash before installing
this version: older Stash builds reject the versioned manifest.
There is no `ui.entry`; native v3 settings and backend hooks provide
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
Updates descended from scene/image creation hooks are also skipped, so automatic
initialization cannot become a manual catalog override. Unchanged
values do not append duplicate edits. Failures are logged as plugin
errors after the successful Stash operation; hooks do not veto or roll it back.

Expand **Settings → Plugins → Catalog Metadata** to configure sync direction,
dry run, filename title fallback, import exclusions, entity creation, organized
policy, name tolerance, refresh tag and the four mapping settings. Save changes
to persist them in Stash.
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

Catalog imports and exports skip media outside `SCRAPE_MEDIA_ROOT`. The optional
filename title fallback also handles media outside that root. This plugin does
not delete media, prune posts, or change backup retention.

## Filename title fallback

Version 1.3 adds **Use filename when title is missing**, enabled by default. On
creation and tagged refresh, title selection follows this order:

1. The explicit import mapping or standard catalog/XML/filename-rule title.
2. A nonblank title already in Stash.
3. The primary media filename without its final extension.

The fallback covers scenes and images with no catalog match, including files
outside the catalog source. It never replaces a nonblank existing title with a
filename. Unmatched items receive only a title update; other fields, relations
and organized state are untouched. A real media file path is required.

Explicit `title` mappings remain authoritative: `empty` leaves the title alone,
and `null` or a blank value is not replaced with a filename. A standard title
exclusion also disables fallback. Import direction, dry run and the organized
item policy still apply; tagged refreshes can include organized items. Automatic
title updates carry the import marker and never become manual catalog overrides.

After updating to 1.3, disable **titleFromFilename** and remove its ID from any
custom hook order. Catalog Metadata provides the fallback itself. Keeping the
old plugin enabled would still overwrite existing titles before Catalog Metadata
runs. No Stash backend update is required beyond the v3 API required by 1.2.


## Organized items

**Skip organized items on creation** checks the scene or image that was just
created. The hook supplies its Stash ID; the plugin loads that item and reads its
current `organized` flag. It does not search for another item with a matching
filename, title, hash, or catalog entry. For example, an item created with
`organized: true`, or marked organized by an earlier creation hook, is skipped.
A normal new item with `organized: false` is imported. This also governs the
filename title fallback. **Refresh tagged items from catalog** bypasses the
check so an intentional refresh can include organized items.

**Mark imported items organized** sets that flag after a catalog or XML import
only when all fields in `config.py`'s `set_organized_only_if` are present. The
default requirements are **title, performers, details, date, studio, tags, and
cover image**. A successful import can therefore leave the item unorganized,
for example when it has no cover image. Filename-rule imports and filename-only
title fallbacks do not mark items organized.

The completeness check uses standard import data (including merged existing
Stash values) and folder defaults, before custom jq mappings are applied.
Custom mappings do not satisfy that earlier check; an explicit `organized`
import mapping controls the final value instead. Disabling the checkbox does
not clear existing organized flags. Tagged refreshes still apply this marking
policy even though they bypass the skip policy. Ordinary Stash edits trigger
exports, not another automatic import.

## Field mappings

**Scene import**, **Image import**, **Scene export**, and **Image export** are
separate settings. In the current v3 editor, each row has a **Target field** and
a **jq expression**. Enter expressions directly, including quotes and line
breaks; no JSON string escaping is needed. Use **Add mapping** for a new target
and the remove button to delete one. Use **Preview mappings** before saving expressions. Select a scene or image,
then **Load entity data** to read its Stash snapshot and catalog context.
**Test expression** evaluates the current unsaved mappings against that input.
You can also paste or edit the sample JSON directly.
Mapping settings use native JSON objects in the API and configuration. Saved
JSON text from version 1.1 is read without losing existing overrides; new saves
use objects. Update Stash to get the row editor; the plugin's mapping format
has not changed. Removing every row saves an empty map rather than restoring
manifest defaults.

Import mappings override the standard importer; an empty object keeps its
existing behavior. Target any supported `SceneUpdateInput` or `ImageUpdateInput`
field except `id` and `clientMutationId`. Relation targets such as `studio_id`
and `performer_ids` expect Stash IDs. Standard imports still resolve names using
the matching/creation settings. Explicit mappings take precedence over the
standard import blacklist.

Example import overrides:

| Target field | jq expression |
| --- | --- |
| `title` | `.catalog.title // empty` |
| `details` | `.observations[-1].payload.content // empty` |
| `director` | `.catalog.director // empty` |
| `custom_fields` | `{partial: {catalog_author: .observations[-1].payload.author.name}}` |
| `organized` | `false` |

Export targets are the catalog's supported manual fields: `title`, `details`,
`date`, `director`, `studio`, `movie`, `actors`, `tags`, `urls`. Relation values
are names rather than Stash IDs. Any queried Stash field, including
`custom_fields`, can provide a value for these targets.

Example export rows (keep other default rows if wanted; an empty export map
disables exports for that entity type):

| Target field | jq expression |
| --- | --- |
| `title` | `select(.fields \| index("title")) \| .stash.title` |
| `details` | `select(.fields \| index("custom_fields")) \| .stash.custom_fields.catalog_caption // empty` |
| `actors` | `select(.fields \| index("performer_ids")) \| [.stash.performers[].name]` |

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

## Preview mappings with a library item

Version 1.4 requires a Stash v3 backend with entity preview support. Update
Stash before installing this plugin version. Each mapping setting offers the
appropriate scene or image picker; search by title or file path and use the ID
to distinguish similar entries. The plugin uses the same primary media path as
its normal import/export hooks to locate catalog evidence.

Previews read Stash and the catalog only. They do not save settings, update
entities, create performers/studios/tags/groups, append catalog overrides or
trigger hooks. They work for organized items and either sync direction; those
settings still control real imports/exports. Missing items or paths, unavailable
catalogs, media outside the configured source, and oversized contexts report
errors instead of running an import.

- **Import:** `.catalog` uses the same XML, filename defaults, translations and
  manual overrides as the normal importer. `.observations` exposes raw captures.
  An unsaved first mapping works even when the saved map is empty. Results show
  custom mapped fields only; `{}` does not mean the standard importer would do
  nothing. Standard imports, title fallback, organized checks and relation
  resolution/creation are not run by a preview.
- **Export:** `.catalog` is the current catalog reader projection. `.fields`
  initially simulates changing the current scalar and relationship fields in
  `.input`; no real edit has occurred. Edit `.fields` (for example `["title"]`)
  and `.input` to try a specific event. To simulate a new value, also edit the
  corresponding `.stash` value, since that represents the post-edit snapshot.
  `.settings` contains saved settings. Results show jq output before the normal
  unchanged-value filter and catalog field validation, so a real export may
  skip a value already present or reject an unsupported target/value.

Editing the sample input changes only the preview. Editing an expression or
input hides the old result until you test again. **Save** persists mappings;
preview buttons never do. The Stash HTTP client additionally blocks mutations
in preview mode, and integration tests check the catalog's data files remain
unchanged (SQLite's transient shared-memory read locks are excluded).

Stash calls people **performers**. The catalog's normalized manual field is
`actors`, an array of names; raw observations retain each source's own keys.
Import relation mappings use `performer_ids` (Stash IDs), while export mappings
can use target `actors` with `[.stash.performers[].name]`.

## Performer names, aliases and account links

Version 1.5 matches every imported `actors` name against both Stash canonical
names and **all** aliases, including single-word usernames. Matching ignores
case, surrounding whitespace and Unicode composition; it does not use fuzzy or
substring matches. Several matching aliases on one performer still count as
one candidate. A canonical-name match does not outrank another performer's alias.
If multiple performers match, the importer skips that name and logs their IDs,
names and disambiguations. It neither chooses the first result nor creates
another performer. Existing scene/image relationships remain intact. Explicit
`performer_ids` jq mappings continue to take precedence.

An explicit account link can resolve a collision for content from that account.
The account must occur in the file's captured posts; being somewhere else in a
joined catalog is insufficient. If two linked performers still match the same
name on that file, it remains ambiguous. An uploader is not automatically added
as a depicted performer: the imported metadata must already name that person.

With **Sync performer identities to catalogs** enabled and an export-capable
sync direction, successful Stash performer merges and identity edits also update
catalog identities. Association comes from Twitter/X or Reddit **profile URLs**
on the performers, or from **Performer account links**. Several accounts on the
same service work the same way as accounts across services. Post URLs, shared
files/hashes and names alone do not establish an association. A username found
under multiple stable account IDs requires an explicit choice; duplicate URLs
on different Stash performers are also reported as conflicts.

For existing merges or accounts without supported profile URLs:

1. Add each account's profile URL to the appropriate Stash performer, or run
   **Preview performer catalog links** to see name-only candidates and account
   keys in the task log. Preview is read-only, regardless of sync direction.
2. Resolve ambiguous cases with **Performer account links**, a native JSON
   object mapping account keys to Stash performer ID strings. For example:

   ```json
   {
     "twitter:id:12345": "42",
     "reddit:id:t2_abc": "42"
   }
   ```

3. Save the setting, preview again, then run **Sync performer catalog links**.
   It honors dry run and sync direction. This also reconciles accounts added to
   the catalog since the last performer edit. Removing a setting does not undo
   an association already applied to the catalog.

The sync joins creator catalogs using the catalog's existing audited link
operation, labels the joined catalog with the canonical Stash name, and retains
original account IDs, handles, posts, raw observations and source databases.
Subreddit collection catalogs stay separate. No media files are renamed or
deleted. The merge hook includes the original profiles before Stash removes
them, so discarded source aliases and URLs remain available as identity evidence.
Old name strings in captured/manual metadata are preserved and can resolve via
the stored identity; the plugin does not rewrite historical captures.

Identity records and account bindings are stored in plugin-owned tables in
`registry.sqlite3`, included in normal catalog snapshots. **Performer link
namespace** scopes IDs to this Stash database; choose a different value when
connecting a different Stash database. The first actual sync creates these
tables; previews and imports do not. Failed links can be retried with the sync
task. Hooks run after Stash commits, so a catalog failure is logged and cannot
roll back the Stash merge.

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
