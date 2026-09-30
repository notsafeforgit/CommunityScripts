"""Configurable mappings evaluated by Stash's shared jq API."""
import json
import os

import config
import log
from catalogReader import get_reader, mapping_context, write_overrides

IMPORT_MARKER = 'catalogMetadata:import'


def preview_update_input(kind, item):
    """Simulate a metadata edit using current values; this is never submitted."""
    scalars = ('title', 'details', 'code', 'date', 'urls', 'rating100', 'organized')
    scalars += ('director', 'production_date', 'resume_time', 'play_duration') if kind == 'scene' else ('photographer',)
    result = {key: item[key] for key in scalars if key in item}
    result['id'] = str(item['id'])
    result['studio_id'] = (item.get('studio') or {}).get('id')
    for source, target in (('performers', 'performer_ids'), ('tags', 'tag_ids'), ('galleries', 'gallery_ids')):
        result[target] = [row['id'] for row in item.get(source, [])]
    if 'custom_fields' in item:
        result['custom_fields'] = {'full': item['custom_fields']}
    if kind == 'scene':
        result['groups'] = [{'group_id': row['group']['id'], 'scene_index': row.get('scene_index')}
                            for row in item.get('groups', [])]
    return result


def is_import_notification(hook):
    if (hook.get('input') or {}).get('clientMutationId') == IMPORT_MARKER:
        return True
    # Initialization by any creation hook must not become a manual override.
    return any(parent.get('type') in ('Scene.Create.Post', 'Image.Create.Post')
               for parent in hook.get('parentHooks', []))


class CatalogMappings:
    def __init__(self, stash):
        self.stash = stash
        settings = stash.gql_pluginSettings()
        self.settings = settings
        self.direction = settings.get('sync_direction', 'both')
        self.mappings = {}
        for entity in ('scene', 'image'):
            for direction in ('import', 'export'):
                key = f'{entity}_{direction}_mappings'
                value = settings.get(key, {})
                # Preserve saved overrides from the pre-versioned release.
                if isinstance(value, str):
                    value = json.loads(value)
                if not isinstance(value, dict) or any(not k or not isinstance(v, str) for k, v in value.items()):
                    raise ValueError(f'{key} must be an object of target fields and jq expressions')
                self.mappings[key] = value
        # Keep config.py as the fallback for existing, undeclared preferences.
        for key, value in settings.items():
            if hasattr(config, key):
                if isinstance(getattr(config, key), list):
                    value = json.loads(value)
                    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                        raise ValueError(f'{key} requires a JSON array of strings')
                setattr(config, key, value)

    def importing(self):
        return self.direction in ('both', 'import')

    def has_import_mappings(self, kind):
        return bool(self.mappings[f'{kind}_import_mappings'])

    def apply_title_fallback(self, kind, item, path, payload):
        # Explicit mappings own the field, including empty/null/blank results.
        if 'title' in self.mappings[f'{kind}_import_mappings']:
            return
        if 'title' in config.blacklist:
            payload.pop('title', None)
            return
        for title in (payload.get('title'), item.get('title')):
            if isinstance(title, str) and title.strip():
                payload['title'] = title
                return
        if self.settings.get('filename_title_fallback', True) and path:
            title = os.path.splitext(os.path.basename(path))[0]
            if title.strip():
                payload['title'] = title
                return
        payload.pop('title', None)

    def import_payload(self, kind, item, path, catalog, payload):
        mappings = self.mappings[f'{kind}_import_mappings']
        if 'id' in mappings or 'clientMutationId' in mappings:
            raise ValueError('Import mappings cannot change id or clientMutationId')
        if mappings:
            context = mapping_context(get_reader(), path, item, catalog)
            mapped = self.stash.gql_evaluateMappings(mappings, context)
            # An explicit `empty` mapping disables the corresponding default.
            for key in mappings:
                payload.pop(key, None)
            payload.update(mapped)
        self.apply_title_fallback(kind, item, path, payload)
        payload['id'] = str(item['id'])
        payload['clientMutationId'] = IMPORT_MARKER
        return payload

    def export_context(self, reader, item, path, hook):
        # The refresh marker is an internal command, so omit it from the export
        # view before evaluating either previews or real mappings. Keep the
        # original Stash item and mutation input intact.
        export_item = dict(item)
        if isinstance(item.get('tags'), list):
            reload_tag = self.settings.get('reload_tag', config.reload_tag)
            export_item['tags'] = [tag for tag in item['tags'] if tag.get('name') != reload_tag]
        context = mapping_context(reader, path, export_item, reader.metadata(path))
        context.update({'fields': hook.get('inputFields') or [], 'input': hook.get('input') or {}})
        return context

    def export_item(self, kind, item, path, hook):
        if self.direction not in ('both', 'export'):
            return None
        if is_import_notification(hook):
            return None
        reader = get_reader()
        try:
            reader.relpath(path)
        except ValueError:
            log.LogDebug(f'Skipping media outside the catalog source: {path}')
            return None
        context = self.export_context(reader, item, path, hook)
        fields = self.stash.gql_evaluateMappings(self.mappings[f'{kind}_export_mappings'], context)
        # Do not turn an unchanged projection into a new manual override. Null
        # explicitly removes an override, so it is compared with overrides only.
        overrides = reader.overrides(path)
        fields = {key: value for key, value in fields.items()
                  if (key in overrides if value is None else context['catalog'].get(key) != value)}
        if not fields:
            return None
        if config.dry_mode:
            log.LogInfo(f'Dry mode. Would write catalog metadata for {path}: {json.dumps(fields)}')
            return fields
        result = write_overrides(reader, path, fields)
        log.LogInfo(f'Wrote catalog metadata for {kind} {item["id"]}: {", ".join(sorted(fields))}')
        return result
