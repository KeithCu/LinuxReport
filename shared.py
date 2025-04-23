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
from typing import Any, Optional, cast, Type
from abc import ABC, abstractmethod
import multiprocessing

import diskcache
import fasteners

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

RSS_TIMEOUT = 30  # Timeout value in seconds for RSS feed operations

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

    # Feed cache accessors for clarity
    def get_feed(self, url: str) -> Optional[RssFeed]:
        """Retrieve a raw RSS feed from cache."""
        value = self.get(url)
        return cast(Optional[RssFeed], value)

    def set_feed(self, url: str, feed: RssFeed, timeout: Optional[int] = None) -> None:
        """Cache a raw RSS feed with optional timeout."""
        if not isinstance(feed, RssFeed):
            raise TypeError(f"set_feed expects RssFeed, got {type(feed).__name__}")
        self.put(url, feed, timeout)

    def get_last_fetch(self, url: str) -> Optional[datetime.datetime]:
        """Get the last fetch timestamp for a feed."""
        value = self.get(url + ":last_fetch")
        return cast(Optional[datetime.datetime], value)

    def set_last_fetch(self, url: str, timestamp: Any, timeout: Optional[int] = None) -> None:
        """Cache the last fetch timestamp for a feed."""
        self.put(url + ":last_fetch", timestamp, timeout)

    # Template cache accessors for clarity
    def get_template(self, site_key: str) -> Optional[str]:
        """Retrieve a rendered template from cache."""
        value = self.get(site_key)
        return cast(Optional[str], value)

    def set_template(self, site_key: str, template: str, timeout: Optional[int] = None) -> None:
        """Cache a rendered template with optional timeout."""
        if not isinstance(template, str):
            raise TypeError(f"set_template expects str, got {type(template).__name__}")
        self.put(site_key, template, timeout)

# Global Variables
history = FeedHistory.FeedHistory(data_file=f"{PATH}/feed_history{str(MODE)}.pickle")
g_c = DiskCacheWrapper(PATH) #Private cache for each instance
g_cs = DiskCacheWrapper(SPATH) #Shared cache for all instances

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
    def acquire(self, timeout_seconds: int = 60, wait: bool = False, 
                retry_delay: float = 0.5, max_wait_seconds: float = 30) -> bool:
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

    @abstractmethod
    def force_release(self) -> bool:
        pass

