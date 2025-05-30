"""
shared.py

This module contains shared utilities, classes, and constants for the LinuxReport project.
"""

import datetime
import os
import time
from enum import Enum
from typing import Any, Optional, Type

import diskcache
from cacheout import Cache

import FeedHistory
from SqliteLock import LockBase, DiskcacheSqliteLock, FileLockWrapper

class Mode(str, Enum):
    """Enumeration for different report modes using string values."""
    LINUX_REPORT = "linux"
    COVID_REPORT = "covid"
    TECHNO_REPORT = "techno"
    AI_REPORT = "ai"
    PYTHON_REPORT = "python"
    TRUMP_REPORT = "trump"
    SPACE_REPORT = "space"
    PV_REPORT = "pv"

# Domains allowed for Content Security Policy (CSP) - controls which domains can load resources
# like images, fonts, and scripts on our pages
ALLOWED_DOMAINS = [
    'https://linuxreport.net',
    'https://www.linuxreport.net',

    'https://covidreport.org',
    'https://www.covidreport.org',

    'https://aireport.keithcu.com',

    'https://pvreport.org',
    'https://www.pvreport.org',

    'https://trumpreport.info',
    'https://www.trumpreport.info',

    'https://news.thedetroitilove.com',

    'http://127.0.0.1:5000',
    'https://fonts.googleapis.com',
    'https://fonts.gstatic.com',
]

# Domains allowed to make API requests to this server (CORS only)
# These domains can send requests to our endpoints
ALLOWED_REQUESTER_DOMAINS = [
    'https://covidreport.org',
    'https://www.covidreport.org',

    'https://aireport.keithcu.com',

    'https://pvreport.org',
    'https://www.pvreport.org',

    'https://trumpreport.info',
    'https://www.trumpreport.info',

    'https://news.thedetroitilove.com',

    'https://linuxreport.net',
    'https://www.linuxreport.net',
    # Add more domains as needed
]

ENABLE_CORS = True

# Simple map from Mode enum to URL identifiers - identical to enum values
MODE_MAP = {mode: mode.value for mode in Mode}

# Config modules derived from mode names
CONFIG_MODULES = {mode: f"{mode.value}_report_settings" for mode in Mode}

# Path for code and cache
PATH: str = os.path.dirname(os.path.abspath(__file__))

# Shared path for weather, etc.
SPATH: str = "/run/linuxreport"
TZ = FeedHistory.FeedConfig.TZ
EXPIRE_MINUTES: int = 60 * 5
EXPIRE_HOUR: int = 3600
EXPIRE_DAY: int = 3600 * 12
EXPIRE_WEEK: int = 86400 * 7
EXPIRE_YEARS: int = 86400 * 365 * 2

MODE = Mode.AI_REPORT

URLS_COOKIE_VERSION = "2"

# Enable or disable URL customization functionality (both reordering and adding custom URLs)
ENABLE_URL_CUSTOMIZATION = True

# Enable CDN delivery for images - overrides the URL_IMAGES path with CDN URL
ENABLE_URL_IMAGE_CDN_DELIVERY = True
CDN_IMAGE_URL = "https://linuxreportstatic.us-ord-1.linodeobjects.com/"

# Enable fetching non-custom feeds from object store instead of original URLs
ENABLE_OBJECT_STORE_FEEDS = False
OBJECT_STORE_FEED_URL = "https://linuxreportupdates.us-ord-1.linodeobjects.com/feeds/"
OBJECT_STORE_FEED_TIMEOUT = 15 * 60  # 15 minutes in seconds

# Enable publishing feeds to object store when fetched
ENABLE_OBJECT_STORE_FEED_PUBLISH = False

# Enable infinite scroll view mode for mobile
INFINITE_SCROLL_MOBILE = True

# Debug mode for infinite scroll (enables on desktop)
INFINITE_SCROLL_DEBUG = True

RSS_TIMEOUT = 30  # Timeout value in seconds for RSS feed operations

