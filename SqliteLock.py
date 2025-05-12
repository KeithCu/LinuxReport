"""
SqliteLock.py

This module contains lock implementations using SQLite (via diskcache) and file-based locking.
"""

import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional

import diskcache
from filelock import FileLock, Timeout

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

class DiskcacheSqliteLock(LockBase):
    """
    A distributed lock implementation using the global diskcache (with a Sqlite backend).
    This lock supports waiting when a lock is unavailable and provides
    features for reliable multi-process and multi-threaded environments.
    """
    def __init__(self, lock_name: str, cache_instance: diskcache.Cache, owner_prefix: Optional[str] = None):
        self.cache = cache_instance
        self.lock_key = f"lock::{lock_name}"
        if owner_prefix is None:
            owner_prefix = f"pid{os.getpid()}_tid{threading.get_ident()}"
        self.owner_id = f"{owner_prefix}_{uuid.uuid4()}"
        self._locked = False

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
            time.sleep(0.5)  # Short sleep before retrying

    def _attempt_acquire(self, timeout_seconds: int) -> bool:
        """Internal method that attempts to acquire the lock once."""
        try:
            with self.cache.transact():
                now = time.monotonic()
                current_value = self.cache.get(self.lock_key)

                # Lock exists and is still valid
                if current_value is not None:
                    expiry_time = current_value[1]
                    # Lock is still valid
                    if now < expiry_time:
                        return False
                    # Lock exists but has expired - we'll overwrite it

                # Set expiry and store our claim
                expiry = now + timeout_seconds
                self.cache.set(self.lock_key, (self.owner_id, expiry), expire=timeout_seconds + 5)

                # Verify our ownership
                final_value = self.cache.get(self.lock_key)
                if final_value is not None and final_value[0] == self.owner_id:
                    self._locked = True
                    return True

                self._locked = False
                return False
        except (diskcache.Timeout, Timeout) as e:
            # Log the exception but don't crash
            print(f"Error acquiring lock {self.lock_key}: {e}")
            self._locked = False
            return False
        except Exception as e:
            # Log the exception but don't crash
            print(f"Error acquiring lock {self.lock_key}: {e}")
            self._locked = False
            return False

    def release(self) -> bool:
        """
        Releases the lock if currently held by this instance.
        Returns True if the lock was successfully released, False otherwise.
        """
        if not self._locked:
            return False  # We don't hold the lock

        success = False
        try:
            with self.cache.transact():
                # Verify ownership before deleting
                current_value = self.cache.get(self.lock_key)
                if current_value is not None and current_value[0] == self.owner_id:
                    self.cache.delete(self.lock_key)
                    success = True
        except Exception as e:
            # Log error if needed
            print(f"Error releasing lock {self.lock_key}: {e}")
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

class FileLockWrapper(LockBase):
    def __init__(self, lock_file_path: str):
        self.lock_file_path = lock_file_path
        self._lock = FileLock(lock_file_path)
        self._is_locked = False

    def acquire(self, timeout_seconds: int = 60, wait: bool = False) -> bool:
        try:
            if wait:
                self._lock.acquire(timeout=timeout_seconds)
            else:
                self._lock.acquire(timeout=0)
            self._is_locked = True
            return True
        except Timeout:
            self._is_locked = False
            return False

    def release(self) -> bool:
        if self._is_locked:
            self._lock.release()
            self._is_locked = False
            return True
        return False

    def __enter__(self):
        acquired = self.acquire()
        if not acquired:
            raise TimeoutError("Failed to acquire lock within the specified timeout.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def locked(self) -> bool:
        return self._is_locked
