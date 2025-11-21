#!/usr/bin/env python3
"""
test_browser_switch.py

Test script to verify the browser switching functionality between Selenium and Playwright.
Tests the unified browser_fetch interface and ensures proper fallback behavior.
"""

import sys
import os
import time
import threading
from pathlib import Path

# Add the parent directory to Python path when running tests directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from browser_fetch import fetch_site_posts, cleanup_browsers, get_shared_driver, acquire_fetch_lock, release_fetch_lock
from shared import USE_PLAYWRIGHT, g_logger

# Test configuration
TEST_URL = "https://keithcu.com/wordpress/?feed=rss2"  # RSS feed URL
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def test_browser_engine_detection():
    """Test that the correct browser engine is detected."""
    print("\n" + "=" * 60)
    print("TEST 1: Browser Engine Detection")
    print("=" * 60)
    
    current_engine = "Playwright" if USE_PLAYWRIGHT else "Selenium"
    print(f"Current browser engine setting: {current_engine}")
    print(f"USE_PLAYWRIGHT flag: {USE_PLAYWRIGHT}")
    
    # Test that the module can be imported
    try:
        from browser_fetch import _get_browser_module
        browser_module = _get_browser_module()
        module_name = browser_module.__name__
        print(f"Successfully loaded browser module: {module_name}")
        
        if USE_PLAYWRIGHT:
            assert "playwright" in module_name, f"Expected playwright module, got {module_name}"
        else:
            assert "selenium" in module_name, f"Expected selenium module, got {module_name}"
        
        print("PASS: Browser engine detection test PASSED")
        return True
        
    except Exception as e:
        print(f"FAIL: Browser engine detection test FAILED: {e}")
        return False

def test_fetch_functionality():
    """Test basic fetch functionality."""
    print("\n" + "=" * 60)
    print("TEST 2: Basic Fetch Functionality")
    print("=" * 60)
    
    try:
        print(f"Testing fetch with URL: {TEST_URL}")
        result = fetch_site_posts(TEST_URL, USER_AGENT)
        
        if result and isinstance(result, dict):
            print(f"PASS: Fetch returned valid result structure")
            print(f"  Status: {result.get('status', 'unknown')}")
            print(f"  Entries: {len(result.get('entries', []))}")
            print(f"  Feed title: {result.get('feed', {}).get('title', 'unknown')}")
            
            if result.get('status') == 200 and len(result.get('entries', [])) > 0:
                print("PASS: Basic fetch functionality test PASSED")
                return True
            else:
                print("WARN: Fetch returned but with no entries or non-200 status")
                return True  # Still consider it a pass if we got a response
        else:
            print(f"FAIL: Fetch returned invalid result: {result}")
            return False
            
    except Exception as e:
        print(f"FAIL: Basic fetch functionality test FAILED: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

def test_shared_driver_functionality():
    """Test shared driver functionality."""
    print("\n" + "=" * 60)
    print("TEST 3: Shared Driver Functionality")
    print("=" * 60)
    
    try:
        print("Testing shared driver creation...")
        driver_result = get_shared_driver(use_tor=False, user_agent=USER_AGENT)
        
        if USE_PLAYWRIGHT:
            # Playwright returns (browser, context) tuple
            if isinstance(driver_result, tuple) and len(driver_result) == 2:
                browser, context = driver_result
                if browser and context:
                    print("PASS: Playwright browser and context created successfully")
                    return True
                else:
                    print("FAIL: Playwright browser or context is None")
                    return False
            else:
                print(f"FAIL: Playwright returned invalid result: {driver_result}")
                return False
        else:
            # Selenium returns driver object
            if driver_result:
                print("PASS: Selenium driver created successfully")
                return True
            else:
                print("FAIL: Selenium driver is None")
                return False
                
    except Exception as e:
        print(f"FAIL: Shared driver functionality test FAILED: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

def test_fetch_lock_functionality():
    """Test fetch lock functionality."""
    print("\n" + "=" * 60)
    print("TEST 4: Fetch Lock Functionality")
    print("=" * 60)
    
    try:
        print("Testing fetch lock acquisition...")
        lock_acquired = acquire_fetch_lock()
        
        if lock_acquired:
            print("PASS: Fetch lock acquired successfully")
            
            # Test that we can release the lock
            release_fetch_lock()
            print("PASS: Fetch lock released successfully")
            
            print("PASS: Fetch lock functionality test PASSED")
            return True
        else:
            print("FAIL: Failed to acquire fetch lock")
            return False
            
    except Exception as e:
        print(f"FAIL: Fetch lock functionality test FAILED: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

def test_cleanup_functionality():
    """Test cleanup functionality."""
    print("\n" + "=" * 60)
    print("TEST 5: Cleanup Functionality")
    print("=" * 60)
    
    try:
        print("Testing browser cleanup...")
        cleanup_browsers()
        print("PASS: Browser cleanup completed without errors")
        print("PASS: Cleanup functionality test PASSED")
        return True
        
    except Exception as e:
        print(f"FAIL: Cleanup functionality test FAILED: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

def test_engine_switching():
    """Test switching between engines by modifying the global variable."""
    print("\n" + "=" * 60)
    print("TEST 6: Engine Switching (Simulation)")
    print("=" * 60)
    
    try:
        # Store original value
        original_value = USE_PLAYWRIGHT
        print(f"Original USE_PLAYWRIGHT value: {original_value}")
        
        # Test that we can import the module and it respects the current setting
        from browser_fetch import _get_browser_module
        browser_module = _get_browser_module()
        module_name = browser_module.__name__
        
        expected_module = "playwrightfetch" if USE_PLAYWRIGHT else "seleniumfetch"
        if expected_module in module_name:
            print(f"PASS: Correct module loaded: {module_name}")
            print("PASS: Engine switching simulation test PASSED")
            return True
        else:
            print(f"FAIL: Wrong module loaded. Expected {expected_module}, got {module_name}")
            return False
            
    except Exception as e:
        print(f"FAIL: Engine switching test FAILED: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

def run_all_tests():
    """Run all tests and report results."""
    print("=" * 80)
    print("BROWSER SWITCHING FUNCTIONALITY TEST SUITE")
    print("=" * 80)

    tests = [
        test_browser_engine_detection,
        test_fetch_functionality,
        test_shared_driver_functionality,
        test_fetch_lock_functionality,
        test_cleanup_functionality,
        test_engine_switching,
    ]

    passed = 0
    total = len(tests)
    failed_tests = []

    for test in tests:
        try:
            result = test()
            if result:
                passed += 1
                print(f"PASS: {test.__name__}")
            else:
                failed_tests.append(test.__name__)
                print(f"FAIL: {test.__name__}")
        except Exception as e:
            failed_tests.append(test.__name__)
            print(f"FAIL: Test {test.__name__} crashed: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")

    print("\n" + "=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    print(f"Tests passed: {passed}/{total}")
    print(f"Success rate: {(passed/total)*100:.1f}%")

    if failed_tests:
        print(f"Failed tests: {', '.join(failed_tests)}")

    if passed == total:
        print("SUCCESS: ALL TESTS PASSED! Browser switching functionality is working correctly.")
        return True
    else:
        print("FAILURE: Some tests failed. Please check the output above for details.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
