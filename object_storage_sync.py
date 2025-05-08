"""
object_storage_sync.py

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

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("object_storage_sync")

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

# Object Storage configuration
STORAGE_ENABLED = False  # Global switch to enable/disable object storage functionality
STORAGE_PROVIDER = Provider.S3  # Default provider (S3 protocol)
STORAGE_REGION = "us-east-1"  # Default region
STORAGE_BUCKET_NAME = "feed-sync"  # Default bucket name
STORAGE_ACCESS_KEY = ""
STORAGE_SECRET_KEY = ""
STORAGE_HOST = "s3.linode.com"  # For Linode Object Storage

# Sync configuration
SYNC_PREFIX = "feed-updates/"  # Prefix for feed updates
CHECK_INTERVAL = 30  # Default interval to check for updates (seconds)
SERVER_ID = os.getenv("SERVER_ID", hashlib.md5(os.uname().nodename.encode()).hexdigest()[:8])
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

def init_storage():
    """Initialize storage driver if enabled"""
    global _storage_driver, _storage_container
    
    if not LIBCLOUD_AVAILABLE:
        return False
        
    if not STORAGE_ENABLED:
        return False
    
    if _storage_driver is None:
        try:
            cls = get_driver(STORAGE_PROVIDER)
            _storage_driver = cls(
                STORAGE_ACCESS_KEY, 
                STORAGE_SECRET_KEY,
                region=STORAGE_REGION,
                host=STORAGE_HOST
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
            if not os.path.exists(CACHE_DIR):
                os.makedirs(CACHE_DIR)
                
            return True
        except Exception as e:
            logger.error(f"Error initializing storage driver: {e}")
            _storage_driver = None
            return False
    
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
    return f"{SYNC_PREFIX}{SERVER_ID}/{url_hash}_{timestamp}.json"

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
        objects = list(_storage_container.list_objects(prefix=SYNC_PREFIX))
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
        objects = list(_storage_container.list_objects(prefix=SYNC_PREFIX))
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

def configure_storage(enabled=False, provider=None, region=None, bucket_name=None, 
                     access_key=None, secret_key=None, host=None, check_interval=None):
    """Configure object storage settings
    
    Args:
        enabled: Whether to enable object storage functionality
        provider: Storage provider (Provider.S3, etc.)
        region: Storage region
        bucket_name: Storage bucket name
        access_key: Storage access key
        secret_key: Storage secret key
        host: Storage host (for S3-compatible storage)
        check_interval: Interval to check for updates (seconds)
    """
    global STORAGE_ENABLED, STORAGE_PROVIDER, STORAGE_REGION, STORAGE_BUCKET_NAME
    global STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY, STORAGE_HOST, CHECK_INTERVAL
    
    # If libcloud is not available, always force disabled
    if not LIBCLOUD_AVAILABLE:
        STORAGE_ENABLED = False
        if enabled:
            logger.warning("apache-libcloud is not installed. Feed synchronization remains disabled.")
        return False
    
    was_enabled = STORAGE_ENABLED
    STORAGE_ENABLED = enabled
    
    # Update configuration if provided
    if provider is not None:
        STORAGE_PROVIDER = provider
    
    if region is not None:
        STORAGE_REGION = region
    
    if bucket_name is not None:
        STORAGE_BUCKET_NAME = bucket_name
    
    if access_key is not None:
        STORAGE_ACCESS_KEY = access_key
    
    if secret_key is not None:
        STORAGE_SECRET_KEY = secret_key
    
    if host is not None:
        STORAGE_HOST = host
    
    if check_interval is not None:
        CHECK_INTERVAL = check_interval
    
    # Reset driver when configuration changes
    global _storage_driver, _storage_container
    _storage_driver = None
    _storage_container = None
    
    # Start or stop services based on enabled state
    if STORAGE_ENABLED:
        if was_enabled:
            # If it was already enabled, restart services
            stop_storage_watcher()
        return start_storage_watcher()
    else:
        if was_enabled:
            stop_storage_watcher()
        return False 