MAX_ITEMS = 40  # Maximum number of items to process / remember in RSS feeds

config_module_name = CONFIG_MODULES.get(MODE)
if not config_module_name:
    raise ValueError("Invalid mode specified.")

config_settings = __import__(config_module_name, fromlist=["CONFIG"])

ALL_URLS = config_settings.CONFIG.ALL_URLS
SITE_URLS = config_settings.CONFIG.SITE_URLS
USER_AGENT = config_settings.CONFIG.USER_AGENT
URL_IMAGES = config_settings.CONFIG.URL_IMAGES
FAVICON = URL_IMAGES + config_settings.CONFIG.FAVICON
LOGO_URL = URL_IMAGES + config_settings.CONFIG.LOGO_URL
WEB_DESCRIPTION = config_settings.CONFIG.WEB_DESCRIPTION
WEB_TITLE = config_settings.CONFIG.WEB_TITLE
ABOVE_HTML_FILE = f"{MODE.value}reportabove.html"
CUSTOM_FETCH_CONFIG = config_settings.CONFIG.CUSTOM_FETCH_CONFIG
SITE_PATH = config_settings.CONFIG.PATH

# If CDN delivery is enabled, override URL_IMAGES with the CDN URL
if ENABLE_URL_IMAGE_CDN_DELIVERY:
    URL_IMAGES = CDN_IMAGE_URL
    FAVICON = CDN_IMAGE_URL + config_settings.CONFIG.FAVICON
    LOGO_URL = CDN_IMAGE_URL + config_settings.CONFIG.LOGO_URL


WELCOME_HTML = (
    '<font size="4">(Displays instantly, refreshes hourly) - Fork me on <a target="_blank"'
    'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
    'href = "https://gitlab.com/keithcu/linuxreport">GitLab. </a></font>'
    '<br/>Now using <a href="https://openrouter.ai" target="_blank">OpenRouter</a> to access a variety of free LLMs for selecting the top headlines.'
)
STANDARD_ORDER_STR = str(SITE_URLS)

# 1) Define the order of your js modules
_JS_MODULES = [
    'core.js',
    'weather.js',
    'chat.js',
    'config.js'
]

