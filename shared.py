"""
Shared Utilities Module for LinuxReport

This module contains shared utilities, classes, constants, and configuration management
for the LinuxReport project. It provides centralized access to common functionality
across the application including caching, rate limiting, RSS feed management, and
configuration handling.

Key Features:
- Configuration management and mode handling
- Distributed caching with diskcache and memory caches
- Rate limiting with dynamic limits based on user type
- RSS feed data structures and utilities
- Web bot detection and filtering
- Lock management for distributed operations

Author: LinuxReport System
License: See LICENSE file
"""

# Standard library imports
import datetime
import os
from enum import Enum
from typing import Any, Optional, Type

# Third-party imports
import diskcache
from cacheout import Cache
import ipaddress

# Flask-related imports
from flask import request
from flask_login import current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Local application imports
import FeedHistory
from SqliteLock import LockBase, DiskcacheSqliteLock
from models import load_config

# =============================================================================
# FLASK MONITORING DASHBOARD CONFIGURATION
# =============================================================================

# Flask-MonitoringDashboard configuration
FLASK_DASHBOARD = False
FLASK_DASHBOARD_USERNAME = "admin"  # Change this to your preferred username
FLASK_DASHBOARD_PASSWORD = "admin"  # Change this to your preferred password

# =============================================================================
# CONFIGURATION LOADING AND SETTINGS
# =============================================================================

# Load configuration from models
config = load_config()
settings = config.get('settings', {})

# Export user-configurable settings
ALLOWED_DOMAINS = settings.get('allowed_domains', [])
ALLOWED_REQUESTER_DOMAINS = settings.get('allowed_requester_domains', [])
ENABLE_CORS = True

# =============================================================================
# MODE ENUMERATION AND CONFIGURATION
# =============================================================================

class Mode(str, Enum):
    """
    Enumeration for different report modes using string values.
    
    This enum defines the available report types in the system. It can be
    dynamically extended with additional modes from the configuration file.
    """
    # Base modes that are always available
    LINUX_REPORT = "linux"
    COVID_REPORT = "covid"
    TECHNO_REPORT = "techno"
    AI_REPORT = "ai"
    PYTHON_REPORT = "python"
    TRUMP_REPORT = "trump"
    SPACE_REPORT = "space"
    PV_REPORT = "pv"

    @classmethod
    def from_config(cls, config_modes):
        """
        Create a new Mode enum with additional modes from config.
        
        Args:
            config_modes (list): List of mode configurations from config file
            
        Returns:
            Enum: New enum class with all base and configured modes
        """
        # Start with base modes
        mode_dict = {mode.name: mode.value for mode in cls}
        
        # Add modes from config
        for mode in config_modes:
            name = mode['name'].upper()
            if name not in mode_dict:
                mode_dict[name] = mode['name']
        
        # Create new enum class with all modes
        return Enum('Mode', mode_dict, type=str)

# Create Mode enum with config modes
Mode = Mode.from_config(config['reports']['modes'])

# Simple map from Mode enum to URL identifiers - identical to enum values
MODE_MAP = {mode: mode.value for mode in Mode}

# Config modules derived from mode names
CONFIG_MODULES = {mode: f"{mode.value}_report_settings" for mode in Mode}

# =============================================================================
# PATH AND STORAGE CONFIGURATION
# =============================================================================

# Path for code and cache
PATH: str = os.path.dirname(os.path.abspath(__file__))

# Shared path for weather, etc.
SPATH: str = config['storage']['shared_path']
TZ = FeedHistory.FeedConfig.TZ

# =============================================================================
# CACHE EXPIRATION CONSTANTS
# =============================================================================

# Cache expiration time constants (in seconds)
EXPIRE_MINUTES: int = 60 * 5      # 5 minutes
EXPIRE_HOUR: int = 3600           # 1 hour
EXPIRE_DAY: int = 3600 * 12       # 12 hours
EXPIRE_WEEK: int = 86400 * 7      # 7 days
EXPIRE_YEARS: int = 86400 * 365 * 2  # 2 years

# =============================================================================
# APPLICATION MODE AND VERSION SETTINGS
# =============================================================================

# Current application mode
MODE = Mode.AI_REPORT

# URL cookie version for cache invalidation
URLS_COOKIE_VERSION = "2"

# Enable or disable URL customization functionality (both reordering and adding custom URLs)
ENABLE_URL_CUSTOMIZATION = True

