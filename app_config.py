"""
app_config.py

Centralized configuration management for LinuxReport.
This module provides a single source of truth for all configuration values,
eliminating duplicate configuration loading across the application.

Features:
- Cached configuration loading with validation
- Fail-fast error handling for missing configuration
- Type-safe configuration access
- Centralized configuration validation
- No local dependencies (foundational module)

Author: LinuxReport System
License: See LICENSE file
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
import socket
import yaml
import logging
from functools import lru_cache
from typing import Dict, Any, Optional, List
from pathlib import Path

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
# CONFIGURATION MANAGER CLASS
# =============================================================================

class ConfigManager:
    """
    Centralized configuration manager with caching and validation.
    
    This class provides a single source of truth for all configuration values,
    eliminating duplicate configuration loading across the application.
    """
    
    _instance = None
    _config = None
    _validated = False
    
    def __new__(cls):
        """Singleton pattern to ensure only one configuration instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'ConfigManager':
        """Get the singleton instance of ConfigManager."""
        if cls._instance is None:
            cls._instance = ConfigManager()
        return cls._instance
    
    @lru_cache(maxsize=1)
    def load_config(self) -> Dict[str, Any]:
        """
        Load and cache configuration from config.yaml file.
        
        Returns:
            Dict[str, Any]: Configuration dictionary
            
        Raises:
            FileNotFoundError: If config.yaml is not found
            yaml.YAMLError: If config.yaml is malformed
            ValueError: If required configuration sections are missing
        """
        config_path = os.path.join(PATH, 'config.yaml')
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not isinstance(config, dict):
                raise ValueError("Configuration file must contain a valid YAML dictionary")
            
            return config
            
        except yaml.YAMLError as e:
            raise ValueError(f"Malformed configuration file: {e}")
        except Exception as e:
            logging.error(f"Error loading config.yaml: {e}")
            raise
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the configuration dictionary, loading it if necessary.
        
        Returns:
            Dict[str, Any]: Configuration dictionary
        """
        if self._config is None:
            self._config = self.load_config()
            self._validate_config()
        return self._config
    
    def _validate_config(self) -> None:
        """
        Validate that all required configuration sections exist.
        
        Raises:
            ValueError: If required configuration sections are missing
        """
        if self._validated:
            return
            
        config = self._config
        required_sections = ['admin', 'storage', 'settings']
        missing_sections = [section for section in required_sections if section not in config]
        
        if missing_sections:
            raise ValueError(f"Missing required configuration sections: {missing_sections}")
        
        # Validate admin section
        admin_section = config['admin']
        if 'password' not in admin_section:
            raise ValueError("Missing required admin.password configuration")
        
        # Validate storage section
        storage_section = config['storage']
        required_storage_keys = ['enabled', 'provider', 'region', 'bucket_name', 'access_key', 'secret_key', 'host', 'sync_path', 'shared_path']
        missing_storage_keys = [key for key in required_storage_keys if key not in storage_section]
        if missing_storage_keys:
            raise ValueError(f"Missing required storage configuration keys: {missing_storage_keys}")
        
        # Validate settings section
        settings_section = config['settings']
        required_settings_keys = ['allowed_domains', 'allowed_requester_domains', 'cdn', 'object_store', 'welcome_html']
        missing_settings_keys = [key for key in required_settings_keys if key not in settings_section]
        if missing_settings_keys:
            raise ValueError(f"Missing required settings configuration keys: {missing_settings_keys}")
        
        self._validated = True
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.
        
        Args:
            key_path: Configuration key path (e.g., 'admin.password')
            default: Default value if key is not found
            
        Returns:
            Configuration value or default
        """
        config = self.get_config()
        keys = key_path.split('.')
        
        try:
            value = config
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def require(self, key_path: str) -> Any:
        """
        Get a required configuration value, failing if not found.
        
        Args:
            key_path: Configuration key path (e.g., 'admin.password')
            
        Returns:
            Configuration value
            
        Raises:
            ValueError: If the configuration key is not found
        """
        value = self.get(key_path)
        if value is None:
            raise ValueError(f"Required configuration key not found: {key_path}")
        return value

# =============================================================================
# GLOBAL CONFIGURATION INSTANCE
# =============================================================================

