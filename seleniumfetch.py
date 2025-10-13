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
        
        # Log current Chrome processes before creating new driver
        log_chrome_processes()

        # Use shared browser creation logic
        chrome_args = get_common_chrome_options(use_tor, user_agent)
        
        options = Options()
        for arg in chrome_args:
            options.add_argument(arg)
        
        # Add Selenium-specific options
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        # NOTE: We DON'T disable useAutomationExtension as that would break Selenium!

        g_logger.info("Installing ChromeDriver...")
        service = Service(ChromeDriverManager(
            chrome_type=ChromeType.CHROMIUM).install())
        g_logger.info("ChromeDriver installed successfully")

        g_logger.info("Creating Chrome WebDriver instance...")
        driver = webdriver.Chrome(service=service, options=options)
        g_logger.info("Chrome WebDriver created successfully")

        # Set timeouts to prevent hanging
        driver.set_page_load_timeout(BROWSER_TIMEOUT)
        driver.set_script_timeout(BROWSER_TIMEOUT)

        # Log the process ID of the created driver
        try:
            if hasattr(driver, 'service') and hasattr(driver.service, 'process'):
                process_id = driver.service.process.pid if driver.service.process else 'unknown'
                g_logger.info(f"Chrome driver created with process ID: {process_id}")
            else:
                g_logger.warning("Could not determine Chrome driver process ID")
        except Exception as pid_error:
            g_logger.warning(f"Error getting driver process ID: {pid_error}")

        g_logger.info("Chrome driver setup completed successfully")
        
        # Log Chrome processes after creation to verify
        g_logger.info("Chrome processes after driver creation:")
        log_chrome_processes()
        
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
    _request_count = 0  # Track number of requests to force cleanup

    def __init__(self, use_tor, user_agent):
        """
        Initialize a new SharedSeleniumDriver instance.
        
        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the driver
        """
        super().__init__(use_tor, user_agent)
        g_logger.info(f"Initializing SharedSeleniumDriver with Tor: {use_tor}, User-Agent: {user_agent[:50]}...")
        try:
            self.driver = create_driver(use_tor, user_agent)
            self._process_id = self._get_driver_process_id()
            g_logger.info(f"SharedSeleniumDriver initialized successfully with process ID: {self._process_id}")
        except Exception as e:
            g_logger.error(f"Error in SharedSeleniumDriver.__init__: {e}")
            raise

    def _get_driver_process_id(self):
        """Get the process ID of the Chrome driver for monitoring."""
        try:
            if hasattr(self.driver, 'service') and hasattr(self.driver.service, 'process'):
                process = self.driver.service.process
                if process:
                    return process.pid
        except Exception as e:
            g_logger.debug(f"Could not get driver process ID: {e}")
        return None

    @classmethod
    def get_driver(cls, use_tor, user_agent):
        """
        Get or create a shared WebDriver instance.

        Returns the singleton driver instance, creating it if needed.
        Note: Cleanup is now handled after each fetch operation, not here.

        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the driver

        Returns:
            webdriver.Chrome: Configured Chrome WebDriver instance
        """
        with cls._lock:
            cls._request_count += 1
            g_logger.info(f"Driver request #{cls._request_count} - Tor: {use_tor}")
            
            # Create instance if needed or invalid
            if cls._instance is None or not cls._is_instance_valid(cls._instance, use_tor, user_agent):
                if cls._instance:
                    g_logger.info("Cleaning up invalid driver instance")
                    cls._cleanup_instance()
                try:
                    cls._instance = SharedSeleniumDriver(use_tor, user_agent)
                    g_logger.info(f"Created new driver instance with Tor: {use_tor}, Process ID: {cls._instance._process_id}")
                except Exception as e:
                    g_logger.error(f"Error creating driver: {e}")
                    cls._instance = None
                    return None

            cls._instance.last_used = time.time()
            g_logger.debug(f"Returning driver instance, last used: {cls._instance.last_used}")
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
                g_logger.debug(f"Driver health check passed for process ID: {getattr(self, '_process_id', 'unknown')}")
                return True
            g_logger.warning("Driver health check failed: no driver instance")
            return False
        except Exception as e:
            g_logger.warning(f"Driver health check failed: {e}")
            return False

    @classmethod
    def _cleanup_instance(cls):
        """
        Clean up the current driver instance safely with enhanced logging and process monitoring.
        """
        if cls._instance:
            process_id = getattr(cls._instance, '_process_id', 'unknown')
            g_logger.info(f"Starting cleanup of driver instance with process ID: {process_id}")
            
            try:
                # Try to quit the driver gracefully
                cls._instance.driver.quit()
                g_logger.info(f"WebDriver quit successfully for process ID: {process_id}")
                
                # Verify process is actually terminated
                cls._verify_process_cleanup(process_id)
                
            except Exception as e:
                g_logger.error(f"Error quitting WebDriver for process ID {process_id}: {e}")
                try:
                    # Fallback: try to close the driver
                    cls._instance.driver.close()
                    g_logger.info(f"WebDriver closed successfully for process ID: {process_id}")
                except Exception as e2:
                    g_logger.error(f"Error closing WebDriver for process ID {process_id}: {e2}")
                    # Last resort: try to kill the process
                    cls._force_kill_process(process_id)
            finally:
                cls._instance = None
                g_logger.info(f"Driver instance cleanup completed, instance set to None")
        else:
            g_logger.debug("No driver instance to cleanup")

    @classmethod
    def _verify_process_cleanup(cls, process_id):
        """Verify that the driver process has been properly terminated."""
        if process_id == 'unknown' or not psutil:
            return
            
        try:
            process = psutil.Process(process_id)
            if process.is_running():
                g_logger.warning(f"Driver process {process_id} is still running after quit(), attempting force kill")
                cls._force_kill_process(process_id)
            else:
                g_logger.info(f"Driver process {process_id} successfully terminated")
        except psutil.NoSuchProcess:
            g_logger.info(f"Driver process {process_id} already terminated")
        except Exception as e:
            g_logger.error(f"Error verifying process cleanup for {process_id}: {e}")

    @classmethod
    def _force_kill_process(cls, process_id):
        """Force kill a driver process if it's still running."""
        if process_id == 'unknown' or not psutil:
            return
            
        try:
            process = psutil.Process(process_id)
            if process.is_running():
                g_logger.warning(f"Force killing driver process {process_id}")
                process.terminate()
                time.sleep(2)
                if process.is_running():
                    g_logger.warning(f"Process {process_id} still running, using kill()")
                    process.kill()
                    time.sleep(1)
                g_logger.info(f"Driver process {process_id} force killed")
            else:
                g_logger.info(f"Driver process {process_id} already terminated")
        except psutil.NoSuchProcess:
            g_logger.info(f"Driver process {process_id} already terminated")
        except Exception as e:
            g_logger.error(f"Error force killing process {process_id}: {e}")

    @classmethod
    def _cleanup_all_instances(cls):
        """
        Clean up all driver instances safely.
        """
        g_logger.info("Cleaning up all Selenium driver instances")
        cls._cleanup_instance()
        g_logger.info("All Selenium driver instances cleaned up")

    @classmethod
    def force_cleanup_after_request(cls):
        """
        Force cleanup of the current driver instance after a request to prevent zombie processes.
        This should be called after each fetch operation.
        """
        g_logger.info("Forcing driver cleanup after request to prevent zombie processes")
        with cls._lock:
            if cls._instance:
                g_logger.info(f"Cleaning up driver after request (request count: {cls._request_count})")
                cls._cleanup_instance()
                cls._request_count = 0  # Reset counter after cleanup
                g_logger.info("Driver cleanup completed, request count reset to 0")
            else:
                g_logger.debug("No driver instance to cleanup after request")

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

