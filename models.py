"""
models.py

Defines data models and configuration structures for the LinuxReport project.
Provides user authentication, configuration management, and utility functions
for the Flask application.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List
import socket
import time
import os
import yaml
import logging
from flask_login import UserMixin

# =============================================================================
# GLOBAL CONSTANTS AND CONFIGURATION
# =============================================================================

PATH: str = os.path.dirname(os.path.abspath(__file__))

# =============================================================================
# SHARED CONFIGURATION DICTIONARIES
# =============================================================================

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

# =============================================================================
# DATA MODELS AND CONFIGURATION CLASSES
# =============================================================================

@dataclass
class SiteConfig:
    """
    Configuration for a site.
    
    Centralized configuration structure for site-specific settings including
    URLs, appearance, scheduling, and custom fetch configurations.
    
    Attributes:
        ALL_URLS (Dict[str, RssInfo]): Dictionary mapping URLs to RSS feed information
        USER_AGENT (str): User agent string for HTTP requests
        SITE_URLS (List[str]): List of site URLs
        URL_IMAGES (str): Base URL for site images
        FAVICON (str): Path to site favicon
        LOGO_URL (str): URL to site logo
        WEB_DESCRIPTION (str): Site description for meta tags
        WEB_TITLE (str): Site title
        REPORT_PROMPT (str): Prompt template for report generation
        PATH (str): Base path for the site
        SCHEDULE (List[int]): List of hours when auto-updates should run
        CUSTOM_FETCH_CONFIG (dict): Optional custom fetch configuration
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
    PATH: str  # Base path for the site
    SCHEDULE: List[int]  # List of hours when auto-updates should run
    CUSTOM_FETCH_CONFIG: dict = None


class RssInfo:
    """
    Represents information about an RSS feed.
    
    Simple data container for RSS feed metadata including logo information
    and site URL.
    
    Attributes:
        logo_url (str): URL to the feed's logo image
        logo_alt (str): Alt text for the logo image
        site_url (str): URL to the main site
    """
    
    def __init__(self, logo_url, logo_alt, site_url):
        """
        Initialize RSS feed information.
        
        Args:
            logo_url (str): URL to the feed's logo image
            logo_alt (str): Alt text for the logo image
            site_url (str): URL to the main site
        """
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url


class User(UserMixin):
    """
    Simple user model for Flask-Login that works with config.yaml.
    
    Provides user authentication functionality integrated with the application's
    configuration system. All users in this system are treated as administrators.
    
    Attributes:
        id (str): User identifier
        is_admin (bool): Always True for this simple system
    """
    
    def __init__(self, user_id):
        """
        Initialize a user instance.
        
        Args:
            user_id (str): Unique identifier for the user
        """
        self.id = user_id
        self.is_admin = True  # All users in this system are admins
    
    @staticmethod
    def get(user_id):
        """
        Get user by ID - in this simple system, any valid ID returns an admin user.
        
        Args:
            user_id (str): User identifier to look up
            
        Returns:
            User: User instance if ID is 'admin', None otherwise
        """
        if user_id == 'admin':
            return User('admin')
        return None
    
    @staticmethod
    def authenticate(username, password):
        """
        Authenticate user against config.yaml password.
        
        Validates user credentials against the stored configuration.
        Only the 'admin' username is supported in this system.
        
        Args:
            username (str): Username to authenticate
            password (str): Password to validate
            
        Returns:
            User: Authenticated user instance if credentials are valid, None otherwise
        """
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
    
    Defines the interface for thread-safe locking mechanisms used throughout
    the application for resource coordination and synchronization.
    """
    
    @abstractmethod
    def acquire(self, timeout_seconds: int = 60, wait: bool = False) -> bool:
        """
        Acquire the lock.
        
        Args:
            timeout_seconds (int): Maximum time to wait for lock acquisition
            wait (bool): Whether to wait for lock availability
            
        Returns:
            bool: True if lock was acquired, False otherwise
        """
        pass

    @abstractmethod
    def release(self) -> bool:
        """
        Release the lock.
        
        Returns:
            bool: True if lock was released, False otherwise
        """
        pass

    @abstractmethod
    def __enter__(self):
        """Context manager entry point."""
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point."""
        pass

    @abstractmethod
    def locked(self) -> bool:
        """
        Check if the lock is currently held.
        
        Returns:
            bool: True if lock is held, False otherwise
        """
        pass

    @abstractmethod
    def renew(self, timeout_seconds: int) -> bool:
        """
        Renew the lock timeout.
        
        Args:
            timeout_seconds (int): New timeout duration
            
        Returns:
            bool: True if lock was renewed, False otherwise
        """
        pass

# =============================================================================
# GLOBAL SETTINGS AND FLAGS
# =============================================================================

DEBUG = False

USE_TOR = True

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def is_tor_running():
    """
    Check if Tor is running by attempting to connect to the SOCKS proxy port.
    
    Attempts to establish a connection to the default Tor SOCKS proxy port
    (9050) to determine if Tor is available for use.
    
    Returns:
        bool: True if Tor is running and accessible, False otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)  # 1 second timeout
        result = sock.connect_ex(('127.0.0.1', 9050))
        sock.close()
        return result == 0
    except:
        return False

# Check if Tor is actually running and update USE_TOR accordingly
if USE_TOR and not is_tor_running():
    print("Tor is enabled but not running. Falling back to direct connection.")
    USE_TOR = False

# =============================================================================
# CONFIGURATION MANAGEMENT FUNCTIONS
# =============================================================================

def load_config():
    """
    Load configuration from config.yaml file.
    
    Reads and validates the application configuration from the config.yaml
    file. Ensures all required sections are present and properly formatted.
    
    Returns:
        dict: Configuration dictionary with all settings
        
    Raises:
        FileNotFoundError: If config.yaml file is missing
        ValueError: If required configuration sections are missing
        Exception: For other configuration loading errors
    """
    config_path = os.path.join(PATH, 'config.yaml')
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                yaml_config = yaml.safe_load(f)
                
                # Update config with values from YAML file
                if yaml_config and isinstance(yaml_config, dict):
                    # Handle admin section
                    if 'admin' in yaml_config and isinstance(yaml_config['admin'], dict):
                        # Add settings section if not present
                        if 'settings' not in yaml_config:
                            yaml_config['settings'] = {}
                        return yaml_config
                    else:
                        raise ValueError("Missing 'admin' section in config file.")
        else:
            raise FileNotFoundError(f"Config file not found: {config_path}")
    except Exception as e:
        logging.error(f"Error loading config.yaml: {e}")
        raise


def get_admin_password():
    """
    Get the admin password from configuration.
    
    Retrieves the administrator password from the loaded configuration.
    
    Returns:
        str: Administrator password from configuration
    """
    config = load_config()
    return config['admin']['password']


def get_secret_key():
    """
    Get the secret key from configuration.
    
    Retrieves the Flask secret key from configuration. If no secret key
    is configured, generates a random one for security.
    
    Returns:
        str: Flask secret key for session management
    """
    config = load_config()
    return config['admin'].get('secret_key') or os.urandom(24).hex()


def get_weather_api_key():
    """
    Get the weather API key from configuration.
    
    Retrieves the weather API key from the configuration for weather
    service integration.
    
    Returns:
        str: Weather API key if configured, None otherwise
    """
    config = load_config()
    return config['admin'].get('weather_api_key')
