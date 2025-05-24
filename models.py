"""
models.py

Defines data models and configuration structures for the LinuxReport project.
"""

# Standard library imports
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List
import socket
import time


@dataclass
class SiteConfig:
    """Configuration for a site."""
    ALL_URLS: Dict[str, "RssInfo"]
    USER_AGENT: str
    SITE_URLS: List[str]
    URL_IMAGES: str
    FAVICON: str
    LOGO_URL: str
    WEB_DESCRIPTION: str
    WEB_TITLE: str
    REPORT_PROMPT: str
    PATH: str  # Base path for the site
    SCHEDULE: List[int]  # List of hours when auto-updates should run
    CUSTOM_FETCH_CONFIG: dict = None

class RssInfo:
    """Represents information about an RSS feed."""
    def __init__(self, logo_url, logo_alt, site_url):
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url


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

    @abstractmethod
    def renew(self, timeout_seconds: int) -> bool:
        pass

DEBUG = False

USE_TOR = True

def is_tor_running():
    """Check if Tor is running by attempting to connect to the SOCKS proxy port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)  # 1 second timeout
        result = sock.connect_ex(('127.0.0.1', 9050))
        sock.close()
        return result == 0
    except:
        return False

# Add a global config for Tor usage

# Check if Tor is actually running and update USE_TOR accordingly
if USE_TOR and not is_tor_running():
    print("Tor is enabled but not running. Falling back to direct connection.")
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