# Create global configuration manager instance
config_manager = ConfigManager.get_instance()

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def is_tor_running() -> bool:
    """
    Check if Tor is running by attempting to connect to the SOCKS proxy port.
    
    Returns:
        bool: True if Tor is running, False otherwise
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
# CONFIGURATION ACCESS FUNCTIONS
# =============================================================================

def load_config() -> Dict[str, Any]:
    """
    Load configuration from config.yaml file.
    
    This function is maintained for backward compatibility.
    New code should use the ConfigManager directly.
    
    Returns:
        Dict[str, Any]: Configuration dictionary
    """
    return config_manager.get_config()

def get_admin_password() -> str:
    """
    Get the admin password from configuration.
    
    Returns:
        str: Admin password
        
    Raises:
        ValueError: If admin password is not configured
    """
    return config_manager.require('admin.password')

def get_secret_key() -> str:
    """
    Get the secret key from configuration.
    
    Returns:
        str: Secret key (generates a random one if not configured)
    """
    secret_key = config_manager.get('admin.secret_key')
    if not secret_key:
        secret_key = os.urandom(24).hex()
    return secret_key

def get_weather_api_key() -> Optional[str]:
    """
    Get the weather API key from configuration.
    
    Returns:
        Optional[str]: Weather API key or None if not configured
    """
    return config_manager.get('admin.weather_api_key')

def get_storage_config() -> Dict[str, Any]:
    """
    Get the storage configuration.
    
    Returns:
        Dict[str, Any]: Storage configuration dictionary
    """
    return config_manager.get('storage', {})

def get_settings_config() -> Dict[str, Any]:
    """
    Get the settings configuration.
    
    Returns:
        Dict[str, Any]: Settings configuration dictionary
    """
    return config_manager.get('settings', {})

def get_allowed_domains() -> List[str]:
    """
    Get the list of allowed domains for CSP and CORS.
    
    Returns:
        List[str]: List of allowed domains
    """
    return config_manager.get('settings.allowed_domains', [])

def get_allowed_requester_domains() -> List[str]:
    """
    Get the list of domains allowed to make API requests.
    
    Returns:
        List[str]: List of allowed requester domains
    """
    return config_manager.get('settings.allowed_requester_domains', [])

def get_cdn_config() -> Dict[str, Any]:
    """
    Get the CDN configuration.
    
    Returns:
        Dict[str, Any]: CDN configuration dictionary
    """
    return config_manager.get('settings.cdn', {})

def get_object_store_config() -> Dict[str, Any]:
    """
    Get the object store configuration.
    
    Returns:
        Dict[str, Any]: Object store configuration dictionary
    """
    return config_manager.get('settings.object_store', {})

def get_welcome_html() -> str:
    """
    Get the welcome HTML message.
    
    Returns:
        str: Welcome HTML message
    """
    return config_manager.get('settings.welcome_html', '')

def get_reports_config() -> Dict[str, Any]:
    """
    Get the reports configuration.
    
    Returns:
        Dict[str, Any]: Reports configuration dictionary
    """
    return config_manager.get('reports', {})

def is_storage_enabled() -> bool:
    """
    Check if object storage is enabled.
    
    Returns:
        bool: True if storage is enabled, False otherwise
    """
    return config_manager.get('storage.enabled', False)

def is_cdn_enabled() -> bool:
    """
    Check if CDN is enabled.
    
    Returns:
        bool: True if CDN is enabled, False otherwise
    """
    return config_manager.get('settings.cdn.enabled', False)

def is_object_store_enabled() -> bool:
    """
    Check if object store feeds are enabled.
    
    Returns:
        bool: True if object store feeds are enabled, False otherwise
    """
    return config_manager.get('settings.object_store.enabled', False)

# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================

def validate_configuration() -> None:
    """
    Validate the entire configuration and raise errors for any issues.
    
    This function should be called during application startup to ensure
    all required configuration is present and valid.
    
    Raises:
        ValueError: If configuration is invalid or missing required values
    """
    try:
        # This will trigger validation
        config_manager.get_config()
        print("Configuration validation passed successfully")
    except Exception as e:
        print(f"Configuration validation failed: {e}")
        raise

# =============================================================================
# CONFIGURATION RELOADING (for development)
# =============================================================================

def reload_configuration() -> None:
    """
    Reload configuration from disk (useful for development).
    
    This clears the cache and forces a fresh load of the configuration file.
    """
    config_manager._config = None
    config_manager._validated = False
    config_manager.load_config.cache_clear()
    print("Configuration reloaded successfully")

# =============================================================================
# INITIALIZATION
# =============================================================================

# Validate configuration on module import
try:
    validate_configuration()
except Exception as e:
    print(f"Warning: Configuration validation failed during import: {e}")
    # Don't raise here to allow the module to be imported for testing