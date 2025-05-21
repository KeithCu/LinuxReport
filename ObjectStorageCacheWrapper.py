"""
ObjectStorageCacheWrapper.py

Object Storage-based cache wrapper for feed updates. Used to manage cache operations with libcloud.

This module implements a caching system that:
- Uses object storage (via libcloud) as the primary storage backend
- Maintains a local in-memory cache for fast access
- Implements background refresh of expired cache entries
- Shares thread pool and refresh locks across all instances

Key features:
- Two-level caching: in-memory + object storage
- Background refresh of expired entries
- Thread pool for managing concurrent background operations
- Deduplication of refresh operations across instances
- Automatic cleanup of expired entries

The cache wrapper provides a compatible interface with DiskCacheWrapper but uses
object storage as the backend instead of local disk cache.
"""
import json
import hashlib
import datetime
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor
import threading

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
    _thread_pool = ThreadPoolExecutor(max_workers=4)
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
            content, metadata = object_storage_sync.fetch_bytes(obj_name, force=True)
            if content:
                data = json.loads(content.decode('utf-8'))
                if datetime.datetime.now(TZ).timestamp() <= data.get('expires', float('inf')):
                    g_cm.set(memory_key, data, ttl=self.local_cache_expiry)
        except Exception as e:
            print(f"Error refreshing object {obj_name}: {e}")
        finally:
            # Clean up the lock
            self._refresh_locks.pop(key, None)
        
    def get(self, key: str) -> Any:
        """Get a value from the cache.
        
        This method implements a two-level cache with background refresh:
        1. First checks in-memory cache
        2. If value is expired, returns it and triggers background refresh
        3. If no cached value exists, fetches from object storage
        
        The background refresh ensures that expired values are still returned
        immediately while fresh data is fetched asynchronously.
        """
        memory_key = self._get_memory_cache_key(key)
        cached_value = g_cm.get(memory_key)
        
        if cached_value is not None:
            # Check if the value is expired
            if isinstance(cached_value, dict) and 'expires' in cached_value:
                if datetime.datetime.now(TZ).timestamp() > cached_value['expires']:
                    # Value is expired, trigger background refresh if not already refreshing
                    if key not in self._refresh_locks:
                        self._refresh_locks[key] = threading.Lock()
                        self._thread_pool.submit(self._background_refresh, key, memory_key)
                    return cached_value.get('value')
            return cached_value
        
        # No cached value, fetch from object storage
        obj_name = self._get_object_name(key)
        try:
            content, metadata = object_storage_sync.fetch_bytes(obj_name, force=True)
            if content:
                data = json.loads(content.decode('utf-8'))
                if datetime.datetime.now(TZ).timestamp() > data.get('expires', float('inf')):
                    return None
                g_cm.set(memory_key, data, ttl=self.local_cache_expiry)
                return data.get('value')
            return None
        except Exception as e:
            print(f"Error getting object {obj_name}: {e}")
            return None

    def put(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        """Store a value in the cache.
        
        Stores in both in-memory cache and object storage. The value is stored with
        metadata including expiration time and server ID.
        """
        memory_key = self._get_memory_cache_key(key)
        g_cm.set(memory_key, value, ttl=self.local_cache_expiry)
        
        obj_name = self._get_object_name(key)
        expires_at = (datetime.datetime.now(TZ).timestamp() + timeout) if timeout is not None else float('inf')
        data_to_store = {
            'value': value,
            'timestamp': datetime.datetime.now(TZ).timestamp(),
            'expires': expires_at,
            'server_id': oss_config.SERVER_ID
        }
        json_data = json.dumps(data_to_store).encode('utf-8')
        extra_metadata = {'content_type': 'application/json'}
        object_storage_sync.publish_bytes(json_data, key=obj_name, metadata=extra_metadata)
            
    def delete(self, key: str) -> None:
        """Delete a value from both in-memory and object storage caches."""
        # Delete from memory cache first
        memory_cache_key = self._get_memory_cache_key(key)
        g_cm.delete(memory_cache_key)
        
        object_name = self._get_object_name(key)
        try:
            obj_to_delete = oss_config._storage_container.get_object(object_name=object_name)
            oss_config._storage_container.delete_object(obj_to_delete)
        except oss_config.ObjectDoesNotExistError:
            pass
        except Exception as e:
            print(f"Error deleting cache value for {key}: {e}")
            
    def has(self, key: str) -> bool:
        """Check if a key exists in either in-memory or object storage cache."""
        memory_key = self._get_memory_cache_key(key)
        if g_cm.has(memory_key):
            return True
        
        obj_name = self._get_object_name(key)
        try:
            content, metadata = object_storage_sync.fetch_bytes(obj_name, force=True)
            if content is not None:
                g_cm.set(memory_key, None, ttl=self.local_cache_expiry)  # Cache existence
                return True
            return False
        except Exception:
            return False

    def has_feed_expired(self, url: str, last_fetch: Optional[datetime] = None) -> bool:
        """Check if a feed has expired based on the last fetch time."""
        # Get the last fetch time if not provided
        if last_fetch is None:
            last_fetch = self.get_last_fetch(url)
            
        # If no last fetch time found, the feed has expired
        if last_fetch is None:
            return True
            
        # Use the shared history module
        from shared import history
        return history.has_expired(url, last_fetch)
        
    def get_last_fetch(self, url: str) -> Optional[datetime]:
        """Get the last fetch time for a URL from object storage."""
        last_fetch_key = url + ":last_fetch"
        return self.get(last_fetch_key)
        
    def set_last_fetch(self, url: str, timestamp: Any, timeout: Optional[int] = None) -> None:
        """Set the last fetch time for a URL in object storage."""
        last_fetch_key = url + ":last_fetch"
        self.put(last_fetch_key, timestamp, timeout)

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
