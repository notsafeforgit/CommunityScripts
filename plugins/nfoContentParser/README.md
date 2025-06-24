# Enhanced NFO Content Parser for Stash

This enhanced version of the NFO Scene Parser plugin now supports **scenes, images, and galleries**, allowing you to automatically populate metadata for all your content types using NFO files or filename patterns.

## Features

- **Multi-Content Support**: Automatically processes scenes, images, and galleries
- **NFO File Parsing**: Supports Kodi-compatible NFO files for all content types
- **Regex Pattern Matching**: Flexible filename pattern extraction for any content type
- **Smart NFO Discovery**: Automatically finds the best matching NFO file
- **Automatic Entity Creation**: Creates missing performers, studios, tags, and movies
- **Reload Functionality**: Bulk reprocess tagged content across all types
- **Content-Type Specific Configuration**: Different settings for scenes, images, and galleries

## Supported Content Types

### Scenes
Full support for all existing scene functionality plus:
- Movie/series integration
- Cover images
- Director information
- Scene indexing

### Images  
- Title and date metadata
- Performer and studio tagging
- Rating system
- URL references

### Galleries
- Collection/album support
- Detailed descriptions
- Performer and studio tagging
- Cover images

## NFO File Structure Mapping

| Stash Field | NFO Field(s) | Scenes | Images | Galleries |
|-------------|--------------|--------|---------|-----------|
| `title` | `title`, `originaltitle`, `sorttitle` | ✓ | ✓ | ✓ |
| `details` | `plot`, `outline`, `tagline` | ✓ | ✓ | ✓ |
| `studio` | `studio` | ✓ | ✓ | ✓ |
| `performers` | `actor.name` (sorted by `actor.order`) | ✓ | ✓ | ✓ |
| `movie` | `set.name`, `album` | ✓ | ✗ | ✗ |
| `rating` | `userrating`, `ratings.rating` | ✓ | ✓ | ✓ |
| `tags` | `tag`, `genre` | ✓ | ✓ | ✓ |
| `date` | `premiered`, `year` | ✓ | ✓ | ✓ |
| `url` | `url` | ✓ | ✓ | ✓ |
| `director` | `director` (movies only) | ✓ | ✗ | ✗ |
| `cover_image` | `thumb`, local files | ✓ | ✓ | ✓ |
| `id` | `uniqueid` | ✓ | ✓ | ✓ |

## Installation

1. Copy all plugin files to your Stash plugins directory
2. Rename the main file to `nfoContentParser.py`
3. Update your Stash plugin configuration to use the new YAML file
4. Configure the plugin settings in `config.py`

## Configuration

### Basic Settings

```python
# Process all content types or skip organized content
skip_organized = True
set_organized_nfo = True

# Content types to create missing entities for
create_missing_performers = True
create_missing_studios = True  
create_missing_tags = True
create_missing_movies = True  # Scenes only

# Reload tag for bulk processing
reload_tag = "_NFO_RELOAD"
```

### Content-Type Specific Settings

```python
# Override global settings for specific content types
image_settings = {
    "skip_organized": False,  # Process organized images
    "blacklist": ["details"],  # Images don't support details
}

gallery_settings = {
    "create_missing_movies": False,  # Galleries as standalone collections
}
```

## NFO File Discovery

The plugin uses intelligent NFO file discovery:

### For Scenes (existing behavior)
1. `filename.nfo` (exact match)
2. `ID_number.nfo` pattern matching
3. Folder fallback

### For Images
1. `image.nfo` (content-type specific)
2. `filename.nfo` (traditional match)
3. `folder.nfo` (folder fallback)

### For Galleries
1. `gallery.nfo` (content-type specific)
2. `filename.nfo` (traditional match)
3. `folder.nfo` (folder fallback)

## Regex Pattern Support

Create `nfoSceneParser.json` files with content-type specific patterns:

