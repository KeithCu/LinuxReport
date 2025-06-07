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
import os
import yaml
import logging

PATH: str = os.path.dirname(os.path.abspath(__file__))

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


def load_config():
    """
    Load configuration from config.yaml file.
    Returns a dictionary with configuration values.
    Raises an exception if the config file is missing or if necessary keys are missing.
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
    """Get the admin password from configuration."""
    config = load_config()
    return config['admin']['password']
