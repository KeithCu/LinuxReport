"""
Shared Utilities Module for LinuxReport

This module contains core shared utilities, constants, and configuration management
for the LinuxReport project. It provides centralized access to common functionality
across the application including caching, mode management, RSS feed data structures,
and configuration handling.

Key Features:
- Configuration management and mode handling
- Distributed caching with diskcache and memory caches
- RSS feed data structures and utilities
- Lock management for distributed operations
- Application-wide constants and settings
- Dynamic configuration loading based on report modes

Note: Rate limiting, web bot detection, and request utilities have been moved to
request_utils.py. Application initialization and Flask setup have been moved to
app.py. Database models and cache wrappers have been moved to models.py.

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
from flask_limiter import Limiter
from flask_restful import Api

# Local application imports
import FeedHistory
from SqliteLock import LockBase, DiskcacheSqliteLock
from app_config import get_settings_config, get_allowed_domains, get_allowed_requester_domains, get_cdn_config, get_object_store_config, get_welcome_html, get_reports_config, get_storage_config
from request_utils import get_rate_limit_key, dynamic_rate_limit, WEB_BOT_USER_AGENTS, get_ip_prefix, format_last_updated
from models import DiskCacheWrapper, RssFeed

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

# Load configuration from centralized config manager
settings = get_settings_config()

# Export user-configurable settings
ALLOWED_DOMAINS = get_allowed_domains()
ALLOWED_REQUESTER_DOMAINS = get_allowed_requester_domains()
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
reports_config = get_reports_config()
Mode = Mode.from_config(reports_config.get('modes', []))

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
storage_config = get_storage_config()
SPATH: str = storage_config['shared_path']
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
cdn_config = get_cdn_config()
CDN_IMAGE_URL = cdn_config['image_url']
ENABLE_URL_IMAGE_CDN_DELIVERY = cdn_config['enabled']

# =============================================================================
# OBJECT STORAGE CONFIGURATION
# =============================================================================

# Enable fetching non-custom feeds from object store instead of original URLs
object_store_config = get_object_store_config()
ENABLE_OBJECT_STORE_FEEDS = object_store_config['enabled']
OBJECT_STORE_FEED_URL = object_store_config['feed_url']
OBJECT_STORE_FEED_TIMEOUT = object_store_config['feed_timeout']

# Enable publishing feeds to object store when fetched
ENABLE_OBJECT_STORE_FEED_PUBLISH = object_store_config['enable_publish']

# =============================================================================
# USER INTERFACE SETTINGS
# =============================================================================

# Enable infinite scroll view mode for mobile
INFINITE_SCROLL_MOBILE = True

# Debug mode for infinite scroll (enables on desktop)
INFINITE_SCROLL_DEBUG = True

# =============================================================================
# GEOLOCATION SETTINGS
# =============================================================================

# Disable IP-based geolocation when user provides browser geolocation
# When True, the system will use default coordinates (Detroit) instead of IP-based location
# when browser geolocation is not available or denied
DISABLE_IP_GEOLOCATION = True

# =============================================================================
# RSS FEED CONFIGURATION
# =============================================================================

# Timeout value in seconds for RSS feed operations
RSS_TIMEOUT = 30

# Maximum number of items to process / remember in RSS feeds
MAX_ITEMS = 40

# Welcome message from config
WELCOME_HTML = get_welcome_html()

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
# RATE LIMITING CONFIGURATION
# =============================================================================

# Initialize Flask-Limiter with dynamic rate limiting
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=["10 per minute"],
    strategy="fixed-window"
)

# =============================================================================
# FLASK-RESTFUL API GLOBAL
# =============================================================================

# Global Flask-RESTful API instance (initialized in app.py)
API = None

def set_flask_restful_api(api_instance):
    """
    Set the global Flask-RESTful API instance.
    
    Args:
        api_instance: Flask-RESTful API instance
    """
    global API
    API = api_instance

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


