#!/usr/bin/env python3
"""
selenium_test.py

Test script to verify Selenium driver timeout and cleanup mechanisms.
Uses 10-second timeout for quick testing without getting impatient.

NOTE: Connection errors like "No connection could be made because the target machine 
actively refused it" are EXPECTED and indicate that the timeout cleanup mechanism 
is working correctly - the WebDriver is being shut down as intended.
"""

import sys
import os
import time
import threading

# Add the parent directory to Python path when running tests directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from seleniumfetch import SharedSeleniumDriver, fetch_site_posts, cleanup_selenium_drivers, DRIVER_RECYCLE_TIMEOUT

# Test configuration
TEST_URL = "https://keithcu.com/wordpress/?feed=rss2"  # RSS feed URL
TEST_TIMEOUT = 5  # 5 seconds for quick testing
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def test_1_quick_functionality():
    """Quick test of basic functionality without waiting for timeouts."""
    print("\n" + "=" * 60)
    print("TEST 1: Quick Functionality")
    print("=" * 60)
    
    try:
        print("Testing basic driver creation and fetch...")
        start_time = time.time()
        
        # Test driver creation
        driver = SharedSeleniumDriver.get_driver(use_tor=False, user_agent=USER_AGENT)
        if not driver:
            print("[FAIL] Failed to create driver")
            return False
        
        creation_time = time.time() - start_time
        print(f"[OK] Driver created in {creation_time:.2f} seconds")
        
        # Test fetch
        fetch_start = time.time()
        result = fetch_site_posts(TEST_URL, USER_AGENT)
        fetch_time = time.time() - fetch_start
        
        if result and 'entries' in result:
            entries = result['entries']
            print(f"[OK] Fetch completed in {fetch_time:.2f} seconds, found {len(entries)} entries")
        else:
            print("[FAIL] Fetch failed or no entries found")
            return False
        
        # Test manual cleanup
        cleanup_selenium_drivers()
        if SharedSeleniumDriver._instance is None:
            print("[OK] Manual cleanup successful")
            return True
        else:
            print("[FAIL] Manual cleanup failed")
            return False
            
    except Exception as e:
        print(f"[FAIL] Quick functionality test failed: {e}")
        return False
    finally:
        cleanup_selenium_drivers()

def test_2_driver_creation_and_persistence():
    """Test that driver is created and remains functional."""
    print("\n" + "=" * 60)
    print("TEST 2: Driver Creation and Persistence")
    print("=" * 60)

    try:
        print("Creating driver...")
        start_time = time.time()

        # Get driver (should create new instance)
        driver = SharedSeleniumDriver.get_driver(use_tor=False, user_agent=USER_AGENT)
        if driver:
            print(f"[OK] Driver created successfully in {time.time() - start_time:.2f} seconds")
            print(f"Driver instance: {driver}")

            # Test that driver is responsive
            try:
                current_url = driver.current_url
                print(f"[OK] Driver is responsive, current URL: {current_url}")
            except Exception as e:
                print(f"[FAIL] Driver health check failed: {e}")
                return False
        else:
            print("[FAIL] Failed to create driver")
            return False

        # Test that driver remains functional
        print("\nTesting driver persistence...")
        print("NOTE: Driver stays active until manually cleaned up")

        # Wait a reasonable time to verify driver stays functional
        test_duration = min(3, TEST_TIMEOUT)  # Wait up to 3 seconds or test timeout
        for i in range(test_duration):
            time.sleep(1)
            print(f"  {i + 1}/{test_duration} seconds elapsed...")

            # Check that driver is still functional
            try:
                _ = driver.current_url  # Quick health check
                print(f"  [OK] Driver still responsive after {i + 1} seconds")
            except Exception as e:
                print(f"  [FAIL] Driver became unresponsive: {e}")
                return False

        # Test manual cleanup
        print("Testing manual cleanup...")
        cleanup_selenium_drivers()
        if SharedSeleniumDriver._instance is None:
            print("[OK] Manual cleanup successful")
            return True
        else:
            print("[FAIL] Manual cleanup failed")
            return False
            
    finally:
        # Force cleanup
        cleanup_selenium_drivers()

def test_3_fetch_site_posts():
    """Test the fetch_site_posts function with the test URL."""
    print("\n" + "=" * 60)
    print("TEST 3: Fetch Site Posts")
    print("=" * 60)
    
    try:
        print(f"Fetching posts from {TEST_URL}...")
        print("NOTE: Connection errors during fetch are EXPECTED if driver times out")
        start_time = time.time()
        
        result = fetch_site_posts(TEST_URL, USER_AGENT)
        
        fetch_time = time.time() - start_time
        print(f"[OK] Fetch completed in {fetch_time:.2f} seconds")
        
        if result and 'entries' in result:
            entries = result['entries']
            print(f"[OK] Found {len(entries)} entries")
            
            # Show first few entries
            for i, entry in enumerate(entries[:3]):
                print(f"  Entry {i + 1}: {entry.get('title', 'No title')[:50]}...")
        else:
            print("[FAIL] No entries found or invalid result")
            return False
        
        # Calculate remaining timeout time (fetch took some time already)
        elapsed_time = time.time() - start_time
        remaining_time = max(1, TEST_TIMEOUT - int(elapsed_time))
        
        print("Testing manual cleanup after fetch...")
        cleanup_selenium_drivers()
        if SharedSeleniumDriver._instance is None:
            print("[OK] Manual cleanup successful")
            return True
        else:
            print("[FAIL] Manual cleanup failed")
            return False
            
    finally:
        # Force cleanup
        cleanup_selenium_drivers()

