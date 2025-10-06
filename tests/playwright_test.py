#!/usr/bin/env python3
"""
playwright_test.py

Test script to verify Playwright fetching functionality.
"""

import sys
import os
import time
import threading
import traceback

# Add the parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from seleniumfetch import fetch_site_posts, USE_PLAYWRIGHT

# Test configuration
TEST_URL = "https://keithcu.com/wordpress/?feed=rss2"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def run_test(test_name, test_func):
    """Helper to run a test and print results."""
    print("\n" + "=" * 60)
    print(f"RUNNING: {test_name}")
    print("=" * 60)
    try:
        success = test_func()
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {test_name}")
        return success
    except Exception as e:
        print(f"✗ ERROR in {test_name}: {e}")
        traceback.print_exc()
        return False

def test_fetch_rss_feed():
    """Tests fetching and parsing of an RSS feed via Playwright."""
    print(f"Fetching posts from {TEST_URL}...")
    result = fetch_site_posts(TEST_URL, USER_AGENT)

    if not (result and result.get('status') == 200 and isinstance(result.get('entries'), list)):
        print(f"✗ Fetch failed or returned an invalid structure. Result: {result}")
        return False

    if not result['entries']:
        print(f"✗ Fetch succeeded but found no entries. Result: {result}")
        return False

    print(f"✓ Fetch successful, found {len(result['entries'])} entries.")
    entry = result['entries'][0]
    if 'title' in entry and 'link' in entry:
        print(f"  Sample entry: {entry['title'][:60]}...")
        return True
    else:
        print(f"✗ Entries are missing required keys 'title' or 'link'. Entry: {entry}")
        return False

def test_concurrent_fetches():
    """Tests thread-safety by running multiple fetches concurrently."""
    results = [False] * 3

    def worker(index):
        print(f"Worker {index}: Starting fetch...")
        try:
            result = fetch_site_posts(TEST_URL, USER_AGENT)
            if result and result.get('status') == 200 and result.get('entries'):
                print(f"Worker {index}: Fetch successful.")
                results[index] = True
            else:
                print(f"Worker {index}: Fetch failed. Result: {result}")
        except Exception as e:
            print(f"Worker {index}: Exception - {e}")
            traceback.print_exc()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successful_fetches = sum(1 for r in results if r)
    print(f"\nCompleted {successful_fetches}/{len(results)} concurrent fetches successfully.")
    return successful_fetches == len(results)

if __name__ == '__main__':
    if not USE_PLAYWRIGHT:
        print("SKIPPING Playwright tests: USE_PLAYWRIGHT is set to False.")
        sys.exit(0)

    print("Playwright Test Suite")

    test_results = [
        run_test("Single RSS Feed Fetch", test_fetch_rss_feed),
        run_test("Concurrent RSS Feed Fetches", test_concurrent_fetches),
    ]

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in test_results if r)
    total = len(test_results)

    if passed == total:
        print(f"🎉 All {total} tests passed! Playwright implementation is working correctly.")
    else:
        print(f"⚠️  {passed}/{total} tests passed. Check the output above for details.")
        sys.exit(1)