# Common webbot user agents that should not trigger background refreshes or OpenWeather queries
WEB_BOT_USER_AGENTS = [
    # Google Crawlers
    "Googlebot",
    "Google-InspectionTool",
    "Google-Site-Verification",
    "Google-Extended",

    # Bing Crawlers
    "Bingbot",
    "AdIdxBot",
    "MicrosoftPreview",

    # Yandex Crawlers
    "YandexBot",
    "YandexMobileBot",
    "YandexImages",

    # AI-Related Crawlers
    "GPTBot",
    "ClaudeBot",
    "CCBot",
    "Bytespider",
    "Applebot",

    # Other Common Crawlers
    "Baiduspider",
    "DuckDuckBot",
    "AhrefsBot",
    "SemrushBot",
    "MJ12bot",
    "KeybaseBot",
    "Lemmy",
    "CookieHubScan",
    "Hydrozen.io",
    "SummalyBot",
    "DotBot",
    "Coccocbot"
]



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

    def get(self, key: str) -> Any:
        return self.cache.get(key)

    def put(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        self.cache.set(key, value, expire=timeout)

    def delete(self, key: str) -> None:
        self.cache.delete(key)

    def has(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        return key in self.cache

    def has_feed_expired(self, url: str, last_fetch: Optional[datetime.datetime] = None) -> bool:
        """Check if a feed has expired based on the last fetch time.
        
        Args:
            url: The URL of the feed to check
            last_fetch: Optional pre-fetched last_fetch timestamp to avoid duplicate calls
        
        Returns:
            True if the feed has expired, False otherwise
        """
        if last_fetch is None:
            last_fetch = self.get_last_fetch(url)
        if last_fetch is None:
            return True
        return history.has_expired(url, last_fetch)

    def get_last_fetch(self, url: str) -> Optional[datetime.datetime]:
        """Get the last fetch time for a URL from the shared disk cache."""
        last_fetch = self.get(url + ":last_fetch")
        return last_fetch

    def set_last_fetch(self, url: str, timestamp: Any, timeout: Optional[int] = None) -> None:
        """Set the last fetch time for a URL in the shared disk cache."""
        # Store in disk cache (g_c) - this is the shared, authoritative source.
        self.put(url + ":last_fetch", timestamp, timeout)

# Global Variables
history = FeedHistory.FeedHistory(data_file=f"{PATH}/feed_history-{str(MODE.value)}")
g_c = DiskCacheWrapper(PATH) #Private cache for each instance
g_cs = DiskCacheWrapper(SPATH) #Shared cache for all instances stored in /run/linuxreport, for weather, etc.
g_cm = Cache()  # In-memory cache with per-item TTL
# --- Shared Keys ---
GLOBAL_FETCH_MODE_LOCK_KEY = "global_fetch_mode"

# Configuration for Chat Cache
# Set to True to use the shared cache (g_cs) for chat comments and banned IPs
# Set to False to use the site-specific cache (g_c)
USE_SHARED_CACHE_FOR_CHAT = False

# Helper function to get the appropriate cache for chat features
def get_chat_cache() -> DiskCacheWrapper:
    """Returns the cache instance to use for chat based on the configuration."""
    return g_cs if USE_SHARED_CACHE_FOR_CHAT else g_c

# Selectable lock class and factory
LOCK_CLASS: Type[LockBase] = DiskcacheSqliteLock

def get_lock(lock_name: str, owner_prefix: Optional[str] = None) -> LockBase:
    """Get a DiskcacheSqliteLock instance."""
    return DiskcacheSqliteLock(lock_name, g_cs.cache, owner_prefix)

# Original factory implementation (commented out for reference):
# def get_lock(lock_name: str, owner_prefix: Optional[str] = None) -> LockBase:
#     """Factory to get a lock instance using the selected lock class."""
#     if issubclass(LOCK_CLASS, FileLockWrapper):
#         return LOCK_CLASS(lock_name)
#     elif issubclass(LOCK_CLASS, DiskcacheSqliteLock):
#         return LOCK_CLASS(lock_name, g_cs.cache, owner_prefix)
#     else:
#         raise TypeError(f"Unsupported lock class: {LOCK_CLASS}")

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

_file_cache = {}
_FILE_CHECK_INTERVAL_SECONDS = 5 * 60 # 5 minutes

def get_cached_file_content(file_path, encoding='utf-8'):
    """Return content of any file, caching and invalidating when it changes.
    Checks mtime only if _FILE_CHECK_INTERVAL_SECONDS have passed since the last check.
    """
    now = time.monotonic()
    entry = _file_cache.get(file_path)

    # Check if cache entry exists and if we should skip the mtime check
    if entry and (now - entry.get('last_check_time', 0)) < _FILE_CHECK_INTERVAL_SECONDS:
        return entry['content']

    # Proceed with mtime check or initial load
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        # File doesn't exist or inaccessible
        if entry: # Remove stale entry if it exists
            del _file_cache[file_path]
        return ''

    # If cache entry exists and mtime matches, update check time and return content
    if entry and entry['mtime'] == mtime:
        entry['last_check_time'] = now
        return entry['content']

    # Read file fresh or because mtime changed
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
    except FileNotFoundError:
        content = ''
        # Ensure mtime reflects the non-existent state if we somehow got here
        mtime = -1 # Or some other indicator that it's gone

    _file_cache[file_path] = {'mtime': mtime, 'content': content, 'last_check_time': now}
    return content

def clear_page_caches():
    """Clear all page caches from the in-memory cache."""
    # Get all keys from the cache
    keys = list(g_cm.keys())
    # Delete all keys that start with page-cache:
    for key in keys:
        if key.startswith('page-cache:'):
            g_cm.delete(key)

