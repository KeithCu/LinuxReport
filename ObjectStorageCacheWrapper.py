"""
ObjectStorageCacheWrapper.py

Object Storage-based cache wrapper for feed updates. Used to manage cache operations with libcloud.

This module implements a caching system that:
- Uses object storage (via libcloud) as the primary storage backend
- Maintains a local in-memory cache for fast access
- Implements background refresh of expired cache entries
- Shares thread pool and refresh locks across all instances
- Uses last-modified caching to avoid unnecessary content fetches

Key features:
- Two-level caching: in-memory + object storage
- Background refresh of expired entries
- Thread pool for managing concurrent background operations
- Deduplication of refresh operations across instances
- Automatic cleanup of expired entries
- Last-modified caching to optimize content fetches

The cache wrapper provides a compatible interface with DiskCacheWrapper but uses
object storage as the backend instead of local disk cache.
"""
import json
import hashlib
import datetime
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor
import threading
from libcloud.storage.drivers.s3 import S3StorageDriver

# Import from our config module
import object_storage_config as oss_config
import object_storage_sync

# Import in-memory cache from shared
from shared import g_cm, TZ, EXPIRE_HOUR

# Default local cache expiration time (15 minutes)
DEFAULT_LOCAL_CACHE_EXPIRY = 15 * 60  # 15 minutes in seconds