# =============================================================================
# CDN AND IMAGE DELIVERY SETTINGS
# =============================================================================

# CDN and image settings from config
CDN_IMAGE_URL = settings['cdn']['image_url']
ENABLE_URL_IMAGE_CDN_DELIVERY = settings['cdn']['enabled']

# =============================================================================
# OBJECT STORAGE CONFIGURATION
# =============================================================================

# Enable fetching non-custom feeds from object store instead of original URLs
ENABLE_OBJECT_STORE_FEEDS = settings['object_store']['enabled']
OBJECT_STORE_FEED_URL = settings['object_store']['feed_url']
OBJECT_STORE_FEED_TIMEOUT = settings['object_store']['feed_timeout']

# Enable publishing feeds to object store when fetched
ENABLE_OBJECT_STORE_FEED_PUBLISH = settings['object_store']['enable_publish']

# =============================================================================
# USER INTERFACE SETTINGS
# =============================================================================

# Enable infinite scroll view mode for mobile
INFINITE_SCROLL_MOBILE = True

# Debug mode for infinite scroll (enables on desktop)
INFINITE_SCROLL_DEBUG = True

# Enable compression caching for faster response times (disabled by default)
ENABLE_COMPRESSION_CACHING = False

# =============================================================================
# RSS FEED CONFIGURATION
# =============================================================================

# Timeout value in seconds for RSS feed operations
RSS_TIMEOUT = 30

# Maximum number of items to process / remember in RSS feeds
MAX_ITEMS = 40

# Welcome message from config
WELCOME_HTML = settings['welcome_html']

# =============================================================================
# DYNAMIC CONFIGURATION LOADING
# =============================================================================

# Load configuration module based on current mode
config_module_name = CONFIG_MODULES.get(MODE)
if not config_module_name:
    raise ValueError("Invalid mode specified.")

config_settings = __import__(config_module_name, fromlist=["CONFIG"])

# Extract configuration values
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

# Override image URLs with CDN if enabled
if ENABLE_URL_IMAGE_CDN_DELIVERY:
    URL_IMAGES = CDN_IMAGE_URL
    FAVICON = CDN_IMAGE_URL + config_settings.CONFIG.FAVICON
    LOGO_URL = CDN_IMAGE_URL + config_settings.CONFIG.LOGO_URL

STANDARD_ORDER_STR = str(SITE_URLS)

# =============================================================================
# JAVASCRIPT MODULE CONFIGURATION
# =============================================================================

# Define the order of JavaScript modules for loading
_JS_MODULES = [
    'infinitescroll.js',
    'core.js',
    'weather.js',
    'chat.js',
    'config.js',
]

# =============================================================================
# WEB BOT DETECTION
# =============================================================================

# Common web bot user agents that should not trigger background refreshes or OpenWeather queries
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

# =============================================================================
# RATE LIMITING CONFIGURATION
# =============================================================================

def get_rate_limit_key():
    """
    Get rate limit key based on user type and IP address.
    
    This function determines the appropriate rate limiting key based on:
    - Whether the user is authenticated (admin)
    - Whether the request is from a known web bot
    - The remote IP address
    
    Returns:
        str: Rate limit key in format "type:ip_address"
    """
    # Check if user is authenticated (admin)
    if current_user.is_authenticated:
        return f"admin:{get_remote_address()}"

    # Check if request is from a web bot
    user_agent = request.headers.get('User-Agent', '')
    is_web_bot = any(bot in user_agent for bot in WEB_BOT_USER_AGENTS)
    
    if is_web_bot:
        return f"bot:{get_remote_address()}"
    
    return f"user:{get_remote_address()}"

def dynamic_rate_limit():
    """
    Return rate limit based on user type.
    
    Provides different rate limits for different types of users:
    - Admins: Higher limits for administrative functions
    - Bots: Lower limits to prevent abuse
    - Regular users: Standard limits
    
    Returns:
        str: Rate limit string in format "X per minute"
    """
    key = get_rate_limit_key()
    
    if key.startswith("admin:"):
        return "50 per minute"  # Higher limits for admins
    elif key.startswith("bot:"):
        return "10 per minute"    # Lower limits for bots
    else:
        return "20 per minute"  # Standard limits for users

# Initialize Flask-Limiter with dynamic rate limiting
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=["10 per minute"],
    strategy="fixed-window"
)