```json
{
  "regex": "^(?P<title>.+)\\s\\[(?P<date>\\d{4})\\]$",
  "splitter": ",",
  "scope": "filename",
  "scene": {
    "regex": "^(?P<title>.+)\\s-\\s(?P<performers>.+)\\s\\[(?P<studio>.+)\\]\\[(?P<date>\\d{4}-\\d{2}-\\d{2})\\]$",
    "splitter": ","
  },
  "image": {
    "regex": "^(?P<title>.+)\\s-\\s(?P<performers>.+)\\s\\[(?P<date>\\d{4})\\]$",
    "splitter": ";"
  },
  "gallery": {
    "regex": "^(?P<album>.+)\\s-\\s(?P<performers>.+)\\s\\[(?P<studio>.+)\\]$",
    "splitter": "|"
  }
}
```

### Supported Regex Groups

#### All Content Types
- `title`: Content title
- `performers`: Performer names (split by splitter)
- `studio`: Studio name
- `tags`: Tag names (split by splitter)  
- `premiered`: Date in various formats
- `rating`: Numeric rating
- `plot`: Details for item

## Example NFO Files

### Scene NFO (movie.nfo)
```xml
<movie>
    <title>Amazing Scene Title</title>
    <plot>Detailed description of the scene content.</plot>
    <studio>Studio Name</studio>
    <director>Director Name</director>
    <premiered>2024-01-15</premiered>
    <userrating>8</userrating>
    <genre>Action</genre>
    <genre>Drama</genre>
    <actor>
        <name>Performer One</name>
        <order>0</order>
    </actor>
    <actor>
        <name>Performer Two</name>
        <order>1</order>
    </actor>
    <set>
        <name>Movie Series Name</name>
        <index>1</index>
    </set>
    <thumb aspect="poster">http://example.com/poster.jpg</thumb>
</movie>
```

### Image NFO (image.nfo)
```xml
<movie>
    <title>Beautiful Portrait</title>
    <studio>Photography Studio</studio>
    <premiered>2024-01-15</premiered>
    <plot>Description of the image for details.</plot>
    <userrating>9</userrating>
    <tag>Portrait</tag>
    <tag>Professional</tag>
    <actor>
        <name>Model Name</name>
        <order>0</order>
    </actor>
</movie>
```

### Gallery NFO (gallery.nfo)
```xml
<movie>
    <title>Photo Collection Title</title>
    <plot>Description of the photo collection.</plot>
    <studio>Photography Studio</studio>
    <premiered>2024-01-15</premiered>
    <userrating>8</userrating>
    <tag>Collection</tag>
    <tag>Series</tag>
    <actor>
        <name>Model One</name>
        <order>0</order>
    </actor>
    <actor>
        <name>Model Two</name>
        <order>1</order>
    </actor>
    <set>
        <name>Album Name</name>
    </set>
    <uniqueid>gallery_54321</uniqueid>
</movie>
```

## Usage

### Automatic Processing
The plugin automatically triggers on:
- `Scene.Create.Post`
- `Image.Create.Post` 
- `Gallery.Create.Post`

### Manual Reload
1. Tag content with your reload tag (default: `_NFO_RELOAD`)
2. Run the "Reload tagged content" task
3. The plugin will process all tagged scenes, images, and galleries

### Dry Run Mode
Enable `dry_mode = True` in config.py to test without making changes.

## Troubleshooting

### Debug Logging
Enable debug logging in Stash to see detailed processing information:
- NFO file discovery process
- Regex pattern matching
- Entity creation/matching
- Field mapping decisions

### Common Issues

1. **NFO not found**: Check file naming and location
2. **Regex not matching**: Verify pattern in `nfoSceneParser.json`
3. **Missing performers**: Check `create_missing_performers` setting
4. **Content not updating**: Verify `skip_organized` setting

## Advanced Configuration

### Custom Field Mapping
Modify parsers to support additional NFO fields or custom Stash fields.

### Multi-Language Support
Use `originaltitle` vs `title` for international content.

### Batch Processing
Use reload functionality for bulk metadata updates across content types.

## Version History

- **v2.0.0**: Added image and gallery support, content-type specific configurations
- **v1.3.1**: Original scene-only version

## Contributing

When contributing:
1. Maintain backward compatibility with scenes
2. Test with all content types (scenes, images, galleries)
3. Update documentation for new content-type specific features
4. Add appropriate error handling for content-type differences