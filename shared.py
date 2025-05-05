"""
shared.py

This module contains shared utilities, classes, and constants for the LinuxReport project.
"""

import datetime
import os
import threading
import time
import uuid
from enum import Enum
from typing import Any, Optional, Type
from abc import ABC, abstractmethod

import diskcache
from cacheout import Cache
from filelock import FileLock, Timeout

import FeedHistory

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

# Simple map from Mode enum to URL identifiers - identical to enum values
MODE_MAP = {mode: mode.value for mode in Mode}

# Config modules derived from mode names
CONFIG_MODULES = {mode: f"{mode.value}_report_settings" for mode in Mode}

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

URLS_COOKIE_VERSION = "2"

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
FAVICON = config_settings.CONFIG.FAVICON
LOGO_URL = config_settings.CONFIG.LOGO_URL
WEB_DESCRIPTION = config_settings.CONFIG.WEB_DESCRIPTION
WEB_TITLE = config_settings.CONFIG.WEB_TITLE
ABOVE_HTML_FILE = config_settings.CONFIG.ABOVE_HTML_FILE
CUSTOM_FETCH_CONFIG = config_settings.CONFIG.CUSTOM_FETCH_CONFIG

WELCOME_HTML = (
    '<font size="4">(Displays instantly, refreshes hourly) - Fork me on <a target="_blank"'
    'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
    'href = "https://gitlab.com/keithcu/linuxreport">GitLab. </a></font>'
    '<br/>The Reddit Woke mafia had blocked my user-agent and IP address for political reasons, (I was making max a few requests per hour!!) '
    '<br/>So, I picked a random USER_AGENT and am using <a href = "https://www.torproject.org/">TOR</a> to fetch Reddit feeds. Checkmate, bitches!'
)
STANDARD_ORDER_STR = str(SITE_URLS)


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

    def has_feed_expired(self, url: str) -> bool:
        """Check if a feed has expired based on the last fetch time."""
        last_fetch = self.get_last_fetch(url)
        if last_fetch is None:
            return True
        return history.has_expired(url, last_fetch)

    def get_last_fetch(self, url: str) -> Optional[datetime.datetime]:
        """Get the last fetch time for a URL with caching."""
        cache_key = f"last_fetch::{url}"
        cached_last_fetch = g_cm.get(cache_key)
        if cached_last_fetch is not None:
            return cached_last_fetch
            
        # If not in cache, get from disk
        last_fetch = self.get(url + ":last_fetch")
        g_cm.set(cache_key, last_fetch, ttl=EXPIRE_HOUR)
        return last_fetch

    def set_last_fetch(self, url: str, timestamp: Any, timeout: Optional[int] = None) -> None:
        """Set the last fetch time for a URL and cache it in memory."""
        # Store in disk cache
        self.put(url + ":last_fetch", timestamp, timeout)
        
        # Also update the in-memory cache
        g_cm.set(f"last_fetch::{url}", timestamp, ttl=EXPIRE_HOUR)

# Global Variables
history = FeedHistory.FeedHistory(data_file=f"{PATH}/feed_history{str(MODE)}.pickle")
g_c = DiskCacheWrapper(PATH) #Private cache for each instance
g_cs = DiskCacheWrapper(SPATH) #Shared cache for all instances stored in /run/linuxreport, for weather, etc.
g_cm = Cache(maxsize=100, ttl=3600)  # In-memory cache with per-item TTL (seconds)
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

# Simple non-blocking lock using global Python/diskcache cache (g_cs)
class LockBase(ABC):
    @abstractmethod
    def acquire(self, timeout_seconds: int = 60, wait: bool = False) -> bool:
        pass

    @abstractmethod
    def release(self) -> bool:
        pass

    @abstractmethod
    def __enter__(self):
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @abstractmethod
    def locked(self) -> bool:
        pass


