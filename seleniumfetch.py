"""
seleniumfetch.py

Selenium-based web scraping system for JavaScript-rendered content and dynamic sites.
Provides functions to fetch and parse posts from sites requiring JavaScript rendering
or special handling, using Selenium WebDriver and BeautifulSoup. Includes site-specific
configurations, shared driver management, and thread-safe operations.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import time
import threading
import atexit
import signal
import sys

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

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
    SharedBrowserManager, get_common_chrome_options, BrowserErrorHandler,
    SeleniumElementExtractor, BrowserUtils
)

# =============================================================================
# TIMEOUT CONSTANTS
# =============================================================================

# Driver lifecycle timeout - for resource management
DRIVER_RECYCLE_TIMEOUT = 300  # 5 minutes - timeout for driver recycling

# Note: All other timeout constants are now imported from browser_fetch
# to maintain consistency across all browser modules

# =============================================================================
# WEBDRIVER CONFIGURATION AND CREATION
# =============================================================================

def create_driver(use_tor, user_agent):
    """
    Create and configure a Chrome WebDriver instance using shared browser creation logic.
    
    Args:
        use_tor (bool): Whether to use Tor proxy for connections
        user_agent (str): User agent string to use for requests
        
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    try:
        g_logger.info(f"Creating Chrome driver with Tor: {use_tor}, User-Agent: {user_agent[:50]}...")

        # Use shared browser creation logic
        chrome_args = get_common_chrome_options(use_tor, user_agent)
        
        options = Options()
        for arg in chrome_args:
            options.add_argument(arg)
        
        # Add Selenium-specific options
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        # NOTE: We DON'T disable useAutomationExtension as that would break Selenium!

        g_logger.debug("Installing ChromeDriver...")
        service = Service(ChromeDriverManager(
            chrome_type=ChromeType.CHROMIUM).install())
        g_logger.debug("ChromeDriver installed successfully")

        g_logger.debug("Creating Chrome WebDriver instance...")
        driver = webdriver.Chrome(service=service, options=options)
        g_logger.debug("Chrome WebDriver created successfully")

        # Set timeouts to prevent hanging
        driver.set_page_load_timeout(BROWSER_TIMEOUT)
        driver.set_script_timeout(BROWSER_TIMEOUT)

        g_logger.info("Chrome driver setup completed successfully")
        return driver
        
    except (WebDriverException, OSError, ValueError) as e:
        g_logger.error(f"Error creating Chrome driver: {e}")
        g_logger.error(f"Error type: {type(e).__name__}")
        import traceback
        g_logger.error(f"Full traceback: {traceback.format_exc()}")
        raise

# =============================================================================
# SHARED SELENIUM DRIVER MANAGEMENT
# =============================================================================

