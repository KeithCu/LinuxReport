"""
object_storage_sync.py

Object Storage-based publisher/subscriber for feed updates. Used to synchronize feed updates across multiple servers.
Uses libcloud to interface with object storage providers (like Linode Object Storage).

Optimizations for Linode Object Storage:
- Uses S3's built-in metadata (last-modified, etag, content-length) for caching
- Leverages Linode's eventual consistency with retry mechanisms
- Optimized for regional storage to reduce latency
"""
import time
import os
import hashlib
from io import BytesIO
from typing import Optional, Dict, Union, Any
from functools import wraps
import json
import datetime
import mimetypes

import unittest
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Import from object_storage_config
import object_storage_config as oss_config
from shared import g_cm

from object_storage_config import (
    LIBCLOUD_AVAILABLE, STORAGE_ENABLED,
    init_storage, SERVER_ID, STORAGE_SYNC_PATH,
    _storage_driver, _storage_container,
    StorageOperationError,
    ConfigurationError,
    StorageConnectionError,
    LibcloudError,
    generate_object_name,
    MAX_RETRY_ATTEMPTS,
    RETRY_MULTIPLIER,
    MAX_RETRY_INTERVAL
)

def generate_file_object_name(file_path: str) -> str:
    """Generate a unique object name for a file
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: Unique object name for storage
    """
    return generate_object_name(file_path, prefix="files")

def get_file_metadata(file_path: str) -> Optional[Dict]:
    """Get metadata for a file using S3's built-in metadata fields
    
    Args:
        file_path: Path to the file
        
    Returns:
        dict: File metadata including:
            - hash: SHA-256 hash of file contents
            - size: File size in bytes
            - last_modified: Last modified timestamp
            - content_type: MIME type of the file
            - content: File contents
            or None on error
    """
    try:
        # Check if file exists and is accessible
        if not os.path.exists(file_path):
            print(f"File does not exist: {file_path}")
            return None
            
        # Get basic file stats
        stats = os.stat(file_path)
        file_size = stats.st_size
        last_modified = datetime.datetime.fromtimestamp(stats.st_mtime)
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = 'application/octet-stream'
            
        # Read file and generate hash in one operation
        with open(file_path, 'rb') as f:
            content = f.read()
            file_hash = hashlib.sha256(content).hexdigest()
            
        return {
            'hash': file_hash,
            'size': file_size,
            'last_modified': last_modified,
            'content_type': content_type,
            'content': content
        }
    except Exception as e:
        print(f"Error getting file metadata for {file_path}: {e}")
        return None

def _init_check():
    """Ensure storage is initialized, raising an exception if not."""
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        raise ConfigurationError("Storage is not enabled or Libcloud is not available")
    if not init_storage():
        raise StorageConnectionError("Failed to initialize storage")
    return True

def _get_object_metadata(obj: Any) -> Dict:
    """Get S3 metadata from an object.
    
    Args:
        obj: S3 object to get metadata from
        
    Returns:
        dict: Object metadata including last_modified, size, and hash
    """
    return {
        'last_modified': obj.extra.get('last_modified'),
        'size': obj.size,
        'hash': obj.hash
    }

def _get_object(obj_name: str) -> Optional[Any]:
    """Get an object from storage.
    
    Args:
        obj_name: Name of the object to get
        
    Returns:
        object: The object if found, None otherwise
    """
    try:
        _init_check()
        try:
            return _storage_container.get_object(object_name=obj_name)
        except Exception:
            return None
    except Exception as e:
        print(f"Error getting object {obj_name}: {e}")
        raise

