"""
config.py

Handles all static configuration loading for the application.
This module reads from config.yaml and provides configuration values and secrets.
It is designed to be a foundational module with no local dependencies.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
import socket
import yaml
import logging

# =============================================================================
# GLOBAL CONSTANTS AND CONFIGURATION
# =============================================================================

PATH: str = os.path.dirname(os.path.abspath(__file__))
DEBUG = False
USE_TOR = True

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
# UTILITY FUNCTIONS
# =============================================================================

def is_tor_running():
    """
    Check if Tor is running by attempting to connect to the SOCKS proxy port.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)  # 1 second timeout
        result = sock.connect_ex(('127.0.0.1', 9050))
        sock.close()
        return result == 0
    except socket.error:
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
    """
    config_path = os.path.join(PATH, 'config.yaml')
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        else:
            raise FileNotFoundError(f"Config file not found: {config_path}")
    except Exception as e:
        logging.error(f"Error loading config.yaml: {e}")
        raise

def get_admin_password():
    """
    Get the admin password from configuration.
    """
    config = load_config()
    return config['admin']['password']

def get_secret_key():
    """
    Get the secret key from configuration.
    """
    config = load_config()
    return config['admin'].get('secret_key') or os.urandom(24).hex()

def get_weather_api_key():
    """
    Get the weather API key from configuration.
    """
    config = load_config()
    return config['admin'].get('weather_api_key')