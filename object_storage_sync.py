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

# Constants for last-written tracking
BUCKET_LAST_WRITTEN_KEY = f"{STORAGE_SYNC_PATH}last-written"
DEFAULT_CACHE_EXPIRY = 300  # 5 minutes in seconds

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

@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=RETRY_MULTIPLIER, max=MAX_RETRY_INTERVAL),
    retry=retry_if_exception_type((StorageOperationError, LibcloudError)),
    reraise=True
)
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

@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=RETRY_MULTIPLIER, max=MAX_RETRY_INTERVAL),
    retry=retry_if_exception_type((StorageOperationError, LibcloudError)),
    reraise=True
)
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

def _update_bucket_last_written():
    """Update the bucket's last-written timestamp in object storage"""
    try:
        timestamp = str(time.time())
        timestamp_bytes = timestamp.encode('utf-8')
        _storage_driver.upload_object_via_stream(
            iterator=BytesIO(timestamp_bytes),
            container=_storage_container,
            object_name=BUCKET_LAST_WRITTEN_KEY
        )
    except Exception as e:
        print(f"Error updating bucket last-written timestamp: {e}")
        # Don't raise - this is a best-effort operation

@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=RETRY_MULTIPLIER, max=MAX_RETRY_INTERVAL),
    retry=retry_if_exception_type((StorageOperationError, LibcloudError)),
    reraise=True
)
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
        safe_key = generate_object_name(key, "data")
        object_name = f"{STORAGE_SYNC_PATH}bytes/{SERVER_ID}/{safe_key}"
        
        content_stream = BytesIO(bytes_data)
        obj = _storage_driver.upload_object_via_stream(
            iterator=content_stream,
            container=_storage_container,
            object_name=object_name
        )
        
        # Update bucket last-written timestamp
        _update_bucket_last_written()
        
        print(f"Published {len(bytes_data)} bytes to object: {object_name}")
        return obj
    except Exception as e:
        print(f"Error publishing bytes with key: {key}, exception: {e}")
        raise

@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=RETRY_MULTIPLIER, max=MAX_RETRY_INTERVAL),
    retry=retry_if_exception_type((StorageOperationError, LibcloudError)),
    reraise=True
)
def fetch_bytes(key: str) -> tuple[Optional[bytes], Optional[Dict]]:
    """Fetch bytes data from object storage with its metadata.
    
    Args:
        key: Identifier for the object to fetch
    
    Returns:
        Tuple containing data and metadata or None values if not found
    """
    try:
        obj = _get_object(f"{STORAGE_SYNC_PATH}bytes/{SERVER_ID}/{generate_object_name(key, 'data')}")
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