def log_chrome_processes():
    """
    Log information about current Chrome processes to help debug zombie process issues.
    """
    if not psutil:
        g_logger.warning("psutil not available, cannot monitor Chrome processes")
        return
    
    try:
        chrome_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'status']):
            try:
                if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                    chrome_processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'status': proc.info['status'],
                        'cmdline': ' '.join(proc.info['cmdline'][:3]) if proc.info['cmdline'] else 'N/A'
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if chrome_processes:
            g_logger.info(f"Found {len(chrome_processes)} Chrome processes:")
            for proc in chrome_processes:
                g_logger.info(f"  PID {proc['pid']}: {proc['name']} ({proc['status']}) - {proc['cmdline']}")
        else:
            g_logger.info("No Chrome processes found")
            
    except Exception as e:
        g_logger.error(f"Error monitoring Chrome processes: {e}")

def force_cleanup_all_chrome_processes():
    """
    Force cleanup of all Chrome processes that might be zombie processes.
    This is a last resort function for debugging zombie process issues.
    """
    if not psutil:
        g_logger.warning("psutil not available, cannot force cleanup Chrome processes")
        return
    
    g_logger.warning("Force cleaning up all Chrome processes - this may affect other applications!")
    
    try:
        killed_count = 0
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                    # Check if it's a ChromeDriver process (usually has --test-type in cmdline)
                    cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                    if '--test-type' in cmdline or 'chromedriver' in cmdline.lower():
                        g_logger.warning(f"Force killing Chrome process PID {proc.info['pid']}: {cmdline}")
                        proc.kill()
                        killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        g_logger.warning(f"Force killed {killed_count} Chrome processes")
        
    except Exception as e:
        g_logger.error(f"Error force cleaning Chrome processes: {e}")

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
    Includes automatic cleanup after each request to prevent zombie processes.
    
    Args:
        url (str): URL of the site to fetch posts from
        user_agent (str): User agent string for HTTP requests
        
    Returns:
        dict: Feed-like structure with entries, metadata, and status information
    """
    g_logger.info(f"Starting Selenium fetch for URL: {url}")
    
    try:
        # Import here to avoid circular imports
        from browser_fetch import fetch_site_posts as unified_fetch_site_posts
        g_logger.info(f"Calling unified fetch_site_posts for URL: {url}")
        result = unified_fetch_site_posts(url, user_agent)
        g_logger.info(f"Unified fetch_site_posts completed for URL: {url}")
        
        # Force cleanup after each request to prevent zombie processes
        g_logger.info(f"Selenium fetch completed for URL: {url}, forcing cleanup")
        SharedSeleniumDriver.force_cleanup_after_request()
        g_logger.info(f"Cleanup completed for URL: {url}")
        
        return result
        
    except Exception as e:
        g_logger.error(f"Error during Selenium fetch for {url}: {e}")
        # Ensure cleanup even on error
        try:
            g_logger.info(f"Attempting cleanup after error for URL: {url}")
            SharedSeleniumDriver.force_cleanup_after_request()
            g_logger.info(f"Cleanup after error completed for URL: {url}")
        except Exception as cleanup_error:
            g_logger.error(f"Error during cleanup after fetch error: {cleanup_error}")
        
        # Return empty result on error
        return {
            'entries': [],
            'etag': '',
            'modified': None,
            'feed': {'title': url, 'link': url, 'description': ''},
            'href': url,
            'status': 500
        }