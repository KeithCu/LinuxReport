"""
SqliteLock.py

Provides a robust, distributed lock implementation using a SQLite backend via the
diskcache library. This is designed for safe multi-process and multi-threaded
coordination.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import diskcache
from filelock import Timeout  # Note: filelock.Timeout is the exception class

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from models import g_logger, LockBase

# =============================================================================
# SQLITE-BASED LOCK IMPLEMENTATION
# =============================================================================

class DiskcacheSqliteLock(LockBase):
    """
    A distributed lock using a diskcache.Cache instance (with a SQLite backend).

    This lock is designed for multi-process and multi-threaded environments. It uses
    atomic transactions, ownership verification, and lock expiry to ensure safety.
    """
    def __init__(self, lock_name: str, cache_instance: diskcache.Cache, owner_prefix: Optional[str] = None):
        """
        Initializes the lock instance.

        Args:
            lock_name (str): A unique name for the lock.
            cache_instance (diskcache.Cache): The diskcache instance to use for storage.
            owner_prefix (str, optional): A prefix for the owner ID. If None, it is
                                          auto-generated from the process and thread IDs.
        """
        self.cache = cache_instance
        self.lock_key = f"lock::{lock_name}"
        if owner_prefix is None:
            owner_prefix = f"pid{os.getpid()}_tid{threading.get_ident()}"
        self.owner_id = f"{owner_prefix}_{uuid.uuid4()}"
        self._locked = False
        self._lock_expiry = 0

    def acquire(self, timeout_seconds: int = 60, wait: bool = False) -> bool:
        """
        Tries to acquire the lock, with an option to wait.

        Args:
            timeout_seconds (int): The duration (in seconds) the lock is held before it expires.
                                   Also used as the maximum wait time if `wait` is True.
            wait (bool): If True, the method will block and wait until the lock is acquired
                         or the timeout is reached. If False, it returns immediately.

        Returns:
            bool: True if the lock was acquired, False otherwise.
        """
        if self._locked and time.monotonic() < self._lock_expiry:
            return True  # Already hold a valid lock

        start_time = time.monotonic()
        while True:
            if self._attempt_acquire(timeout_seconds):
                return True
            if not wait or (time.monotonic() - start_time) > timeout_seconds:
                return False
            
            # Exponential backoff with jitter to prevent thundering herd problem
            sleep_time = min(0.1 * (2 ** (time.monotonic() - start_time)), 1.0) + (uuid.uuid4().int % 100 / 1000)
            time.sleep(sleep_time)

    def _attempt_acquire(self, timeout_seconds: int) -> bool:
        """Internal method that makes a single attempt to acquire the lock."""
        try:
            with self.cache.transact():
                now = time.monotonic()
                current_value = self.cache.get(self.lock_key)

                # If a lock exists and is still valid, we cannot acquire it.
                if current_value is not None:
                    _, expiry_time = current_value
                    if now < expiry_time:
                        return False
                
                # Set our lock with an expiry time.
                expiry = now + timeout_seconds
                self.cache.set(self.lock_key, (self.owner_id, expiry), expire=timeout_seconds + 5)

                # Verify that we actually acquired the lock.
                final_value = self.cache.get(self.lock_key)
                if final_value and final_value[0] == self.owner_id:
                    self._locked = True
                    self._lock_expiry = expiry
                    return True

                return False # Lost the race
        except (diskcache.Timeout, Timeout) as e:
            g_logger.warning(f"Timeout error while acquiring lock '{self.lock_key}': {e}")
        except Exception as e:
            g_logger.error(f"Unexpected error acquiring lock '{self.lock_key}': {e}")
        
        self._locked = False
        return False

    def release(self) -> bool:
        """
        Releases the lock if it is currently held by this instance.

        Returns:
            bool: True if the lock was successfully released, False otherwise.
        """
        if not self.locked():
            return False

        try:
            with self.cache.transact():
                # Verify ownership before deleting to prevent releasing a lock acquired by another process.
                current_value = self.cache.get(self.lock_key)
                if current_value and current_value[0] == self.owner_id:
                    self.cache.delete(self.lock_key)
                    self._locked = False
                    self._lock_expiry = 0
                    return True
            return False # Lock was not ours
        except Exception as e:
            g_logger.error(f"Error releasing lock '{self.lock_key}': {e}")
            return False

    def __enter__(self):
        """Acquires the lock when entering a `with` block."""
        if not self.acquire(wait=True):
            raise TimeoutError(f"Could not acquire lock '{self.lock_key}' within the timeout period.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Releases the lock when exiting a `with` block."""
        self.release()

    def locked(self) -> bool:
        """Checks if the lock is currently held by this instance and is not expired."""
        if not self._locked:
            return False

        if time.monotonic() >= self._lock_expiry:
            self._locked = False # Our lock has expired
            return False

        return True
    def renew(self, timeout_seconds: int) -> bool:
        """Renews the lock with a new timeout."""
        pass

