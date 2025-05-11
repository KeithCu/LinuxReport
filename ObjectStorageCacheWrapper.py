"""
ObjectStorageCacheWrapper.py

Object Storage-based cache wrapper for feed updates. Used to manage cache operations with libcloud.
"""
import time
import json
import hashlib
from datetime import datetime
from typing import Any, Optional
from pathlib import Path
from io import BytesIO

# Import from our config module
import object_storage_config as oss_config

# Import in-memory cache from shared
from shared import g_cm

# Default local cache expiration time (15 minutes)
DEFAULT_LOCAL_CACHE_EXPIRY = 15 * 60  # 15 minutes in seconds

class ObjectStorageCacheWrapper:
    """Wrapper for object storage to manage caching operations with libcloud.
    
    This class provides a compatible interface with DiskCacheWrapper but uses object storage
    as the backend instead of local disk cache.
    """
    def __init__(self, cache_dir: str, local_cache_expiry: int = DEFAULT_LOCAL_CACHE_EXPIRY) -> None:
        """Initialize the object storage cache wrapper.
        
        Args:
            cache_dir: Base directory for local cache operations (used for temporary storage)
            local_cache_expiry: Time in seconds for local in-memory cache entries to expire
        """
        self.cache_dir = Path(cache_dir)
        self._ensure_cache_dir()
        self.local_cache_expiry = local_cache_expiry
        
    def _ensure_cache_dir(self) -> None:
        """Ensure the cache directory exists."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise oss_config.ConfigurationError(f"Error creating cache directory: {e}")
            
    def _get_object_name(self, key: str) -> str:
        """Generate a unique object name for a cache key."""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return f"{oss_config.STORAGE_SYNC_PREFIX}cache/{oss_config.SERVER_ID}/{key_hash}"
        
    def _get_memory_cache_key(self, key: str) -> str:
        """Generate a unique memory cache key."""
        return f"objstorage_cache:{key}"
        
    def get(self, key: str) -> Any:
        """Get a value from the cache.
        
        First checks in-memory cache, then falls back to object storage if not found.
        """
        # First check in-memory cache
        memory_cache_key = self._get_memory_cache_key(key)
        cached_value = g_cm.get(memory_cache_key)
        if cached_value is not None:
            return cached_value
            
        # Not found in memory cache, try object storage
        if not oss_config.LIBCLOUD_AVAILABLE or not oss_config.STORAGE_ENABLED:
            return None
            
        if not oss_config.init_storage():
            return None
            
        try:
            object_name = self._get_object_name(key)
            obj = oss_config._storage_container.get_object(object_name=object_name)
            
            # Download the object to a temporary file
            temp_download_path = self.cache_dir / f"temp_{hashlib.md5(object_name.encode()).hexdigest()}"
            try:
                obj.download(destination_path=str(temp_download_path), overwrite_existing=True)
                with open(temp_download_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            finally:
                if temp_download_path.exists():
                    try:
                        temp_download_path.unlink()
                    except OSError:
                        pass

            # Check if expired
            expires = data.get('expires')
            if expires is not None and expires != float('inf') and time.time() > expires:
                self.delete(key)
                return None

            value = data.get('value')
            
            # Store in memory cache
            g_cm.set(memory_cache_key, value, ttl=self.local_cache_expiry)
            
            return value
            
        except oss_config.ObjectDoesNotExistError:
            return None
        except Exception as e:
            oss_config.logger.error(f"Error getting cache value for {key}: {e}")
            return None
            
    def put(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        """Store a value in the cache.
        
        Stores in both in-memory cache and object storage.
        """
        # Store in memory cache first
        memory_cache_key = self._get_memory_cache_key(key)
        g_cm.set(memory_cache_key, value, ttl=self.local_cache_expiry)
        
        if not oss_config.LIBCLOUD_AVAILABLE or not oss_config.STORAGE_ENABLED:
            return
            
        if not oss_config.init_storage():
            return
            
        object_name = self._get_object_name(key)
        data_stream = None
        try:
            expires_at = (time.time() + timeout) if timeout is not None else float('inf')
            data_to_store = {
                'value': value,
                'timestamp': time.time(),
                'expires': expires_at 
            }
            
            json_data = json.dumps(data_to_store).encode('utf-8')
            data_stream = BytesIO(json_data)
            
            metadata = {
                'cache_key': key,
                'timestamp': str(data_to_store['timestamp']),
                'expires': str(data_to_store['expires']),
                'server_id': oss_config.SERVER_ID
            }
            
            oss_config._storage_driver.upload_object_via_stream(
                iterator=data_stream,
                container=oss_config._storage_container,
                object_name=object_name,
                extra={'meta_data': metadata, 'content_type': 'application/json'}
            )
                
        except Exception as e:
            oss_config.logger.error(f"Error putting cache value for {key}: {e}")
        finally:
            if data_stream:
                data_stream.close()
            
    def delete(self, key: str) -> None:
        """Delete a value from the cache."""
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
        except oss_config.ObjectDoesNotExistError:
            pass
        except Exception as e:
            oss_config.logger.error(f"Error deleting cache value for {key}: {e}")
            
    def has(self, key: str) -> bool:
        """Check if a key exists in the cache."""
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
            oss_config._storage_container.get_object(object_name=object_name)
            # Cache the existence
            g_cm.set(memory_cache_key, None, ttl=self.local_cache_expiry)
            return True
        except oss_config.ObjectDoesNotExistError:
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