def retry_decorator(max_retries: int = MAX_RETRY_ATTEMPTS):
    """Create retry decorator for object storage operations"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return retry(
                    stop=stop_after_attempt(max_retries),
                    wait=wait_exponential(
                        multiplier=RETRY_MULTIPLIER,
                        max=MAX_RETRY_INTERVAL
                    ),
                    retry=retry_if_exception_type((StorageOperationError, LibcloudError)),
                    reraise=True
                )(func)(*args, **kwargs)
            except Exception as e:
                print(f"Operation {func.__name__} failed after retries: {str(e)}")
                raise
        return wrapper
    return decorator

@retry_decorator()
def publish_file(file_path: str) -> Any:
    """Publish a file from disk to object storage.
    
    Args:
        file_path: Path to the file to publish
        
    Returns:
        The uploaded object on success
    """
    try:
        _init_check()
        file_metadata = get_file_metadata(file_path)
        if file_metadata:
            bytes_data = file_metadata['content']
            return publish_bytes(bytes_data, file_path)
        print(f"No content found in file: {file_path}")
        return None
    except Exception as e:
        print(f"Error publishing file: {file_path}, exception: {e}")
        raise

@retry_decorator()
def fetch_file(file_path: str) -> tuple[Optional[bytes], Optional[Dict]]:
    """Fetch a file from object storage as bytes with its metadata.
    
    Args:
        file_path: Identifier for the file to fetch
    
    Returns:
        Tuple containing file content and metadata or None values if not found
    """
    try:
        content, metadata = fetch_bytes(file_path)
        print(f"Fetched file ({len(content) if content else 0} bytes) from key: {file_path}")
        return content, metadata
    except Exception as e:
        print(f"Error fetching file: {file_path}, exception: {e}")
        raise

@retry_decorator()
def publish_bytes(bytes_data: bytes, key: str) -> Any:
    """Publish raw bytes to object storage.
    
    Args:
        bytes_data: Data to publish
        key: Identifier for the object
        
    Returns:
        The uploaded object on success
    """
    try:
        _init_check()
        
        if not bytes_data and not isinstance(bytes_data, bytes):
            raise ValueError(f"Invalid bytes data. Type: {type(bytes_data)}, Data: {bytes_data}")
        
        # Generate a safe object key from the key identifier
        safe_key = generate_object_key(key, "data")
        object_name = f"{STORAGE_SYNC_PATH}bytes/{SERVER_ID}/{safe_key}"
        
        content_stream = BytesIO(bytes_data)
        obj = _storage_driver.upload_object_via_stream(
            iterator=content_stream,
            container=_storage_container,
            object_name=object_name
        )
        
        print(f"Published {len(bytes_data)} bytes to object: {object_name}")
        return obj
    except Exception as e:
        print(f"Error publishing bytes with key: {key}, exception: {e}")
        raise

@retry_decorator()
def fetch_bytes(key: str) -> tuple[Optional[bytes], Optional[Dict]]:
    """Fetch bytes data from object storage with its metadata.
    
    Args:
        key: Identifier for the object to fetch
    
    Returns:
        Tuple containing data and metadata or None values if not found
    """
    try:
        obj = _get_object(f"{STORAGE_SYNC_PATH}bytes/{SERVER_ID}/{generate_object_key(key, 'data')}")
        if obj:
            content_buffer = BytesIO()
            _storage_driver.download_object_as_stream(obj, content_buffer)
            content = content_buffer.getvalue()
            metadata = _get_object_metadata(obj)
            print(f"Retrieved {len(content)} bytes for key: {key}")
            return content, metadata
        
        print(f"No content found for key: {key}")
        return None, None
    except Exception as e:
        print(f"Error fetching bytes for key: {key}, exception: {e}")
        raise

@retry_decorator()
def smart_fetch(key: str, cache_expiry: int = None) -> tuple[Optional[bytes], Optional[Dict]]:
    """Smart fetch that handles caching and metadata checks using the global cache manager.
    
    Args:
        key: Identifier for the object to fetch
        cache_expiry: Optional cache expiry time in seconds
        
    Returns:
        Tuple containing raw bytes and metadata or None values if not found
    """
    try:
        # Check global cache first
        memory_key = f"objstorage_cache:{key}"
        cached_value = g_cm.get(memory_key)
        if cached_value is not None:
            return cached_value, None

        # Get object and metadata
        obj = _get_object(f"{STORAGE_SYNC_PATH}bytes/{SERVER_ID}/{generate_object_key(key, 'data')}")
        if not obj:
            return None, None

        metadata = _get_object_metadata(obj)
        
        # Check last-modified in global cache
        last_modified_key = f"{memory_key}:last_modified"
        cached_last_modified = g_cm.get(last_modified_key)
        
        if cached_last_modified == metadata['last_modified']:
            cached_content = g_cm.get(f"{memory_key}:content")
            if cached_content:
                return cached_content, metadata

        # Fetch content
        content_buffer = BytesIO()
        _storage_driver.download_object_as_stream(obj, content_buffer)
        content = content_buffer.getvalue()
        
        if not content:
            return None, None
            
        # Cache the results if expiry is provided
        if cache_expiry is not None:
            g_cm.set(memory_key, content, ttl=cache_expiry)
            g_cm.set(last_modified_key, metadata['last_modified'], ttl=cache_expiry)
            g_cm.set(f"{memory_key}:content", content, ttl=cache_expiry)
        
        return content, metadata
            
    except Exception as e:
        print(f"Error in smart_fetch for key: {key}, exception: {e}")
        raise

class TestObjectStorageSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test environment before running tests"""
        if not init_storage():
            raise RuntimeError("Failed to initialize storage for tests")
    
    def test_generate_object_name(self):
        result = generate_object_name('http://example.com/feed')
        self.assertTrue(result.startswith(f"{oss_config.STORAGE_SYNC_PATH}{oss_config.SERVER_ID}/feeds/"))
        self.assertTrue(result.endswith('.json'))
    
    def test_generate_file_object_name(self):
        result = generate_file_object_name('/path/to/file.txt')
        self.assertTrue(result.startswith(f"{oss_config.STORAGE_SYNC_PATH}files/{oss_config.SERVER_ID}/"))

    def test_publish_fetch_roundtrip(self):
        test_data = b'Test content for roundtrip'
        test_key = 'roundtrip_test'
        
        # Test 1: Upload
        uploaded_obj = publish_bytes(test_data, test_key)
        self.assertIsNotNone(uploaded_obj, "Publish should succeed")
        
        # Test 2: Fetch
        fetched_data, metadata = fetch_bytes(test_key)
        self.assertIsNotNone(fetched_data)
        self.assertEqual(fetched_data, test_data)
        
        # Verify metadata fields
        self.assertIn('last_modified', metadata)
        self.assertIn('size', metadata)
        self.assertIn('hash', metadata)

    def test_fetch_nonexistent(self):
        """Test fetching nonexistent data"""
        empty_bytes, empty_meta = fetch_bytes('nonexistent_key')
        self.assertIsNone(empty_bytes)
        self.assertIsNone(empty_meta)

    def test_error_scenarios(self):
        """Test various error scenarios"""
        # Test invalid key types
        with self.assertRaises(ValueError):
            publish_bytes(b'content', None)
            
        with self.assertRaises(ValueError):
            publish_bytes(b'content', 123)
            
        # Test empty content
        empty_obj = publish_bytes(b'', 'empty_key')
        self.assertIsNotNone(empty_obj, "Should allow publishing empty content")

    def test_object_key_safety(self):
        """Test that object key generation handles problematic inputs"""
        test_cases = [
            'normal_key',
            'key with spaces',
            'key/with/slashes',
            'key%with!special@chars',
            'key_with_über_unicode',
            'very/long/key/' + 'a' * 255,
        ]
        
        for key in test_cases:
            safe_key = generate_object_key(key)
            self.assertNotIn('/', safe_key, "Object key should not contain slashes")

    def test_file_metadata(self):
        """Test file metadata handling with temp files"""
        test_data = b'Content for file metadata test'
        
        # Create temporary file
        test_path = 'metadata_test_file.tmp'
        try:
            with open(test_path, 'wb') as f:
                f.write(test_data)
            
            metadata = get_file_metadata(test_path)
            self.assertIsNotNone(metadata)
            self.assertIn('hash', metadata)
            self.assertEqual(hashlib.sha256(test_data).hexdigest(), metadata['hash'])
        finally:
            if os.path.exists(test_path):
                os.remove(test_path)


if __name__ == '__main__':
    if not init_storage():  # Attempt to initialize storage before running tests
        print("Storage initialization failed; tests may not run fully.")
    
    unittest.main()