class DiskcacheSqliteLock(LockBase):
    """
    A distributed lock implementation using the global diskcache (with a Sqlite backend).
    
    This lock supports waiting/retrying when a lock is unavailable and provides
    features for reliable multi-process and multi-threaded environments:
    
    - Wait with configurable retry strategy
    - Deadlock prevention with configurable timeouts
    - Ownership verification to prevent accidental releases
    - Self-repair for abandoned locks (with ownership verification)
    """
    def __init__(self, lock_name: str, owner_prefix: Optional[str] = None):
        self.cache = g_cs
        self.lock_key = f"lock::{lock_name}"
        if owner_prefix is None:
            owner_prefix = f"pid{os.getpid()}_tid{threading.get_ident()}"
        self.owner_id = f"{owner_prefix}_{uuid.uuid4()}"
        self._locked = False
        
    def acquire(self, timeout_seconds: int = 60, wait: bool = False, 
                retry_delay: float = 0.5, max_wait_seconds: float = 30) -> bool:
        """
        Tries to acquire the lock with support for waiting/retrying.
        
        Args:
            timeout_seconds: How long the lock should be held before expiring
            wait: If True, will wait and retry until the lock is acquired or max_wait_seconds is reached
            retry_delay: Seconds between retry attempts
            max_wait_seconds: Maximum seconds to wait for the lock if wait=True
            
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
                
            # If not waiting or we've exceeded max wait time, return False
            if not wait or (time.monotonic() - start_time > max_wait_seconds):
                return False
                
            # Sleep before retrying
            time.sleep(retry_delay)
    
    def _attempt_acquire(self, timeout_seconds: int) -> bool:
        """Internal method that attempts to acquire the lock once."""
        try:
            with self.cache.cache.transact():
                now = time.monotonic()
                current_value = self.cache.get(self.lock_key)
                
                # Lock exists and is still valid
                if current_value is not None:
                    owner, expiry_time = current_value
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
        
    def force_release(self) -> bool:
        """
        Force-release any lock with this name, regardless of ownership.
        USE WITH EXTREME CAUTION as this can cause race conditions.
        Returns True if a lock was released, False if no lock existed.
        """
        try:
            current_value = self.cache.get(self.lock_key)
            if current_value is not None:
                self.cache.delete(self.lock_key)
                return True
            return False
        except Exception as e:
            print(f"Error force-releasing lock {self.lock_key}: {e}")
            return False

class FastenersFileLock(LockBase):
    """
    A file-based lock using the fasteners library, with added thread safety.
    Suitable for local inter-process and inter-thread locking.
    """
    _thread_locks = {}
    _thread_locks_lock = threading.Lock()

    def __init__(self, lock_name: str, owner_prefix: Optional[str] = None):
        self.lock_file = os.path.join(SPATH, f"{lock_name}.lock")
        self._lock = fasteners.InterProcessLock(self.lock_file)
        # Ensure a unique threading.Lock per lock_file
        with FastenersFileLock._thread_locks_lock:
            if self.lock_file not in FastenersFileLock._thread_locks:
                FastenersFileLock._thread_locks[self.lock_file] = threading.Lock()
            self._thread_lock = FastenersFileLock._thread_locks[self.lock_file]
        self._locked = False

    def acquire(self, timeout_seconds: int = 60, wait: bool = False, 
                retry_delay: float = 0.5, max_wait_seconds: float = 30) -> bool:
        if self._locked:
            return True
        # Acquire thread lock first
        thread_acquired = self._thread_lock.acquire(timeout=max_wait_seconds if wait else 0)
        if not thread_acquired:
            return False
        try:
            if wait:
                acquired = self._lock.acquire(blocking=True, timeout=max_wait_seconds)
            else:
                acquired = self._lock.acquire(blocking=False)
            self._locked = acquired
            if not acquired:
                self._thread_lock.release()
            return acquired
        except Exception:
            self._thread_lock.release()
            raise

    def release(self) -> bool:
        if self._locked:
            self._lock.release()
            self._thread_lock.release()
            self._locked = False
            return True
        return False

    def __enter__(self):
        if not self.acquire(wait=True):
            raise TimeoutError(f"Could not acquire fasteners lock '{self.lock_file}'")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def locked(self) -> bool:
        return self._locked

    def force_release(self) -> bool:
        # Not supported by fasteners; just try to release if locked
        if self._locked:
            self.release()
            return True
        return False

class MultiprocessLock(LockBase):
    """
    A lock using multiprocessing.Lock for inter-process and inter-thread safety (on the same machine).
    Includes print logging for acquire/release/force_release.
    """
    _locks = {}
    _locks_lock = threading.Lock()

    def __init__(self, lock_name: str, owner_prefix: Optional[str] = None):
        self.lock_name = lock_name
        with MultiprocessLock._locks_lock:
            if lock_name not in MultiprocessLock._locks:
                MultiprocessLock._locks[lock_name] = multiprocessing.Lock()
            self._lock = MultiprocessLock._locks[lock_name]
        self._locked = False
        self.owner_prefix = owner_prefix or f"pid{os.getpid()}_tid{threading.get_ident()}"

    def acquire(self, timeout_seconds: int = 60, wait: bool = False, 
                retry_delay: float = 0.5, max_wait_seconds: float = 30) -> bool:
        if self._locked:
            print(f"[MultiprocessLock] Already locked: {self.lock_name}")
            return True
        block = wait
        timeout = max_wait_seconds if wait else 0
        try:
            acquired = self._lock.acquire(block, timeout)
            self._locked = acquired
            print(f"[MultiprocessLock] acquire({self.lock_name}, owner={self.owner_prefix}) -> {acquired}")
            return acquired
        except Exception as e:
            print(f"[MultiprocessLock] Error acquiring {self.lock_name}: {e}")
            self._locked = False
            return False

    def release(self) -> bool:
        if not self._locked:
            print(f"[MultiprocessLock] release({self.lock_name}) called but not locked.")
            return False
        try:
            self._lock.release()
            print(f"[MultiprocessLock] release({self.lock_name}, owner={self.owner_prefix}) -> True")
            self._locked = False
            return True
        except Exception as e:
            print(f"[MultiprocessLock] Error releasing {self.lock_name}: {e}")
            return False

    def __enter__(self):
        if not self.acquire(wait=True):
            raise TimeoutError(f"Could not acquire MultiprocessLock '{self.lock_name}'")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def locked(self) -> bool:
        state = self._lock.locked()
        print(f"[MultiprocessLock] locked({self.lock_name}) -> {state}")
        return state

    def force_release(self) -> bool:
        # No true force-release, just try to release if locked
        if self._locked:
            print(f"[MultiprocessLock] force_release({self.lock_name})")
            return self.release()
        print(f"[MultiprocessLock] force_release({self.lock_name}) called but not locked.")
        return False

# Selectable lock class and factory
LOCK_CLASS: Type[LockBase] = DiskcacheSqliteLock

def get_lock(lock_name: str, owner_prefix: Optional[str] = None) -> LockBase:
    """Factory to get a lock instance using the selected lock class."""
    return LOCK_CLASS(lock_name, owner_prefix)

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
