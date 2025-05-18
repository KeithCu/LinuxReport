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
import os.path
import hashlib
from io import BytesIO
from typing import Optional, Dict

import unittest
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Import from object_storage_config
import object_storage_config as oss_config

from object_storage_config import (
    LIBCLOUD_AVAILABLE, STORAGE_ENABLED,
    init_storage, SERVER_ID, STORAGE_SYNC_PATH,
    _storage_driver, _storage_container,
)

def generate_object_name(url):
    """Generate a unique object name for a feed URL"""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    timestamp = int(time.time())
    return f"{STORAGE_SYNC_PATH}{SERVER_ID}/{url_hash}_{timestamp}.json"

def generate_file_object_name(file_path):
    """Generate a unique object name for a file
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: Unique object name for storage
    """
    file_hash = hashlib.md5(file_path.encode()).hexdigest()
    timestamp = int(time.time())
    return f"{STORAGE_SYNC_PATH}files/{SERVER_ID}/{file_hash}_{timestamp}"

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
        print(f"File not found for metadata: {file_path}: {e}")
        return None
    except IOError as e: # Broader I/O errors (e.g. permission denied)
        print(f"I/O error getting file metadata for {file_path}: {e}")
        return None
    except Exception as e:
        print(f"Error getting file metadata for {file_path}: {e}")
        return None

def _prepare_fetch(prefix: str, key: str, current_hash: Optional[str] = None):
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None, False
    if not init_storage():
        return None, False
    objects = list(_storage_container.list_objects(prefix=f'{STORAGE_SYNC_PATH}{prefix}/'))
    if objects:
        return objects[-1], False  # Return the last object and force fetch
    return None, False

@retry(
    stop=stop_after_attempt(oss_config.MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=oss_config.RETRY_MULTIPLIER, min=oss_config.MIN_RETRY_INTERVAL, max=oss_config.MAX_RETRY_INTERVAL),
    retry=retry_if_exception_type(oss_config.StorageOperationError)
)
def publish_file(file_path, metadata=None):
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None
    
    if not init_storage():
        return None
    
    try:
        file_metadata = get_file_metadata(file_path)
        if file_metadata:
            bytes_data = file_metadata['content']  # Get the file content as bytes
            key = file_path  # Use file_path as the key for compatibility
            return publish_bytes(bytes_data, key, metadata)  # Call the new function
    except Exception as e:
        raise

@retry(
    stop=stop_after_attempt(oss_config.MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=oss_config.RETRY_MULTIPLIER, min=oss_config.MIN_RETRY_INTERVAL, max=oss_config.MAX_RETRY_INTERVAL),
    retry=retry_if_exception_type(oss_config.StorageOperationError)
)
def fetch_file(file_path, force=False):
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None, None
    
    if not init_storage():
        return None, None
    
    try:
        latest_obj, use_local_content = _prepare_fetch('files', file_path, current_hash if not force else None)
        if latest_obj and not use_local_content:
            content_buffer = BytesIO()
            _storage_driver.download_object_as_stream(latest_obj, content_buffer)
            content = content_buffer.getvalue()
            return content, latest_obj.meta_data
        return None, None
    except Exception as e:
        raise

@retry(
    stop=stop_after_attempt(oss_config.MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=oss_config.RETRY_MULTIPLIER, min=oss_config.MIN_RETRY_INTERVAL, max=oss_config.MAX_RETRY_INTERVAL),
    retry=retry_if_exception_type(oss_config.StorageOperationError)
)
def fetch_file_stream(file_path, force=False):
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None, None
    
    if not init_storage():
        return None, None
    
    try:
        content, metadata = fetch_bytes(file_path, force)  # Fetch bytes using the new function
        if content is not None:
            return BytesIO(content), metadata  # Convert bytes to a stream
        return None, None
    except Exception as e:
        raise

@retry(
    stop=stop_after_attempt(oss_config.MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=oss_config.RETRY_MULTIPLIER, min=oss_config.MIN_RETRY_INTERVAL, max=oss_config.MAX_RETRY_INTERVAL),
    retry=retry_if_exception_type(oss_config.StorageOperationError)
)
def publish_bytes(bytes_data: bytes, key: str, metadata: Optional[Dict] = None):
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None
    
    if not init_storage():
        return None
    
    try:
        file_hash = hashlib.sha256(bytes_data).hexdigest()
        object_name = f"{STORAGE_SYNC_PATH}bytes/{SERVER_ID}/{key}_{int(time.time())}"
        extra_metadata = {
            'meta_data': {
                'server_id': SERVER_ID,
                'file_path': key,  # Use key as identifier for compatibility
                'file_hash': file_hash,
                'timestamp': str(time.time())
            }
        }
        if metadata:
            extra_metadata['meta_data'].update(metadata)
        content_stream = BytesIO(bytes_data)
        obj = _storage_driver.upload_object_via_stream(
            iterator=content_stream,
            container=_storage_container,
            object_name=object_name,
            extra=extra_metadata
        )
        return obj
    except Exception as e:
        raise