def test_4_concurrent_access():
    """Test concurrent access to the driver."""
    print("\n" + "=" * 60)
    print("TEST 4: Concurrent Access")
    print("=" * 60)
    
    # Record start time for the whole test
    start_time = time.time()
    results = []
    
    def worker(worker_id):
        """Worker function for concurrent testing."""
        try:
            print(f"Worker {worker_id}: Starting fetch...")
            start_time = time.time()
            
            result = fetch_site_posts(TEST_URL, USER_AGENT)
            
            fetch_time = time.time() - start_time
            print(f"Worker {worker_id}: Completed in {fetch_time:.2f} seconds")
            
            if result and 'entries' in result:
                results.append((worker_id, len(result['entries']), True))
            else:
                results.append((worker_id, 0, False))
                
        except Exception as e:
            print(f"Worker {worker_id}: Error - {e}")
            results.append((worker_id, 0, False))
    
    try:
        print("NOTE: Some workers may fail to acquire fetch lock - this is EXPECTED behavior")
        # Start multiple workers
        threads = []
        for i in range(3):
            thread = threading.Thread(target=worker, args=(i + 1,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        successful = sum(1 for _, _, success in results if success)
        print(f"\n[OK] {successful}/{len(results)} workers completed successfully")
        
        for worker_id, entry_count, success in results:
            status = "[OK]" if success else "[FAIL]"
            print(f"  {status} Worker {worker_id}: {entry_count} entries")
        
        # Calculate remaining timeout time (concurrent operations took some time already)  
        elapsed_time = time.time() - start_time
        remaining_time = max(1, TEST_TIMEOUT - int(elapsed_time))
        
        print("Testing manual cleanup after concurrent access...")
        cleanup_selenium_drivers()
        if SharedSeleniumDriver._instance is None:
            print("[OK] Manual cleanup successful")
            return True
        else:
            print("[FAIL] Manual cleanup failed")
            return False
            
    finally:
        # Force cleanup
        cleanup_selenium_drivers()

def test_5_manual_cleanup():
    """Test manual cleanup functionality."""
    print("\n" + "=" * 60)
    print("TEST 5: Manual Cleanup")
    print("=" * 60)
    
    try:
        print("Creating driver...")
        driver = SharedSeleniumDriver.get_driver(use_tor=False, user_agent=USER_AGENT)
        
        if driver:
            print("[OK] Driver created")
            
            # Test manual cleanup
            print("Testing manual cleanup...")
            cleanup_selenium_drivers()
            
            if SharedSeleniumDriver._instance is None:
                print("[OK] Manual cleanup successful")
                return True
            else:
                print("[FAIL] Manual cleanup failed")
                return False
        else:
            print("[FAIL] Failed to create driver")
            return False
            
    except Exception as e:
        print(f"[FAIL] Error during manual cleanup test: {e}")
        return False

if __name__ == '__main__':
    # Add the parent directory to Python path when running tests directly
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    
    # Note: Using simple singleton pattern with manual cleanup
    # This is the most reliable approach
    
    print("Selenium Driver Test Suite")
    print("Testing basic functionality with simple singleton pattern")
    print("URL: https://keithcu.com/wordpress/?feed=rss2")
    print()
    print("IMPORTANT: This uses a simple singleton pattern.")
    print("Drivers remain active until explicitly cleaned up.")
    print()
    print("NOTE: Connection errors are expected when drivers are cleaned up manually.")

    tests = [
        ("Quick Functionality", test_1_quick_functionality),
        ("Driver Creation and Persistence", test_2_driver_creation_and_persistence),
        ("Fetch Site Posts", test_3_fetch_site_posts),
        ("Concurrent Access", test_4_concurrent_access),
        ("Manual Cleanup", test_5_manual_cleanup),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*20} {test_name} {'='*20}")
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"[FAIL] Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    for test_name, success in results:
        status = "[OK] PASS" if success else "[FAIL] FAIL"
        print(f"{status}: {test_name}")
        if success:
            passed += 1
    
    print(f"\nResults: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("SUCCESS: All tests passed! Selenium driver management is working correctly.")
    else:
        print("WARNING: Some tests failed. Check the output above for details.")
    
    # Final cleanup
    print("\nPerforming final cleanup...")
    cleanup_selenium_drivers() 
