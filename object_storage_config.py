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
STORAGE_PROVIDER = "linode"  # options: "s3", "linode", "local"
STORAGE_REGION = "us-east-1"
STORAGE_BUCKET_NAME = "feed-sync"
STORAGE_ACCESS_KEY = ""  # Loaded from config.yaml
STORAGE_SECRET_KEY = ""  # Loaded from config.yaml
STORAGE_HOST = "s3.linode.com"
STORAGE_SYNC_PREFIX = "feed-updates/"

# Sync configuration
SERVER_ID = hashlib.md5(os.uname().nodename.encode()).hexdigest()[:8] if hasattr(os, 'uname') else "default_server_id"

# Internal state
_storage_driver = None
_storage_container = None
_secrets_loaded = False

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
                                
            return True
        except LibcloudError as e: # Catch specific libcloud errors during driver init/container ops
            _storage_driver = None
            _storage_container = None
            raise StorageConnectionError(f"Libcloud error initializing storage driver: {e}")
        except Exception as e: # General fallback for other init issues
            _storage_driver = None
            _storage_container = None
            raise StorageConnectionError(f"Error initializing storage driver: {e}")
    
    return True


def get_file_metadata(file_path):
    """Get metadata for a file including hash and timestamp
    
    Args:
        file_path: Path to the file
        
    Returns:
        dict: File metadata including hash and timestamp
    """
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
            file_hash = hashlib.sha256(content).hexdigest()
            stat = os.stat(file_path)
            return {
                'hash': file_hash,
                'size': stat.st_size,
                'mtime': stat.st_mtime,
                'ctime': stat.st_ctime,
                'content': content  # Include content for in-memory operations
            }
    except FileNotFoundError as e:
        logger.error(f"File not found for metadata: {file_path}: {e}")
        return None
    except IOError as e: # Broader I/O errors (e.g. permission denied)
        logger.error(f"I/O error getting file metadata for {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting file metadata for {file_path}: {e}")
        return None

def _find_latest_object_version(metadata_file_path_match: str, prefix: str) -> Optional[Object]:
    """Finds the latest version of an object in storage based on metadata file_path and timestamp."""
    if not _storage_container: # Should be initialized by init_storage
        return None

    objects = list(_storage_container.list_objects(prefix=prefix))
    latest_obj = None
    latest_timestamp = 0
    
    for obj_item in objects:
        try:
            meta = obj_item.meta_data
            if meta and meta.get('file_path') == metadata_file_path_match:
                timestamp = float(meta.get('timestamp', 0))
                if timestamp > latest_timestamp:
                    latest_obj = obj_item
                    latest_timestamp = timestamp
        except (ValueError, TypeError) as e: # Catch issues with float conversion or missing keys
            logger.warning(f"Could not parse metadata for object {obj_item.name} while finding latest: {e}")
            continue
    return latest_obj 