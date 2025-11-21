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
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwrightfetch import fetch_site_posts

# Test configuration
TEST_URL = "https://keithcu.com/wordpress/?feed=rss2"  # RSS feed URL
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def test_1_fetch_site_posts():
    """Test the main fetch_site_posts function."""
    print("\nTest 1: fetch_site_posts function")
    
    try:
        # Test fetch_site_posts with a simple URL
        result = fetch_site_posts(TEST_URL, USER_AGENT)
        
        if result and 'status' in result and result['status'] == 200:
            print(f"SUCCESS: fetch_site_posts returned status: {result['status']}")
            print(f"SUCCESS: Found {len(result.get('entries', []))} entries")
            return True
        else:
            print(f"FAILED: fetch_site_posts failed or returned invalid result: {result}")
            return False
            
    except Exception as e:
        print(f"FAILED: Test failed with exception: {e}")
        traceback.print_exc()
        return False

def test_2_concurrent_fetch():
    """Test concurrent fetching to verify thread safety."""
    print("\nTest 2: Concurrent fetching")
    
    results = []
    
    def worker(worker_id):
        """Worker function for concurrent testing."""
        try:
            print(f"Worker {worker_id}: Starting fetch...")
            start_time = time.time()
            
            result = fetch_site_posts(TEST_URL, USER_AGENT)

            fetch_time = time.time() - start_time
            print(f"Worker {worker_id}: Completed in {fetch_time:.2f} seconds")

            if result and 'entries' in result and result['status'] == 200:
                results.append((worker_id, len(result['entries']), True))
            else:
                results.append((worker_id, 0, False))
                
        except Exception as e:
            print(f"Worker {worker_id}: Error - {e}")
            results.append((worker_id, 0, False))

    try:
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
        print(f"\nSUCCESS: {successful}/{len(results)} workers completed successfully")
        
        for worker_id, entry_count, success in results:
            status = "SUCCESS" if success else "FAILED"
            print(f"  {status}: Worker {worker_id} found {entry_count} entries")
        
        return successful > 0
            
    except Exception as e:
        print(f"FAILED: Test failed with exception: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("Playwright Test Suite")
    print("=" * 50)
    
    tests = [
        test_1_fetch_site_posts,
        test_2_concurrent_fetch
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
    exit_code = main()
    sys.exit(exit_code)