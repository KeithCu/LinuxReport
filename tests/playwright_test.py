#!/usr/bin/env python3
"""
playwright_test.py

Test suite for Playwright-based web scraping functionality.
Tests browser management, content extraction, and cleanup operations.
"""

import os
import sys
import time
import threading
import traceback

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwrightfetch import SharedPlaywrightBrowser, fetch_site_posts, cleanup_playwright_browsers, BROWSER_RECYCLE_TIMEOUT

# Test configuration
TEST_URL = "https://keithcu.com/wordpress/?feed=rss2"  # RSS feed URL
TEST_TIMEOUT = 5  # 5 seconds for quick testing
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def test_1_basic_browser_creation():
    """Test basic browser creation and cleanup."""
    print("Test 1: Basic browser creation and cleanup")
    
    try:
        # Reset any existing state
        SharedPlaywrightBrowser.reset_for_testing()
        
        # Test browser creation
        browser, context = SharedPlaywrightBrowser.get_browser_context(use_tor=False, user_agent=USER_AGENT)
        if not browser or not context:
            print("FAILED: Failed to create browser")
            return False
        
        print("SUCCESS: Browser created successfully")
        
        # Test basic page navigation
        page = context.new_page()
        page.goto(TEST_URL, timeout=30000)
        title = page.title()
        print(f"SUCCESS: Page loaded successfully: {title}")
        
        # Test manual cleanup
        cleanup_playwright_browsers()
        if SharedPlaywrightBrowser._instance is None:
            print("SUCCESS: Manual cleanup successful")
            return True
        else:
            print("FAILED: Manual cleanup failed")
            return False
            
    except Exception as e:
        print(f"FAILED: Test failed with exception: {e}")
        traceback.print_exc()
        return False
    finally:
        cleanup_playwright_browsers()

def test_2_browser_creation_and_persistence():
    """Test browser creation and TTL-based persistence."""
    print("\nTest 2: Browser creation and persistence")
    
    try:
        # Reset any existing state
        SharedPlaywrightBrowser.reset_for_testing()
        
        start_time = time.time()
        
        # Get browser (should create new instance)
        browser, context = SharedPlaywrightBrowser.get_browser_context(use_tor=False, user_agent=USER_AGENT)
        if browser and context:
            print(f"SUCCESS: Browser created successfully in {time.time() - start_time:.2f} seconds")
        else:
            print("FAILED: Failed to create browser")
            return False
        
        # Test that we can get the same instance quickly
        start_time = time.time()
        browser2, context2 = SharedPlaywrightBrowser.get_browser_context(use_tor=False, user_agent=USER_AGENT)
        if browser2 and context2:
            print(f"SUCCESS: Retrieved existing browser in {time.time() - start_time:.2f} seconds")
        else:
            print("FAILED: Failed to retrieve existing browser")
            return False
        
        # Test page navigation
        page = context.new_page()
        page.goto(TEST_URL, timeout=30000)
        title = page.title()
        print(f"SUCCESS: Page navigation successful: {title}")
        
        return True
        
    except Exception as e:
        print(f"FAILED: Test failed with exception: {e}")
        traceback.print_exc()
        return False
    finally:
        # Force cleanup
        cleanup_playwright_browsers()

def test_3_fetch_site_posts():
    """Test the main fetch_site_posts function."""
    print("\nTest 3: fetch_site_posts function")
    
    try:
        # Reset any existing state
        SharedPlaywrightBrowser.reset_for_testing()
        
        # Test fetch_site_posts with a simple URL
        result = fetch_site_posts(TEST_URL, USER_AGENT)
        
        if result and 'status' in result:
            print(f"SUCCESS: fetch_site_posts returned status: {result['status']}")
            print(f"SUCCESS: Found {len(result.get('entries', []))} entries")
            return True
        else:
            print("FAILED: fetch_site_posts failed or returned invalid result")
            return False
            
    except Exception as e:
        print(f"FAILED: Test failed with exception: {e}")
        traceback.print_exc()
        return False
    finally:
        # Force cleanup
        cleanup_playwright_browsers()

