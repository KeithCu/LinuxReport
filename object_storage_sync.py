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
    try:
        config = load_config()
        storage_config = config.get('storage')
        
        if not storage_config:
            raise ConfigurationError("Missing 'storage' section in config.yaml")
            
        # Only load secrets
        global STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY
        STORAGE_ACCESS_KEY = storage_config.get('access_key', '')
        STORAGE_SECRET_KEY = storage_config.get('secret_key', '')
        
        if STORAGE_ENABLED and (not STORAGE_ACCESS_KEY or not STORAGE_SECRET_KEY):
            raise ConfigurationError("Storage access key and secret key must be provided in config.yaml")
            
    except Exception as e:
        logger.error(f"Error loading storage secrets: {e}")
        raise

# Set up logging with structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("object_storage_sync")

# Initialize configuration
try:
    load_storage_secrets()
except Exception as e:
    logger.error(f"Error loading storage secrets: {e}")

# Check if libcloud is available
LIBCLOUD_AVAILABLE = False
try:
    from libcloud.storage.types import Provider, ContainerDoesNotExistError
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
        except Exception as e:
            raise ConfigurationError(f"Failed to create cache directory: {e}")
            
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
            versions = list_file_versions(object_name)
            
            if not versions:
                return None
                
            # Get the latest version
            latest_version = max(versions, key=lambda x: x['timestamp'])
            
            # Use existing fetch_file_stream for better integration
            stream, metadata = fetch_file_stream(object_name, force=True)
            if stream is None:
                return None
                
            # Read and parse the content
            data = json.loads(stream.read().decode('utf-8'))
            
            # Check expiration
            expires = float(metadata.get('expires', 'inf'))
            if expires != float('inf') and time.time() > expires:
                self.delete(key)  # Clean up expired entry
                return None
                
            return data.get('value')
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in cache for key {key}: {e}")
            return None
        except Exception as e:
            raise StorageOperationError(f"Error getting cache value for {key}: {e}")
            
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
        try:
            object_name = self._get_object_name(key)
            
            # Prepare the data
            data = {
                'value': value,
                'timestamp': time.time(),
                'expires': time.time() + timeout if timeout else None
            }
            
            # Write to temporary file
            temp_path = self.cache_dir / f"temp_{int(time.time())}"
            with open(temp_path, 'w') as f:
                json.dump(data, f)
                
            # Use existing publish_file for better integration
            metadata = {
                'cache_key': key,
                'timestamp': str(time.time()),
                'expires': str(data['expires']) if data['expires'] else 'never',
                'type': 'cache_entry',
                'server_id': SERVER_ID
            }
            
            publish_file(str(temp_path), metadata)
                
        except Exception as e:
            raise StorageOperationError(f"Error putting cache value for {key}: {e}")
        finally:
            # Clean up temp file
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception as e:
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
            
        try:
            object_name = self._get_object_name(key)
            versions = list_file_versions(object_name)
            
            for version in versions:
                delete_file_version(version['object_name'])
                
        except Exception as e:
            raise StorageOperationError(f"Error deleting cache value for {key}: {e}")
            
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
            
        try:
            object_name = self._get_object_name(key)
            versions = list_file_versions(object_name)
            
            if not versions:
                return False
                
            # Get the latest version
            latest_version = max(versions, key=lambda x: x['timestamp'])
            
            # Check expiration
            expires = float(latest_version.get('expires', 'inf'))
            if expires != float('inf') and time.time() > expires:
                self.delete(key)  # Clean up expired entry
                return False
                
            return True
            
        except Exception as e:
            raise StorageOperationError(f"Error checking cache for {key}: {e}")
            
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
            
        try:
            object_name = self._get_object_name(key)
            return list_file_versions(object_name)
        except Exception as e:
            raise StorageOperationError(f"Error listing versions for {key}: {e}")
            
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
                    except Exception as e:
                        logger.warning(f"Error processing object during cleanup: {e}")
                        continue
                        
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
        return False
        
    if not STORAGE_ENABLED:
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
        except Exception as e:
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
    
    try:
        # Create a unique object name
        object_name = generate_object_name(url)
        
        # Create a JSON string from the data
        json_data = json.dumps(data)
        
        # Create a temporary file
        temp_file_path = os.path.join(CACHE_DIR, f"temp_{SERVER_ID}_{int(time.time())}.json")
        with open(temp_file_path, 'w') as f:
            f.write(json_data)
        
        # Upload the file
        with open(temp_file_path, 'rb') as iterator:
            extra = {
                'meta_data': {
                    'server_id': SERVER_ID,
                    'feed_url': url,
                    'timestamp': str(time.time())
                },
                'content_type': 'application/json'
            }
            obj = _storage_driver.upload_object_via_stream(
                iterator=iterator,
                container=_storage_container,
                object_name=object_name,
                extra=extra
            )
            
        # Clean up the temporary file
        try:
            os.remove(temp_file_path)
        except:
            pass
            
        logger.info(f"Published feed update for {url} to object storage as {object_name}")
        return obj
    except Exception as e:
        logger.error(f"Error publishing feed update to object storage: {e}")
        return None

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
                
            # Parse server ID from object name
            try:
                parts = obj.name.split('/')
                if len(parts) >= 2:
                    obj_server_id = parts[1].split('/')[0]
                    
                    # Skip our own updates
                    if obj_server_id == SERVER_ID:
                        _last_known_objects[obj.name] = current_time
                        continue
            except:
                # If we can't parse the server ID, still process it
                pass
            
            # Download and process the object
            process_update_object(obj)
            
            # Mark as known
            _last_known_objects[obj.name] = current_time
        
        # Clean up old entries from our cache
        expired_time = current_time - 3600  # 1 hour expiration
        expired_keys = [k for k, v in _last_known_objects.items() if v < expired_time]
        for key in expired_keys:
            del _last_known_objects[key]
            
        _last_check_time = current_time
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")

