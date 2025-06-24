import os
import xml.etree.ElementTree as xml
import base64
import glob
import re
import requests
import config
import log
from abstractParser import AbstractParser


class NfoParser(AbstractParser):
    def __init__(self, content_path, defaults=None, folder_mode=False, content_type="scene"):
        super().__init__()
        if defaults:
            self._defaults = defaults

        self._content_path = content_path
        self._content_type = content_type
        self._nfo_file = None
        self._nfo_root = None

        if config.nfo_location.lower() != "with files":
            return

        if folder_mode:
            # Look for folder.nfo in current dir or one parent up
            dir_path = os.path.dirname(content_path)
            folder_nfo = os.path.join(dir_path, "folder.nfo")
            if os.path.exists(folder_nfo):
                self._nfo_file = folder_nfo
            else:
                parent_folder_nfo = os.path.join(os.path.dirname(dir_path), "folder.nfo")
                if os.path.exists(parent_folder_nfo):
                    self._nfo_file = parent_folder_nfo
        else:
            # Find matching NFO for the content file
            self._nfo_file = self._find_matching_nfo(content_path)

    def _find_matching_nfo(self, content_path):
        """Find an NFO file that matches the given content path."""
        if self._content_type == "gallery":
            # For galleries, look for NFO files in the gallery directory
            # Try multiple naming patterns:
            # 1. folder.nfo
            # 2. gallery_name.nfo (matching folder name)
            
            log.LogDebug(f"Looking for gallery NFO in: {content_path}")
            
            folder_nfo = os.path.join(content_path, "folder.nfo")
            log.LogDebug(f"Checking for: {folder_nfo}")
            if os.path.exists(folder_nfo):
                log.LogDebug(f"Found folder.nfo: {folder_nfo}")
                return folder_nfo
            
            # Try gallery name + .nfo
            gallery_name = os.path.basename(content_path.rstrip(os.sep))
            gallery_nfo = os.path.join(content_path, f"{gallery_name}.nfo")
            log.LogDebug(f"Checking for: {gallery_nfo}")
            if os.path.exists(gallery_nfo):
                log.LogDebug(f"Found gallery-named NFO: {gallery_nfo}")
                return gallery_nfo
            
            # Check one parent level up for folder.nfo
            parent_folder_nfo = os.path.join(os.path.dirname(content_path), "folder.nfo")
            log.LogDebug(f"Checking parent for: {parent_folder_nfo}")
            if os.path.exists(parent_folder_nfo):
                log.LogDebug(f"Found parent folder.nfo: {parent_folder_nfo}")
                return parent_folder_nfo
            
            log.LogDebug(f"No NFO file found for gallery: {content_path}")
            return None
        else:
            # For images and scenes, match filename exactly
            nfo_path = os.path.splitext(content_path)[0] + ".nfo"
            log.LogDebug(f"Looking for {self._content_type} NFO: {nfo_path}")
            return nfo_path

    def _get_cover_images(self):
        """Get cover images from disk or download from URLs."""
        if "cover_image" in config.blacklist:
            return []
        
        # Try to get images from disk first
        thumb_images = self._read_local_images()
        if thumb_images:
            return thumb_images
        
        # Fall back to downloading from URLs
        return self._download_thumb_images()

    def _read_local_images(self):
        """Read local image files."""
        if not self._nfo_file:
            return []
        
        thumb_images = []
        path_no_ext = os.path.splitext(self._nfo_file)[0]
        file_no_ext = os.path.split(path_no_ext)[1]
        
        if self._content_type == "gallery":
            # For galleries, look in the gallery folder
            gallery_dir = os.path.dirname(self._nfo_file)
            pattern = re.compile(r"^.*(cover|poster|thumb|folder)\d*\.(jpe?g|png|webp)$", re.I)
            files = glob.glob(f"{gallery_dir}{os.path.sep}*.*")
        else:
            # For images/scenes, look for matching filename
            pattern = re.compile(f"^.*{re.escape(file_no_ext)}(-cover|-poster|-thumb|\\d+)?\\.(jpe?g|png|webp)$", re.I)
            files = glob.glob(f"{path_no_ext}*.*")
        
        for file_path in sorted(files):
            if len(thumb_images) >= self._image_Max:
                break
            if pattern.match(os.path.basename(file_path)):
                try:
                    with open(file_path, "rb") as img:
                        thumb_images.append(img.read())
                except Exception as e:
                    log.LogDebug(f"Failed to read image {file_path}: {e}")
        
        return thumb_images

    def _download_thumb_images(self):
        """Download thumbnail images from URLs in NFO."""
        if not self._nfo_root:
            return []
        
        # Get thumb URLs from NFO
        thumb_urls = []
        for aspect in ["landscape", "poster", ""]:
            query = f"thumb[@aspect='{aspect}']" if aspect else "thumb"
            matches = self._nfo_root.findall(query)
            for match in matches:
                if match.text:
                    thumb_urls.append(match.text)
            if thumb_urls:
                break
        
        # Download images
        thumb_images = []
        for url in thumb_urls[:self._image_Max]:
            try:
                r = requests.get(url, timeout=10)
                thumb_images.append(r.content)
            except Exception as e:
                log.LogDebug(f"Failed to download image from {url}: {e}")
        
        return thumb_images

    def _extract_actors(self):
        """Extract actor names from NFO."""
        actors = []
        for actor in self._nfo_root.findall("actor/name"):
            if actor.text:
                actors.append(actor.text)
        return actors

    def _extract_tags(self):
        """Extract tags from NFO."""
        tags = []
        for tag in self._nfo_root.findall("tag"):
            if tag.text:
                tags.append(tag.text)
        for genre in self._nfo_root.findall("genre"):
            if genre.text:
                tags.append(genre.text)
        return list(set(tags))

    def _extract_rating(self):
        """Extract rating from NFO."""
        # Try userrating first
        user_rating = self._nfo_root.findtext("userrating")
        if user_rating:
            return round(float(user_rating))
        
        # Try ratings/rating
        rating_elem = self._nfo_root.find("ratings/rating")
        if rating_elem is not None:
            max_value = float(rating_elem.attrib.get("max", 1))
            value = float(rating_elem.findtext("value") or 0)
            return round(value / max_value * 100)
        
        return 0

    def _extract_date(self):
        """Extract date from NFO."""
        # Try premiered first, then year
        premiered = self._nfo_root.findtext("premiered")
        if premiered:
            return premiered
        
        year = self._nfo_root.findtext("year")
        if year:
            return f"{year}-01-01"
        
        return None

    def _get_title(self):
        """Get title based on content type."""
        if self._content_type == "gallery":
            # For galleries, try set name first
            set_name = self._nfo_root.findtext("set/name")
            if set_name:
                return set_name
        elif self._content_type == "image":
            # For images, try name field
            name = self._nfo_root.findtext("name")
            if name:
                return name
        
        # Default title extraction
        return (self._nfo_root.findtext("originaltitle") or 
                self._nfo_root.findtext("title") or 
                self._nfo_root.findtext("sorttitle") or 
                self._get_default("title", "re"))

    def parse(self):
        """Parse the NFO file and extract data."""
        if not self._nfo_file or not os.path.exists(self._nfo_file):
            return {}
        
        log.LogDebug(f"Parsing '{self._nfo_file}' for {self._content_type} content")
        
        # Parse XML
        try:
            with open(self._nfo_file, mode="r", encoding="utf-8") as nfo:
                content = nfo.read().strip().replace("&nbsp;", " ")
            self._nfo_root = xml.fromstring(content)
        except Exception as e:
            log.LogError(f"Could not parse nfo '{self._nfo_file}': {e}")
            return {}
        
        # Get cover images
        images = self._get_cover_images()
        b64_images = []
        for img in images:
            try:
                b64_img = base64.b64encode(img).decode('utf-8')
                b64_images.append(f"data:image/jpeg;base64,{b64_img}")
            except Exception as e:
                log.LogDebug(f"Failed to encode image: {e}")
        
        # Extract all data
        file_data = {
            "file": self._nfo_file,
            "source": "nfo",
            "title": self._get_title(),
            "director": self._nfo_root.findtext("director") or self._get_default("director"),
            "details": (self._nfo_root.findtext("plot") or 
                       self._nfo_root.findtext("outline") or 
                       self._nfo_root.findtext("tagline") or 
                       self._get_default("details")),
            "studio": self._nfo_root.findtext("studio") or self._get_default("studio"),
            "uniqueid": self._nfo_root.findtext("uniqueid"),
            "date": self._extract_date() or self._get_default("date"),
            "actors": self._extract_actors() or self._get_default("actors"),
            "tags": list(set(self._extract_tags() + self._get_default("tags"))),
            "rating": self._extract_rating() or self._get_default("rating"),
            "cover_image": b64_images[0] if len(b64_images) > 0 else None,
            "other_image": b64_images[1] if len(b64_images) > 1 else None,
            "movie": self._nfo_root.findtext("set/name") or self._get_default("title", "nfo"),
            "scene_index": self._nfo_root.findtext("set/index"),
            "urls": [self._nfo_root.findtext("url")] if self._nfo_root.findtext("url") else None,
        }
        
        # Content-type specific adjustments
        if self._content_type == "gallery" and not file_data["movie"]:
            file_data["movie"] = self._nfo_root.findtext("album")
        
        return file_data