def test_4_concurrent_access():
    """Test concurrent browser access and thread safety."""
    print("\nTest 4: Concurrent browser access")
    
    # Reset any existing state
    SharedPlaywrightBrowser.reset_for_testing()
    
    # Reset shutdown flag from previous tests
    SharedPlaywrightBrowser._shutdown_initiated = False
    
    # Record start time for the whole test
    test_start_time = time.time()
    
    results = []
    threads = []
    
    def worker_thread(thread_id):
        """Worker thread function."""
        try:
            start_time = time.time()
            browser, context = SharedPlaywrightBrowser.get_browser_context(use_tor=False, user_agent=USER_AGENT)
            end_time = time.time()
            
            if browser and context:
                results.append({
                    'thread_id': thread_id,
                    'success': True,
                    'duration': end_time - start_time,
                    'browser': browser,
                    'context': context
                })
                print(f"SUCCESS: Thread {thread_id} got browser in {end_time - start_time:.2f} seconds")
            else:
                results.append({
                    'thread_id': thread_id,
                    'success': False,
                    'duration': end_time - start_time
                })
                print(f"FAILED: Thread {thread_id} failed to get browser")
                
        except Exception as e:
            results.append({
                'thread_id': thread_id,
                'success': False,
                'error': str(e)
            })
            print(f"FAILED: Thread {thread_id} failed with exception: {e}")
    
    try:
        # Create multiple threads
        for i in range(3):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=30)  # 30 second timeout per thread
        
        # Check results
        successful_threads = [r for r in results if r.get('success', False)]
        failed_threads = [r for r in results if not r.get('success', False)]
        
        print(f"SUCCESS: {len(successful_threads)} threads succeeded")
        if failed_threads:
            print(f"FAILED: {len(failed_threads)} threads failed")
            for failed in failed_threads:
                print(f"  Thread {failed['thread_id']}: {failed.get('error', 'Unknown error')}")
        
        # Test that browsers are automatically cleaned up after TTL
        print("Waiting for browser cleanup...")
        cleanup_detected = False
        for i in range(BROWSER_RECYCLE_TIMEOUT + 10):
            remaining_time = BROWSER_RECYCLE_TIMEOUT + 10 - i
            time.sleep(1)
            print(f"  {i + 1}/{BROWSER_RECYCLE_TIMEOUT + 10} seconds elapsed...")
            if SharedPlaywrightBrowser._instance is None:
                print("SUCCESS: Browser was automatically cleaned up after concurrent access")
                cleanup_detected = True
                break
        
        if not cleanup_detected:
            # Check one more time after full wait
            if SharedPlaywrightBrowser._instance is None:
                print("SUCCESS: Browser was automatically cleaned up after concurrent access")
                return True
            else:
                print("FAILED: Browser was not automatically cleaned up")
                return False
        
        return len(successful_threads) > 0
        
    except Exception as e:
        print(f"FAILED: Test failed with exception: {e}")
        traceback.print_exc()
        return False
    finally:
        # Force cleanup
        cleanup_playwright_browsers()

def test_5_manual_cleanup():
    """Test manual cleanup functionality."""
    print("\nTest 5: Manual cleanup")
    
    # Reset shutdown flag from previous tests
    SharedPlaywrightBrowser._shutdown_initiated = False
    
    try:
        print("Creating browser...")
        browser, context = SharedPlaywrightBrowser.get_browser_context(use_tor=False, user_agent=USER_AGENT)
        
        if browser and context:
            print("SUCCESS: Browser created successfully")
            
            # Test manual cleanup
            print("Testing manual cleanup...")
            cleanup_playwright_browsers()
            
            if SharedPlaywrightBrowser._instance is None:
                print("SUCCESS: Manual cleanup successful")
                return True
            else:
                print("FAILED: Manual cleanup failed")
                return False
        else:
            print("FAILED: Failed to create browser")
            return False
            
    except Exception as e:
        print(f"FAILED: Test failed with exception: {e}")
        traceback.print_exc()
        return False
    finally:
        # Force cleanup
        cleanup_playwright_browsers()

def main():
    """Run all tests."""
    print("Playwright Test Suite")
    print("=" * 50)
    
    tests = [
        test_1_basic_browser_creation,
        test_2_browser_creation_and_persistence,
        test_3_fetch_site_posts,
        test_4_concurrent_access,
        test_5_manual_cleanup
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"FAILED: Test {test.__name__} failed with exception: {e}")
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("SUCCESS: All tests passed!")
        return 0
    else:
        print("FAILED: Some tests failed!")
        return 1

if __name__ == "__main__":
    # Final cleanup
    print("\nPerforming final cleanup...")
    cleanup_playwright_browsers()
    
    exit_code = main()
    sys.exit(exit_code)
