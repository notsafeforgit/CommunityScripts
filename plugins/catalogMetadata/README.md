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
Version 1.8 requires `scrape-catalog` 0.3.0 or later for shared post metadata and
catalog-owned performer UUIDs. Its `ui.entry` provides Catalog review through the shared v3 UI host.
No Python jq package or jq executable is needed at runtime.

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
- `.observations`: post revisions ordered by capture time and observation ID.
  Each `.payload` contains shared source metadata, such as the post caption and
  author. `[-1]` selects the last revision. Multiple images/videos in a post share
  that body; `.captures[]` retains each original capture ID, time, extractor
  version and `.payload_patch` with attachment/provenance fields such as `num`,
  `filename`, `_url` or `nfo_path`. Genuine post changes and different post IDs
  stay separate. Unchanged NFO documents also share storage behind the reader.
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
  manual overrides as the normal importer. `.observations` exposes shared post
  bodies and their capture patches.
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

## Catalog-owned performer identities

Version 1.7 gives each linked performer a random UUID owned by the catalog
registry. Names, aliases, source accounts and Stash IDs are attributes and
associations. A rename preserves the UUID. A Stash merge retains the destination
UUID and redirects source UUIDs and former Stash IDs to it, keeping their aliases
and profile evidence. If the destination has no UUID yet, an existing source
UUID is retained. All source catalogs and download directories stay separate.

`registry.sqlite3` stores `performer_identities`, `performer_identity_bindings`,
`performer_account_associations`, and append-only `performer_identity_events`.
Normal catalog snapshots include all of them. The library owns this data; it
survives plugin removal and is readable without Stash. Source account keys,
captured observations, item metadata overrides and media paths are preserved.

**Performer link namespace** identifies the Stash library, not a person. Keep it
when restoring that database; choose a different namespace for another or rebuilt
library. In **Catalog performers**, **Link Stash performer** can bind an existing
catalog UUID to a performer in that library. It rejects conflicting current
bindings instead of silently combining different UUIDs.

The first write migrates previously saved plugin links, aliases and redirects
into these catalog-owned tables, in the same registry transaction as the action.
It is idempotent and retains the old tables for inspection. Read-only imports and
previews do not run migrations. An administrator can migrate existing saved links
without syncing additional proposals:

```sh
scrape-catalog migrate-performer-identities          # read-only preview
scrape-catalog migrate-performer-identities --apply  # registry-only migration
scrape-catalog performer-identities                 # read-only UUIDs and bindings
```

Older physical catalog merges are kept readable. Accounts in those catalogs can
now be assigned separately; migration does not attempt to reverse historical
copies or move media. Future plugin operations never call the physical catalog
merge API. **Legacy performer account links** remains an import source for old
settings. Reviewed registry choices, including intentional unlinks, take
precedence; use the review screen to manage new associations.

## Profile matching

With **Sync performer identities to catalogs** enabled and an export-capable sync
direction, performer edits/merges update the catalog identity registry. The sync
recognizes Twitter/X, Reddit, Instagram, Bluesky (DID or handle), TikTok, Tumblr,
OnlyFans, Fansly, Patreon and Coomer/Kemono profile URLs. Mirror links use the
upstream service plus user identifier: Patreon user 123 and Fansly user 123 are
separate accounts. Supported mirror domain variants follow the gallery-dl URL
shapes, and service names are not restricted to a fixed list.

Other gallery-dl extractors can match exact profile URLs explicitly present in
captured author metadata. The catalog records these in `account_profile_urls`;
this does not require the gallery-dl package or a network request inside Stash.
Generic nested author/user/owner objects are supported. A feed/download URL or a
bio website is not assumed to identify its author. Older observations without
profile evidence remain available for explicit review. Extractors that do not
provide an author identity/profile URL need a manual account association.

Matching names alone produces review candidates. Reused handles, multiple Stash
performers claiming an account, and ambiguous imported performer names require an
explicit choice. Being the source account owner does not automatically tag that
person as depicted in every scene or image.

## Catalog review page

Update the catalog library before installing **Catalog Metadata 1.8**, then
reload the Stash UI. Open **Catalog review** from navigation or **Settings →
Plugins → Catalog Metadata → Open Catalog review**. Scene/image jq previews remain
in plugin settings.

**Source accounts** lists individual accounts, their source folders and matching
evidence. Unlabeled catalog hashes are no longer presented as additional entities;
**Show source identifiers** reveals the account key and source catalog ID.

1. Filter/search accounts. **Conflicting links** indicates competing evidence;
   **Name or alias match** needs a decision; **Ready to review** has profile/link
   evidence. **All accounts** includes unmatched and intentionally unlinked items.
2. Choose **Review**, then choose a **Stash performer** or an existing **Catalog
   performer**. The Stash choice creates a UUID only if that performer has none.
3. **Preview link** shows the single account being changed, its previous owner,
   the destination UUID or proposed UUID creation, and accounts already associated
   with that performer. Other accounts are not automatically swept into this action.
4. **Apply reviewed link** saves that association. **Preview unlink** and **Apply
   reviewed unlink** remove one account association and persist an explicit opt-out
   so automatic profile matching cannot immediately recreate it. Linking it again
   is an explicit choice. An empty identity remains available with the same UUID.

**Catalog performers** presents a unified view of each performer’s accounts,
aliases, Stash bindings and source folders. **Manage account** reassigns/unlinks
one account without merging or splitting the source databases.

Browsing and previewing are read-only. Apply honors dry run, sync direction and
identity-sync settings. It rechecks current data after obtaining the writer lock,
rejects stale previews, and commits the identity, binding, association and audit
event together in one registry transaction. It performs no Stash mutation.

The **Preview performer catalog links** and **Sync performer catalog links** tasks
remain available for profile-based proposals and synchronization, including new
accounts discovered since the last performer edit. Explicit review decisions take
precedence. Existing scenes/images are not automatically re-imported; use tagged
refresh when needed. Hooks run after Stash commits, so a catalog failure is logged
and cannot undo the completed Stash operation.

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

The browser entry is built from `ui/src/index.jsx` using the host's React runtime,
TanStack Form, Zod and shared controls; it bundles no second copy of React.

```sh
sh ui/build.sh
STASH_UI_ROOT=/path/to/stash/ui/v3 node ui/tests/browser.mjs
```

The browser test uses installed Stash development dependencies and a local mock
API. It covers explicit apply, stale previews, failure/retry, dry run, mobile
layout and a deployment prefix. Set `PLAYWRIGHT_BROWSERS_PATH` if needed. The
shipped `ui/index.js` is generated; rebuild it after editing JSX. Plugin layout
CSS is scoped in `ui/review.css` because Stash does not compile plugin Tailwind.

The implementation inherits the repository's AGPL-3.0-only license and credits
the `nfoFileParser` contributors for the Stash mapping and XML/filename parsers.