class DiskcacheSqliteLock(LockBase):
    """
    A distributed lock implementation using the global diskcache (with a Sqlite backend).
    This lock supports waiting when a lock is unavailable and provides
    features for reliable multi-process and multi-threaded environments.
    """
    def __init__(self, lock_name: str, owner_prefix: Optional[str] = None):
        self.cache = g_cs
        self.lock_key = f"lock::{lock_name}"
        if owner_prefix is None:
            owner_prefix = f"pid{os.getpid()}_tid{threading.get_ident()}"
        self.owner_id = f"{owner_prefix}_{uuid.uuid4()}"
        self._locked = False

    def acquire(self, timeout_seconds: int = 60, wait: bool = False) -> bool:
        """
        Tries to acquire the lock.
        Args:
            timeout_seconds: How long the lock should be held before expiring
            wait: If True, will wait until the lock is acquired or timeout_seconds is reached
        Returns:
            True if lock was acquired, False otherwise
        """
        if self._locked:
            return True

        start_time = time.monotonic()
        while True:
            acquired = self._attempt_acquire(timeout_seconds)
            if acquired:
                return True
            if not wait:
                return False
            if (time.monotonic() - start_time) > timeout_seconds:
                return False
            time.sleep(0.1)  # Short sleep before retrying

    def _attempt_acquire(self, timeout_seconds: int) -> bool:
        """Internal method that attempts to acquire the lock once."""
        try:
            with self.cache.cache.transact():
                now = time.monotonic()
                current_value = self.cache.get(self.lock_key)
                
                # Lock exists and is still valid
                if current_value is not None:
                    expiry_time = current_value[1]
                    # Lock is still valid
                    if now < expiry_time:
                        return False
                    # Lock exists but has expired - we'll overwrite it
                
                # Set expiry and store our claim
                expiry = now + timeout_seconds
                self.cache.put(self.lock_key, (self.owner_id, expiry), timeout=timeout_seconds + 5)
                
                # Verify our ownership
                final_value = self.cache.get(self.lock_key)
                if final_value is not None and final_value[0] == self.owner_id:
                    self._locked = True
                    return True
                
                self._locked = False
                return False
        except (diskcache.Timeout, Timeout) as e:
            # Log the exception but don't crash
            print(f"Error acquiring lock {self.lock_key}: {e}")
            self._locked = False
            return False
        except Exception as e:
            # Log the exception but don't crash
            print(f"Error acquiring lock {self.lock_key}: {e}")
            self._locked = False
            return False

    def release(self) -> bool:
        """
        Releases the lock if currently held by this instance.
        Returns True if the lock was successfully released, False otherwise.
        """
        if not self._locked:
            return False  # We don't hold the lock

        success = False
        try:
            with self.cache.cache.transact():
                # Verify ownership before deleting
                current_value = self.cache.get(self.lock_key)
                if current_value is not None and current_value[0] == self.owner_id:
                    self.cache.delete(self.lock_key)
                    success = True
        except Exception as e:
            # Log error if needed
            print(f"Error releasing lock {self.lock_key}: {e}")
            success = False
        
        # Whether successful or not, we're no longer locked
        self._locked = False
        return success

    def __enter__(self):
        if not self.acquire(wait=True):
            raise TimeoutError(f"Could not acquire lock '{self.lock_key}'")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def locked(self) -> bool:
        """Check if the lock is currently held by this instance."""
        return self._locked

class FileLockWrapper(LockBase):
    def __init__(self, lock_file_path: str):
        self.lock_file_path = lock_file_path
        self._lock = FileLock(lock_file_path)
        self._is_locked = False

    def acquire(self, timeout_seconds: int = 60, wait: bool = False) -> bool:
        try:
            if wait:
                self._lock.acquire(timeout=timeout_seconds)
            else:
                self._lock.acquire(timeout=0)
            self._is_locked = True
            return True
        except Timeout:
            self._is_locked = False
            return False

    def release(self) -> bool:
        if self._is_locked:
            self._lock.release()
            self._is_locked = False
            return True
        return False

    def __enter__(self):
        acquired = self.acquire()
        if not acquired:
            raise TimeoutError("Failed to acquire lock within the specified timeout.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def locked(self) -> bool:
        return self._is_locked

# Selectable lock class and factory
LOCK_CLASS: Type[LockBase] = DiskcacheSqliteLock

def get_lock(lock_name: str, owner_prefix: Optional[str] = None) -> LockBase:
    """Factory to get a lock instance using the selected lock class."""
    if issubclass(LOCK_CLASS, FileLockWrapper):
        return LOCK_CLASS(lock_name)
    elif issubclass(LOCK_CLASS, DiskcacheSqliteLock):
        return LOCK_CLASS(lock_name)
    else:
        raise TypeError(f"Unsupported lock class: {LOCK_CLASS}")

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
