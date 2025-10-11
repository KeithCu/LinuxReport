"""
browser_fetch.py

Unified browser interface for web scraping that automatically switches between
Selenium and Playwright based on a global configuration variable.

This module provides a consistent API regardless of which browser engine is used,
making it easy to switch between Selenium and Playwright without changing
application code.

Author: LinuxReport System
License: See LICENSE file
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import time
import threading
import atexit
import signal
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import random
import re
import requests
from bs4 import BeautifulSoup

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from shared import g_cs, CUSTOM_FETCH_CONFIG, g_logger, WORKER_PROXYING, PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD, USE_PLAYWRIGHT

# =============================================================================
# BROWSER ENGINE SELECTION
# =============================================================================

def _get_browser_module():
    """
    Dynamically import the appropriate browser module based on configuration.
    
    Returns:
        module: Either seleniumfetch or playwrightfetch module
        
    Raises:
        ImportError: If neither browser module is available
    """
    if USE_PLAYWRIGHT:
        try:
            import playwrightfetch
            g_logger.info("Using Playwright for browser automation")
            return playwrightfetch
        except ImportError as e:
            g_logger.warning(f"Playwright not available ({e}), falling back to Selenium")
            try:
                import seleniumfetch
                g_logger.info("Fallback: Using Selenium for browser automation")
                return seleniumfetch
            except ImportError as e2:
                g_logger.error(f"Both Playwright and Selenium are unavailable. Playwright error: {e}, Selenium error: {e2}")
                raise ImportError("Neither Playwright nor Selenium browser modules are available")
    else:
        try:
            import seleniumfetch
            g_logger.info("Using Selenium for browser automation")
            return seleniumfetch
        except ImportError as e:
            g_logger.warning(f"Selenium not available ({e}), falling back to Playwright")
            try:
                import playwrightfetch
                g_logger.info("Fallback: Using Playwright for browser automation")
                return playwrightfetch
            except ImportError as e2:
                g_logger.error(f"Both Selenium and Playwright are unavailable. Selenium error: {e}, Playwright error: {e2}")
                raise ImportError("Neither Selenium nor Playwright browser modules are available")

# =============================================================================
# UNIFIED API FUNCTIONS
# =============================================================================

def fetch_site_posts(url, user_agent):
    """
    Fetch posts from a website using the configured browser engine.
    
    This function automatically uses either Selenium or Playwright based on
    the USE_PLAYWRIGHT global variable in shared.py.
    
    Args:
        url (str): URL of the site to fetch posts from
        user_agent (str): User agent string for HTTP requests
        
    Returns:
        dict: Feed-like structure with entries, metadata, and status information
        
    Raises:
        ImportError: If neither browser module is available
        Exception: If the underlying browser module raises an exception
    """
    try:
        browser_module = _get_browser_module()
        return browser_module.fetch_site_posts(url, user_agent)
    except ImportError:
        # Re-raise ImportError as-is
        raise
    except Exception as e:
        g_logger.error(f"Error in fetch_site_posts: {e}")
        raise

def cleanup_browsers():
    """
    Clean up all browser instances using the configured browser engine.
    
    This function automatically calls the appropriate cleanup function
    based on the USE_PLAYWRIGHT global variable in shared.py.
    """
    try:
        browser_module = _get_browser_module()
        
        if USE_PLAYWRIGHT:
            try:
                browser_module.cleanup_playwright_browsers()
            except AttributeError:
                # Fallback if function doesn't exist
                g_logger.warning("Playwright cleanup function not found")
        else:
            try:
                browser_module.cleanup_selenium_drivers()
            except AttributeError:
                # Fallback if function doesn't exist
                g_logger.warning("Selenium cleanup function not found")
    except ImportError:
        g_logger.warning("No browser modules available for cleanup")
    except Exception as e:
        g_logger.error(f"Error during browser cleanup: {e}")

# =============================================================================
# COMPATIBILITY FUNCTIONS
# =============================================================================

def get_shared_driver(use_tor, user_agent):
    """
    Get a shared browser driver/context using the configured browser engine.
    
    Args:
        use_tor (bool): Whether to use Tor proxy
        user_agent (str): User agent string for the browser
        
    Returns:
        tuple or object: Browser driver/context depending on engine used
    """
    browser_module = _get_browser_module()
    
    if USE_PLAYWRIGHT:
        try:
            return browser_module.SharedPlaywrightBrowser.get_browser_context(use_tor, user_agent)
        except AttributeError:
            g_logger.error("Playwright SharedPlaywrightBrowser not available")
            return None, None
    else:
        try:
            return browser_module.SharedSeleniumDriver.get_driver(use_tor, user_agent)
        except AttributeError:
            g_logger.error("Selenium SharedSeleniumDriver not available")
            return None

def acquire_fetch_lock():
    """
    Acquire the fetch lock using the configured browser engine.
    
    Returns:
        bool: True if lock was acquired successfully
    """
    browser_module = _get_browser_module()
    
    if USE_PLAYWRIGHT:
        try:
            return browser_module.SharedPlaywrightBrowser.acquire_fetch_lock()
        except AttributeError:
            g_logger.error("Playwright fetch lock not available")
            return False
    else:
        try:
            return browser_module.SharedSeleniumDriver.acquire_fetch_lock()
        except AttributeError:
            g_logger.error("Selenium fetch lock not available")
            return False

def release_fetch_lock():
    """
    Release the fetch lock using the configured browser engine.
    """
    browser_module = _get_browser_module()
    
    if USE_PLAYWRIGHT:
        try:
            browser_module.SharedPlaywrightBrowser.release_fetch_lock()
        except AttributeError:
            g_logger.warning("Playwright fetch lock release not available")
    else:
        try:
            browser_module.SharedSeleniumDriver.release_fetch_lock()
        except AttributeError:
            g_logger.warning("Selenium fetch lock release not available")

# =============================================================================
# GLOBAL CLEANUP REGISTRATION
# =============================================================================

def _atexit_handler():
    """
    Atexit handler for cleanup on normal program termination.
    """
    g_logger.info("Program exiting, cleaning up browsers...")
    cleanup_browsers()

# Register cleanup handler
atexit.register(_atexit_handler)

# =============================================================================
# EXPORT COMPATIBILITY
# =============================================================================

# Export the main functions for easy importing
__all__ = [
    'fetch_site_posts',
    'cleanup_browsers', 
    'get_shared_driver',
    'acquire_fetch_lock',
    'release_fetch_lock'
]