class ObjectStorageCacheWrapper:
    """Wrapper for object storage to manage caching operations with libcloud.
    
    This class provides a compatible interface with DiskCacheWrapper but uses object storage
    as the backend instead of local disk cache. It implements a two-level caching system with
    background refresh of expired entries.
    
    Class-level resources:
    - _thread_pool: Shared thread pool for background refresh operations
    - _refresh_locks: Shared locks to prevent duplicate refresh operations
    """
    # Class-level thread pool shared across all instances
    _thread_pool = ThreadPoolExecutor(max_workers=1)
    # Class-level refresh locks shared across all instances
    _refresh_locks = {}
    
    def __init__(self, local_cache_expiry: int = DEFAULT_LOCAL_CACHE_EXPIRY) -> None:
        """Initialize the object storage cache wrapper.
        
        Args:
            local_cache_expiry: Time in seconds for local in-memory cache entries to expire
            
        Raises:
            ConfigurationError: If object storage is not available or not properly configured
        """
        self.local_cache_expiry = local_cache_expiry
        
        # Check storage configuration upfront
        if not oss_config.LIBCLOUD_AVAILABLE or not oss_config.STORAGE_ENABLED:
            raise oss_config.ConfigurationError("Object storage is not available or not enabled")
            
        if not oss_config.init_storage():
            raise oss_config.ConfigurationError("Failed to initialize object storage")
                    
    def _get_object_name(self, key: str) -> str:
        """Generate a unique object name for a cache key."""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return f"{oss_config.STORAGE_SYNC_PATH}cache/{oss_config.SERVER_ID}/{key_hash}"
        
    def _get_memory_cache_key(self, key: str) -> str:
        """Generate a unique memory cache key."""
        return f"objstorage_cache:{key}"
        
    def _background_refresh(self, key: str, memory_key: str) -> None:
        """Background task to refresh a cache value.
        
        This method is called asynchronously to fetch fresh data from object storage
        and update the local cache. It's triggered when an expired value is accessed.
        """
        obj_name = self._get_object_name(key)
        try:
            obj = oss_config._storage_container.get_object(object_name=obj_name)
            content = obj.as_stream().read()
            if content:
                data = json.loads(content.decode('utf-8'))
                g_cm.set(memory_key, data, ttl=self.local_cache_expiry)
        except Exception as e:
            print(f"Error refreshing object {obj_name}: {e}")
        finally:
            # Clean up the lock
            self._refresh_locks.pop(key, None)
        
    def _get_object_metadata(self, obj_name: str) -> Optional[dict]:
        """Get object metadata without fetching content.
        
Linode Object Storage, being S3-compatible, supports system-defined metadata similar to AWS S3, accessible via libcloud's `Object` instance. This includes:
- last-modified: The date and time the object was last modified, available in `obj.extra['last_modified']`, essential for tracking updates.
- content-length: The object size in bytes, accessible as `obj.size` or `obj.extra['content_length']`.
- etag: An entity tag (often an MD5 hash for unencrypted objects), accessible as `obj.hash` or `obj.extra['etag']`, used as a version identifier.
- content-type: The MIME type of the object, available as `obj.content_type`, indicating the data format.
- Optional headers: Fields like `cache-control`, `content-disposition`, or `x-amz-storage-class` may be included in `obj.extra` if configured during object creation.        
        Returns:
            dict: Object metadata including last_modified, size, and hash (etag), or None if object doesn't exist
        """
        try:
            obj = oss_config._storage_container.get_object(object_name=obj_name)
            return {
                'last_modified': obj.extra.get('last_modified'),
                'size': obj.size,
                'hash': obj.hash
            }
        except Exception as e:
            print(f"Error getting metadata for {obj_name}: {e}")
            return None

    def get(self, key: str) -> Any:
        """Get a value from the cache.
        
        This method implements a two-level cache with background refresh and last-modified caching:
        1. First checks in-memory cache
        2. If value is expired, returns it and triggers background refresh
        3. If no cached value exists, checks last-modified before fetching content
        4. Only fetches content if last-modified has changed
        
        The background refresh ensures that expired values are still returned
        immediately while fresh data is fetched asynchronously.
        """
        memory_key = self._get_memory_cache_key(key)
        cached_value = g_cm.get(memory_key)
        
        if cached_value is not None:
            return cached_value
        
        # No cached value, check object storage
        obj_name = self._get_object_name(key)
        
        # First get metadata to check last-modified
        metadata = self._get_object_metadata(obj_name)
        if not metadata:
            return None
            
        # Check if we have a cached version with same last-modified
        last_modified_key = f"{memory_key}:last_modified"
        cached_last_modified = g_cm.get(last_modified_key)
        
        if cached_last_modified == metadata['last_modified']:
            # Content hasn't changed, return cached value if it exists
            cached_content = g_cm.get(f"{memory_key}:content")
            if cached_content:
                return cached_content
        
        # Content has changed or no cached content, fetch from storage
        try:
            obj = oss_config._storage_container.get_object(object_name=obj_name)
            content = obj.as_stream().read()
            
            if content:
                data = json.loads(content.decode('utf-8'))
                # Cache both the content and last-modified
                g_cm.set(memory_key, data, ttl=self.local_cache_expiry)
                g_cm.set(last_modified_key, metadata['last_modified'], ttl=self.local_cache_expiry)
                g_cm.set(f"{memory_key}:content", data, ttl=self.local_cache_expiry)
                
                return data
            return None
        except Exception as e:
            print(f"Error getting object {obj_name}: {e}")
            return None

    def put(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        """Store a value in the cache.
        
        Stores in both in-memory cache and object storage.
        """
        memory_key = self._get_memory_cache_key(key)
        g_cm.set(memory_key, value, ttl=self.local_cache_expiry)
        
        obj_name = self._get_object_name(key)
        json_data = json.dumps(value).encode('utf-8')
        object_storage_sync.publish_bytes(json_data, key=obj_name)
            
    def delete(self, key: str) -> None:
        """Delete a value from both in-memory and object storage caches."""
        # Delete from memory cache first
        memory_cache_key = self._get_memory_cache_key(key)
        g_cm.delete(memory_cache_key)
        g_cm.delete(f"{memory_cache_key}:last_modified")
        g_cm.delete(f"{memory_cache_key}:content")
        
        object_name = self._get_object_name(key)
        try:
            obj_to_delete = oss_config._storage_container.get_object(object_name=object_name)
            oss_config._storage_container.delete_object(obj_to_delete)
        except Exception as e:
            print(f"Error deleting cache value for {key}: {e}")
            
    def has(self, key: str) -> bool:
        """Check if a key exists in either in-memory or object storage cache."""
        memory_key = self._get_memory_cache_key(key)
        if g_cm.has(memory_key):
            return True
        
        obj_name = self._get_object_name(key)
        try:
            obj = oss_config._storage_container.get_object(object_name=obj_name)
            return obj is not None
        except Exception:
            return False

    def has_feed_expired(self, url: str, last_fetch: Optional[datetime] = None) -> bool:
        """Check if a feed has expired based on the last_modified metadata.
        
        Args:
            url: The URL of the feed to check
            last_fetch: Optional last fetch time (ignored, kept for compatibility)
            
        Returns:
            bool: True if the feed has expired, False otherwise
        """
        obj_name = self._get_object_name(url)
        try:
            metadata = self._get_object_metadata(obj_name)
            if not metadata or not metadata.get('last_modified'):
                return True
                
            # Use the shared history module to check if the last_modified time is too old
            from shared import history
            return history.has_expired(url, metadata['last_modified'])
        except Exception as e:
            print(f"Error checking feed expiration for {url}: {e}")
            return True

    def set_last_fetch(self, url: str, timestamp: Any, timeout: Optional[int] = None) -> None:
        """No-op method kept for backward compatibility.
        
        The last fetch time is now tracked via S3's last_modified metadata.
        """
        pass

def migrate_from_disk_cache() -> None:
    """Migrate data from disk cache to object storage cache.
    
    This function copies all entries from the existing disk cache to the new
    object storage cache, preserving expiration times.
    """
    import shared  # Import to access DiskCacheWrapper
    from shared import g_c  # Assuming g_c is the instance from shared.py
    
    old_cache = g_c  # Reference to the existing DiskCacheWrapper instance
    new_cache = ObjectStorageCacheWrapper()  # Create an instance of the new cache
    
    for key in old_cache.cache.iterkeys():  # Iterate through keys in the old cache
        if old_cache.has(key):
            value = old_cache.get(key)  # Get value from old cache
            metadata = old_cache.get(key, read=False)  # Fetch metadata to get expire_time
            expire_time = metadata['expire_time']
            current_time = datetime.datetime.now(TZ).timestamp()
            timeout = expire_time - current_time if expire_time > current_time else EXPIRE_HOUR
            new_cache.put(key, value, timeout=timeout)  # Use calculated timeout
            print(f'Migrated key: {key}')  # Optional logging
    print('Migration completed.')

if __name__ == "__main__":
    migrate_from_disk_cache()  # Trigger migration when run directly
