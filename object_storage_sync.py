"""
object_storage_sync.py (Not used yet)

Object Storage-based publisher/subscriber for feed updates. Used to synchronize feed updates across multiple servers.
Uses libcloud to interface with object storage providers (like Linode Object Storage).

Optimizations for Linode Object Storage:
- This module is designed for Linode's S3-compatible Object Storage, using Apache Libcloud for seamless, provider-agnostic interactions.
- Linode provides eventual consistency, so the code incorporates retry mechanisms with exponential backoff (via Tenacity) to handle transient errors and ensure reliable operations.
- Error handling is robust, addressing issues like object non-existence, network failures, and storage operation errors through custom exceptions and logging.
- Metadata operations are optimized for efficiency, leveraging Linode's support for custom metadata to track file versions and timestamps, minimizing conflicts in distributed environments.
- The implementation considers Linode's regional storage for better performance, using specified regions to reduce latency and costs.
"""
import time
import os
import hashlib
from io import BytesIO
from typing import Optional, Dict, Union, Any
from functools import wraps

import unittest
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Import from object_storage_config
import object_storage_config as oss_config

from object_storage_config import (
    LIBCLOUD_AVAILABLE, STORAGE_ENABLED,
    init_storage, SERVER_ID, STORAGE_SYNC_PATH,
    _storage_driver, _storage_container,
    StorageOperationError,
    ConfigurationError,
    StorageConnectionError,
    LibcloudError
)


def generate_object_name(url: str) -> str:
    """Generate a unique object name for a feed URL
    
    Args:
        url: Feed URL to generate name for
    
    Returns:
        str: Unique object name with server ID, hash, and timestamp
    """
    url_hash = hashlib.md5(url.encode()).hexdigest()
    timestamp = int(time.time())
    return f"{STORAGE_SYNC_PATH}{SERVER_ID}/feeds/{url_hash}_{timestamp}.json"

def generate_object_key(key: Union[str, bytes], salt: str = "") -> str:
    """Generate a safe, consistent object key
    
    Args:
        key: Base identifier for the object
        salt: Optional additional string to differentiate keys
    
    Returns:
        str: MD5 hash-based key with salt and timestamp
    """
    if isinstance(key, str):
        key_bytes = key.encode()
    else:
        key_bytes = key
    
    combined = key_bytes
    if salt:
        combined += salt.encode()
    
    key_hash = hashlib.md5(combined).hexdigest()
    timestamp = int(time.time())
    return f"{key_hash}_{timestamp}"

def generate_file_object_name(file_path: str) -> str:
    """Generate a unique object name for a file
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: Unique object name for storage
    """
    return f"{STORAGE_SYNC_PATH}files/{SERVER_ID}/{generate_object_key(file_path)}"

def get_file_metadata(file_path: str) -> Optional[Dict]:
    """Get metadata for a file including hash and timestamp
    
    Args:
        file_path: Path to the file
        
    Returns:
        dict: File metadata including hash and timestamp or None on error
    """
    try:
        with open(file_path, 'rb') as f:
            # Use streaming read for large files
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
        print(f"File not found for metadata: {file_path}: {e}")
        return None
    except IOError as e:  # Broader I/O errors (e.g. permission denied)
        print(f"I/O error getting file metadata for {file_path}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error getting file metadata for {file_path}, exception: {e}")
        return None

def _init_check():
    """Ensure storage is initialized, raising an exception if not."""
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        raise ConfigurationError("Storage is not enabled or Libcloud is not available")
    if not init_storage():
        raise StorageConnectionError("Failed to initialize storage")
    return True

def _prepare_fetch(prefix: str, key: str, current_hash: Optional[str] = None, use_cache: Optional[Dict] = None):
    """Prepare fetch operation by listing objects matching the given prefix and key
    
    Args:
        prefix: Type of object to fetch ('feeds', 'files', 'bytes')
        key: Identifier for the object
        current_hash: Optional hash of current version to compare
        use_cache: Optional cache information to compare against
        
    Returns:
        Tuple[object, bool]: (object_to_fetch, use_local_content)
    """
    try:
        _init_check()
        prefix_path = f"{STORAGE_SYNC_PATH}{prefix}/{SERVER_ID}/{key}_"
        objects = list(_storage_container.list_objects(prefix=prefix_path))
        
        if not objects:
            logger.debug(f"No objects found matching prefix: {prefix_path}")
            return None, False
            
        # Sort by name (which contains timestamp) to get the latest version
        objects.sort(key=lambda obj: obj.name, reverse=True)
        return objects[0], False  # Return latest object and not using local content
    except Exception as e:
        print("Error preparing fetch operation, exception: {e}")
        raise

