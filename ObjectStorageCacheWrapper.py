"""
ObjectStorageCacheWrapper.py (Not used yet)

Object Storage-based cache wrapper for feed updates. Used to manage cache operations with libcloud.
"""
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
from io import BytesIO # Ensure BytesIO is imported for fetch_file_stream if used directly for content
from libcloud.common.types import LibcloudError # For more specific exception handling

class ObjectStorageCacheWrapper:
    """Wrapper for object storage to manage caching operations with libcloud.
    
    This class provides a compatible interface with DiskCacheWrapper but uses object storage
    as the backend instead of local disk cache. It integrates with the existing file
    synchronization and metadata handling functionality.
    """
    def __init__(self, cache_dir: str) -> None:
        """Initialize the object storage cache wrapper.
        
        Args:
            cache_dir: Base directory for local cache operations (used for temporary storage)
            
        Raises:
            ConfigurationError: If cache directory cannot be created
        """
        self.cache_dir = Path(cache_dir)
        self._ensure_cache_dir()
        self._cleanup_lock = threading.Lock()
        
    def _ensure_cache_dir(self) -> None:
        """Ensure the cache directory exists.
        
        Raises:
            ConfigurationError: If directory cannot be created
        """
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e: # Specific exception for directory creation
            raise ConfigurationError(f"Failed to create cache directory {self.cache_dir}: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error creating cache directory: {e}")
            
    def _get_object_name(self, key: str) -> str:
        """Generate a unique object name for a cache key.
        
        Args:
            key: The cache key
            
        Returns:
            str: Unique object name for storage
        """
        return f"{STORAGE_SYNC_PREFIX}cache/{SERVER_ID}/{hashlib.md5(key.encode()).hexdigest()}"
        
    def get(self, key: str) -> Any:
        """Get a value from the cache.
        
        Args:
            key: The cache key to retrieve
            
        Returns:
            The cached value or None if not found
            
        Raises:
            StorageOperationError: If there are issues with storage operations
        """
        if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
            return None
            
        if not init_storage():
            return None
            
        try:
            object_name = self._get_object_name(key)
            obj = _storage_container.get_object(object_name=object_name)
            
            # Check expiration from metadata first (if available and reliable)
            obj_meta = obj.meta_data
            if obj_meta:
                expires_str_meta = obj_meta.get('expires') # Match key used in put()
                if expires_str_meta:
                    try:
                        expires_meta = float(expires_str_meta)
                        if expires_meta != float('inf') and time.time() > expires_meta:
                            logger.info(f"Cache entry for key {key} (object {object_name}) expired based on metadata. Deleting.")
                            # Use self.delete() to ensure proper deletion logic is called
                            # Be careful of potential recursion if delete() also calls get() or has()
                            # For now, directly delete from storage, assuming delete() is robust
                            try:
                                obj_to_delete = _storage_container.get_object(object_name=object_name) # Re-fetch in case it was deleted by another process
                                _storage_container.delete_object(obj_to_delete)
                            except ObjectDoesNotExistError:
                                logger.debug(f"Object {object_name} already deleted, possibly by another process or self.delete.")
                            except LibcloudError as del_e:
                                logger.warning(f"Libcloud error deleting metadata-expired object {object_name}: {del_e}")
                            return None
                    except ValueError:
                        logger.warning(f"Invalid 'expires' metadata '{expires_str_meta}' for object {object_name} during get(). Proceeding with content download.")

            # Download content
            temp_download_path = self.cache_dir / f"temp_cache_get_{hashlib.md5(object_name.encode()).hexdigest()}"
            try:
                obj.download(destination_path=str(temp_download_path), overwrite_existing=True)
                with open(temp_download_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            finally:
                if temp_download_path.exists():
                    try:
                        temp_download_path.unlink()
                    except OSError as e:
                        logger.warning(f"Failed to remove temporary download file {temp_download_path}: {e}")

            # Check expiration from metadata (stored by put)
            expires_str = data.get('expires')
            if expires_str is not None:
                expires = float(expires_str)
                if expires != float('inf') and time.time() > expires:
                    logger.info(f"Cache entry for key {key} (object {object_name}) expired.")
                    self.delete(key)  # Clean up expired entry
                    return None
            
            return data.get('value')
            
        except ObjectDoesNotExistError:
            logger.debug(f"Cache miss for key {key} (object {object_name})")
            return None
        except LibcloudError as e: # Libcloud specific errors
            raise StorageOperationError(f"Libcloud error getting cache value for {key} (object {object_name}): {e}")
        except IOError as e: # Errors related to temp file IO
            raise StorageOperationError(f"I/O error getting cache value for {key} (object {object_name}): {e}")
        except Exception as e: # General fallback
            raise StorageOperationError(f"Error getting cache value for {key} (object {object_name}): {e}")
            
    def put(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        """Store a value in the cache.
        
        Args:
            key: The cache key
            value: The value to store
            timeout: Optional expiration time in seconds
            
        Raises:
            StorageOperationError: If there are issues with storage operations
        """
        if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
            return
            
        if not init_storage():
            return
            
        object_name = self._get_object_name(key)
        
        try:
            # Prepare the data
            expires_at = (time.time() + timeout) if timeout is not None else float('inf')
            data_to_store = {
                'value': value,
                'timestamp': time.time(),
                'expires': expires_at 
            }
            
            # Convert data to JSON string and then to bytes
            json_data_str = json.dumps(data_to_store)
            json_data_bytes = json_data_str.encode('utf-8')
            
            # Use BytesIO for in-memory stream
            data_stream = BytesIO(json_data_bytes)
            
            # Metadata for the object storage
            metadata = {
                'cache_key': key,
                'timestamp': str(data_to_store['timestamp']),
                'expires': str(data_to_store['expires']),
                'type': 'cache_entry',
                'server_id': SERVER_ID
            }
            
            # Upload the stream
            _storage_driver.upload_object_via_stream(
                iterator=data_stream,
                container=_storage_container,
                object_name=object_name,
                extra={'meta_data': metadata, 'content_type': 'application/json'}
            )
            logger.info(f"Stored cache entry for key {key} as object {object_name}")
                
        except LibcloudError as e: # Libcloud specific errors
            raise StorageOperationError(f"Libcloud error putting cache value for {key} (object {object_name}): {e}")
        except IOError as e: # Errors related to temp file IO (e.g., NamedTemporaryFile, open)
            raise StorageOperationError(f"I/O error putting cache value for {key} (object {object_name}): {e}")
        except json.JSONDecodeError as e: # Should not happen here with dump, but for completeness
            raise StorageOperationError(f"JSON encoding error for key {key}: {e}")
        except Exception as e: # General fallback
            raise StorageOperationError(f"Error putting cache value for {key} (object {object_name}): {e}")
        finally:
            # No temporary file to clean up
            if 'data_stream' in locals() and data_stream: # Check if data_stream was defined
                data_stream.close() # Good practice to close BytesIO objects
            
    def delete(self, key: str) -> None:
        """Delete a value from the cache.
        
        Args:
            key: The cache key to delete
            
        Raises:
            StorageOperationError: If there are issues with storage operations
        """
        if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
            return
            
        if not init_storage():
            return
            
        object_name = self._get_object_name(key)
        try:
            # Retrieve the object first
            obj_to_delete = _storage_container.get_object(object_name=object_name)
            _storage_container.delete_object(obj_to_delete) # Pass the Object instance
            logger.info(f"Deleted cache entry for key {key} (object {object_name})")
        except ObjectDoesNotExistError:
            logger.debug(f"Attempted to delete non-existent cache object {object_name} for key {key}")
        except LibcloudError as e:
            raise StorageOperationError(f"Libcloud error deleting cache value for {key} (object {object_name}): {e}")
        except Exception as e: # General fallback
            raise StorageOperationError(f"Error deleting cache value for {key} (object {object_name}): {e}")
            
    def has(self, key: str) -> bool:
        """Check if a key exists in the cache.
        
        Args:
            key: The cache key to check
            
        Returns:
            True if the key exists and is not expired, False otherwise
            
        Raises:
            StorageOperationError: If there are issues with storage operations
        """
        if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
            return False
            
        if not init_storage():
            return False
            
        object_name = self._get_object_name(key)
        try:
            obj = _storage_container.get_object(object_name=object_name)
            
            obj_meta = obj.meta_data 
            if not obj_meta:
                logger.warning(f"No metadata found for object {object_name} during 'has' check. Assuming not expired but this is risky.")
                
            expires_str = obj_meta.get('expires')
            if expires_str:
                try:
                    expires = float(expires_str)
                    if expires != float('inf') and time.time() > expires:
                        logger.info(f"Cache entry for key {key} (object {object_name}) found but expired. Deleting.")
                        self.delete(key)  # Clean up expired entry
                        return False
                except ValueError:
                    logger.error(f"Invalid 'expires' metadata '{expires_str}' for object {object_name}. Treating as error or non-existent.")
                    return False

            return True
            
        except ObjectDoesNotExistError:
            return False
        except LibcloudError as e: # Libcloud specific errors
            raise StorageOperationError(f"Libcloud error checking cache for {key} (object {object_name}): {e}")
        except ValueError as e: # For float conversion of expires_str
             logger.error(f"Invalid 'expires' metadata format for {object_name}: {e}")
             raise StorageOperationError(f"Invalid metadata format for {key}: {e}")
        except Exception as e: # General fallback
            raise StorageOperationError(f"Error checking cache for {key} (object {object_name}): {e}")
            
    def list_versions(self, key: str) -> List[Dict[str, Any]]:
        """List all versions of a cache entry.
        
        Args:
            key: The cache key to list versions for
            
        Returns:
            List of version objects with metadata
            
        Raises:
            StorageOperationError: If there are issues with storage operations
        """
        if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
            return []
            
        if not init_storage():
            return []
            
        object_name = self._get_object_name(key)
        try:
            obj = _storage_container.get_object(object_name=object_name)
            
            version_info = {
                'object_name': obj.name,
                'timestamp': obj.meta_data.get('timestamp'),
                'size': obj.size,
                'hash': obj.hash,
                'metadata': obj.meta_data
            }
            if 'server_id' in obj.meta_data:
                 version_info['server_id'] = obj.meta_data['server_id']
            if 'cache_key' in obj.meta_data:
                 version_info['cache_key'] = obj.meta_data['cache_key']

            return [version_info]
        except ObjectDoesNotExistError:
            return []
        except LibcloudError as e: # Libcloud specific errors
            raise StorageOperationError(f"Libcloud error listing versions for {key} (object {object_name}): {e}")
        except Exception as e: # General fallback
            raise StorageOperationError(f"Error listing versions for {key} (object {object_name}): {e}")
            
    def cleanup_expired(self) -> None:
        """Clean up expired cache entries.
        
        Raises:
            StorageOperationError: If there are issues with storage operations
        """
        if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
            return
            
        if not init_storage():
            return
            
        with self._cleanup_lock:
            try:
                # List all cache objects
                prefix = f"{STORAGE_SYNC_PREFIX}cache/"
                objects = list(_storage_container.list_objects(prefix=prefix))
                current_time = time.time()
                
                for obj in objects:
                    try:
                        # Check expiration
                        expires = float(obj.meta_data.get('expires', 'inf'))
                        if expires != float('inf') and current_time > expires:
                            delete_file_version(obj.name)
                    except (ValueError, TypeError) as e: # Specific error for float conversion or missing keys in metadata
                        logger.warning(f"Error processing object {obj.name} metadata during cleanup: {e}")
                        continue
                    except LibcloudError as e: # Libcloud error during delete_file_version or accessing obj properties
                        logger.warning(f"Libcloud error processing object {obj.name} during cleanup: {e}")
                        continue
                    except Exception as e: # Broader catch for unexpected issues with one object
                        logger.warning(f"Unexpected error processing object {obj.name} during cleanup: {e}")
                        continue
                        
            except LibcloudError as e: # Error listing objects
                raise StorageOperationError(f"Libcloud error during cache cleanup (listing objects): {e}")
            except Exception as e:
                raise StorageOperationError(f"Error cleaning up expired cache entries: {e}")
            
    def start_watcher(self) -> bool:
        """Start the background watcher for cache updates.
        
        Returns:
            True if watcher was started successfully
        """
        return start_storage_watcher()
        
    def stop_watcher(self) -> None:
        """Stop the background watcher."""
        stop_storage_watcher()
        
    def configure(self, enabled: bool = False, **kwargs) -> bool:
        """Configure the cache wrapper.
        
        Args:
            enabled: Whether to enable object storage functionality
            **kwargs: Additional configuration options passed to configure_storage
            
        Returns:
            True if configuration was successful
            
        Raises:
            ConfigurationError: If configuration fails
        """
        try:
            return configure_storage(enabled=enabled, **kwargs)
        except Exception as e:
            raise ConfigurationError(f"Failed to configure cache wrapper: {e}")
