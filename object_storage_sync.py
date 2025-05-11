"""
object_storage_sync.py (Not used yet)

Object Storage-based publisher/subscriber for feed updates. Used to synchronize feed updates across multiple servers.
Uses libcloud to interface with object storage providers (like Linode Object Storage).
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
import tempfile # Added for IV.1
from io import BytesIO # Ensure BytesIO is imported for fetch_file_stream if used directly for content
from libcloud.common.types import LibcloudError # For more specific exception handling

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
SYNC_PREFIX = "feed-updates/"  # Prefix for feed updates
CHECK_INTERVAL = 30  # Default interval to check for updates (seconds)
SERVER_ID = hashlib.md5(os.uname().nodename.encode()).hexdigest()[:8]
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

# Callbacks for feed updates
_feed_update_callbacks = []

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

# Set up logging with structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("object_storage_sync")

# Initialize configuration
# try:
#     load_storage_secrets() # Removed top-level call for II.1
# except Exception as e:
#     logger.error(f"Error loading storage secrets: {e}")

# Check if libcloud is available
LIBCLOUD_AVAILABLE = False
try:
    from libcloud.storage.types import Provider, ContainerDoesNotExistError, ObjectDoesNotExistError
    from libcloud.storage.providers import get_driver
    from libcloud.storage.base import Object
    import libcloud.security
    
    # Disable SSL verification for development
    # libcloud.security.VERIFY_SSL_CERT = False
    
    LIBCLOUD_AVAILABLE = True
except ImportError:
    logger.warning("apache-libcloud is not installed. Object Storage feed synchronization will be disabled.")

# Check if watchdog is available for file change monitoring
WATCHDOG_AVAILABLE = False
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    logger.warning("watchdog is not installed. File change monitoring will be disabled.")

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
            
        temp_path = None
        object_name = self._get_object_name(key)
        
        try:
            # Prepare the data
            expires_at = (time.time() + timeout) if timeout is not None else float('inf')
            data_to_store = {
                'value': value,
                'timestamp': time.time(),
                'expires': expires_at 
            }
            
            # Write to temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=self.cache_dir, suffix='.json', encoding='utf-8') as tmp_file:
                json.dump(data_to_store, tmp_file)
                temp_path = Path(tmp_file.name)
            
            # Metadata for the object storage
            metadata = {
                'cache_key': key,
                'timestamp': str(data_to_store['timestamp']),
                'expires': str(data_to_store['expires']),
                'type': 'cache_entry',
                'server_id': SERVER_ID
            }
            
            # Upload the file
            with open(temp_path, 'rb') as iterator:
                _storage_driver.upload_object_via_stream(
                    iterator=iterator,
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
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError as e:
                    logger.warning(f"Failed to clean up temporary file {temp_path}: {e}")
            
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
            _storage_container.delete_object(object_name)
            logger.info(f"Deleted cache entry for key {key} (object {object_name})")
        except ObjectDoesNotExistError:
            logger.debug(f"Attempted to delete non-existent cache object {object_name} for key {key}")
        except LibcloudError as e: # Libcloud specific errors
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

def register_feed_update_callback(cb):
    """Register a callback function to be called when feed updates are received
    
    Args:
        cb: Callback function that takes (url, feed_content, feed_data) parameters
    """
    if cb not in _feed_update_callbacks:
        _feed_update_callbacks.append(cb)

def generate_object_name(url):
    """Generate a unique object name for a feed URL"""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    timestamp = int(time.time())
    return f"{STORAGE_SYNC_PREFIX}{SERVER_ID}/{url_hash}_{timestamp}.json"

def publish_feed_update(url, feed_content=None, feed_data=None):
    """Publish feed update to object storage
    
    Args:
        url: The feed URL that was updated
        feed_content: The actual feed content that was fetched (parsed feed entries, HTML, etc.)
                      This should be the complete data needed to update on the receiving end
        feed_data: Optional additional metadata about the update (timestamp, etc.)
    """
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None
        
    if not init_storage():
        return None
    
    data = {
        "url": url,
        "feed_content": feed_content,
        "feed_data": feed_data,
        "server_id": SERVER_ID,
        "timestamp": time.time()
    }
    
    temp_file_path_obj = None # For tempfile management
    try:
        # Create a unique object name
        object_name = generate_object_name(url)
        
        # Create a JSON string from the data
        json_data = json.dumps(data)
        
        # Create a temporary file using tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=CACHE_DIR, suffix='.json', encoding='utf-8') as tmp_file:
            tmp_file.write(json_data)
            temp_file_path_obj = Path(tmp_file.name)
        
        # Upload the file
        with open(temp_file_path_obj, 'rb') as iterator:
            extra = {
                'meta_data': {
                    'server_id': SERVER_ID,
                    'feed_url': url,
                    'timestamp': str(time.time()) # Ensure this timestamp is what cleanup_old_updates expects
                },
                'content_type': 'application/json'
            }
            obj = _storage_driver.upload_object_via_stream(
                iterator=iterator,
                container=_storage_container,
                object_name=object_name,
                extra=extra
            )
            
        logger.info(f"Published feed update for {url} to object storage as {object_name}")
        return obj
    except LibcloudError as e:
        logger.error(f"Libcloud error publishing feed update to object storage for {url}: {e}")
        return None
    except IOError as e: # For temp file issues
        logger.error(f"I/O error publishing feed update for {url}: {e}")
        return None
    except json.JSONDecodeError as e: # Should not happen with dumps, but for safety
        logger.error(f"JSON encoding error publishing feed update for {url}: {e}")
        return None
    except Exception as e: 
        logger.error(f"Error publishing feed update to object storage: {e}")
        return None
    finally:
        # Clean up the temporary file
        if temp_file_path_obj and temp_file_path_obj.exists():
            try:
                temp_file_path_obj.unlink()
            except OSError as e: # Log specific error for cleanup failure (III.2)
                logger.warning(f"Failed to remove temporary file {temp_file_path_obj}: {e}")

def check_for_updates():
    """Check object storage for new feed updates from other servers"""
    global _last_check_time, _last_known_objects
    
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return
        
    if not init_storage():
        return
    
    try:
        # List objects with our prefix
        objects = list(_storage_container.list_objects(prefix=STORAGE_SYNC_PREFIX))
        current_time = time.time()
        
        # Filter out our own updates and process only new ones
        for obj in objects:
            # Skip if we already know about this object
            if obj.name in _last_known_objects:
                continue
            
            # Use metadata for server ID (VI.1)
            obj_server_id = None
            if obj.meta_data:
                obj_server_id = obj.meta_data.get('server_id')

            if obj_server_id == SERVER_ID:
                _last_known_objects[obj.name] = current_time
                continue
            
            # Delegate processing to a helper function (V.2)
            _process_single_remote_update(obj, current_time)
        
        # Clean up old entries from our cache
        expired_time = current_time - 3600  # 1 hour expiration
        expired_keys = [k for k, v in _last_known_objects.items() if v < expired_time]
        for key in expired_keys:
            del _last_known_objects[key]
            
        _last_check_time = current_time
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")

def _process_single_remote_update(obj: Object, current_time: float): # Added V.2
    """Helper function to process a single object update from storage."""
    global _last_known_objects
    try:
        # Download and process the object
        process_update_object(obj) # process_update_object already handles download, parse, callbacks
        
        # Mark as known
        _last_known_objects[obj.name] = current_time
    except LibcloudError as e:
        logger.error(f"Libcloud error in _process_single_remote_update for {obj.name}: {e}")
    except IOError as e: # from process_update_object if it has file IO issues
        logger.error(f"I/O error in _process_single_remote_update for {obj.name}: {e}")
    except json.JSONDecodeError as e: # from process_update_object
        logger.error(f"JSON decode error in _process_single_remote_update for {obj.name}: {e}")
    except Exception as e:
        logger.error(f"Error processing remote update for object {obj.name}: {e}")

def process_update_object(obj):
    """Process a feed update object"""
    temp_file_path_obj = None # For tempfile management
    try:
        # Download the object to a temporary file using tempfile
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, dir=CACHE_DIR, suffix='.json') as tmp_file:
            # No, download method needs a path string.
            # obj.download(tmp_file) # This won't work directly if download expects path
            temp_file_path_obj = Path(tmp_file.name)
            # We need to close it before libcloud writes to it, or ensure download can take a file object.
            # Most download methods expect a path.
        
        # Ensure temp_file_path_obj is set for download
        if not temp_file_path_obj: # Should have been created by NamedTemporaryFile
             raise StorageOperationError("Failed to create temporary file path for download.")

        obj.download(destination_path=str(temp_file_path_obj), overwrite_existing=True)
        
        # Parse the JSON data
        with open(temp_file_path_obj, 'r', encoding='utf-8') as f: # Read in text mode
            data = json.loads(f.read())
        
        # Clean up the temporary file
        # Moved to finally block
        
        # Skip updates from our own server
        if data.get("server_id") == SERVER_ID:
            return
            
        # Extract the data
        url = data["url"]
        feed_content = data.get("feed_content")
        feed_data = data.get("feed_data")
        source_server = data.get("server_id", "unknown")
        
        logger.info(f"Received feed update for {url} from {source_server} with {'content' if feed_content else 'no content'}")
        
        # Call registered callbacks
        for cb in _feed_update_callbacks:
            try:
                cb(url, feed_content, feed_data)
            except Exception as e:
                logger.error(f"Error in feed update callback: {e}")
    except LibcloudError as e:
        logger.error(f"Libcloud error processing update object {obj.name}: {e}")
    except FileNotFoundError as e: # For temp file not found after creation (unlikely with NamedTemporaryFile)
        logger.error(f"Temporary file not found for {obj.name}: {e}")
    except IOError as e: # For temp file read/write issues
        logger.error(f"I/O error processing update object {obj.name}: {e}")
    except json.JSONDecodeError as e: # For JSON parsing issues
        logger.error(f"JSON decode error processing update object {obj.name}: {e}")
    except Exception as e: 
        logger.error(f"Error processing update object: {e}")
    finally:
        # Clean up the temporary file
        if temp_file_path_obj and temp_file_path_obj.exists():
            try:
                temp_file_path_obj.unlink()
            except OSError as e: # Log specific error for cleanup failure (III.2)
                logger.warning(f"Failed to remove temporary download file {temp_file_path_obj}: {e}")

def storage_watcher_thread():
    """Background thread function to periodically check for updates"""
    global _sync_running
    
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return
        
    logger.info("Storage watcher thread started")
    _sync_running = True
    
    while _sync_running:
        try:
            check_for_updates()
        except StorageError as e: # Catch our custom storage errors
            logger.error(f"Storage error in watcher: {e}")
        except Exception as e:
            logger.error(f"Error in storage watcher: {e}")
            
        # Sleep until next check
        time.sleep(CHECK_INTERVAL)

class FeedFileEventHandler(FileSystemEventHandler):
    """Event handler for file system events on the cache directory"""
    
    def on_modified(self, event):
        """Called when a file is modified"""
        if not event.is_directory:
            try:
                file_path = event.src_path
                if file_path.endswith('.feed'):
                    # Parse the feed URL from the filename
                    filename = os.path.basename(file_path)
                    feed_url = filename.replace('.feed', '')
                    
                    # Read the feed content
                    with open(file_path, 'r') as f:
                        feed_content = f.read()
                    
                    # Publish the update
                    publish_feed_update(feed_url, feed_content)
                    logger.info(f"Published feed update for {feed_url} triggered by file change")
            except IOError as e: # For file read error
                logger.error(f"I/O error handling file modification for {feed_url}: {e}")
            except Exception as e:
                logger.error(f"Error handling file modification: {e}")

def start_file_watcher(watch_dir):
    """Start watching a directory for file changes to automatically publish feed updates"""
    global _observer, _file_event_handler
    
    if not WATCHDOG_AVAILABLE:
        logger.warning("Cannot start file watcher: watchdog module not available")
        return False
    
    if _observer is not None:
        # Already running
        return True
    
    try:
        _file_event_handler = FeedFileEventHandler()
        _observer = Observer()
        _observer.schedule(_file_event_handler, watch_dir, recursive=False)
        _observer.start()
        logger.info(f"File watcher started for directory: {watch_dir}")
        return True
    except Exception as e: # Watchdog specific exceptions could be caught here if known
        logger.error(f"Error starting file watcher: {e}")
        _observer = None
        return False

def stop_file_watcher():
    """Stop the file watcher"""
    global _observer
    
    if _observer is not None:
        _observer.stop()
        _observer.join()
        _observer = None
        logger.info("File watcher stopped")

def start_storage_watcher():
    """Start the background thread for checking storage updates"""
    global _watcher_thread
    
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return False
        
    if _watcher_thread is not None and _watcher_thread.is_alive():
        return True  # Already running
        
    if init_storage():
        _watcher_thread = threading.Thread(target=storage_watcher_thread, daemon=True)
        _watcher_thread.start()
        logger.info("Storage watcher started")
        return True
        
    return False

def stop_storage_watcher():
    """Stop the storage watcher thread"""
    global _sync_running
    
    _sync_running = False
    if _watcher_thread is not None:
        # Wait for thread to finish
        _watcher_thread.join(timeout=CHECK_INTERVAL + 1)
        logger.info("Storage watcher stopped")

def cleanup_old_updates(max_age_hours=24):
    """Clean up old update objects in storage
    
    Args:
        max_age_hours: Maximum age of objects to keep (in hours)
    """
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return
        
    if not init_storage():
        return
    
    try:
        # List objects with our prefix
        objects = list(_storage_container.list_objects(prefix=STORAGE_SYNC_PREFIX))
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for obj in objects:
            try:
                # Use metadata for timestamp (VI.1)
                timestamp_str = None
                if obj.meta_data:
                    timestamp_str = obj.meta_data.get('timestamp')
                
                if timestamp_str:
                    timestamp = float(timestamp_str)
                    age = current_time - timestamp
                    
                    if age > max_age_seconds:
                        # Delete old object
                        _storage_container.delete_object(obj) # This should be obj.name or obj itself depending on API
                                                              # _storage_container.delete_object(obj) is usually correct for libcloud
                        logger.info(f"Cleaned up old update object: {obj.name} (age: {age/3600:.2f} hours)")
                else:
                    # Fallback or warning if timestamp metadata is missing
                    logger.warning(f"Object {obj.name} is missing timestamp metadata during cleanup. Skipping.")

            except ValueError:
                logger.warning(f"Could not parse timestamp for object {obj.name} during cleanup. Skipping.")
            except Exception as e:
                logger.warning(f"Error processing object {obj.name} during cleanup: {e}")
    except Exception as e:
        logger.error(f"Error cleaning up old updates: {e}")

def configure_storage(enabled: bool = False, **kwargs) -> bool:
    """Configure object storage settings.
    
    Args:
        enabled: Whether to enable object storage functionality
        **kwargs: Additional configuration options
        
    Returns:
        bool: True if configuration was successful
        
    Raises:
        ConfigurationError: If configuration is invalid
    """
    global STORAGE_ENABLED, STORAGE_PROVIDER, STORAGE_REGION, STORAGE_BUCKET_NAME
    global STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY, STORAGE_HOST, STORAGE_CHECK_INTERVAL
    global STORAGE_CACHE_DIR, STORAGE_SYNC_PREFIX
    global _secrets_loaded

    # If libcloud is not available, always force disabled
    if not LIBCLOUD_AVAILABLE:
        if enabled:
            logger.warning("apache-libcloud is not installed. Feed synchronization remains disabled.")
        return False
    
    try:
        # Update configuration
        new_config = {
            'enabled': enabled,
            'provider': kwargs.get('provider', STORAGE_PROVIDER),
            'region': kwargs.get('region', STORAGE_REGION),
            'bucket_name': kwargs.get('bucket_name', STORAGE_BUCKET_NAME),
            'access_key': kwargs.get('access_key', STORAGE_ACCESS_KEY),
            'secret_key': kwargs.get('secret_key', STORAGE_SECRET_KEY),
            'host': kwargs.get('host', STORAGE_HOST),
            'check_interval': kwargs.get('check_interval', STORAGE_CHECK_INTERVAL),
            'cache_dir': kwargs.get('cache_dir', STORAGE_CACHE_DIR),
            'sync_prefix': kwargs.get('sync_prefix', STORAGE_SYNC_PREFIX)
        }
        
        # Validate configuration if enabled
        if new_config['enabled']:
            if not new_config['access_key'] or not new_config['secret_key']:
                raise ConfigurationError("Storage access key and secret key must be provided")
            if not new_config['bucket_name']:
                raise ConfigurationError("Storage bucket name must be provided")
        
        # Update global variables
        STORAGE_ENABLED = new_config['enabled']
        STORAGE_PROVIDER = new_config['provider']
        STORAGE_REGION = new_config['region']
        STORAGE_BUCKET_NAME = new_config['bucket_name']
        STORAGE_ACCESS_KEY = new_config['access_key']
        STORAGE_SECRET_KEY = new_config['secret_key']
        STORAGE_HOST = new_config['host']
        STORAGE_CHECK_INTERVAL = new_config['check_interval']
        STORAGE_CACHE_DIR = new_config['cache_dir']
        STORAGE_SYNC_PREFIX = new_config['sync_prefix']
        
        # Reset driver when configuration changes
        global _storage_driver, _storage_container
        _storage_driver = None
        _storage_container = None
        
        # If enabling, secrets might need to be re-evaluated or re-loaded.
        if STORAGE_ENABLED:
            if not STORAGE_ACCESS_KEY or not STORAGE_SECRET_KEY:
                 logger.info("Storage enabled. Access/secret keys will be loaded by init_storage if not already set.")

            if kwargs.get('access_key') or kwargs.get('secret_key'):
                _secrets_loaded = True 
            elif STORAGE_ENABLED and (not STORAGE_ACCESS_KEY or not STORAGE_SECRET_KEY):
                 _secrets_loaded = False 

        # Start or stop services based on enabled state
        if STORAGE_ENABLED:
            return start_storage_watcher()
        else:
            stop_storage_watcher()
            return True
            
    except ConfigurationError as e: # Catch our own config errors
        raise # Re-raise if already specific
    except Exception as e:
        raise ConfigurationError(f"Failed to configure storage: {e}")

def cleanup_storage() -> None:
    """Clean up storage resources.
    
    This should be called when shutting down the application.
    """
    global _storage_driver, _storage_container
    
    try:
        stop_storage_watcher()
        stop_file_watcher()
        
        # Close any open connections
        if _storage_driver is not None:
            _storage_driver = None
        if _storage_container is not None:
            _storage_container = None
            
        logger.info("Storage resources cleaned up")
    except Exception as e: # General catch for cleanup, could be libcloud client closing issues etc.
        logger.error(f"Error cleaning up storage resources: {e}")

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

def generate_file_object_name(file_path):
    """Generate a unique object name for a file
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: Unique object name for storage
    """
    file_hash = hashlib.md5(file_path.encode()).hexdigest()
    timestamp = int(time.time())
    return f"{STORAGE_SYNC_PREFIX}files/{SERVER_ID}/{file_hash}_{timestamp}"

def publish_file(file_path, metadata=None):
    """Publish a file to object storage
    
    Args:
        file_path: Path to the file to publish
        metadata: Optional additional metadata about the file
        
    Returns:
        Object: The uploaded storage object or None if failed
    """
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None
        
    if not init_storage():
        return None
    
    try:
        # Get file metadata
        file_metadata = get_file_metadata(file_path)
        if not file_metadata:
            return None
            
        # Generate object name
        object_name = generate_file_object_name(file_path)
        
        # Prepare metadata
        extra_metadata = {
            'meta_data': {
                'server_id': SERVER_ID,
                'file_path': file_path,
                'file_hash': file_metadata['hash'],
                'file_size': str(file_metadata['size']),
                'mtime': str(file_metadata['mtime']),
                'timestamp': str(time.time())
            }
        }
        
        if metadata:
            extra_metadata['meta_data'].update(metadata)
            
        # Create a BytesIO object for streaming
        content_stream = BytesIO(file_metadata['content'])
        
        # Upload using streaming
        obj = _storage_driver.upload_object_via_stream(
            iterator=content_stream,
            container=_storage_container,
            object_name=object_name,
            extra=extra_metadata
        )
            
        logger.info(f"Published file {file_path} to object storage as {object_name}")
        return obj
    except LibcloudError as e:
        logger.error(f"Libcloud error publishing file {file_path} to object storage: {e}")
        return None
    except IOError as e: # For BytesIO or file_metadata content issues
        logger.error(f"I/O error publishing file {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error publishing file to object storage: {e}")
        return None

def fetch_file(file_path, force=False):
    """Fetch a file from object storage if it has changed
    
    Args:
        file_path: Path to the file to fetch
        force: If True, fetch regardless of changes
        
    Returns:
        tuple: (content, metadata) if successful, (None, None) if failed
    """
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None, None
        
    if not init_storage():
        return None, None
    
    try:
        # Get current file metadata if it exists
        current_metadata_content = None # Store content to avoid re-reading
        current_file_hash = None
        if os.path.exists(file_path):
            current_file_meta = get_file_metadata(file_path)
            if current_file_meta:
                current_metadata_content = current_file_meta['content']
                current_file_hash = current_file_meta['hash']
            
        # Find the latest version of the file using the helper (V.2)
        # The prefix for 'files' is f"{STORAGE_SYNC_PREFIX}files/"
        file_prefix = f"{STORAGE_SYNC_PREFIX}files/"
        latest_obj = _find_latest_object_version(file_path, file_prefix)
                
        if not latest_obj:
            logger.info(f"No version found for file {file_path} in object storage.")
            return None, None
            
        # Check if we need to update
        if not force and current_file_hash:
            latest_hash_from_meta = latest_obj.meta_data.get('file_hash')
            if latest_hash_from_meta == current_file_hash:
                logger.info(f"File {file_path} is up to date (hash match). Returning local content.")
                return current_metadata_content, latest_obj.meta_data
                
        # Download the content using streaming
        content_buffer = BytesIO()
        # Ensure latest_obj is not None before download. Covered by the check above.
        _storage_driver.download_object_as_stream(latest_obj, content_buffer) # Use download_object_as_stream
        content = content_buffer.getvalue()
        content_buffer.close() # Close the buffer
        
        logger.info(f"Fetched updated version of {file_path} from object storage.")
        return content, latest_obj.meta_data
    except LibcloudError as e: # More specific exception
        logger.error(f"Libcloud error fetching file {file_path} from object storage: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Generic error fetching file {file_path} from object storage: {e}")
        return None, None

def fetch_file_stream(file_path, force=False):
    """Fetch a file from object storage as a stream if it has changed
    
    Args:
        file_path: Path to the file to fetch
        force: If True, fetch regardless of changes
        
    Returns:
        tuple: (stream, metadata) if successful, (None, None) if failed
    """
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None, None
        
    if not init_storage():
        return None, None
    
    try:
        # Get current file metadata if it exists
        current_metadata_content = None # Store content for BytesIO stream
        current_file_hash = None
        if os.path.exists(file_path):
            current_file_meta = get_file_metadata(file_path)
            if current_file_meta:
                current_metadata_content = current_file_meta['content']
                current_file_hash = current_file_meta['hash']
            
        # Find the latest version of the file using the helper (V.2)
        file_prefix = f"{STORAGE_SYNC_PREFIX}files/"
        latest_obj = _find_latest_object_version(file_path, file_prefix)
                
        if not latest_obj:
            logger.info(f"No version found for file {file_path} in object storage (for stream).")
            return None, None
            
        # Check if we need to update
        if not force and current_file_hash:
            latest_hash_from_meta = latest_obj.meta_data.get('file_hash')
            if latest_hash_from_meta == current_file_hash:
                logger.info(f"File {file_path} is up to date (hash match). Returning stream of local content.")
                return BytesIO(current_metadata_content) if current_metadata_content else None, latest_obj.meta_data
                
        # Get the object's stream
        # Ensure latest_obj is not None. Covered by the check above.
        stream = _storage_driver.download_object_as_stream(latest_obj) # download_object_as_stream returns an iterator
        
        logger.info(f"Fetched updated version of {file_path} as stream from object storage.")
        return stream, latest_obj.meta_data
    except LibcloudError as e: # More specific exception
        logger.error(f"Libcloud error fetching file stream for {file_path} from object storage: {e}")
        return None, None
    except IOError as e: # For BytesIO issues if current_metadata_content is bad
        logger.error(f"I/O error with local content stream for {file_path}: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Generic error fetching file stream for {file_path} from object storage: {e}")
        return None, None

def list_file_versions(file_path):
    """List all versions of a file in storage
    
    Args:
        file_path: Path to the file
        
    Returns:
        list: List of version objects with metadata
    """
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return []
        
    if not init_storage():
        return []
    
    try:
        versions = []
        prefix = f"{STORAGE_SYNC_PREFIX}files/"
        objects = list(_storage_container.list_objects(prefix=prefix))
        
        for obj in objects:
            try:
                if obj.meta_data.get('file_path') == file_path:
                    versions.append({
                        'object_name': obj.name,
                        'timestamp': float(obj.meta_data.get('timestamp', 0)),
                        'hash': obj.meta_data.get('file_hash'),
                        'size': int(obj.meta_data.get('file_size', 0)),
                        'server_id': obj.meta_data.get('server_id')
                    })
            except:
                continue
                
        # Sort by timestamp descending
        versions.sort(key=lambda x: x['timestamp'], reverse=True)
        return versions
    except LibcloudError as e:
        logger.error(f"Libcloud error listing file versions for {file_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error listing file versions: {e}")
        return []

def delete_file_version(object_name):
    """Delete a specific version of a file
    
    Args:
        object_name: Name of the object to delete
        
    Returns:
        bool: True if deletion was successful
    """
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return False
        
    if not init_storage():
        return False
    
    try:
        _storage_container.delete_object(object_name)
        logger.info(f"Deleted file version: {object_name}")
        return True
    except LibcloudError as e:
        logger.error(f"Libcloud error deleting file version {object_name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error deleting file version: {e}")
        return False

# Helper function for V.2 (fetch_file and fetch_file_stream)
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