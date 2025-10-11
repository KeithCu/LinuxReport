#!/usr/bin/env python3
"""
playwright_simple_test.py

Simple test suite for Playwright-based web scraping functionality.
Tests browser management and basic functionality without Unicode characters.
"""

import os
import sys
import time
import traceback

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwrightfetch import SharedPlaywrightBrowser, fetch_site_posts, cleanup_playwright_browsers

# Test configuration
TEST_URL = "https://keithcu.com/wordpress/?feed=rss2"  # RSS feed URL
TEST_TIMEOUT = 5  # 5 seconds for quick testing
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def test_basic_browser_creation():
    """Test basic browser creation and cleanup."""
    print("Test: Basic browser creation and cleanup")
    
    try:
        # Reset any existing state
        SharedPlaywrightBrowser.reset_for_testing()
        
        # Test browser creation
        browser, context = SharedPlaywrightBrowser.get_browser_context(use_tor=False, user_agent=USER_AGENT)
        if not browser or not context:
            print("FAILED: Could not create browser")
            return False
        
        print("SUCCESS: Browser created successfully")
        
        # Test basic page navigation
        page = context.new_page()
        page.goto(TEST_URL, timeout=30000)
        title = page.title()
        print(f"SUCCESS: Page loaded successfully: {title}")
        
        # Test manual cleanup
        cleanup_playwright_browsers()
        # Check if all instances are None (cleanup sets them to None but doesn't remove keys)
        all_cleaned = all(instance is None for instance in SharedPlaywrightBrowser._instances.values())
        if all_cleaned:
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

def test_fetch_site_posts():
    """Test the main fetch_site_posts function."""
    print("\nTest: fetch_site_posts function")
    
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

def main():
    """Run all tests."""
    print("Playwright Simple Test Suite")
    print("=" * 50)
    
    tests = [
        test_basic_browser_creation,
        test_fetch_site_posts
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
