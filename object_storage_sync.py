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
import os.path
from pathlib import Path
from io import BytesIO
from config_utils import load_config
from typing import Any, Optional, Dict, List

# Import from object_storage_config
from object_storage_config import (
    logger, LIBCLOUD_AVAILABLE, WATCHDOG_AVAILABLE, STORAGE_ENABLED,
    StorageError, ConfigurationError, StorageConnectionError, StorageOperationError,
    StorageProvider, init_storage, SERVER_ID, STORAGE_SYNC_PREFIX,
    CHECK_INTERVAL, STORAGE_CACHE_DIR, STORAGE_BUCKET_NAME, STORAGE_ACCESS_KEY,
    STORAGE_SECRET_KEY, STORAGE_PROVIDER, STORAGE_REGION, STORAGE_HOST,
    STORAGE_CHECK_INTERVAL, STORAGE_SYNC_PREFIX,
    _feed_update_callbacks, _storage_driver, _storage_container,
    _last_check_time, _last_known_objects, _sync_running, _secrets_loaded,
    _watcher_thread, _observer, _file_event_handler
)

# Ensure libcloud imports are available when needed
if LIBCLOUD_AVAILABLE:
    from libcloud.storage.types import Provider, ContainerDoesNotExistError, ObjectDoesNotExistError
    from libcloud.storage.providers import get_driver
    from libcloud.storage.base import Object
    from libcloud.common.types import LibcloudError

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

def check_for_updates():
    """Check object storage for new feed updates from other servers"""
    
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
    try:
        # Download the object content into a BytesIO buffer
        content_buffer = BytesIO()
        _storage_driver.download_object_as_stream(obj, content_buffer)
        content_buffer.seek(0) # Reset buffer position to the beginning for reading
        
        # Parse the JSON data directly from the buffer
        # The content is bytes, so decode to string before json.loads
        data = json.loads(content_buffer.read().decode('utf-8'))
        content_buffer.close() # Close the buffer

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
        # No longer needed as we are using BytesIO
        pass

def storage_watcher_thread():
    """Background thread function to periodically check for updates"""
    
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return
        
    logger.info("Storage watcher thread started")
    global _sync_running
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
                logger.error(f"I/O error handling file modification for {event.src_path}: {e}")
            except Exception as e:
                logger.error(f"Error handling file modification: {e}")

def start_file_watcher(watch_dir):
    """Start watching a directory for file changes to automatically publish feed updates"""
    
    if not WATCHDOG_AVAILABLE:
        logger.warning("Cannot start file watcher: watchdog module not available")
        return False
    
    if _observer is not None:
        # Already running
        return True
    
    try:
        global _file_event_handler, _observer
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
    
    if _observer is not None:
        _observer.stop()
        _observer.join()
        global _observer
        _observer = None
        logger.info("File watcher stopped")

def start_storage_watcher():
    """Start the background thread for checking storage updates"""
    
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return False
        
    if _watcher_thread is not None and _watcher_thread.is_alive():
        return True  # Already running
        
    if init_storage():
        global _watcher_thread
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
        
        # Update global variables in object_storage_config module
        import object_storage_config
        object_storage_config.STORAGE_ENABLED = new_config['enabled']
        object_storage_config.STORAGE_PROVIDER = new_config['provider']
        object_storage_config.STORAGE_REGION = new_config['region']
        object_storage_config.STORAGE_BUCKET_NAME = new_config['bucket_name']
        object_storage_config.STORAGE_ACCESS_KEY = new_config['access_key']
        object_storage_config.STORAGE_SECRET_KEY = new_config['secret_key']
        object_storage_config.STORAGE_HOST = new_config['host']
        object_storage_config.STORAGE_CHECK_INTERVAL = new_config['check_interval']
        object_storage_config.STORAGE_CACHE_DIR = new_config['cache_dir']
        object_storage_config.STORAGE_SYNC_PREFIX = new_config['sync_prefix']
        
        # Reset driver when configuration changes
        global _storage_driver, _storage_container
        _storage_driver = None
        _storage_container = None
        
        # If enabling, secrets might need to be re-evaluated or re-loaded.
        if object_storage_config.STORAGE_ENABLED:
            if not object_storage_config.STORAGE_ACCESS_KEY or not object_storage_config.STORAGE_SECRET_KEY:
                 logger.info("Storage enabled. Access/secret keys will be loaded by init_storage if not already set.")

            if kwargs.get('access_key') or kwargs.get('secret_key'):
                _secrets_loaded = True 
            elif object_storage_config.STORAGE_ENABLED and (not object_storage_config.STORAGE_ACCESS_KEY or not object_storage_config.STORAGE_SECRET_KEY):
                 _secrets_loaded = False 

        # Start or stop services based on enabled state
        if object_storage_config.STORAGE_ENABLED:
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
    
    try:
        stop_storage_watcher()
        stop_file_watcher()
        
        # Close any open connections
        global _storage_driver, _storage_container
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
        if not force and os.path.exists(file_path):
            current_file_meta = get_file_metadata(file_path)
            if current_file_meta:
                current_metadata_content = current_file_meta['content']
                current_file_hash = current_file_meta['hash']
            
        # Use the helper function
        latest_obj, use_local_content = _prepare_file_fetch(file_path, current_file_hash if not force else None)
                
        if not latest_obj:
            # _prepare_file_fetch already logs if no version is found
            return None, None
            
        # Check if we need to update based on helper's output
        if use_local_content:
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
        if not force and os.path.exists(file_path):
            current_file_meta = get_file_metadata(file_path)
            if current_file_meta:
                current_metadata_content = current_file_meta['content']
                current_file_hash = current_file_meta['hash']
            
        # Use the helper function
        latest_obj, use_local_content = _prepare_file_fetch(file_path, current_file_hash if not force else None)
                
        if not latest_obj:
            # _prepare_file_fetch already logs if no version is found
            return None, None
            
        # Check if we need to update based on helper's output
        if use_local_content:
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
            except (KeyError, ValueError, TypeError) as e: # More specific exceptions
                logger.warning(f"Skipping object {obj.name} in list_file_versions due to metadata issue: {e}")
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
        # Retrieve the object first
        obj_to_delete = _storage_container.get_object(object_name=object_name)
        _storage_container.delete_object(obj_to_delete) # Pass the Object instance
        logger.info(f"Deleted file version: {object_name}")
        return True
    except ObjectDoesNotExistError: # Specific exception if object not found for deletion
        logger.warning(f"Attempted to delete non-existent object {object_name} during delete_file_version.")
        return False
    except LibcloudError as e:
        logger.error(f"Libcloud error deleting file version {object_name}: {e}")
        return False

# Helper function for V.2 (fetch_file and fetch_file_stream)
def _prepare_file_fetch(file_path: str, current_file_hash: Optional[str]):
    """Helper to prepare for fetching a file, returns (latest_obj, use_local_content_flag)."""
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None, False
        
    if not init_storage():
        return None, False

    file_prefix = f"{STORAGE_SYNC_PREFIX}files/"
    latest_obj = _find_latest_object_version(file_path, file_prefix)
            
    if not latest_obj:
        logger.info(f"No version found for file {file_path} in object storage.")
        return None, False
        
    # Check if we can use local content (if not forcing and hash matches)
    use_local_content = False
    if current_file_hash: # current_file_hash will be None if force=True in calling function, or file doesn't exist
        latest_hash_from_meta = latest_obj.meta_data.get('file_hash')
        if latest_hash_from_meta == current_file_hash:
            use_local_content = True
            
    return latest_obj, use_local_content

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