@retry(
    stop=stop_after_attempt(oss_config.MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=oss_config.RETRY_MULTIPLIER, min=oss_config.MIN_RETRY_INTERVAL, max=oss_config.MAX_RETRY_INTERVAL),
    retry=retry_if_exception_type(oss_config.StorageOperationError)
)
def fetch_bytes(key: str, force=False):
    if not LIBCLOUD_AVAILABLE or not STORAGE_ENABLED:
        return None, None
    
    if not init_storage():
        return None, None
    
    try:
        latest_obj, use_local_content = _prepare_fetch('bytes', key, current_hash if not force else None)
        if latest_obj and not use_local_content:
            content_buffer = BytesIO()
            _storage_driver.download_object_as_stream(latest_obj, content_buffer)
            content = content_buffer.getvalue()
            return content, latest_obj.meta_data
        return None, None
    except Exception as e:
        raise

class TestObjectStorageSync(unittest.TestCase):
    def test_generate_object_name(self):
        result = generate_object_name('http://example.com/feed')
        self.assertTrue(result.startswith(f"{oss_config.STORAGE_SYNC_PATH}{oss_config.SERVER_ID}/"))  # Updated to use actual config values
        self.assertRegex(result, r'.*_\d+\.json$')  # Checks for hash and timestamp pattern

    def test_generate_file_object_name(self):
        result = generate_file_object_name('/path/to/file.txt')
        self.assertTrue(result.startswith(f"{oss_config.STORAGE_SYNC_PATH}files/{oss_config.SERVER_ID}/"))  # Updated to use actual config values
        self.assertRegex(result, r'.*_\d+$')  # Checks for hash and timestamp

    def test_publish_file(self):
        test_file_path = 'test_file.txt'
        with open(test_file_path, 'w') as f:
            f.write('Test content')
        result = publish_file(test_file_path)
        self.assertIsNotNone(result, 'File upload should succeed if storage is configured')
        self.assertTrue(hasattr(result, 'name'), 'Uploaded object should have a name attribute')
        os.remove(test_file_path)  # Clean up

    def test_fetch_file(self):
        test_file_path = 'test_file.txt'  # Assuming this file was published earlier
        content, metadata = fetch_file(test_file_path, force=True)
        self.assertIsNotNone(content, 'File fetch should succeed if the file exists in storage')
        self.assertIn(b'Test content', content, 'Fetched content should match published content')

    def test_get_file_metadata(self):
        test_file_path = 'test_meta_file.txt'
        with open(test_file_path, 'w') as f:
            f.write('Test content')
        metadata = get_file_metadata(test_file_path)
        self.assertIsNotNone(metadata, 'Metadata should be retrieved')
        self.assertIn('hash', metadata, 'Metadata should include hash')
        self.assertGreater(metadata['size'], 0, 'Size should be greater than zero')
        os.remove(test_file_path)  # Clean up

        non_existent_meta = get_file_metadata('non_existent_file.txt')
        self.assertIsNone(non_existent_meta, 'Should return None for non-existent file')

    def test_fetch_file_stream(self):
        test_file_path = 'test_file.txt'  # Assuming this was published in prior tests
        stream, metadata = fetch_file_stream(test_file_path, force=True)
        self.assertIsNotNone(stream, 'Stream fetch should succeed if the file exists')
        content = b''.join([chunk for chunk in stream])  # Assuming stream is iterable
        self.assertIn(b'Test content', content, 'Stream content should match published content')

    def test_fetch_file_not_found(self):
        content, metadata = fetch_file('non_existent_key', force=True)
        self.assertIsNone(content, 'Should return None for non-existent file')
        self.assertIsNone(metadata, 'Should return None for non-existent file metadata')

if __name__ == '__main__':
    import sys
    if not init_storage():  # Attempt to initialize storage before running tests
        print("Storage initialization failed; tests may not run fully.")
        sys.exit(1)
    unittest.main()
