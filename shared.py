"""
shared.py

This module contains shared utilities, classes, and constants for the LinuxReport project.
"""

import os
from enum import Enum
import datetime
from typing import Optional, Any

import diskcache
import FeedHistory

class Mode(Enum):
    """Enumeration for different report modes."""
    LINUX_REPORT = 1
    COVID_REPORT = 2
    TECHNO_REPORT = 3
    AI_REPORT = 4
    PYTHON_REPORT = 5
    TRUMP_REPORT = 6
    SPACE_REPORT = 7

# Constants
DEBUG: bool = False

# Path for code and cache
PATH: str = "/srv/http/LinuxReport2"

# Shared path for weather, etc.
SPATH: str = "/run/linuxreport"
TZ = FeedHistory.TZ
EXPIRE_MINUTES: int = 60 * 5
EXPIRE_HOUR: int = 3600
EXPIRE_DAY: int = 3600 * 12
EXPIRE_WEEK: int = 86400 * 7
EXPIRE_YEARS: int = 86400 * 365 * 2

MODE = Mode.AI_REPORT

# Constants for configuration
URLS_COOKIE_VERSION = "2"
USE_TOR = True

RSS_TIMEOUT = 300  # Timeout value in seconds for RSS feed operations

MAX_ITEMS = 40  # Maximum number of items to process in RSS feeds

# Mapping for configuration modules
CONFIG_MODULES = {
    Mode.LINUX_REPORT: "linux_report_settings",
    Mode.COVID_REPORT: "covid_report_settings",
    Mode.TECHNO_REPORT: "techno_report_settings",
    Mode.AI_REPORT: "ai_report_settings",
    Mode.TRUMP_REPORT: "trump_report_settings",
}

config_module_name = CONFIG_MODULES.get(MODE)
if not config_module_name:
    raise ValueError("Invalid mode specified.")

config_settings = __import__(config_module_name, fromlist=["CONFIG"])

ALL_URLS = config_settings.CONFIG.ALL_URLS
site_urls = config_settings.CONFIG.site_urls
USER_AGENT = config_settings.CONFIG.USER_AGENT
URL_IMAGES = config_settings.CONFIG.URL_IMAGES
FAVICON = config_settings.CONFIG.FAVICON
LOGO_URL = config_settings.CONFIG.LOGO_URL
WEB_DESCRIPTION = config_settings.CONFIG.WEB_DESCRIPTION
WEB_TITLE = config_settings.CONFIG.WEB_TITLE
ABOVE_HTML_FILE = config_settings.CONFIG.ABOVE_HTML_FILE

WELCOME_HTML = (
    '<font size="4">(Displays instantly, refreshes hourly) - Fork me on <a target="_blank"'
    'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
    'href = "https://gitlab.com/keithcu/linuxreport">GitLab. </a></font>'
    '<br/>The Reddit Woke mafia had blocked my user-agent and IP address for political reasons, (I was making max a few requests per hour!!) '
    '<br/>So, I picked a random USER_AGENT and am using <a href = "https://www.torproject.org/">TOR</a> to fetch Reddit feeds. Checkmate, bitches!'
)
STANDARD_ORDER_STR = str(site_urls)

# Classes
class RssFeed:
    """Represents an RSS feed with entries and optional top articles."""
    def __init__(self, entries: list, top_articles: Optional[list] = None) -> None:
        self.entries = entries
        self.top_articles = top_articles if top_articles else []
        self.__post_init__()

    def __post_init__(self) -> None:
        """Ensure top_articles attribute is initialized."""
        if not hasattr(self, 'top_articles'):
            object.__setattr__(self, 'top_articles', [])

    def __setstate__(self, state: dict) -> None:
        """Restore state and reinitialize attributes."""
        object.__setattr__(self, '__dict__', state)
        self.__post_init__()

class DiskCacheWrapper:
    """Wrapper for diskcache to manage caching operations."""
    def __init__(self, cache_dir: str) -> None:
        self.cache = diskcache.Cache(cache_dir)

    def has(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        return key in self.cache

    def get(self, key: str) -> Any:
        """Retrieve a value from the cache by key."""
        return self.cache.get(key)

    def put(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        """Store a value in the cache with an optional timeout."""
        self.cache.set(key, value, expire=timeout)

    def delete(self, key: str) -> None:
        """Delete a key from the cache."""
        self.cache.delete(key)

    def has_feed_expired(self, url: str) -> bool:
        """Check if a feed has expired based on the last fetch time."""
        last_fetch = self.get(url + ":last_fetch")
        if last_fetch is None:
            return True
        return history.has_expired(url, last_fetch)

# Global Variables
history = FeedHistory.FeedHistory(data_file=f"{PATH}/feed_history{str(MODE)}.pickle")
g_c = DiskCacheWrapper(PATH)

# Functions
def format_last_updated(last_fetch: Optional[datetime.datetime]) -> str:
    """Format the last fetch time as 'HH:MM AM/PM'."""
    if not last_fetch:
        return "Unknown"
    return last_fetch.strftime("%I:%M %p")

def format_last_updated_fancy(last_fetch: Optional[datetime.datetime]) -> str:
    """Format the last fetch time as 'X minutes ago' or 'X hours ago'."""
    if not last_fetch:
        return "Unknown"

    now = datetime.datetime.now()
    delta = now - last_fetch
    total_minutes = delta.total_seconds() / 60.0

    if total_minutes < 60:
        rounded_minutes = round(total_minutes / 5.0) * 5
        return f"{int(rounded_minutes)} minutes ago"
    else:
        rounded_hours = round(total_minutes / 60.0)
        if rounded_hours == 1:
            return "1 hour ago"
        return f"{int(rounded_hours)} hours ago"
