"""
playwrightfetch.py

Playwright-based web scraping system for JavaScript-rendered content and dynamic sites.
Provides functions to fetch and parse posts from sites requiring JavaScript rendering
or special handling, using Playwright and BeautifulSoup. Includes site-specific
configurations, and thread-safe operations.
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
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

try:
    import psutil
except ImportError:
    psutil = None

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from shared import g_cs, CUSTOM_FETCH_CONFIG, g_logger, WORKER_PROXYING, PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD
from app_config import FetchConfig
from browser_fetch import (
    NETWORK_TIMEOUT, FETCH_LOCK_TIMEOUT, BROWSER_TIMEOUT, BROWSER_WAIT_TIMEOUT,
    extract_base_domain, get_site_config, build_feed_result, clean_patriots_title, create_post_entry,
    extract_rss_data, safe_find_element, extract_title, extract_link, extract_post_data as shared_extract_post_data
)

# =============================================================================
# TIMEOUT CONSTANTS
# =============================================================================

# Note: PLAYWRIGHT_TIMEOUT, WEBDRIVER_TIMEOUT, and BROWSER_WAIT_TIMEOUT are now imported from browser_fetch
# to maintain consistency across all browser modules

# =============================================================================
# SPECIAL SITE CONFIGURATIONS
# =============================================================================

# =============================================================================
# PLAYWRIGHT BROWSER CONFIGURATION AND CREATION
# =============================================================================

def create_browser_context(playwright, use_tor, user_agent):
    """
    Create and configure a Playwright browser context.

    Sets up a Chromium browser with appropriate options for web scraping,
    including proxy configuration for Tor if enabled and custom user agent.

    Args:
        playwright: Playwright instance
        use_tor (bool): Whether to use Tor proxy for connections
        user_agent (str): User agent string to use for requests

    Returns:
        tuple: (browser, context) - Configured Playwright browser and context instances
    """
    try:
        g_logger.info(f"Creating Playwright browser with Tor: {use_tor}, User-Agent: {user_agent[:50]}...")

        # Launch browser with performance and anti-detection options
        browser_options = {
            "headless": True,
            "args": [
                # Anti-detection measures
                "--disable-blink-features=AutomationControlled",
                # Performance optimizations
                "--disable-extensions",
                "--disable-plugins",
                "--disable-images",  # Speed up loading
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=TranslateUI",
                "--disable-ipc-flooding-protection",
                "--memory-pressure-off",
                "--max-old-space-size=4096",  # Limit memory usage
                # Use consistent window size to avoid detection patterns
                "--window-size=1920,1080",
            ]
        }

        browser = playwright.chromium.launch(**browser_options)

        # Context options
        context_options = {
            "user_agent": user_agent,
            "viewport": {"width": 1920, "height": 1080},
            "ignore_https_errors": True,
            "java_script_enabled": True,
            # Additional anti-detection
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "geolocation": None,  # Disable geolocation
            "permissions": [],  # No permissions
        }

        if use_tor:
            context_options["proxy"] = {"server": "socks5://127.0.0.1:9050"}

        context = browser.new_context(**context_options)
        g_logger.debug("Playwright browser and context created successfully")
        return browser, context

    except Exception as e:
        g_logger.error(f"Error creating Playwright browser: {e}")
        g_logger.error(f"Error type: {type(e).__name__}")
        import traceback
        g_logger.error(f"Full traceback: {traceback.format_exc()}")
        raise

# =============================================================================
# SHARED PLAYWRIGHT BROWSER MANAGEMENT
# =============================================================================

class SharedPlaywrightBrowser:
    """
    Thread-safe manager for Playwright browser contexts.

    Uses thread-local storage to avoid Playwright's threading limitations.
    Each thread gets its own browser instance to prevent "Cannot switch to a different thread" errors.
    """

    _instances = {}  # Thread-local instances
    _lock = threading.Lock()
    _fetch_lock = threading.Lock()
    _playwright_instance = None

    def __init__(self, use_tor, user_agent):
        """
        Initialize a new SharedPlaywrightBrowser instance.

        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the browser context
        """
        g_logger.debug(f"Initializing SharedPlaywrightBrowser with Tor: {use_tor}")
        try:
            self.playwright = sync_playwright().start()
            self.browser, self.context = create_browser_context(self.playwright, use_tor, user_agent)
            self.last_used = time.time()
            self.use_tor = use_tor
            self.user_agent = user_agent
            g_logger.debug("SharedPlaywrightBrowser initialized successfully")
        except Exception as e:
            g_logger.error(f"Error in SharedPlaywrightBrowser.__init__: {e}")
            raise

    @classmethod
    def get_browser_context(cls, use_tor, user_agent):
        """
        Get or create a thread-local browser context.

        Returns a thread-local browser context, creating it if needed.
        Each thread gets its own browser instance to avoid threading issues.

        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the context

        Returns:
            tuple: (browser, context) - Playwright browser and context instances
        """
        thread_id = threading.get_ident()
        
        with cls._lock:
            # Get or create thread-local instance
            if thread_id not in cls._instances or not cls._is_instance_valid(cls._instances[thread_id], use_tor, user_agent):
                if thread_id in cls._instances:
                    cls._cleanup_thread_instance(thread_id)
                try:
                    cls._instances[thread_id] = SharedPlaywrightBrowser(use_tor, user_agent)
                    g_logger.info(f"Created new thread-local browser context instance with Tor: {use_tor} for thread {thread_id}")
                except Exception as e:
                    g_logger.error(f"Error creating browser context for thread {thread_id}: {e}")
                    cls._instances[thread_id] = None
                    return None, None

            cls._instances[thread_id].last_used = time.time()
            return cls._instances[thread_id].browser, cls._instances[thread_id].context

    @classmethod
    def acquire_fetch_lock(cls):
        """
        Acquire the fetch lock to synchronize fetch operations.

        Ensures only one fetch operation can run at a time to prevent
        resource conflicts and rate limiting issues.

        Returns:
            bool: True if lock was acquired successfully
        """
        try:
            return cls._fetch_lock.acquire(timeout=FETCH_LOCK_TIMEOUT)  # 30 second timeout
        except Exception as e:
            g_logger.error(f"Error acquiring fetch lock: {e}")
            return False

    @classmethod
    def release_fetch_lock(cls):
        """
        Release the fetch lock after fetch operation is complete.

        Safely releases the fetch lock, handling cases where the lock
        may not have been acquired.
        """
        try:
            cls._fetch_lock.release()
        except RuntimeError:
            # Lock was not acquired, ignore
            pass

    @classmethod
    def _is_instance_valid(cls, instance, use_tor, user_agent):
        """
        Check if the current browser instance is valid for the given configuration.

        Args:
            use_tor (bool): Required Tor configuration
            user_agent (str): Required user agent string

        Returns:
            bool: True if current instance matches configuration
        """
        try:
            # Only reuse if config matches
            if not (instance and
                    instance.use_tor == use_tor and
                    instance.user_agent == user_agent and
                    hasattr(instance, 'context') and
                    hasattr(instance, 'browser')):
                return False

            # Check if context is still responsive
            try:
                # Simple test to check if context is alive
                pages = instance.context.pages
                return True
            except Exception as e:
                g_logger.debug(f"Context health check failed: {e}")
                return False

        except Exception as e:
            g_logger.error(f"Error during context validation: {e}")
            return False

    @classmethod
    def _cleanup_thread_instance(cls, thread_id):
        """
        Clean up a specific thread's browser instance safely.
        """
        if thread_id in cls._instances and cls._instances[thread_id]:
            instance = cls._instances[thread_id]
            try:
                # Close context first, then browser
                if hasattr(instance, 'context') and instance.context:
                    instance.context.close()
                    g_logger.debug(f"Browser context closed successfully for thread {thread_id}")
                if hasattr(instance, 'browser') and instance.browser:
                    instance.browser.close()
                    g_logger.debug(f"Browser closed successfully for thread {thread_id}")
                if hasattr(instance, 'playwright') and instance.playwright:
                    instance.playwright.stop()
                    g_logger.debug(f"Playwright stopped successfully for thread {thread_id}")
            except Exception as e:
                g_logger.error(f"Error during browser cleanup for thread {thread_id}: {e}")
            finally:
                cls._instances[thread_id] = None
                g_logger.debug(f"Browser instance set to None for thread {thread_id}")

    @classmethod
    def _cleanup_instance(cls):
        """
        Clean up all thread-local browser instances safely.
        """
        for thread_id in list(cls._instances.keys()):
            cls._cleanup_thread_instance(thread_id)

    @classmethod
    def force_cleanup(cls):
        """
        Force shutdown and cleanup of the browser instance.
        """
        g_logger.info("Forcing Playwright browser cleanup...")
        with cls._lock:
            cls._cleanup_instance()
            g_logger.info("Force cleanup completed")

    @classmethod
    def reset_for_testing(cls):
        """
        Reset all thread-local instances for testing purposes.
        This method is only used in test environments.
        """
        with cls._lock:
            cls._cleanup_instance()
            g_logger.debug("Reset for testing completed")


# =============================================================================
# GLOBAL CLEANUP FUNCTIONS
# =============================================================================

def cleanup_playwright_browsers():
    """
    Global cleanup function to ensure all Playwright browsers are properly shut down.

    This function can be called from other modules or during application shutdown
    to ensure no browser instances are left running.
    """
    g_logger.info("Cleaning up all Playwright browsers...")
    SharedPlaywrightBrowser.force_cleanup()


def _signal_handler(signum, frame):
    """
    Signal handler for graceful shutdown.
    """
    g_logger.info(f"Received signal {signum}, cleaning up Playwright browsers...")
    cleanup_playwright_browsers()
    sys.exit(0)


def _atexit_handler():
    """
    Atexit handler for cleanup on normal program termination.
    """
    g_logger.info("Program exiting, cleaning up Playwright browsers...")
    cleanup_playwright_browsers()

# Register cleanup handlers
atexit.register(_atexit_handler)
# Signal handlers commented out since code always runs under Apache/mod_wsgi
# mod_wsgi already handles SIGTERM and SIGINT, so registration is ignored
# signal.signal(signal.SIGTERM, _signal_handler)
# signal.signal(signal.SIGINT, _signal_handler)

# =============================================================================
# PLAYWRIGHT-SPECIFIC UTILITY FUNCTIONS
# =============================================================================

def _playwright_find_element(post, selector):
    """Playwright-specific element finder."""
    return post.locator(selector).first

def _playwright_get_attribute(element, attr):
    """Playwright-specific attribute getter."""
    return element.get_attribute(attr)

def _playwright_get_text(element):
    """Playwright-specific text getter."""
    return element.text_content()


def _log_debugging_info(post, use_playwright, context):
    """
    Log debugging information for failed element extraction.

    Args:
        post: The post element being processed
        use_playwright (bool): Whether using Playwright or BeautifulSoup
        context (str): Context for the debugging info (e.g., "title", "link")
    """
    try:
        # Show what text content is available for debugging
        if use_playwright:
            all_text = post.text_content()[:200] + "..." if len(post.text_content()) > 200 else post.text_content()
        else:
            all_text = post.get_text()[:200] + "..." if len(post.get_text()) > 200 else post.get_text()
        g_logger.info(f"Available text content for {context}: {all_text}")

        # Show available links and classes for debugging
        try:
            if use_playwright:
                # For Playwright, we need to find links within the element
                links = post.locator('a').all()
                links_info = []
                for link in links[:3]:
                    href = link.get_attribute('href')
                    links_info.append(href or 'NO_HREF')
            else:
                all_links = post.find_all('a')
                links_info = [a.get('href', 'NO_HREF') for a in all_links[:3]]
            g_logger.info(f"Available links for {context}: {links_info}")

            if not use_playwright:
                g_logger.info(f"Available classes for {context}: {post.get('class', [])}")
        except Exception as link_error:
            g_logger.debug(f"Error getting link info for {context}: {link_error}")
    except Exception as debug_e:
        g_logger.debug(f"Error during debug output for {context}: {debug_e}")


# =============================================================================
# PLAYWRIGHT-SPECIFIC EXTRACTION WRAPPERS
# =============================================================================

def extract_post_data_playwright(post, config, url, use_playwright):
    """
    Playwright-specific wrapper for extract_post_data.
    """
    return shared_extract_post_data(
        post, config, url, use_playwright,
        get_text_func=_playwright_get_text,
        find_func=_playwright_find_element,
        get_attr_func=_playwright_get_attribute
    )


def extract_post_data(post, config, url, use_playwright):
    """
    Extract post data from a web element using the provided configuration.

    Parses title, link, and other metadata from a post element using either
    Playwright Locator or BeautifulSoup object depending on the extraction method.

    Args:
        post: Playwright Locator or BeautifulSoup Tag containing post data
        config: Configuration object with selectors and settings
        url (str): Base URL for resolving relative links
        use_playwright (bool): Whether using Playwright or BeautifulSoup for extraction

    Returns:
        dict or list: Extracted post data with title, link, id, summary, and timestamps,
                     or None if extraction fails. For RSS feeds, returns a list of entries.
    """
    if use_playwright:
        return extract_post_data_playwright(post, config, url, use_playwright)
    else:
        # BeautifulSoup fallback - use shared function directly
        return shared_extract_post_data(
            post, config, url, use_playwright,
            get_text_func=None,
            find_func=None,
            get_attr_func=None
        )

# =============================================================================
# MAIN SITE FETCHING FUNCTION
# =============================================================================

def fetch_site_posts(url, user_agent):
    """
    Fetch posts from a website using Playwright browser automation.
    
    This function now delegates to the unified browser_fetch implementation
    to eliminate code duplication while maintaining Playwright-specific functionality.
    
    Args:
        url (str): URL of the site to fetch posts from
        user_agent (str): User agent string for HTTP requests
        
    Returns:
        dict: Feed-like structure with entries, metadata, and status information
    """
    # Import here to avoid circular imports
    from browser_fetch import fetch_site_posts as unified_fetch_site_posts
    return unified_fetch_site_posts(url, user_agent)