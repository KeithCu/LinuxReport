"""
models.py

Defines data models and configuration structures for the LinuxReport project.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from flask_login import UserMixin
import datetime
import logging
import os
import sys

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import diskcache

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Import the global logger instance from dedicated logging module
from Logging import g_logger

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from app_config import get_admin_password
import FeedHistory

# =============================================================================
# DATA MODELS AND CONFIGURATION CLASSES
# =============================================================================

@dataclass
class SiteConfig:
    """
    Configuration for a site.
    """
    ALL_URLS: Dict[str, "RssInfo"]
    USER_AGENT: str
    SITE_URLS: List[str] #This is the order of the URLs in the display (left to right), most active at top
    URL_IMAGES: str
    FAVICON: str
    LOGO_URL: str
    WEB_DESCRIPTION: str
    WEB_TITLE: str
    REPORT_PROMPT: str
    PATH: str
    SCHEDULE: List[int]
    CUSTOM_FETCH_CONFIG: Optional[Dict[str, Any]] = None

class RssInfo:
    """
    Represents information about an RSS feed.
    """
    def __init__(self, logo_url, logo_alt, site_url):
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url

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
        self.cache = diskcache.Cache(cache_dir, disk_min_file_size=10000000)

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

    def has_feed_expired(self, url: str, last_fetch: Optional[datetime.datetime] = None, history: Optional[FeedHistory.FeedHistory] = None) -> bool:
        """
        Check if a feed has expired based on the last fetch time.
        
        Args:
            url (str): The URL of the feed to check
            last_fetch (Optional[datetime.datetime]): Pre-fetched last_fetch timestamp 
                                                    to avoid duplicate calls
            history (Optional[FeedHistory.FeedHistory]): FeedHistory instance to use for expiration checking.
                                                       If None, uses the global history instance from shared.py
        
        Returns:
            bool: True if the feed has expired, False otherwise
        """
        if last_fetch is None:
            last_fetch = self.get_last_fetch(url)
        if last_fetch is None:
            return True
        
        # Use provided history instance or the global one from shared
        if history is None:
            # Import here to avoid circular imports
            import shared
            history = shared.history
        
        return history.has_expired(url, last_fetch)

    def get_all_last_fetches(self, urls: List[str]) -> Dict[str, Optional[datetime.datetime]]:
        """
        Get last fetch times for multiple URLs in a single operation.
        
        Args:
            urls (List[str]): List of URLs to check
            
        Returns:
            Dict[str, Optional[datetime.datetime]]: Dictionary mapping URLs to their last fetch times
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
        all_fetches = self.get('all_last_fetches') or {}
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
        all_fetches = self.get('all_last_fetches') or {}
        all_fetches[url] = timestamp
        self.put('all_last_fetches', all_fetches, timeout)

    def clear_last_fetch(self, url: str) -> None:
        """
        Clear the last fetch time for a URL in the shared disk cache.
        
        Args:
            url (str): URL to clear last fetch time for
        """
        self.set_last_fetch(url, None)

class User(UserMixin):
    """
    Simple user model for Flask-Login that works with config.yaml.
    """
    def __init__(self, user_id):
        self.id = user_id
        self.is_admin = True

    @staticmethod
    def get(user_id):
        if user_id == 'admin':
            return User('admin')
        return None

    @staticmethod
    def authenticate(username, password):
        if username == 'admin':
            correct_password = get_admin_password()
            if password == correct_password:
                return User('admin')
        return None

# =============================================================================
# ABSTRACT BASE CLASSES
# =============================================================================

class LockBase(ABC):
    """An abstract base class defining the interface for a lock."""

    @abstractmethod
    def acquire(self, timeout_seconds: int = 60, wait: bool = False) -> bool:
        """Acquires the lock, optionally waiting for it to become available."""
        pass

    @abstractmethod
    def release(self) -> bool:
        """Releases the lock."""
        pass

    @abstractmethod
    def __enter__(self):
        """Enters the context manager, acquiring the lock."""
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exits the context manager, releasing the lock."""
        pass

    @abstractmethod
    def locked(self) -> bool:
        """Checks if the lock is currently held."""
        pass

    @abstractmethod
    def renew(self, timeout_seconds: int) -> bool:
        """Renews the lock with a new timeout."""
        pass
