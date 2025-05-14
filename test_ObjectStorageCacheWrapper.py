import unittest
from unittest.mock import patch, MagicMock
from ObjectStorageCacheWrapper import ObjectStorageCacheWrapper  # Adjust import if needed
import datetime
from shared import TZ  # Assuming this is needed for tests
import time

class TestObjectStorageCacheWrapper(unittest.TestCase):

    def setUp(self):
        self.cache_wrapper = ObjectStorageCacheWrapper(local_cache_expiry=300)  # Use real initialization

    def test_init_success(self):
        # Test successful initialization (will use real backend)
        try:
            ObjectStorageCacheWrapper(local_cache_expiry=300)
            self.assertTrue(True)  # If no exception, success
        except Exception as e:
            self.fail(f"Initialization failed: {e}")

    def test_init_failure_no_storage(self):
        # Test initialization failure when storage is not available
        self.mock_oss_config.LIBCLOUD_AVAILABLE = False
        with self.assertRaises(Exception):  # Expect ConfigurationError
            ObjectStorageCacheWrapper()

    def test_get_success(self):
        # Test getting a value from cache
        with patch('ObjectStorageCacheWrapper.g_cm.get', return_value='test_value'):
            result = self.cache_wrapper.get('test_key')
            self.assertEqual(result, 'test_value')

    def test_get_from_storage(self):
        # Test getting from real object storage
        cache = ObjectStorageCacheWrapper(local_cache_expiry=300)
        # Assuming you have a test key setup; otherwise, this may fail
        result = cache.get('test_key')  # This will hit the real backend
        self.assertIsNone(result)  # Or assert based on expected real behavior

    def test_put_success(self):
        # Test putting to real object storage
        cache = ObjectStorageCacheWrapper(local_cache_expiry=300)
        cache.put('test_key', 'test_value', timeout=3600)  # Real put operation
        self.assertTrue(cache.has('test_key'))  # Verify with real has check

    def test_delete_success(self):
        # Test deleting a value from cache
        with patch('ObjectStorageCacheWrapper.g_cm.delete') as mock_delete:
            with patch('ObjectStorageCacheWrapper.oss_config._storage_container.delete_object') as mock_del_obj:
                self.cache_wrapper.delete('test_key')
                mock_delete.assert_called_with('objstorage_cache:test_key')
                mock_del_obj.assert_called()

    def test_has_success(self):
        # Test checking if a key exists
        with patch('ObjectStorageCacheWrapper.g_cm.has', return_value=True):
            result = self.cache_wrapper.has('test_key')
            self.assertTrue(result)

    def test_has_feed_expired(self):
        # Test feed expiration check
        last_fetch = datetime.datetime.now(TZ)
        with patch('shared.history.has_expired', return_value=True):
            result = self.cache_wrapper.has_feed_expired('test_url', last_fetch)
            self.assertTrue(result)

    def test_migrate_from_disk_cache(self):
        # Test migration function (mocked for safety)
        with patch('ObjectStorageCacheWrapper.shared.g_c.cache.iterkeys', return_value=['key1']):
            with patch('ObjectStorageCacheWrapper.shared.g_c.get', return_value='value'):
                with patch('ObjectStorageCacheWrapper.ObjectStorageCacheWrapper.put') as mock_put:
                    ObjectStorageCacheWrapper.migrate_from_disk_cache()  # Static method
                    mock_put.assert_called()

    def test_get_expired_item(self):
        # Test getting an expired item from real backend
        cache = ObjectStorageCacheWrapper(local_cache_expiry=1)  # Short expiry for testing
        cache.put('expire_test_key', 'test_value', timeout=1)  # 1-second timeout
        time.sleep(2)  # Wait for it to expire
        result = cache.get('expire_test_key')
        self.assertIsNone(result)  # Expect None for expired item

    def test_has_feed_expired_true(self):
        # Test has_feed_expired for an expired feed
        cache = ObjectStorageCacheWrapper(local_cache_expiry=1)
        past_time = datetime.datetime.now(TZ) - datetime.timedelta(days=2)  # 2 days ago
        cache.set_last_fetch('expired_url', past_time, timeout=1)
        result = cache.has_feed_expired('expired_url', past_time)
        self.assertTrue(result)

    def test_has_feed_expired_false(self):
        # Test has_feed_expired for a non-expired feed
        cache = ObjectStorageCacheWrapper(local_cache_expiry=1)
        recent_time = datetime.datetime.now(TZ)
        cache.set_last_fetch('non_expired_url', recent_time, timeout=60)  # 1 minute timeout
        result = cache.has_feed_expired('non_expired_url', recent_time)
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main() 