class SharedSeleniumDriver(SharedBrowserManager):
    """
    Thread-safe singleton manager for Selenium WebDriver instances.
    
    Inherits from SharedBrowserManager to use shared lock management,
    instance validation, and cleanup operations.
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self, use_tor, user_agent):
        """
        Initialize a new SharedSeleniumDriver instance.
        
        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the driver
        """
        super().__init__(use_tor, user_agent)
        g_logger.debug(f"Initializing SharedSeleniumDriver with Tor: {use_tor}")
        try:
            self.driver = create_driver(use_tor, user_agent)
            g_logger.debug("SharedSeleniumDriver initialized successfully")
        except Exception as e:
            g_logger.error(f"Error in SharedSeleniumDriver.__init__: {e}")
            raise

    @classmethod
    def get_driver(cls, use_tor, user_agent):
        """
        Get or create a shared WebDriver instance.

        Returns the singleton driver instance, creating it if needed.

        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the driver

        Returns:
            webdriver.Chrome: Configured Chrome WebDriver instance
        """
        with cls._lock:
            # Create instance if needed or invalid
            if cls._instance is None or not cls._is_instance_valid(cls._instance, use_tor, user_agent):
                if cls._instance:
                    cls._cleanup_instance()
                try:
                    cls._instance = SharedSeleniumDriver(use_tor, user_agent)
                    g_logger.info(f"Created new driver instance with Tor: {use_tor}")
                except Exception as e:
                    g_logger.error(f"Error creating driver: {e}")
                    cls._instance = None
                    return None

            cls._instance.last_used = time.time()
            return cls._instance.driver

    def is_valid(self):
        """
        Check if the Selenium driver is still valid and responsive.
        
        Returns:
            bool: True if driver is valid, False otherwise
        """
        try:
            if hasattr(self, 'driver') and self.driver:
                # Use a simple command with timeout to test if driver is alive
                self.driver.execute_script("return document.readyState;")
                return True
            return False
        except Exception as e:
            g_logger.debug(f"Driver health check failed: {e}")
            return False

    @classmethod
    def _cleanup_instance(cls):
        """
        Clean up the current driver instance safely.
        """
        if cls._instance:
            try:
                # Try to quit the driver gracefully
                cls._instance.driver.quit()
                g_logger.debug("WebDriver quit successfully")
            except Exception as e:
                g_logger.error(f"Error quitting WebDriver: {e}")
                try:
                    # Fallback: try to close the driver
                    cls._instance.driver.close()
                    g_logger.debug("WebDriver closed successfully")
                except Exception as e2:
                    g_logger.error(f"Error closing WebDriver: {e2}")
                    # Last resort: try to kill the process
                    try:
                        if hasattr(cls._instance.driver, 'service') and hasattr(cls._instance.driver.service, 'process'):
                            process = cls._instance.driver.service.process
                            if process and process.poll() is None:
                                process.terminate()
                                time.sleep(1)
                                if process.poll() is None:
                                    process.kill()
                                g_logger.debug("WebDriver process terminated")
                    except Exception as e3:
                        g_logger.error(f"Error terminating WebDriver process: {e3}")
            finally:
                cls._instance = None
                g_logger.debug("Instance set to None")

    @classmethod
    def _cleanup_all_instances(cls):
        """
        Clean up all driver instances safely.
        """
        cls._cleanup_instance()

# =============================================================================
# GLOBAL CLEANUP FUNCTION
# =============================================================================

def cleanup_selenium_drivers():
    """
    Global cleanup function to ensure all Selenium drivers are properly shut down.
    
    This function can be called from other modules or during application shutdown
    to ensure no WebDriver instances are left running.
    """
    g_logger.info("Cleaning up all Selenium drivers...")
    SharedSeleniumDriver.force_cleanup()

# =============================================================================
# SELENIUM-SPECIFIC UTILITY FUNCTIONS
# =============================================================================

def extract_post_data_selenium(post, config, url, use_selenium):
    """
    Selenium-specific wrapper for extract_post_data using shared element extractor.
    """
    # Import here to avoid circular imports
    from browser_fetch import extract_post_data as shared_extract_post_data
    
    extractor = SeleniumElementExtractor()
    return shared_extract_post_data(
        post, config, url, use_selenium,
        get_text_func=extractor.get_text,
        find_func=extractor.find_element,
        get_attr_func=extractor.get_attribute
    )

def extract_post_data(post, config, url, use_selenium):
    """
    Extract post data from a web element using the provided configuration.

    Parses title, link, and other metadata from a post element using either
    Selenium WebElement or BeautifulSoup object depending on the extraction method.

    Args:
        post: WebElement (Selenium) or Tag (BeautifulSoup) containing post data
        config: Configuration object with selectors and settings
        url (str): Base URL for resolving relative links
        use_selenium (bool): Whether using Selenium or BeautifulSoup for extraction

    Returns:
        dict or list: Extracted post data with title, link, id, summary, and timestamps,
                     or None if extraction fails. For RSS feeds, returns a list of entries.
    """
    if use_selenium:
        return extract_post_data_selenium(post, config, url, use_selenium)
    else:
        # BeautifulSoup fallback - use shared function directly
        from browser_fetch import extract_post_data as shared_extract_post_data
        return shared_extract_post_data(
            post, config, url, use_selenium,
            get_text_func=None,
            find_func=None,
            get_attr_func=None
        )

# =============================================================================
# MAIN SITE FETCHING FUNCTION
# =============================================================================

def fetch_site_posts(url, user_agent):
    """
    Fetch posts from a website using Selenium WebDriver.
    
    This function now delegates to the unified browser_fetch implementation
    to eliminate code duplication while maintaining Selenium-specific functionality.
    
    Args:
        url (str): URL of the site to fetch posts from
        user_agent (str): User agent string for HTTP requests
        
    Returns:
        dict: Feed-like structure with entries, metadata, and status information
    """
    # Import here to avoid circular imports
    from browser_fetch import fetch_site_posts as unified_fetch_site_posts
    return unified_fetch_site_posts(url, user_agent)