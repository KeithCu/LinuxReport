import os
import time
import threading
import diskcache
import uuid
from contextlib import contextmanager
from SqliteLock import DiskcacheSqliteLock, FileLockWrapper

def clear_cache(cache):
    cache.clear()

def get_unique_lock_file():
    """Generate a unique lock file path for each test run."""
    return f"test_{uuid.uuid4().hex[:8]}.lock"

@contextmanager
def managed_file_lock(lock_file):
    """Context manager for FileLockWrapper that ensures proper cleanup."""
    lock = FileLockWrapper(lock_file)
    try:
        yield lock
    finally:
        if lock.locked():
            lock.release()
        # Note: On Windows, the file may not be immediately deletable due to file handle behavior
        # This is expected and doesn't affect functionality
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except PermissionError:
            pass  # Windows may keep the file handle open briefly

def test_diskcache_lock_basic():
    cache = diskcache.Cache('test_cache')
    clear_cache(cache)
    lock = DiskcacheSqliteLock('test_lock', cache)
    assert lock.acquire(timeout_seconds=5)
    assert lock.locked()
    assert lock.release()
    assert not lock.locked()

def test_diskcache_lock_timeout():
    cache = diskcache.Cache('test_cache')
    clear_cache(cache)
    lock1 = DiskcacheSqliteLock('test_lock', cache)
    lock2 = DiskcacheSqliteLock('test_lock', cache)
    assert lock1.acquire(timeout_seconds=2)
    assert not lock2.acquire(timeout_seconds=0)
    time.sleep(2.1)
    assert lock2.acquire(timeout_seconds=0)

def test_diskcache_lock_wait():
    cache = diskcache.Cache('test_cache')
    clear_cache(cache)
    lock1 = DiskcacheSqliteLock('test_lock', cache)
    lock2 = DiskcacheSqliteLock('test_lock', cache)
    assert lock1.acquire(timeout_seconds=2)
    def delayed_release():
        time.sleep(2)
        lock1.release()
    t = threading.Thread(target=delayed_release)
    t.start()
    assert lock2.acquire(timeout_seconds=5, wait=True)
    t.join()

def test_file_lock_basic():
    lock_file = get_unique_lock_file()
    with managed_file_lock(lock_file) as lock:
        assert lock.acquire()
        assert lock.locked()
        assert lock.release()
        assert not lock.locked()

def test_file_lock_timeout():
    lock_file = get_unique_lock_file()
    with managed_file_lock(lock_file) as lock1:
        print('Acquiring lock1...')
        assert lock1.acquire()
        print('lock1 acquired:', lock1.locked())
        
        with managed_file_lock(lock_file) as lock2:
            print('Trying to acquire lock2 without wait...')
            assert not lock2.acquire(timeout_seconds=0)
            print('lock2 could not acquire (as expected)')
            
            result = {'acquired': False}
            def try_acquire_lock2():
                print('Trying to acquire lock2 with wait (in thread)...')
                result['acquired'] = lock2.acquire(timeout_seconds=5)
                print('lock2 acquired after wait (in thread):', result['acquired'])
            
            t2 = threading.Thread(target=try_acquire_lock2)
            t2.start()
            time.sleep(2)  # Ensure lock2 is waiting
            print('Releasing lock1...')
            lock1.release()
            print('lock1 released')
            t2.join()
            assert result['acquired']

if __name__ == '__main__':
    # Add the parent directory to Python path when running tests directly
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    
    test_diskcache_lock_basic()
    test_diskcache_lock_timeout()
    test_diskcache_lock_wait()
    test_file_lock_basic()
    test_file_lock_timeout()
    print("All tests passed!") 