def process_update_object(obj):
    """Process a feed update object"""
    try:
        # Download the object to a temporary file
        temp_file_path = os.path.join(CACHE_DIR, f"temp_download_{int(time.time())}.json")
        obj.download(temp_file_path)
        
        # Parse the JSON data
        with open(temp_file_path, 'r') as f:
            data = json.loads(f.read())
        
        # Clean up the temporary file
        try:
            os.remove(temp_file_path)
        except:
            pass
        
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
    except Exception as e:
        logger.error(f"Error processing update object: {e}")

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
    except Exception as e:
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
                # Extract timestamp from object name
                parts = obj.name.split('_')
                if len(parts) > 1:
                    timestamp = int(parts[-1].split('.')[0])
                    age = current_time - timestamp
                    
                    if age > max_age_seconds:
                        # Delete old object
                        _storage_container.delete_object(obj)
                        logger.info(f"Cleaned up old update object: {obj.name}")
            except Exception as e:
                logger.warning(f"Error processing object during cleanup: {e}")
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
    
    # If libcloud is not available, always force disabled
    if not LIBCLOUD_AVAILABLE:
        if enabled:
            logger.warning("apache-libcloud is not installed. Feed synchronization remains disabled.")
        return False
    
    try:
        # Update configuration
        new_config = {
            'enabled': enabled,
            'provider': STORAGE_PROVIDER,
            'region': STORAGE_REGION,
            'bucket_name': STORAGE_BUCKET_NAME,
            'access_key': STORAGE_ACCESS_KEY,
            'secret_key': STORAGE_SECRET_KEY,
            'host': STORAGE_HOST,
            'check_interval': STORAGE_CHECK_INTERVAL,
            'cache_dir': STORAGE_CACHE_DIR,
            'sync_prefix': STORAGE_SYNC_PREFIX
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
        
        # Start or stop services based on enabled state
        if STORAGE_ENABLED:
            return start_storage_watcher()
        else:
            stop_storage_watcher()
            return True
            
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
    except Exception as e:
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
        from io import BytesIO
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
        current_metadata = None
        if os.path.exists(file_path):
            current_metadata = get_file_metadata(file_path)
            
        # List objects with matching prefix
        file_hash = hashlib.md5(file_path.encode()).hexdigest()
        prefix = f"{STORAGE_SYNC_PREFIX}files/"
        objects = list(_storage_container.list_objects(prefix=prefix))
        
        # Find the latest version of the file
        latest_obj = None
        latest_timestamp = 0
        
        for obj in objects:
            try:
                # Extract metadata
                meta = obj.meta_data
                if meta.get('file_path') == file_path:
                    timestamp = float(meta.get('timestamp', 0))
                    if timestamp > latest_timestamp:
                        latest_obj = obj
                        latest_timestamp = timestamp
            except:
                continue
                
        if not latest_obj:
            logger.info(f"No version found for file {file_path}")
            return None, None
            
        # Check if we need to update
        if not force and current_metadata:
            latest_hash = latest_obj.meta_data.get('file_hash')
            if latest_hash == current_metadata['hash']:
                logger.info(f"File {file_path} is up to date")
                return current_metadata['content'], latest_obj.meta_data
                
        # Download the content using streaming
        from io import BytesIO
        content_buffer = BytesIO()
        latest_obj.download(content_buffer)
        content = content_buffer.getvalue()
        
        logger.info(f"Fetched updated version of {file_path}")
        return content, latest_obj.meta_data
    except Exception as e:
        logger.error(f"Error fetching file from object storage: {e}")
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
        current_metadata = None
        if os.path.exists(file_path):
            current_metadata = get_file_metadata(file_path)
            
        # List objects with matching prefix
        file_hash = hashlib.md5(file_path.encode()).hexdigest()
        prefix = f"{STORAGE_SYNC_PREFIX}files/"
        objects = list(_storage_container.list_objects(prefix=prefix))
        
        # Find the latest version of the file
        latest_obj = None
        latest_timestamp = 0
        
        for obj in objects:
            try:
                # Extract metadata
                meta = obj.meta_data
                if meta.get('file_path') == file_path:
                    timestamp = float(meta.get('timestamp', 0))
                    if timestamp > latest_timestamp:
                        latest_obj = obj
                        latest_timestamp = timestamp
            except:
                continue
                
        if not latest_obj:
            logger.info(f"No version found for file {file_path}")
            return None, None
            
        # Check if we need to update
        if not force and current_metadata:
            latest_hash = latest_obj.meta_data.get('file_hash')
            if latest_hash == current_metadata['hash']:
                logger.info(f"File {file_path} is up to date")
                # Return a BytesIO stream of the current content
                from io import BytesIO
                return BytesIO(current_metadata['content']), latest_obj.meta_data
                
        # Get the object's stream
        stream = latest_obj.as_stream()
        
        logger.info(f"Fetched updated version of {file_path} as stream")
        return stream, latest_obj.meta_data
    except Exception as e:
        logger.error(f"Error fetching file stream from object storage: {e}")
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
    except Exception as e:
        logger.error(f"Error deleting file version: {e}")
        return False 