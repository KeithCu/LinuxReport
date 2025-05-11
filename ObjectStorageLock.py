"""
ObjectStorageLock.py

This module implements a distributed lock using object storage (via libcloud).
"""

import os
import threading
import time
import uuid
from typing import Optional
from io import BytesIO
import json
import hashlib

from abc import ABC, abstractmethod

# Import from config module
import object_storage_config as oss_config

class LockBase(ABC):
    @abstractmethod
    def acquire(self, timeout_seconds: int = 60, wait: bool = False) -> bool:
        pass

    @abstractmethod
    def release(self) -> bool:
        pass

    @abstractmethod
    def __enter__(self):
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @abstractmethod
    def locked(self) -> bool:
        pass

class ObjectStorageLock(LockBase):
    """
    A distributed lock implementation using object storage (with libcloud).
    This lock supports waiting when a lock is unavailable and provides
    features for reliable multi-process and multi-threaded environments.
    """
    def __init__(self, lock_name: str, owner_prefix: Optional[str] = None):
        """
        Initialize the object storage lock.
        
        Args:
            lock_name: A unique name for this lock
            owner_prefix: Optional prefix for the owner ID. If None, uses pid and thread ID.
        
        Raises:
            ConfigurationError: If object storage is not available or not properly configured
        """
        # Check storage configuration upfront
        if not oss_config.LIBCLOUD_AVAILABLE or not oss_config.STORAGE_ENABLED:
            raise oss_config.ConfigurationError("Object storage is not available or not enabled")
            
        if not oss_config.init_storage():
            raise oss_config.ConfigurationError("Failed to initialize object storage")
            
        self.lock_name = lock_name
        self.lock_key = f"lock::{lock_name}"
        self.lock_object_name = self._get_object_name(self.lock_key)
        
        if owner_prefix is None:
            owner_prefix = f"pid{os.getpid()}_tid{threading.get_ident()}"
        self.owner_id = f"{owner_prefix}_{uuid.uuid4()}"
        self._locked = False
        
    def _get_object_name(self, key: str) -> str:
        """Generate a unique object name for a lock key."""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return f"{oss_config.STORAGE_SYNC_PREFIX}locks/{oss_config.SERVER_ID}/{key_hash}"
        
    def acquire(self, timeout_seconds: int = 60, wait: bool = False) -> bool:
        """
        Tries to acquire the lock.
        
        Args:
            timeout_seconds: How long the lock should be held before expiring
            wait: If True, will wait until the lock is acquired or timeout_seconds is reached
            
        Returns:
            True if lock was acquired, False otherwise
        """
        if self._locked:
            return True
            
        start_time = time.monotonic()
        while True:
            acquired = self._attempt_acquire(timeout_seconds)
            if acquired:
                return True
            if not wait:
                return False
            if (time.monotonic() - start_time) > timeout_seconds:
                return False
            time.sleep(0.1)  # Short sleep before retrying
            
    def _attempt_acquire(self, timeout_seconds: int) -> bool:
        """Internal method that attempts to acquire the lock once."""
        try:
            now = time.monotonic()
            
            # Try to get existing lock info
            current_lock = self._get_lock_info()
            
            # Lock exists and is still valid
            if current_lock is not None:
                expiry_time = current_lock.get('expiry')
                if expiry_time is not None and now < expiry_time:
                    return False
                # Lock exists but has expired - we'll overwrite it
            
            # Set expiry and store our claim
            expiry = now + timeout_seconds
            
            # Create lock data
            lock_data = {
                'owner_id': self.owner_id,
                'expiry': expiry,
                'created': now,
                'lock_name': self.lock_name
            }
            
            # Upload the lock data
            self._put_lock_info(lock_data)
            
            # Verify our ownership
            final_lock = self._get_lock_info()
            if final_lock is not None and final_lock.get('owner_id') == self.owner_id:
                self._locked = True
                return True
                
            self._locked = False
            return False
            
        except Exception as e:
            # Log the exception but don't crash
            oss_config.logger.error(f"Error acquiring lock {self.lock_key}: {e}")
            self._locked = False
            return False
            
    def _get_lock_info(self):
        """Get the current lock information from object storage."""
        try:
            obj = oss_config._storage_container.get_object(object_name=self.lock_object_name)
            
            # Download and parse the lock data
            data_stream = oss_config._storage_driver.download_object_as_stream(obj)
            data_bytes = b''
            for chunk in data_stream:
                data_bytes += chunk
                
            if data_bytes:
                return json.loads(data_bytes.decode('utf-8'))
            return None
                
        except oss_config.ObjectDoesNotExistError:
            # Lock doesn't exist
            return None
        except Exception as e:
            oss_config.logger.error(f"Error getting lock info for {self.lock_key}: {e}")
            return None
            
    def _put_lock_info(self, lock_data):
        """Store lock information in object storage."""
        data_stream = None
        try:
            json_data = json.dumps(lock_data).encode('utf-8')
            data_stream = BytesIO(json_data)
            
            metadata = {
                'lock_name': self.lock_name,
                'owner_id': self.owner_id,
                'expiry': str(lock_data['expiry']),
                'server_id': oss_config.SERVER_ID
            }
            
            oss_config._storage_driver.upload_object_via_stream(
                iterator=data_stream,
                container=oss_config._storage_container,
                object_name=self.lock_object_name,
                extra={'meta_data': metadata, 'content_type': 'application/json'}
            )
                
        except Exception as e:
            oss_config.logger.error(f"Error putting lock info for {self.lock_key}: {e}")
            raise
        finally:
            if data_stream:
                data_stream.close()
    
    def release(self) -> bool:
        """
        Releases the lock if currently held by this instance.
        Returns True if the lock was successfully released, False otherwise.
        """
        if not self._locked:
            return False  # We don't hold the lock
            
        success = False
        try:
            # Verify ownership before deleting
            current_lock = self._get_lock_info()
            if current_lock is not None and current_lock.get('owner_id') == self.owner_id:
                # Get object reference and delete it
                obj = oss_config._storage_container.get_object(object_name=self.lock_object_name)
                oss_config._storage_container.delete_object(obj)
                success = True
        except Exception as e:
            # Log error if needed
            oss_config.logger.error(f"Error releasing lock {self.lock_key}: {e}")
            success = False
            
        # Whether successful or not, we're no longer locked
        self._locked = False
        return success
        
    def __enter__(self):
        if not self.acquire(wait=True):
            raise TimeoutError(f"Could not acquire lock '{self.lock_key}'")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        
    def locked(self) -> bool:
        """Check if the lock is currently held by this instance."""
        return self._locked 