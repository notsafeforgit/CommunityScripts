# If dry is True, will do a trial run with no permanent changes. 
# Look in the log file for what would have been updated...
dry_mode = False

# nfo file location & naming.
# Possible options:
# - "with files": with the video/image files: Follows NFO standard naming: https://kodi.wiki/view/NFO_files/Movies
# - "...": a specific directory you mention. In this case, the nfo names will match your stash content ids.
# if you set the above to "with files", it'll force filename anyway, to match the filename.
# ! Not yet implemented. Currently, only "with files" is supported
nfo_location = "with files"

# If True, will never update already "organized" content (scenes, images, galleries).
skip_organized = False

# If True, will set the content to "organized" on update from nfo file. 
set_organized_nfo = True

# Set of fields that must be set from the nfo (i.e. "not be empty") for the content to be marked organized. 
# Possible values for all content types: "performers", "studio", "tags", "movie", "title", "details", "date", 
#                                        "rating", "urls" and "cover_image"
# Note: "movie" only applies to scenes
set_organized_only_if = ["title", "performers", "details", "date", "studio", "tags", "cover_image"]

# Blacklist: array of nfo fields that will not be loaded into the content.
# Possible values for all content types: "performers", "studio", "tags", "movie", "title", "details", "date", 
#                                        "rating", "urls" and "cover_image", "director"
# Note: "movie" and "director" only apply to scenes
# Note: "tags" is a special case: if blacklisted, new tags will not be created, but existing tags will be mapped.
blacklist = ["rating"]

# List of tags that will never be created or set to the content.
# Example: blacklisted_tags = ["HD", "Now in HD"]
blacklisted_tags = ["HD", "4K", "Now in HD", "1080p Video", "4k Video"]

# Name of the tag used as 'marker" by the plugin to identify which content to reload.
# Empty string or None disables the reload feature
# This tag will be applied to scenes, images, and galleries that should be reprocessed
reload_tag = "_NFO_RELOAD"

# Creates missing entities in stash's database (or not)
create_missing_performers = True
create_missing_studios = True
create_missing_tags = True
create_missing_movies = True  # Only applies to scenes

# Content type specific settings
# These settings can override global settings for specific content types

# Image specific settings
image_settings = {
    # Override global settings for images if needed
    # "skip_organized": False,  # Example: process organized images
    # "blacklist": ["movie"],  # Images don't use movie field
}

# Gallery specific settings  
gallery_settings = {
    # Override global settings for galleries if needed
    # "create_missing_movies": False,  # Galleries typically don't use movies
}

# Scene specific settings (maintains backward compatibility)
scene_settings = {
    # All existing settings apply to scenes by default
}

###############################################################################
# Do not change config below unless you are absolutely sure of what you do...
###############################################################################

# Whether to look for existing entries also in aliases
search_performer_aliases = True
search_studio_aliases = True

levenshtein_distance_tolerance = 2

# "Single names" means performers with only one word as name like "Anna" or "Siri".
# If true, single names aliases will be ignored: 
# => only the "main" performer name determines if a performer exists or is created.
# Only relevant if search_performer_aliases is True.
ignore_single_name_performer_aliases = True

# If the above is set to true, it can be overruled for some allowed (whitelisted) names
#single_name_whitelist = ["MJFresh", "JMac", "Mazee"]

###############################################################################
# Content Type Specific NFO File Handling
#
# For images and galleries, the plugin will look for NFO files in this order:
# 1. Content-type specific NFO (e.g., "image.nfo", "gallery.nfo")
# 2. Traditional matching NFO (e.g., "filename.nfo")  
# 3. Folder NFO ("folder.nfo") as fallback
#
# This allows for flexible NFO organization while maintaining compatibility
###############################################################################

###############################################################################
# Regex Pattern Support
# 
# Regex patterns are defined in their own config files (nfoSceneParser.json).
# The enhanced parser now supports content-type specific regex patterns:
#
# Example nfoSceneParser.json structure:
# {
#   "regex": "default pattern for scenes",
#   "splitter": ",",
#   "scope": "filename",
#   "scene": {
#     "regex": "scene-specific pattern",
#     "splitter": ","
#   },
#   "image": {
#     "regex": "image-specific pattern", 
#     "splitter": ";"
#   },
#   "gallery": {
#     "regex": "gallery-specific pattern",
#     "splitter": "|"
#   }
# }
#
# If content-type specific patterns are not found, falls back to default pattern.
# See README.md for details
###############################################################################
