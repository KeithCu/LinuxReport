"""
models.py

Defines data models and configuration structures for the LinuxReport project.
"""

# Standard library imports
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class SiteConfig:
    """Configuration for a site."""
    ALL_URLS: Dict[str, "RssInfo"]
    USER_AGENT: str
    site_urls: List[str]
    URL_IMAGES: str
    FAVICON: str
    LOGO_URL: str
    WEB_DESCRIPTION: str
    WEB_TITLE: str
    ABOVE_HTML_FILE: str
    CUSTOM_FETCH_CONFIG: dict = None

class RssInfo:
    """Represents information about an RSS feed."""
    def __init__(self, logo_url, logo_alt, site_url):
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url

DEBUG = False

# Add a global config for Tor usage
USE_TOR = False

# --- Shared Reddit Fetch Config ---
REDDIT_FETCH_CONFIG = {
    "needs_selenium": True,
    "needs_tor": True,
    "post_container": "article",
    "title_selector": "a[id^='post-title-']",
    "link_selector": "a[id^='post-title-']",
    "link_attr": "href",
    "filter_pattern": ""
}