@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=RETRY_MULTIPLIER, max=MAX_RETRY_INTERVAL),
    retry=retry_if_exception_type((StorageOperationError, LibcloudError)),
    reraise=True
)
def smart_fetch(key: str, cache_expiry: int = DEFAULT_CACHE_EXPIRY) -> tuple[Optional[bytes], Optional[Dict]]:
    """Smart fetch that handles caching and metadata checks using the global cache manager.
    
    Args:
        key: Identifier for the object to fetch
        cache_expiry: Optional cache expiry time in seconds (defaults to 5 minutes)
        
    Returns:
        Tuple containing raw bytes and metadata or None values if not found
    """
    try:
        # Check global cache first
        memory_key = f"objstorage_cache:{key}"
        cached_value = g_cm.get(memory_key)
        if cached_value is not None:
            return cached_value, None

        # Get object metadata first (lightweight operation)
        obj = _get_object(f"{STORAGE_SYNC_PATH}bytes/{SERVER_ID}/{generate_object_name(key, 'data')}")
        if not obj:
            return None, None

        metadata = _get_object_metadata(obj)
        
        # Check both bucket last-written and object last-modified timestamps
        bucket_last_written_obj = _get_object(BUCKET_LAST_WRITTEN_KEY)
        if bucket_last_written_obj:
            bucket_last_written_key = f"{memory_key}:bucket_last_written"
            cached_bucket_last_written = g_cm.get(bucket_last_written_key)
            cached_object_last_modified = g_cm.get(f"{memory_key}:object_last_modified")
            
            if cached_bucket_last_written is not None and cached_object_last_modified is not None:
                content_buffer = BytesIO()
                _storage_driver.download_object_as_stream(bucket_last_written_obj, content_buffer)
                current_bucket_last_written = float(content_buffer.getvalue().decode('utf-8'))
                
                # If both timestamps match, we can safely return cached value
                if (cached_bucket_last_written == current_bucket_last_written and 
                    cached_object_last_modified == metadata['last_modified']):
                    return cached_value, None

        # Fetch content if we need to
        content_buffer = BytesIO()
        _storage_driver.download_object_as_stream(obj, content_buffer)
        content = content_buffer.getvalue()
        
        if not content:
            return None, None
            
        # Cache the results
        g_cm.set(memory_key, content, ttl=cache_expiry)
        
        # Cache both timestamps
        if bucket_last_written_obj:
            content_buffer = BytesIO()
            _storage_driver.download_object_as_stream(bucket_last_written_obj, content_buffer)
            current_bucket_last_written = float(content_buffer.getvalue().decode('utf-8'))
            g_cm.set(f"{memory_key}:bucket_last_written", current_bucket_last_written, ttl=cache_expiry)
            g_cm.set(f"{memory_key}:object_last_modified", metadata['last_modified'], ttl=cache_expiry)
        
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
            safe_key = generate_object_name(key)
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

    def test_concurrent_access(self):
        """Test concurrent access to the same object from multiple threads"""
        import threading
        
        test_data = b'Test content for concurrent access'
        test_key = 'concurrent_test'
        results = []
        
        def worker():
            try:
                # Each thread tries to publish and fetch
                publish_bytes(test_data, test_key)
                fetched_data, _ = fetch_bytes(test_key)
                results.append(fetched_data == test_data)
            except Exception as e:
                results.append(False)
        
        # Create multiple threads
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verify all threads succeeded
        self.assertTrue(all(results), "All concurrent operations should succeed")

    def test_smart_fetch_caching(self):
        """Test that smart_fetch properly caches and respects cache expiry"""
        test_data = b'Test content for caching'
        test_key = 'cache_test'
        
        # First publish the data
        publish_bytes(test_data, test_key)
        
        # First fetch should hit storage
        first_fetch, first_meta = smart_fetch(test_key, cache_expiry=2)
        self.assertEqual(first_fetch, test_data)
        
        # Second fetch should hit cache
        second_fetch, second_meta = smart_fetch(test_key, cache_expiry=2)
        self.assertEqual(second_fetch, test_data)
        
        # Wait for cache to expire
        time.sleep(3)
        
        # This fetch should hit storage again
        third_fetch, third_meta = smart_fetch(test_key, cache_expiry=2)
        self.assertEqual(third_fetch, test_data)

    def test_large_file_handling(self):
        """Test handling of large files (>1MB)"""
        # Create a large test file (2MB)
        large_data = b'0' * (2 * 1024 * 1024)
        test_key = 'large_file_test'
        
        # Test publishing
        uploaded_obj = publish_bytes(large_data, test_key)
        self.assertIsNotNone(uploaded_obj)
        
        # Test fetching
        fetched_data, metadata = fetch_bytes(test_key)
        self.assertIsNotNone(fetched_data)
        self.assertEqual(len(fetched_data), len(large_data))
        self.assertEqual(fetched_data, large_data)

    def test_retry_mechanism(self):
        """Test that retry mechanism works for temporary failures"""
        test_data = b'Test content for retry'
        test_key = 'retry_test'
        
        # Mock temporary failures
        original_get_object = _get_object
        failure_count = 0
        
        def mock_get_object(obj_name):
            nonlocal failure_count
            if failure_count < 2:  # Fail first two attempts
                failure_count += 1
                raise StorageOperationError("Temporary failure")
            return original_get_object(obj_name)
        
        # Apply mock
        _get_object = mock_get_object
        
        try:
            # This should succeed after retries
            fetched_data, metadata = fetch_bytes(test_key)
            self.assertIsNotNone(fetched_data)
        finally:
            # Restore original function
            _get_object = original_get_object

    def test_metadata_handling(self):
        """Test that metadata is properly preserved and retrieved"""
        test_data = b'Test content for metadata'
        test_key = 'metadata_test'
        
        # Publish with specific content type
        content_stream = BytesIO(test_data)
        obj = _storage_driver.upload_object_via_stream(
            iterator=content_stream,
            container=_storage_container,
            object_name=test_key,
            extra={'content_type': 'application/json'}
        )
        
        # Fetch and verify metadata
        fetched_data, metadata = fetch_bytes(test_key)
        self.assertIsNotNone(metadata)
        self.assertIn('last_modified', metadata)
        self.assertIn('size', metadata)
        self.assertIn('hash', metadata)
        self.assertEqual(metadata['size'], len(test_data))

    def test_invalid_configuration(self):
        """Test behavior with invalid storage configuration"""
        # Temporarily disable storage
        original_enabled = STORAGE_ENABLED
        STORAGE_ENABLED = False
        
        try:
            with self.assertRaises(ConfigurationError):
                _init_check()
        finally:
            STORAGE_ENABLED = original_enabled

    def test_bucket_last_written_tracking(self):
        """Test that bucket last-written timestamp is properly updated"""
        test_data = b'Test content for last-written'
        test_key = 'last_written_test'
        
        # Get initial last-written timestamp
        initial_obj = _get_object(BUCKET_LAST_WRITTEN_KEY)
        initial_timestamp = float(initial_obj.get_content_as_string()) if initial_obj else 0
        
        # Publish new data
        publish_bytes(test_data, test_key)
        
        # Get new last-written timestamp
        new_obj = _get_object(BUCKET_LAST_WRITTEN_KEY)
        new_timestamp = float(new_obj.get_content_as_string())
        
        # Verify timestamp was updated
        self.assertGreater(new_timestamp, initial_timestamp)


if __name__ == '__main__':
    if not init_storage():  # Attempt to initialize storage before running tests
        print("Storage initialization failed; tests may not run fully.")
    
    unittest.main()
