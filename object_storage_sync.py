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
import unittest

# Import from object_storage_config
from object_storage_config import (
    logger, LIBCLOUD_AVAILABLE, STORAGE_ENABLED,
    StorageError, ConfigurationError, StorageConnectionError, StorageOperationError,
    StorageProvider, init_storage, SERVER_ID, STORAGE_SYNC_PREFIX,
    STORAGE_BUCKET_NAME, STORAGE_ACCESS_KEY,
    STORAGE_SECRET_KEY, STORAGE_PROVIDER, STORAGE_REGION, STORAGE_HOST,
    STORAGE_SYNC_PREFIX,
    _storage_driver, _storage_container,
    _secrets_loaded,
    get_file_metadata
)

# Ensure libcloud imports are available when needed
if LIBCLOUD_AVAILABLE:
    from libcloud.storage.types import Provider, ContainerDoesNotExistError, ObjectDoesNotExistError
    from libcloud.storage.providers import get_driver
    from libcloud.storage.base import Object
    from libcloud.common.types import LibcloudError

def generate_object_name(url):
    """Generate a unique object name for a feed URL"""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    timestamp = int(time.time())
    return f"{STORAGE_SYNC_PREFIX}{SERVER_ID}/{url_hash}_{timestamp}.json"

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

class TestObjectStorageSync(unittest.TestCase):
    def test_generate_object_name(self):
        # Test that the function generates a string with the expected prefix and hash
        result = generate_object_name('http://example.com/feed')
        self.assertTrue(result.startswith('sync_prefixSERVER_ID/'))  # Assuming STORAGE_SYNC_PREFIX and SERVER_ID are set
        self.assertRegex(result, r'.*_\d+\.json$')  # Checks for hash and timestamp pattern

    def test_generate_file_object_name(self):
        # Test that the function generates a string with the expected file prefix and hash
        result = generate_file_object_name('/path/to/file.txt')
        self.assertTrue(result.startswith('sync_prefixfiles/SERVER_ID/'))  # Assuming STORAGE_SYNC_PREFIX and SERVER_ID are set
        self.assertRegex(result, r'.*_\d+$')  # Checks for hash and timestamp

    def test_publish_file(self):
        # Test publishing a sample file; assumes storage is configured
        test_file_path = 'test_file.txt'  # Create a temporary file for testing
        with open(test_file_path, 'w') as f:
            f.write('Test content')
        result = publish_file(test_file_path)
        self.assertIsNotNone(result, 'File upload should succeed if storage is configured')
        self.assertTrue(hasattr(result, 'name'), 'Uploaded object should have a name attribute')
        # Clean up
        os.remove(test_file_path)

    def test_fetch_file(self):
        # Test fetching a file; requires a previously published file
        test_file_path = 'test_file.txt'  # Assuming this file was published earlier
        content, metadata = fetch_file(test_file_path, force=True)
        self.assertIsNotNone(content, 'File fetch should succeed if the file exists in storage')
        self.assertIn(b'Test content', content, 'Fetched content should match published content')

    def test_get_file_metadata(self):
        # Test getting metadata for an existing file
        test_file_path = 'test_meta_file.txt'
        with open(test_file_path, 'w') as f:
            f.write('Test content')
        metadata = get_file_metadata(test_file_path)
        self.assertIsNotNone(metadata, 'Metadata should be retrieved')
        self.assertIn('hash', metadata, 'Metadata should include hash')
        self.assertGreater(metadata['size'], 0, 'Size should be greater than zero')
        os.remove(test_file_path)  # Clean up

        # Test for non-existent file
        non_existent_meta = get_file_metadata('non_existent_file.txt')
        self.assertIsNone(non_existent_meta, 'Should return None for non-existent file')

    def test_fetch_file_stream(self):
        # Test fetching a file stream; requires a previously published file
        test_file_path = 'test_file.txt'  # Assuming this was published in prior tests
        stream, metadata = fetch_file_stream(test_file_path, force=True)
        self.assertIsNotNone(stream, 'Stream fetch should succeed if the file exists')
        # Read and verify stream content
        content = b''.join([chunk for chunk in stream])  # Assuming stream is iterable
        self.assertIn(b'Test content', content, 'Stream content should match published content')

if __name__ == '__main__':
    import sys
    if not init_storage():  # Attempt to initialize storage before running tests
        print("Storage initialization failed; tests may not run fully.")
        sys.exit(1)
    unittest.main()