# =============================================================================
# DATA STRUCTURES AND CLASSES
# =============================================================================

class RssFeed:
    """
    Represents an RSS feed with entries and optional top articles.
    
    This class encapsulates RSS feed data and provides methods for
    managing feed entries and top article tracking.
    """
    
    def __init__(self, entries: list, top_articles: Optional[list] = None) -> None:
        """
        Initialize an RSS feed with entries and optional top articles.
        
        Args:
            entries (list): List of RSS feed entries
            top_articles (Optional[list]): List of top articles to track
        """
        self.entries = entries
        self.top_articles = top_articles if top_articles else []
        self.__post_init__()

    def __post_init__(self) -> None:
        """Ensure top_articles attribute is properly initialized."""
        if not hasattr(self, 'top_articles'):
            object.__setattr__(self, 'top_articles', [])

    def __setstate__(self, state: dict) -> None:
        """
        Restore state and reinitialize attributes during unpickling.
        
        Args:
            state (dict): State dictionary from pickle
        """
        object.__setattr__(self, '__dict__', state)
        self.__post_init__()

class DiskCacheWrapper:
    """
    Wrapper for diskcache to manage caching operations with additional functionality.
    
    This wrapper provides a consistent interface for disk-based caching operations
    and adds custom methods for feed management and expiration checking.
    """
    
    def __init__(self, cache_dir: str) -> None:
        """
        Initialize the cache wrapper with a directory.
        
        Args:
            cache_dir (str): Directory path for cache storage
        """
        self.cache = diskcache.Cache(cache_dir)

    def get(self, key: str) -> Any:
        """
        Retrieve a value from the cache.
        
        Args:
            key (str): Cache key to retrieve
            
        Returns:
            Any: Cached value or None if not found
        """
        return self.cache.get(key)

    def put(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        """
        Store a value in the cache with optional expiration.
        
        Args:
            key (str): Cache key
            value (Any): Value to store
            timeout (Optional[int]): Expiration time in seconds
        """
        self.cache.set(key, value, expire=timeout)

    def delete(self, key: str) -> None:
        """
        Remove a key from the cache.
        
        Args:
            key (str): Cache key to delete
        """
        self.cache.delete(key)

    def has(self, key: str) -> bool:
        """
        Check if a key exists in the cache.
        
        Args:
            key (str): Cache key to check
            
        Returns:
            bool: True if key exists, False otherwise
        """
        return key in self.cache

    def has_feed_expired(self, url: str, last_fetch: Optional[datetime.datetime] = None) -> bool:
        """
        Check if a feed has expired based on the last fetch time.
        
        Args:
            url (str): The URL of the feed to check
            last_fetch (Optional[datetime.datetime]): Pre-fetched last_fetch timestamp 
                                                    to avoid duplicate calls
        
        Returns:
            bool: True if the feed has expired, False otherwise
        """
        if last_fetch is None:
            last_fetch = self.get_last_fetch(url)
        if last_fetch is None:
            return True
        return history.has_expired(url, last_fetch)

    def get_all_last_fetches(self, urls: list[str]) -> dict[str, Optional[datetime.datetime]]:
        """
        Get last fetch times for multiple URLs in a single operation.
        
        Args:
            urls (list[str]): List of URLs to check
            
        Returns:
            dict[str, Optional[datetime.datetime]]: Dictionary mapping URLs to their last fetch times
        """
        all_fetches = self.get('all_last_fetches') or {}
        return {url: all_fetches.get(url) for url in urls}

    def get_last_fetch(self, url: str) -> Optional[datetime.datetime]:
        """
        Get the last fetch time for a URL from the shared disk cache.
        
        Args:
            url (str): URL to get last fetch time for
            
        Returns:
            Optional[datetime.datetime]: Last fetch timestamp or None if not found
        """
        all_fetches = self.get('all_last_fetches')
        if url in all_fetches:
            return all_fetches[url]
        return None

    def set_last_fetch(self, url: str, timestamp: Any, timeout: Optional[int] = None) -> None:
        """
        Set the last fetch time for a URL in the shared disk cache.
        
        Args:
            url (str): URL to set last fetch time for
            timestamp (Any): Timestamp to store
            timeout (Optional[int]): Cache expiration time
        """
        all_fetches = self.get('all_last_fetches')
        all_fetches[url] = timestamp
        self.put('all_last_fetches', all_fetches, timeout)

# =============================================================================
# GLOBAL CACHE INSTANCES
# =============================================================================

# Initialize global cache instances
history = FeedHistory.FeedHistory(data_file=f"{PATH}/feed_history-{str(MODE.value)}")
g_c = DiskCacheWrapper(PATH)      # Private cache for each instance
g_cs = DiskCacheWrapper(SPATH)    # Shared cache for all instances stored in /run/linuxreport, for weather, etc.
g_cm = Cache()                    # In-memory cache with per-item TTL

# =============================================================================
# LOCK MANAGEMENT
# =============================================================================

# Shared lock key for global fetch operations
GLOBAL_FETCH_MODE_LOCK_KEY = "global_fetch_mode"

# Selectable lock class and factory
LOCK_CLASS: Type[LockBase] = DiskcacheSqliteLock

def get_lock(lock_name: str, owner_prefix: Optional[str] = None) -> LockBase:
    """
    Get a DiskcacheSqliteLock instance for distributed locking.
    
    Args:
        lock_name (str): Name of the lock to acquire
        owner_prefix (Optional[str]): Prefix for lock owner identification
        
    Returns:
        LockBase: Lock instance for distributed operations
    """
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

# =============================================================================
# CHAT CACHE CONFIGURATION
# =============================================================================

# Configuration for Chat Cache
# Set to True to use the shared cache (g_cs) for chat comments and banned IPs
# Set to False to use the site-specific cache (g_c)
USE_SHARED_CACHE_FOR_CHAT = False

def get_chat_cache() -> DiskCacheWrapper:
    """
    Returns the cache instance to use for chat features based on configuration.
    
    Returns:
        DiskCacheWrapper: Appropriate cache instance for chat functionality
    """
    return g_cs if USE_SHARED_CACHE_FOR_CHAT else g_c

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def run_one_time_last_fetch_migration(all_urls):
    """
    Performs a one-time migration of last_fetch times from old cache keys to the
    new unified 'all_last_fetches' cache. This is controlled by a flag to ensure
    it only runs once.
    
    Args:
        all_urls (list): List of all URLs to migrate
    """
    with get_lock("last_fetch_migration_lock"):
        if not g_c.has('last_fetch_migration_complete'):
            print("Running one-time migration for last_fetch times...")
            all_fetches = g_c.get('all_last_fetches') or {}
            updated = False
            
            for url in all_urls:
                if url not in all_fetches:
                    old_last_fetch = g_c.get(url + ":last_fetch")
                    if old_last_fetch:
                        print(f"Migrating last_fetch for {url}.")
                        all_fetches[url] = old_last_fetch
                        updated = True
            
            if updated:
                g_c.put('all_last_fetches', all_fetches, timeout=EXPIRE_YEARS)
                
            # Set the flag to indicate migration is complete
            g_c.put('last_fetch_migration_complete', True, timeout=EXPIRE_YEARS)
            print("Last_fetch migration complete.")

def format_last_updated(last_fetch: Optional[datetime.datetime]) -> str:
    """
    Format the last fetch time as 'HH:MM AM/PM' for display.
    
    Args:
        last_fetch (Optional[datetime.datetime]): Timestamp to format
        
    Returns:
        str: Formatted time string or "Unknown" if no timestamp
    """
    if not last_fetch:
        return "Unknown"
    return last_fetch.strftime("%I:%M %p")

def clear_page_caches():
    """
    Clear all page caches from the in-memory cache.
    
    This function removes all cached page data to force fresh content
    generation on the next request.
    """
    # Get all keys from the cache
    keys = list(g_cm.keys())
    # Delete all keys that start with page-cache:
    for key in keys:
        if key.startswith('page-cache:'):
            g_cm.delete(key)

def get_ip_prefix(ip_str):
    """
    Extract the first part of IPv4 or the first block of IPv6 for grouping purposes.
    
    Args:
        ip_str (str): IP address string to process
        
    Returns:
        str: First octet of IPv4 or first block of IPv6, or "Invalid IP" on error
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        if isinstance(ip, ipaddress.IPv4Address):
            return ip_str.split('.')[0]
        elif isinstance(ip, ipaddress.IPv6Address):
            return ip_str.split(':')[0]
    except ValueError:
        return "Invalid IP"
    return None