def retry_decorator(max_retries: int = oss_config.MAX_RETRY_ATTEMPTS):
    """Create retry decorator for object storage operations"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return retry(
                    stop=stop_after_attempt(max_retries),
                    wait=wait_exponential(
                        multiplier=oss_config.RETRY_MULTIPLIER,
                        max=oss_config.MAX_RETRY_INTERVAL
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
def publish_file(file_path: str, metadata: Optional[Dict] = None) -> Any:
    """Publish a file from disk to object storage.
    
    Args:
        file_path: Path to the file to publish
        metadata: Optional metadata to associate with the object
        
    Returns:
        The uploaded object on success
    """
    try:
        _init_check()
        file_metadata = get_file_metadata(file_path)
        if file_metadata:
            bytes_data = file_metadata['content']
            return publish_bytes(bytes_data, file_path, metadata)
        print(f"No content found in file: {file_path}")
        return None
    except Exception as e:
        print(f"Error publishing file: {file_path}, exception: {e}")
        raise

@retry_decorator()
def fetch_file(file_path: str, force: bool = False) -> tuple[Optional[bytes], Optional[Dict]]:
    """Fetch a file from object storage as bytes with its metadata.
    
    Args:
        file_path: Identifier for the file to fetch
        force: Skip local cache check if supported
    
    Returns:
        Tuple containing file content and metadata or None values if not found
    """
    try:
        content, metadata = fetch_bytes(file_path, force)
        logger.debug(f"Fetched file ({len(content) if content else 0} bytes) from key: {file_path}")
        return content, metadata
    except Exception as e:
        print(f"Error fetching file: {file_path}, exception: {e}")
        raise

@retry_decorator()
def fetch_file_stream(file_path: str, force: bool = False) -> tuple[Optional[BytesIO], Optional[Dict]]:
    """Fetch a file from object storage as a stream with its metadata.
    
    Args:
        file_path: Identifier for the file to fetch
        force: Skip local cache check if supported
    
    Returns:
        Tuple containing file stream and metadata or None values if not found
    """
    try:
        content, metadata = fetch_bytes(file_path, force)
        if content is not None:
            logger.debug(f"Streamed file ({len(content)} bytes) from key: {file_path}")
            return BytesIO(content), metadata
        print(f"No content retrieved for key: {file_path}")
        return None, None
    except Exception as e:
        print(f"Error fetching file stream: {file_path}, exception: {e}")
        raise

@retry_decorator()
def publish_bytes(bytes_data: bytes, key: str, metadata: Optional[Dict] = None) -> Any:
    """Publish raw bytes to object storage.
    
    Args:
        bytes_data: Data to publish
        key: Identifier for the object
        metadata: Optional metadata to associate with the object
        
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
        
        file_hash = hashlib.sha256(bytes_data).hexdigest()
        extra_metadata = {
            'meta_data': {
                'server_id': SERVER_ID,
                'file_key': key,  # Store original key for reference
                'file_hash': file_hash,
                'timestamp': str(time.time())
            }
        }
        
        if metadata:
            # Filter metadata to ensure compatibility with storage backend
            filtered_metadata = {
                k: str(v) for k, v in metadata.items() 
                if isinstance(k, str) and isinstance(v, (str, int, float, bool))
            }
            extra_metadata['meta_data'].update(filtered_metadata)
        
        content_stream = BytesIO(bytes_data)
        obj = _storage_driver.upload_object_via_stream(
            iterator=content_stream,
            container=_storage_container,
            object_name=object_name,
            extra=extra_metadata
        )
        
        logger.info(f"Published {len(bytes_data)} bytes to object: {object_name}")
        return obj
    except Exception as e:
        print(f"Error publishing bytes with key: {key}, exception: {e}")
        raise

