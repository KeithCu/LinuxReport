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

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

try:
    import psutil
except ImportError:
    psutil = None

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from shared import g_logger
from browser_fetch import (
    BROWSER_TIMEOUT, BROWSER_WAIT_TIMEOUT,
    SharedBrowserManager, get_common_context_options, BrowserErrorHandler,
    PlaywrightElementExtractor, BrowserUtils
)

# =============================================================================
# TIMEOUT CONSTANTS
# =============================================================================

# Note: All timeout constants are now imported from browser_fetch
# to maintain consistency across all browser modules

# =============================================================================
# PLAYWRIGHT BROWSER CONFIGURATION AND CREATION
# =============================================================================

def _safe_playwright_start():
    """
    Safely start Playwright with logging isolation to avoid Apache/mod_wsgi conflicts.
    
    Returns:
        Playwright instance or None if initialization fails
    """
    try:
        # Temporarily suppress Playwright's logging to avoid Apache/mod_wsgi conflicts
        import logging
        
        # Suppress Playwright's internal logging
        playwright_logger = logging.getLogger("playwright")
        original_level = playwright_logger.level
        playwright_logger.setLevel(logging.CRITICAL)
        
        try:
            playwright_instance = sync_playwright().start()
            return playwright_instance
        finally:
            # Restore original logging level
            playwright_logger.setLevel(original_level)
                
    except Exception as e:
        g_logger.error(f"Error starting Playwright safely: {e}")
        return None

def create_browser_context(playwright, use_tor, user_agent):
    """
    Create and configure a Playwright browser context using shared browser creation logic.

    Args:
        playwright: Playwright instance
        use_tor (bool): Whether to use Tor proxy for connections
        user_agent (str): User agent string to use for requests

    Returns:
        tuple: (browser, context) - Configured Playwright browser and context instances
    """
    try:
        g_logger.info(f"Creating Playwright browser with Tor: {use_tor}, User-Agent: {user_agent[:50]}...")

        # Use shared browser creation logic
        from browser_fetch import get_common_browser_args
        args = get_common_browser_args(use_tor, user_agent)

        # Launch browser with shared options
        browser_options = {
            "headless": True,
            "args": args['anti_detection'] + args['performance']
        }

        browser = playwright.chromium.launch(**browser_options)

        # Use shared context options
        context_options = get_common_context_options(use_tor, user_agent)
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

class SharedPlaywrightBrowser(SharedBrowserManager):
    """
    Thread-safe manager for Playwright browser contexts.

    Uses thread-local storage to avoid Playwright's threading limitations.
    Each thread gets its own browser instance to prevent "Cannot switch to a different thread" errors.
    Inherits from SharedBrowserManager to use shared lock management and cleanup operations.
    """

    _instances = {}  # Thread-local instances
    _lock = threading.Lock()

    def __init__(self, use_tor, user_agent):
        """
        Initialize a new SharedPlaywrightBrowser instance.

        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the browser context
        """
        super().__init__(use_tor, user_agent)
        g_logger.debug(f"Initializing SharedPlaywrightBrowser with Tor: {use_tor}")
        try:
            # Use safe Playwright initialization to avoid Apache/mod_wsgi conflicts
            self.playwright = _safe_playwright_start()
            if not self.playwright:
                raise Exception("Failed to start Playwright safely")
                
            self.browser, self.context = create_browser_context(self.playwright, use_tor, user_agent)
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

    def is_valid(self):
        """
        Check if the Playwright context is still valid and responsive.
        
        Returns:
            bool: True if context is valid, False otherwise
        """
        try:
            if hasattr(self, 'context') and self.context:
                # Simple test to check if context is alive
                pages = self.context.pages
                return True
            return False
        except Exception as e:
            g_logger.debug(f"Context health check failed: {e}")
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
    def _cleanup_all_instances(cls):
        """
        Clean up all thread-local browser instances safely.
        """
        for thread_id in list(cls._instances.keys()):
            cls._cleanup_thread_instance(thread_id)

    @classmethod
    def reset_for_testing(cls):
        """
        Reset all thread-local instances for testing purposes.
        This method is only used in test environments.
        """
        with cls._lock:
            cls._cleanup_all_instances()
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

# =============================================================================
# PLAYWRIGHT-SPECIFIC UTILITY FUNCTIONS
# =============================================================================

def extract_post_data_playwright(post, config, url, use_playwright):
    """
    Playwright-specific wrapper for extract_post_data using shared element extractor.
    """
    # Import here to avoid circular imports
    from browser_fetch import extract_post_data as shared_extract_post_data
    
    extractor = PlaywrightElementExtractor()
    return shared_extract_post_data(
        post, config, url, use_playwright,
        get_text_func=extractor.get_text,
        find_func=extractor.find_element,
        get_attr_func=extractor.get_attribute
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
        from browser_fetch import extract_post_data as shared_extract_post_data
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