"""
object_storage_sync.py

Core object storage functionality needed for ObjectStorageCacheWrapper.
"""
import time
import json
import hashlib
from datetime import datetime
import os.path
from pathlib import Path
from io import BytesIO
from typing import Any, Optional, Dict, List

# Import from object_storage_config
from object_storage_config import (
    logger, LIBCLOUD_AVAILABLE, STORAGE_ENABLED,
    StorageError, ConfigurationError, StorageOperationError,
    init_storage, SERVER_ID, STORAGE_SYNC_PREFIX,
    STORAGE_CACHE_DIR, 
    _storage_driver, _storage_container
)

# Ensure libcloud imports are available when needed
if LIBCLOUD_AVAILABLE:
    from libcloud.storage.types import Provider, ContainerDoesNotExistError, ObjectDoesNotExistError
    from libcloud.storage.base import Object
    from libcloud.common.types import LibcloudError

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