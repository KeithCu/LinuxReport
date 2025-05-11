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

# Import from our new config module
import object_storage_config as oss_config

# Import in-memory cache from shared
from shared import g_cm

# Default local cache expiration time (15 minutes)
DEFAULT_LOCAL_CACHE_EXPIRY = 15 * 60  # 15 minutes in seconds

class ObjectStorageCacheWrapper:
    """Wrapper for object storage to manage caching operations with libcloud.
    
    This class provides a compatible interface with DiskCacheWrapper but uses object storage
    as the backend instead of local disk cache. It integrates with the existing file
    synchronization and metadata handling functionality.
    """
    def __init__(self, cache_dir: str, local_cache_expiry: int = DEFAULT_LOCAL_CACHE_EXPIRY) -> None:
        """Initialize the object storage cache wrapper.
        
        Args:
            cache_dir: Base directory for local cache operations (used for temporary storage)
            local_cache_expiry: Time in seconds for local in-memory cache entries to expire
            
        Raises:
            ConfigurationError: If cache directory cannot be created
        """
        self.cache_dir = Path(cache_dir)
        self._ensure_cache_dir()
        self._cleanup_lock = threading.Lock()
        self.local_cache_expiry = local_cache_expiry
        
    def _ensure_cache_dir(self) -> None:
        """Ensure the cache directory exists.
        
        Raises:
            ConfigurationError: If directory cannot be created
        """
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e: # Specific exception for directory creation
            raise oss_config.ConfigurationError(f"Failed to create cache directory {self.cache_dir}: {e}")
        except Exception as e:
            raise oss_config.ConfigurationError(f"Error creating cache directory: {e}")
            
    def _get_object_name(self, key: str) -> str:
        """Generate a unique object name for a cache key.
        
        Args:
            key: The cache key
            
        Returns:
            str: Unique object name for storage
        """
        # Use hashlib from oss_config if it's not imported directly anymore
        # Assuming hashlib is still directly imported if not prefixed. For now, let's prefix for clarity.
        # However, hashlib is standard, so direct import is also fine.
        # For consistency, if other config vars are prefixed, let's see.
        # hashlib is a standard library, direct use is fine. The config has SERVER_ID which uses hashlib.
        key_hash = oss_config.hashlib.md5(key.encode()).hexdigest()
        return f"{oss_config.STORAGE_SYNC_PREFIX}cache/{oss_config.SERVER_ID}/{key_hash}"
        
    def _get_memory_cache_key(self, key: str) -> str:
        """Generate a unique memory cache key.
        
        Args:
            key: The original cache key
            
        Returns:
            str: Memory cache key with prefix
        """
        return f"objstorage_cache:{key}"
        
    def get(self, key: str) -> Any:
        """Get a value from the cache.
        
        First checks in-memory cache, then falls back to object storage if not found.
        
        Args:
            key: The cache key to retrieve
            
        Returns:
            The cached value or None if not found
            
        Raises:
            StorageOperationError: If there are issues with storage operations
        """
        # First check in-memory cache
        memory_cache_key = self._get_memory_cache_key(key)
        cached_value = g_cm.get(memory_cache_key)
        if cached_value is not None:
            oss_config.logger.debug(f"Cache hit in memory for key {key}")
            return cached_value
            
        # Not found in memory cache, try object storage
        if not oss_config.LIBCLOUD_AVAILABLE or not oss_config.STORAGE_ENABLED:
            return None
            
        if not oss_config.init_storage():
            return None
            
        try:
            object_name = self._get_object_name(key)
            # _storage_container is a global in oss_config
            obj = oss_config._storage_container.get_object(object_name=object_name)
            
            obj_meta = obj.meta_data
            if obj_meta:
                expires_str_meta = obj_meta.get('expires')
                if expires_str_meta:
                    try:
                        expires_meta = float(expires_str_meta)
                        if expires_meta != float('inf') and time.time() > expires_meta:
                            oss_config.logger.info(f"Cache entry for key {key} (object {object_name}) expired based on metadata. Deleting.")
                            try:
                                # Re-fetch might be problematic if object is gone.
                                # obj_to_delete = oss_config._storage_container.get_object(object_name=object_name)
                                oss_config._storage_container.delete_object(obj) # Use the object we already have
                            except oss_config.ObjectDoesNotExistError: # Libcloud's specific error
                                oss_config.logger.debug(f"Object {object_name} already deleted while handling metadata expiry.")
                            except oss_config.LibcloudError as del_e: # Use config's LibcloudError
                                oss_config.logger.warning(f"Libcloud error deleting metadata-expired object {object_name}: {del_e}")
                            return None
                    except ValueError:
                        oss_config.logger.warning(f"Invalid 'expires' metadata '{expires_str_meta}' for object {object_name} during get().")

            temp_download_path = self.cache_dir / f"temp_cache_get_{oss_config.hashlib.md5(object_name.encode()).hexdigest()}"
            try:
                obj.download(destination_path=str(temp_download_path), overwrite_existing=True)
                with open(temp_download_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            finally:
                if temp_download_path.exists():
                    try:
                        temp_download_path.unlink()
                    except OSError as e:
                        oss_config.logger.warning(f"Failed to remove temporary download file {temp_download_path}: {e}")

            expires_str = data.get('expires')
            if expires_str is not None:
                try: # Add try-except for float conversion
                    expires = float(expires_str)
                    if expires != float('inf') and time.time() > expires:
                        oss_config.logger.info(f"Cache entry for key {key} (object {object_name}) expired based on content. Deleting.")
                        self.delete(key)
                        return None
                except ValueError:
                    oss_config.logger.warning(f"Invalid 'expires' in content for object {object_name} ('{expires_str}').")

            value = data.get('value')
            
            # Store in memory cache
            g_cm.set(memory_cache_key, value, ttl=self.local_cache_expiry)
            oss_config.logger.debug(f"Cached key {key} in memory for {self.local_cache_expiry} seconds")
            
            return value
            
        except oss_config.ObjectDoesNotExistError: # Libcloud's specific error
            oss_config.logger.debug(f"Cache miss for key {key} (object {object_name})")
            return None
        except oss_config.LibcloudError as e:
            raise oss_config.StorageOperationError(f"Libcloud error getting cache value for {key} (object {object_name}): {e}")
        except IOError as e:
            raise oss_config.StorageOperationError(f"I/O error getting cache value for {key} (object {object_name}): {e}")
        except Exception as e:
            raise oss_config.StorageOperationError(f"Error getting cache value for {key} (object {object_name}): {e}")
            
    def put(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        """Store a value in the cache.
        
        Stores in both in-memory cache and object storage.
        
        Args:
            key: The cache key
            value: The value to store
            timeout: Optional expiration time in seconds
            
        Raises:
            StorageOperationError: If there are issues with storage operations
        """
        # Store in memory cache first
        memory_cache_key = self._get_memory_cache_key(key)
        g_cm.set(memory_cache_key, value, ttl=self.local_cache_expiry)
        
        if not oss_config.LIBCLOUD_AVAILABLE or not oss_config.STORAGE_ENABLED:
            return
            
        if not oss_config.init_storage():
            return
            
        object_name = self._get_object_name(key)
        data_stream = None # Initialize for finally block
        try:
            expires_at = (time.time() + timeout) if timeout is not None else float('inf')
            data_to_store = {
                'value': value,
                'timestamp': time.time(),
                'expires': expires_at 
            }
            
            json_data_str = json.dumps(data_to_store)
            json_data_bytes = json_data_str.encode('utf-8')
            
            data_stream = BytesIO(json_data_bytes)
            
            metadata = {
                'cache_key': key,
                'timestamp': str(data_to_store['timestamp']),
                'expires': str(data_to_store['expires']),
                'type': 'cache_entry',
                'server_id': oss_config.SERVER_ID
            }
            
            # _storage_driver and _storage_container are from oss_config
            oss_config._storage_driver.upload_object_via_stream(
                iterator=data_stream,
                container=oss_config._storage_container,
                object_name=object_name,
                extra={'meta_data': metadata, 'content_type': 'application/json'}
            )
            oss_config.logger.info(f"Stored cache entry for key {key} as object {object_name}")
                
        except oss_config.LibcloudError as e:
            raise oss_config.StorageOperationError(f"Libcloud error putting cache value for {key} (object {object_name}): {e}")
        except IOError as e:
            raise oss_config.StorageOperationError(f"I/O error putting cache value for {key} (object {object_name}): {e}")
        except json.JSONDecodeError as e:
            raise oss_config.StorageOperationError(f"JSON encoding error for key {key}: {e}")
        except Exception as e:
            raise oss_config.StorageOperationError(f"Error putting cache value for {key} (object {object_name}): {e}")
        finally:
            if data_stream:
                data_stream.close()
            
    def delete(self, key: str) -> None:
        """Delete a value from the cache.
        
        Deletes from both in-memory cache and object storage.
        
        Args:
            key: The cache key to delete
            
        Raises:
            StorageOperationError: If there are issues with storage operations
        """
        # Delete from memory cache first
        memory_cache_key = self._get_memory_cache_key(key)
        g_cm.delete(memory_cache_key)
        
        if not oss_config.LIBCLOUD_AVAILABLE or not oss_config.STORAGE_ENABLED:
            return
            
        if not oss_config.init_storage():
            return
            
        object_name = self._get_object_name(key)
        try:
            obj_to_delete = oss_config._storage_container.get_object(object_name=object_name)
            oss_config._storage_container.delete_object(obj_to_delete)
            oss_config.logger.info(f"Deleted cache entry for key {key} (object {object_name})")
        except oss_config.ObjectDoesNotExistError: # Libcloud's specific error
            oss_config.logger.debug(f"Attempted to delete non-existent cache object {object_name} for key {key}")
        except oss_config.LibcloudError as e:
            raise oss_config.StorageOperationError(f"Libcloud error deleting cache value for {key} (object {object_name}): {e}")
        except Exception as e: # General fallback
            raise oss_config.StorageOperationError(f"Error deleting cache value for {key} (object {object_name}): {e}")
            
    def has(self, key: str) -> bool:
        """Check if a key exists in the cache.
        
        First checks in-memory cache, then falls back to object storage if not found.
        
        Args:
            key: The cache key to check
            
        Returns:
            True if the key exists and is not expired, False otherwise
            
        Raises:
            StorageOperationError: If there are issues with storage operations
        """
        # First check in-memory cache
        memory_cache_key = self._get_memory_cache_key(key)
        if g_cm.has(memory_cache_key):
            return True
            
        if not oss_config.LIBCLOUD_AVAILABLE or not oss_config.STORAGE_ENABLED:
            return False
            
        if not oss_config.init_storage():
            return False
            
        object_name = self._get_object_name(key)
        try:
            obj = oss_config._storage_container.get_object(object_name=object_name)
            
            # Check metadata for expiration
            if obj.meta_data:
                expires_str = obj.meta_data.get('expires')
                if expires_str:
                    try:
                        expires = float(expires_str)
                        if expires != float('inf') and time.time() > expires:
                            oss_config.logger.info(f"Cache entry for key {key} (obj {object_name}) found by has() but is metadata-expired. Deleting.")
                            # Consider calling self.delete(key) but be mindful of re-init_storage() call.
                            # Direct deletion is safer here to avoid potential recursion or re-checking.
                            try:
                                oss_config._storage_container.delete_object(obj)
                            except Exception as del_e: # Catch broad exception during delete
                                oss_config.logger.warning(f"Error deleting metadata-expired object {object_name} during has(): {del_e}")
                            return False 
                    except ValueError:
                         oss_config.logger.warning(f"Invalid 'expires' metadata in has() for {object_name}: '{expires_str}'. Assuming not expired by metadata alone.")
            
            # If not expired by metadata, we assume it exists.
            # Cache the existence so future has() calls don't need to hit storage
            g_cm.set(memory_cache_key, None, ttl=self.local_cache_expiry)
            
            return True
        except oss_config.ObjectDoesNotExistError:
            return False
        except oss_config.LibcloudError as e:
            # Log this error as it might indicate a problem beyond just a missing key
            oss_config.logger.error(f"Libcloud error in has() for key {key} (object {object_name}): {e}")
            raise oss_config.StorageOperationError(f"Libcloud error checking cache for {key}: {e}")
        except Exception as e:
            oss_config.logger.error(f"Generic error in has() for key {key} (object {object_name}): {e}")
            raise oss_config.StorageOperationError(f"Error checking cache for {key}: {e}")

    def has_feed_expired(self, url: str, last_fetch: Optional[datetime] = None) -> bool:
        """Check if a feed has expired based on the last fetch time.
        
        Args:
            url: The URL of the feed to check
            last_fetch: Optional pre-fetched last_fetch timestamp to avoid duplicate calls
        
        Returns:
            True if the feed has expired, False otherwise
        """
        if not oss_config.LIBCLOUD_AVAILABLE or not oss_config.STORAGE_ENABLED:
            return True
            
        # Get the last fetch time if not provided
        if last_fetch is None:
            last_fetch = self.get_last_fetch(url)
            
        # If no last fetch time found, the feed has expired
        if last_fetch is None:
            return True
            
        # We need to import the global history variable from shared module
        # This is similar to how DiskCacheWrapper handles it
        from shared import history
        return history.has_expired(url, last_fetch)
        
    def get_last_fetch(self, url: str) -> Optional[datetime]:
        """Get the last fetch time for a URL from object storage.
        
        Args:
            url: The URL to get the last fetch time for
            
        Returns:
            datetime: The last fetch time or None if not found
        """
        # Last fetch is stored with a specific key format
        last_fetch_key = url + ":last_fetch"
        return self.get(last_fetch_key)
        
    def set_last_fetch(self, url: str, timestamp: Any, timeout: Optional[int] = None) -> None:
        """Set the last fetch time for a URL in object storage.
        
        Args:
            url: The URL to set the last fetch time for
            timestamp: The timestamp to store
            timeout: Optional expiration time in seconds
        """
        # Last fetch is stored with a specific key format
        last_fetch_key = url + ":last_fetch"
        self.put(last_fetch_key, timestamp, timeout)

    def list_versions(self, key: str) -> List[Dict[str, Any]]:
        """List all versions of a cache entry (not typically supported by simple key-value object storage).
        This method might be a misnomer if the backend doesn't support versioning for these cache objects.
        If STORAGE_SYNC_PREFIX/cache/SERVER_ID/HASH is unique, there's only one "version".
        This is more relevant for file sync part. Returning empty list for now.
        """
        oss_config.logger.warning("list_versions is not meaningfully implemented for ObjectStorageCacheWrapper as cache objects are typically not versioned this way.")
        return []

            
    def configure(self, enabled: bool = False, local_cache_expiry: Optional[int] = None, **kwargs) -> bool:
        """Configure cache-specific settings or re-initialize based on global config.
        This method primarily ensures that the cache reflects the global STORAGE_ENABLED state.
        Other configurations (keys, bucket) are managed globally by object_storage_config.
        
        Args:
            enabled: Explicitly enable/disable the cache (reflects global STORAGE_ENABLED)
            local_cache_expiry: Optional time in seconds for local in-memory cache entries to expire
            **kwargs: Potentially cache-specific tunables in the future.
            
        Returns:
            bool: True if configuration/re-check was successful in terms of this cache instance.
        """
        # Update local cache expiry if provided
        if local_cache_expiry is not None:
            self.local_cache_expiry = local_cache_expiry
            oss_config.logger.info(f"Updated local cache expiry to {local_cache_expiry} seconds")
        
        # This cache wrapper's 'enabled' status is tied to the global STORAGE_ENABLED
        # and LIBCLOUD_AVAILABLE.
        # The main configuration (keys, bucket, etc.) is handled by object_storage_config.configure_storage
        
        # Reflect the global enabled state.
        # The actual enabling/disabling of storage happens globally.
        # This method can ensure the cache object is aware or re-initializes certain aspects if necessary.

        if 'cache_dir' in kwargs:
            new_cache_dir = Path(kwargs['cache_dir'])
            if self.cache_dir != new_cache_dir:
                oss_config.logger.info(f"ObjectStorageCacheWrapper cache_dir changed from {self.cache_dir} to {new_cache_dir}")
                self.cache_dir = new_cache_dir
                self._ensure_cache_dir() # Re-ensure the new directory

        # If global storage is enabled, try to init_storage to ensure driver/container are ready.
        if oss_config.STORAGE_ENABLED and oss_config.LIBCLOUD_AVAILABLE:
            oss_config.logger.info("Cache configure: Global storage is enabled, ensuring storage is initialized.")
            return oss_config.init_storage()
        elif not oss_config.STORAGE_ENABLED:
            oss_config.logger.info("Cache configure: Global storage is not enabled. Cache operations will be no-op.")
            return True # Configuration successful in the sense that state is acknowledged.
        elif not oss_config.LIBCLOUD_AVAILABLE:
            oss_config.logger.info("Cache configure: Libcloud not available. Cache operations will be no-op.")
            return False # Cannot be "successfully" configured if libcloud is missing.
        
        return True # Default
