"""
models.py

Defines data models and configuration structures for the LinuxReport project.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List
from flask_login import UserMixin

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from app_config import load_config

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
    SITE_URLS: List[str]
    URL_IMAGES: str
    FAVICON: str
    LOGO_URL: str
    WEB_DESCRIPTION: str
    WEB_TITLE: str
    REPORT_PROMPT: str
    PATH: str
    SCHEDULE: List[int]
    CUSTOM_FETCH_CONFIG: dict = None

class RssInfo:
    """
    Represents information about an RSS feed.
    """
    def __init__(self, logo_url, logo_alt, site_url):
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url

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
            config = load_config()
            correct_password = config['admin']['password']
            if password == correct_password:
                return User('admin')
        return None

# =============================================================================
# ABSTRACT BASE CLASSES
# =============================================================================

class LockBase(ABC):
    """
    Abstract base class for lock implementations.
    """
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