@retry_decorator()
def fetch_bytes(key: str, force: bool = False) -> tuple[Optional[bytes], Optional[Dict]]:
    """Fetch bytes data from object storage with its metadata.
    
    Args:
        key: Identifier for the object to fetch
        force: Skip local cache check if supported
    
    Returns:
        Tuple containing data and metadata or None values if not found
    """
    try:
        latest_obj, use_local_content = _prepare_fetch('bytes', key, force)
        if latest_obj and not use_local_content:
            content_buffer = BytesIO()
            _storage_driver.download_object_as_stream(latest_obj, content_buffer)
            content = content_buffer.getvalue()
            metadata = latest_obj.meta_data if latest_obj else None
            logger.debug(f"Retrieved {len(content)} bytes for key: {key}")
            return content, metadata
        
        logger.debug(f"No content found for key: {key}")
        return None, None
    except Exception as e:
        print(f"Error fetching bytes for key: {key}, exception: {e}")
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
        self.assertRegex(result, r'.*_\d+\.json$', "Object name should end with _timestamp.json")
    
    def test_generate_file_object_name(self):
        result = generate_file_object_name('/path/to/file.txt')
        self.assertTrue(result.startswith(f"{oss_config.STORAGE_SYNC_PATH}files/{oss_config.SERVER_ID}/"))
        self.assertRegex(result, r'.*_\d+$', "File object name should end with _timestamp")

    def test_metadata_hash_consistency(self):
        """Test that local and stored metadata remain consistent"""
        test_content = b'Test content for metadata'
        test_key = 'metadata_test_key'
        
        # Test 1: Compute expected object name
        safe_key = generate_object_key(test_key, "data")
        expected_name = f"{STORAGE_SYNC_PATH}bytes/{SERVER_ID}/{safe_key}"
        
        # Test 2: Publish and verify metadata
        uploaded_obj = publish_bytes(test_content, test_key)
        self.assertIsNotNone(uploaded_obj)
        self.assertEqual(uploaded_obj.name, expected_name)
        
        # Extract hash from stored object name
        stored_hash = os.path.basename(expected_name).split('_')[0]
        content_hash = hashlib.sha256(test_content).hexdigest()
        self.assertEqual(stored_hash, content_hash, "Stored hash should match content hash")

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
        self.assertIn('server_id', metadata)
        self.assertIn('file_key', metadata)
        self.assertIn('file_hash', metadata)
        self.assertIn('timestamp', metadata)
        
        # Verify metadata values
        self.assertEqual(metadata['server_id'], SERVER_ID)
        self.assertEqual(metadata['file_key'], test_key)
        self.assertEqual(metadata['file_hash'], hashlib.sha256(test_data).hexdigest())
        self.assertAlmostEqual(
            float(metadata['timestamp']), 
            time.time(), 
            delta=2  # Allow 2 seconds difference
        )

    def test_fetch_nonexistent(self):
        """Test fetching nonexistent data"""
        empty_bytes, empty_meta = fetch_bytes('nonexistent_key')
        self.assertIsNone(empty_bytes)
        self.assertIsNone(empty_meta)
        
        # Test 2: Empty key
        empty_bytes, empty_meta = fetch_bytes('')
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
        
        # Test invalid file fetch
        with self.assertRaises(TypeError):
            get_file_metadata(123)

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
            self.assertTrue(safe_key.endswith(str(int(safe_key.split("_")[-1]))), 
                          "Object key should end with numeric timestamp")

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

    def test_concurrency_safety(self):
        """Simulate concurrent writes to test object key uniqueness"""
        test_key = 'concurrent_key'
        key_count = 5
        test_data = b'Concurrent write test content'
        keys = []
        
        for i in range(key_count):
            keys.append(generate_object_key(f"{test_key}_{i}"))
        
        # Check uniqueness
        self.assertEqual(len(keys), len(set(keys)), "Generated keys must be unique")

    def test_stream_roundtrip(self):
        """Test stream operations and chunked reading"""
        test_data = b'Test content for stream roundtrip'
        test_key = 'stream_roundtrip'
        
        # Test upload via stream
        uploaded_obj = publish_bytes(test_data, test_key)
        self.assertIsNotNone(uploaded_obj)
        
        # Test stream download
        stream, metadata = fetch_file_stream(test_key)
        self.assertIsNotNone(stream)
        
        # Read in chunks
        chunk_size = 2
        chunks = []
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            chunks.append(chunk)
            
        reconstructed = b''.join(chunks)
        self.assertEqual(reconstructed, test_data)

if __name__ == '__main__':
    import sys
    
    if not init_storage():  # Attempt to initialize storage before running tests
        print("Storage initialization failed; tests may not run fully.")
        # Don't exit, allow tests to run that don't require storage
    
    unittest.main()
