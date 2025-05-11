import threading
import time
import json
import os
import hashlib
from datetime import datetime
import logging
from typing import Any, Optional, Dict, List
from dataclasses import dataclass
from enum import Enum
import os.path
from pathlib import Path
from config_utils import load_config
from io import BytesIO

# Libcloud imports for availability check and init_storage
try:
    from libcloud.storage.types import Provider, ContainerDoesNotExistError, ObjectDoesNotExistError
    from libcloud.storage.providers import get_driver
    from libcloud.storage.base import Object
    import libcloud.security
    from libcloud.common.types import LibcloudError
    LIBCLOUD_AVAILABLE = True
except ImportError:
    LIBCLOUD_AVAILABLE = False
    # Forward declarations for type hints if LIBCLOUD_AVAILABLE is False
    class Provider: pass
    class ContainerDoesNotExistError(Exception): pass
    class ObjectDoesNotExistError(Exception): pass
    class Object: pass
    class LibcloudError(Exception): pass

# Watchdog imports for availability check
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # Forward declarations for type hints if WATCHDOG_AVAILABLE is False
    class Observer: pass
    class FileSystemEventHandler: pass

# Custom exceptions
class StorageError(Exception):
    """Base exception for storage-related errors"""
    pass

class ConfigurationError(StorageError):
    """Raised when there are issues with configuration"""
    pass

class StorageConnectionError(StorageError):
    """Raised when there are issues connecting to storage"""
    pass

class StorageOperationError(StorageError):
    """Raised when storage operations fail"""
    pass

# Storage provider enum
class StorageProvider(Enum):
    S3 = "s3"
    LINODE = "linode"
    LOCAL = "local"

# Set up logging with structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("object_storage_config")

# Object Storage configuration
STORAGE_ENABLED = False
STORAGE_PROVIDER = "s3"  # options: "s3", "linode", "local"
STORAGE_REGION = "us-east-1"
STORAGE_BUCKET_NAME = "feed-sync"
STORAGE_ACCESS_KEY = ""  # Loaded from config.yaml
STORAGE_SECRET_KEY = ""  # Loaded from config.yaml
STORAGE_HOST = "s3.linode.com"
STORAGE_CHECK_INTERVAL = 30
STORAGE_CACHE_DIR = "/tmp/feed_cache"
STORAGE_SYNC_PREFIX = "feed-updates/"

# Sync configuration
CHECK_INTERVAL = 30  # Default interval to check for updates (seconds)
SERVER_ID = hashlib.md5(os.uname().nodename.encode()).hexdigest()[:8] if hasattr(os, 'uname') else "default_server_id"
CACHE_DIR = "/tmp/feed_cache"  # Local cache directory

# Internal state
_storage_driver = None
_storage_container = None
_watcher_thread = None
_observer = None
_file_event_handler = None
_last_check_time = time.time()
_last_known_objects = {}  # Cache of known objects
_sync_running = False
_secrets_loaded = False
_feed_update_callbacks = []

def load_storage_secrets():
    """Load storage secrets from config.yaml"""
    global STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY, _secrets_loaded
    try:
        config = load_config()
        storage_config = config.get('storage')
        
        if not storage_config:
            raise ConfigurationError("Missing 'storage' section in config.yaml")
            
        # Only load secrets
        STORAGE_ACCESS_KEY = storage_config.get('access_key', '')
        STORAGE_SECRET_KEY = storage_config.get('secret_key', '')
        _secrets_loaded = True
        
        if STORAGE_ENABLED and (not STORAGE_ACCESS_KEY or not STORAGE_SECRET_KEY):
            logger.warning("Storage is enabled but access key or secret key might be missing after loading.")
            
    except FileNotFoundError as e: # Specific exception
        _secrets_loaded = False
        logger.error(f"Configuration file not found: {e}")
        raise ConfigurationError(f"Configuration file not found: {e}")
    except KeyError as e: # Specific exception for missing keys in config
        _secrets_loaded = False
        logger.error(f"Missing key in configuration data: {e}")
        raise ConfigurationError(f"Missing key in configuration data: {e}")
    except Exception as e: # Fallback for other load_config or parsing issues
        _secrets_loaded = False
        logger.error(f"Error loading storage secrets: {e}")
        raise ConfigurationError(f"Error loading storage secrets: {e}") # Wrap in custom error

def init_storage() -> bool:
    """Initialize storage driver if enabled.
    
    Returns:
        bool: True if initialization was successful
        
    Raises:
        StorageConnectionError: If there are issues connecting to storage
        ConfigurationError: If configuration is invalid
    """
    global _storage_driver, _storage_container
    
    if not LIBCLOUD_AVAILABLE:
        logger.info("Libcloud not available. Storage functionality disabled.")
        return False
        
    if not STORAGE_ENABLED:
        logger.info("Storage is not enabled in configuration.")
        return False
    
    if _storage_driver is None:
        try:
            # Validate configuration
            if not STORAGE_ACCESS_KEY or not STORAGE_SECRET_KEY:
                raise ConfigurationError("Storage access key and secret key must be provided")
                
            # Get driver class
            cls = get_driver(STORAGE_PROVIDER)
            
            # Initialize driver with connection pooling
            _storage_driver = cls(
                STORAGE_ACCESS_KEY, 
                STORAGE_SECRET_KEY,
                region=STORAGE_REGION,
                host=STORAGE_HOST,
                secure=True  # Always use SSL
            )
            logger.info(f"Storage driver initialized for provider {STORAGE_PROVIDER}")
            
            # Create or get container
            try:
                _storage_container = _storage_driver.get_container(container_name=STORAGE_BUCKET_NAME)
                logger.info(f"Using existing storage container: {STORAGE_BUCKET_NAME}")
            except ContainerDoesNotExistError:
                _storage_container = _storage_driver.create_container(container_name=STORAGE_BUCKET_NAME)
                logger.info(f"Created new storage container: {STORAGE_BUCKET_NAME}")
                
            # Make sure cache directory exists
            cache_path = Path(STORAGE_CACHE_DIR)
            cache_path.mkdir(parents=True, exist_ok=True)
                
            return True
        except LibcloudError as e: # Catch specific libcloud errors during driver init/container ops
            _storage_driver = None
            _storage_container = None
            raise StorageConnectionError(f"Libcloud error initializing storage driver: {e}")
        except OSError as e: # Catch errors related to cache_path.mkdir
            _storage_driver = None
            _storage_container = None
            raise ConfigurationError(f"Failed to create cache directory during storage init {STORAGE_CACHE_DIR}: {e}")
        except Exception as e: # General fallback for other init issues
            _storage_driver = None
            _storage_container = None
            raise StorageConnectionError(f"Error initializing storage driver: {e}")
    
    return True

# Potential future additions:
# - Function to get logger instance
# - Functions to manage _feed_update_callbacks if they become complex
