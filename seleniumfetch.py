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
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from shared import g_cs, CUSTOM_FETCH_CONFIG, g_logger

# =============================================================================
# FEATURE FLAGS
# =============================================================================

# Global flag to enable/disable date extraction feature
# Set to True to enable date extraction, False to disable
ENABLE_DATE_EXTRACTION = False

# =============================================================================
# TIMEOUT CONSTANTS
# =============================================================================

# WebDriver timeouts - for browser operations
WEBDRIVER_TIMEOUT = 10  # 30 seconds for page load and script execution

# Network operation timeouts - for HTTP requests and element waiting
NETWORK_TIMEOUT = 10  # 10 seconds for HTTP requests and WebDriverWait operations

# Thread synchronization timeout - for coordinating fetch operations
FETCH_LOCK_TIMEOUT = 30  # 30 seconds for acquiring fetch lock (longer due to thread coordination)

# Driver lifecycle timeout - for resource management
DRIVER_RECYCLE_TIMEOUT = 300  # 5 minutes - timeout for driver recycling

# Legacy constants for backward compatibility (deprecated - use above constants instead)
PAGE_LOAD_TIMEOUT = WEBDRIVER_TIMEOUT
SCRIPT_TIMEOUT = WEBDRIVER_TIMEOUT
WEBDRIVER_WAIT_TIMEOUT = NETWORK_TIMEOUT
HTTP_REQUEST_TIMEOUT = NETWORK_TIMEOUT

# =============================================================================
# SPECIAL SITE CONFIGURATIONS
# =============================================================================

# Configuration for keithcu.com RSS feed
from app_config import FetchConfig

class KeithcuRssFetchConfig(FetchConfig):
    """
    Keithcu.com RSS-specific fetch configuration.
    
    Inherits from FetchConfig with Keithcu RSS-specific settings.
    """
    def __new__(cls):
        return super().__new__(
            cls,
            needs_selenium=True,  # Using Selenium for testing purposes
            needs_tor=False,
            post_container="pre",  # RSS feeds in browser are wrapped in <pre> tags
            title_selector="title",
            link_selector="link", 
            link_attr="text",  # RSS links are text content, not href attributes
            filter_pattern="",
            use_random_user_agent=False,
            published_selector=None
        )

KEITHCU_RSS_CONFIG = KeithcuRssFetchConfig()

# =============================================================================
# WEBDRIVER CONFIGURATION AND CREATION
# =============================================================================

def create_driver(use_tor, user_agent):
    """
    Create and configure a Chrome WebDriver instance.
    
    Sets up a headless Chrome browser with appropriate options for web scraping,
    including proxy configuration for Tor if enabled and custom user agent.
    
    Args:
        use_tor (bool): Whether to use Tor proxy for connections
        user_agent (str): User agent string to use for requests
        
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    try:
        g_logger.info(f"Creating Chrome driver with Tor: {use_tor}, User-Agent: {user_agent[:50]}...")

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-agent={user_agent}")
        # Additional options to reduce resource usage
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-images")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-features=TranslateUI")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--memory-pressure-off")
        options.add_argument("--max_old_space_size=4096")  # Limit memory usage

        if use_tor:
            options.add_argument("--proxy-server=socks5://127.0.0.1:9050")

        g_logger.debug("Installing ChromeDriver...")
        service = Service(ChromeDriverManager(
            chrome_type=ChromeType.CHROMIUM).install())
        g_logger.debug("ChromeDriver installed successfully")

        g_logger.debug("Creating Chrome WebDriver instance...")
        driver = webdriver.Chrome(service=service, options=options)
        g_logger.debug("Chrome WebDriver created successfully")

        # Set timeouts to prevent hanging
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)  # 30 second page load timeout
        driver.set_script_timeout(SCRIPT_TIMEOUT)     # 30 second script timeout

        # Disable compression by setting Accept-Encoding to identity via CDP
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Accept-Encoding": "identity"}})
        g_logger.info("Chrome driver setup completed successfully")
        return driver
        
    except Exception as e:
        g_logger.error(f"Error creating Chrome driver: {e}")
        g_logger.error(f"Error type: {type(e).__name__}")
        import traceback
        g_logger.error(f"Full traceback: {traceback.format_exc()}")
        raise

# =============================================================================
# SHARED SELENIUM DRIVER MANAGEMENT
# =============================================================================

class SharedSeleniumDriver:
    """
    Thread-safe singleton manager for Selenium WebDriver instances.
    
    Provides centralized management of Chrome WebDriver instances with automatic
    cleanup, configuration validation, and thread synchronization. Implements
    lazy initialization and timeout-based driver recycling for resource efficiency.
    
    Attributes:
        _instance: Singleton driver instance
        _lock: Thread lock for instance management
        _fetch_lock: Thread lock for synchronizing fetch operations
        _timer: Timer for automatic driver cleanup
        _timeout: Timeout duration for driver recycling (seconds)
        _shutdown_initiated: Flag to prevent duplicate shutdown attempts
    """
    
    _instance = None
    _lock = threading.Lock()
    _fetch_lock = threading.Lock()  # New lock for synchronizing fetch operations
    _timer = None
    _timeout = DRIVER_RECYCLE_TIMEOUT  # 5 minutes
    _shutdown_initiated = False  # Flag to prevent duplicate shutdowns

    def __init__(self, use_tor, user_agent):
        """
        Initialize a new SharedSeleniumDriver instance.
        
        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the driver
        """
        g_logger.debug(f"Initializing SharedSeleniumDriver with Tor: {use_tor}")
        try:
            self.driver = create_driver(use_tor, user_agent)
            self.last_used = time.time()
            self.use_tor = use_tor
            self.user_agent = user_agent
            g_logger.debug("SharedSeleniumDriver initialized successfully")
        except Exception as e:
            g_logger.error(f"Error in SharedSeleniumDriver.__init__: {e}")
            raise

    @classmethod
    def get_driver(cls, use_tor, user_agent):
        """
        Get or create a WebDriver instance with the specified configuration.
        
        Returns an existing driver if configuration matches, or creates a new
        one if needed. Automatically manages driver lifecycle and cleanup.
        
        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the driver
            
        Returns:
            webdriver.Chrome: Configured Chrome WebDriver instance
        """
        with cls._lock:
            # Check if shutdown has been initiated
            if cls._shutdown_initiated:
                g_logger.info("Driver creation blocked - shutdown in progress")
                return None
                
            if cls._instance is None or not cls._is_instance_valid(cls._instance, use_tor, user_agent):
                if cls._instance:
                    cls._cleanup_instance()
                
                try:
                    g_logger.info(f"Attempting to create new SharedSeleniumDriver instance...")
                    cls._instance = SharedSeleniumDriver(use_tor, user_agent)
                    # Reset timer only when creating a new instance
                    cls._reset_timer()
                    g_logger.info(f"Created new driver instance with Tor: {use_tor}")
                except Exception as e:
                    g_logger.error(f"Error creating new driver: {e}")
                    g_logger.error(f"Error type: {type(e).__name__}")
                    import traceback
                    g_logger.error(f"Full traceback: {traceback.format_exc()}")
                    cls._instance = None
                    return None
            
            if cls._instance:
                cls._instance.last_used = time.time()
                # Only reset timer when creating a new instance, not on every access
                return cls._instance.driver
            return None

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
        Check if the current driver instance is valid for the given configuration.
        
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
                    hasattr(instance, 'driver')):
                return False
            
            # Check if driver is still responsive with timeout protection
            try:
                # Use a simple command with timeout to test if driver is alive
                instance.driver.execute_script("return document.readyState;")
                return True
            except Exception as e:
                g_logger.debug(f"Driver health check failed: {e}")
                return False

        except Exception as e:
            g_logger.error(f"Error during driver validation: {e}")
            return False

    @classmethod
    def _reset_timer(cls):
        """
        Reset the cleanup timer for automatic driver recycling.
        
        Cancels any existing timer and starts a new one to ensure
        the driver is cleaned up after the timeout period.
        """
        try:
            if cls._timer and cls._timer.is_alive():
                cls._timer.cancel()
                # Don't join the timer thread if we're on the same thread
                if threading.current_thread() != cls._timer:
                    cls._timer.join(timeout=1.0)
                    g_logger.debug("Timer joined successfully")
            g_logger.debug(f"Timer cancelled, timeout was {cls._timeout} seconds")
        except Exception as e:
            g_logger.error(f"Error cancelling timer: {e}")
        finally:
            cls._timer = None

        # Don't create new timer if shutdown is in progress
        if cls._shutdown_initiated:
            return

        try:
            cls._timer = threading.Timer(cls._timeout, cls._shutdown)
            cls._timer.daemon = True
            cls._timer.start()
            g_logger.debug(f"New timer started with {cls._timeout} second timeout")
        except Exception as e:
            g_logger.error(f"Error creating timer: {e}")
            # If timer creation fails during normal operation, schedule immediate cleanup
            if not cls._shutdown_initiated:
                cls._shutdown()

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
    def _shutdown(cls):
        """
        Shutdown and cleanup the current driver instance.
        
        Safely closes the WebDriver and resets the singleton instance
        to allow for fresh driver creation. This method is called by the timer
        for automatic driver recycling, so it resets the shutdown flag after cleanup.
        """
        g_logger.debug(f"Shutdown called - instance exists: {cls._instance is not None}")
        with cls._lock:
            # Set shutdown flag to prevent new instances during cleanup
            cls._shutdown_initiated = True

            # Clean up instance
            cls._cleanup_instance()

            # Cancel any existing timer
            try:
                if cls._timer and cls._timer.is_alive():
                    cls._timer.cancel()
                    g_logger.debug("Timer cancelled during shutdown")
                    # Don't join the timer thread if we're on the same thread
                    if threading.current_thread() != cls._timer:
                        cls._timer.join(timeout=1.0)
                        g_logger.debug("Timer joined successfully")
                    else:
                        g_logger.debug("Skipping timer join (same thread)")
            except Exception as e:
                g_logger.error(f"Error cancelling timer during shutdown: {e}")
            finally:
                cls._timer = None
                g_logger.debug("Timer set to None")

            # Reset shutdown flag to allow new driver creation after cleanup
            # This is safe because we're in a timer callback, not a true shutdown
            cls._shutdown_initiated = False
            g_logger.debug("Shutdown completed - ready for new driver creation")

    @classmethod
    def force_cleanup(cls):
        """
        Force shutdown and cleanup of all resources.
        
        This method can be called manually to ensure the WebDriver
        is properly shut down, useful for debugging or emergency cleanup.
        """
        g_logger.info("Forcing WebDriver cleanup...")
        with cls._lock:
            cls._shutdown_initiated = True

            # Clean up instance
            cls._cleanup_instance()

            # Clean up timer
            try:
                if cls._timer and cls._timer.is_alive():
                    cls._timer.cancel()
                    # Don't join the timer thread if we're on the same thread
                    if threading.current_thread() != cls._timer:
                        cls._timer.join(timeout=2.0)
                        g_logger.debug("Timer joined successfully during force cleanup")
                    else:
                        g_logger.debug("Skipping timer join during force cleanup (same thread)")
            except Exception as e:
                g_logger.error(f"Error during force cleanup timer cancellation: {e}")
            finally:
                cls._timer = None

            # Reset shutdown flag for potential future use
            cls._shutdown_initiated = False
            g_logger.info("Force cleanup completed")

    @classmethod
    def reset_for_testing(cls):
        """
        Reset the class state for testing purposes.
        """
        g_logger.info("Resetting SharedSeleniumDriver for testing...")
        cls.force_cleanup()
        cls._shutdown_initiated = False

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

def _signal_handler(signum, frame):
    """
    Signal handler for graceful shutdown.
    """
    g_logger.info(f"Received signal {signum}, cleaning up Selenium drivers...")
    cleanup_selenium_drivers()
    sys.exit(0)

def _atexit_handler():
    """
    Atexit handler for cleanup on normal program termination.
    """
    g_logger.info("Program exiting, cleaning up Selenium drivers...")
    cleanup_selenium_drivers()

# Register cleanup handlers
atexit.register(_atexit_handler)
# Signal handlers commented out since code always runs under Apache/mod_wsgi
# mod_wsgi already handles SIGTERM and SIGINT, so registration is ignored
# signal.signal(signal.SIGTERM, _signal_handler)
# signal.signal(signal.SIGINT, _signal_handler)

# =============================================================================
# COMPATIBILITY AND UTILITY CLASSES
# =============================================================================

class FeedParserDict(dict):
    """
    Mimic feedparser's FeedParserDict for compatibility.
    
    Provides attribute-style access to dictionary keys to maintain
    compatibility with feedparser's data structure expectations.
    """
    
    def __getattr__(self, key):
        """
        Get dictionary value using attribute syntax.
        
        Args:
            key (str): Dictionary key to access
            
        Returns:
            The value associated with the key
            
        Raises:
            AttributeError: If the key doesn't exist
        """
        if key in self:
            return self[key]
        raise AttributeError(f"No attribute '{key}'")

# =============================================================================
# CONTENT EXTRACTION FUNCTIONS
# =============================================================================

def parse_relative_time(time_text):
    """
    Parse relative time strings like "14 minutes ago", "2 hours ago", etc.
    
    Args:
        time_text (str): Relative time string to parse
        
    Returns:
        tuple: (published_parsed, published) where published_parsed is time.struct_time
               and published is formatted string, or (None, None) if parsing fails
    """
    import re
    from datetime import datetime, timedelta
    
    try:
        # Convert to lowercase for easier matching
        time_text = time_text.lower().strip()
        
        # Patterns for different time units
        patterns = [
            (r'(\d+)\s+minutes?\s+ago', 'minutes'),
            (r'(\d+)\s+hours?\s+ago', 'hours'),
            (r'(\d+)\s+days?\s+ago', 'days'),
            (r'(\d+)\s+weeks?\s+ago', 'weeks'),
            (r'(\d+)\s+months?\s+ago', 'months'),
            (r'(\d+)\s+years?\s+ago', 'years'),
        ]
        
        for pattern, unit in patterns:
            match = re.search(pattern, time_text)
            if match:
                value = int(match.group(1))
                
                # Calculate the actual time
                now = datetime.now()
                
                if unit == 'minutes':
                    delta = timedelta(minutes=value)
                elif unit == 'hours':
                    delta = timedelta(hours=value)
                elif unit == 'days':
                    delta = timedelta(days=value)
                elif unit == 'weeks':
                    delta = timedelta(weeks=value)
                elif unit == 'months':
                    # Approximate months as 30 days
                    delta = timedelta(days=value * 30)
                elif unit == 'years':
                    # Approximate years as 365 days
                    delta = timedelta(days=value * 365)
                
                published_time = now - delta
                published_parsed = published_time.timetuple()
                published = published_time.strftime('%a, %d %b %Y %H:%M:%S GMT')
                
                return published_parsed, published
        
        # If no pattern matches, return None
        return None, None
        
    except Exception as e:
        g_logger.error(f"Error parsing relative time '{time_text}': {e}")
        return None, None

def extract_post_data(post, config, url, use_selenium):
    """
    Extract post data from a web element using the provided configuration.
    
    Parses title, link, and other metadata from a post element using either
    Selenium WebElement or BeautifulSoup object depending on the extraction method.
    
    Args:
        post: WebElement (Selenium) or Tag (BeautifulSoup) containing post data
        config (dict): Configuration dictionary with selectors and settings
        url (str): Base URL for resolving relative links
        use_selenium (bool): Whether using Selenium or BeautifulSoup for extraction
        
    Returns:
        dict: Extracted post data with title, link, id, summary, and timestamps, or None if extraction fails
    """
    # Special handling for RSS feeds loaded through Selenium
    if use_selenium and config.post_container == "pre":
        try:
            # Get the raw XML content from the pre tag
            xml_content = post.text
            
            # Parse as XML using BeautifulSoup
            xml_soup = BeautifulSoup(xml_content, 'xml')
            items = xml_soup.find_all('item')
            
            results = []
            for item in items:
                title_tag = item.find('title')
                link_tag = item.find('link')
                
                if title_tag and link_tag:
                    title = title_tag.get_text().strip()
                    link = link_tag.get_text().strip()
                    
                    if len(title.split()) >= 2:
                        # Use current time for new articles
                        published_parsed = time.gmtime()
                        published = time.strftime('%a, %d %b %Y %H:%M:%S GMT', published_parsed)
                        
                        results.append({
                            "title": title, 
                            "link": link, 
                            "id": link, 
                            "summary": title,  # Use title as summary for RSS
                            "published": published,
                            "published_parsed": published_parsed
                        })
            
            return results if results else None
            
        except Exception as e:
            g_logger.error(f"Error parsing RSS content: {e}")
            return None
    
    # Regular processing for non-RSS content
    try:
        if use_selenium:
            title_element = post.find_element(By.CSS_SELECTOR, config.title_selector)
            title = title_element.text.strip()
        else:
            title_element = post.select_one(config.title_selector)
            if not title_element:
                g_logger.debug(f"No title element found with selector '{config.title_selector}'")
                # Show what elements are available for debugging
                try:
                    all_links = post.find_all('a')
                    g_logger.info(f"Available links in post: {[a.get('href', 'NO_HREF') for a in all_links[:3]]}")
                except:
                    pass
                return None
            title = title_element.text.strip()
    except Exception as e:
        g_logger.error(f"Error extracting title with selector '{config.title_selector}': {e}")
        # Show what text content is available for debugging
        try:
            if use_selenium:
                all_text = post.text[:200] + "..." if len(post.text) > 200 else post.text
            else:
                all_text = post.get_text()[:200] + "..." if len(post.get_text()) > 200 else post.get_text()
            g_logger.info(f"Available text content: {all_text}")
            # Also show available classes for debugging
            if not use_selenium:
                g_logger.info(f"Available classes: {post.get('class', [])}")
        except Exception as debug_e:
            g_logger.debug(f"Error during debug output: {debug_e}")
        return None
    
    if len(title.split()) < 2:
        return None
    
    try:
        if use_selenium:
            link_element = post.find_element(By.CSS_SELECTOR, config.link_selector)
            link = link_element.get_attribute(config.link_attr)
        else:
            link_element = post.select_one(config.link_selector)
            if not link_element:
                g_logger.info(f"No link element found with selector '{config.link_selector}'")
                # Show what elements are available for debugging
                try:
                    all_links = post.find_all('a')
                    g_logger.info(f"Available links in post: {[a.get('href', 'NO_HREF') for a in all_links[:3]]}")
                    # Also show available classes for debugging
                    g_logger.info(f"Available classes: {post.get('class', [])}")
                except Exception as debug_e:
                    g_logger.debug(f"Error during debug output: {debug_e}")
                return None
            # Handle RSS feeds where links are text content, not href attributes
            if config.link_attr == "text":
                link = link_element.get_text().strip()
            else:
                link = link_element.get(config.link_attr)
            if link and link.startswith('/'):
                link = urljoin(url, link)
    except Exception as e:
        g_logger.error(f"Error extracting link with selector '{config.link_selector}': {e}")
        # Show what link content is available for debugging
        try:
            if use_selenium:
                all_links = post.find_elements(By.TAG_NAME, "a")
                g_logger.info(f"Available links: {[a.get_attribute('href') for a in all_links[:3]]}")
            else:
                all_links = post.find_all('a')
                g_logger.info(f"Available links: {[a.get('href', 'NO_HREF') for a in all_links[:3]]}")
                # Also show available classes for debugging
                g_logger.info(f"Available classes: {post.get('class', [])}")
        except Exception as debug_e:
            g_logger.debug(f"Error during debug output: {debug_e}")
        return None
    
    filter_pattern = config.filter_pattern
    if filter_pattern and filter_pattern not in link:
        return None
    
    # Extract published date if feature is enabled and selector is provided
    published_parsed = None
    published = None
    
    if ENABLE_DATE_EXTRACTION and "published_selector" in config:
        try:
            if use_selenium:
                # Handle XPath selectors (starting with .// or //)
                if config.published_selector.startswith(('.//', '//')):
                    date_element = post.find_element(By.XPATH, config.published_selector)
                    date_text = date_element.text.strip()
                else:
                    # Handle CSS selectors
                    date_element = post.find_element(By.CSS_SELECTOR, config.published_selector)
                    date_text = date_element.text.strip()
            else:
                # BeautifulSoup extraction
                if config.published_selector.startswith(('.//', '//')):
                    # Convert XPath to CSS if possible, or use lxml
                    from lxml import html
                    import lxml.etree
                    # For now, fallback to current time for XPath with BeautifulSoup
                    date_text = None
                else:
                    date_element = post.select_one(config.published_selector)
                    date_text = date_element.text.strip() if date_element else None
            
            if date_text:
                published_parsed, published = parse_relative_time(date_text)
                
        except Exception as e:
            g_logger.warning(f"Failed to extract date for {url}: {e}")
            # Fallback to current time
            published_parsed = None
            published = None
    
    # Use current time if date extraction failed or is disabled
    if not published_parsed:
        published_parsed = time.gmtime()
        published = time.strftime('%a, %d %b %Y %H:%M:%S GMT', published_parsed)
    
    return {
        "title": title, 
        "link": link, 
        "id": link, 
        "summary": post.text.strip(),
        "published": published,
        "published_parsed": published_parsed
    }

# =============================================================================
# MAIN SITE FETCHING FUNCTION
# =============================================================================

def fetch_site_posts(url, user_agent):
    """
    Fetch posts from a website using appropriate method based on configuration.
    
    Determines the best method to fetch content (Selenium vs requests) based on
    site configuration and domain analysis. Handles JavaScript-rendered content
    and provides fallback mechanisms for different site types.
    
    Args:
        url (str): URL of the site to fetch posts from
        user_agent (str): User agent string for HTTP requests
        
    Returns:
        dict: Feed-like structure with entries, metadata, and status information
    """
    parsed = urlparse(url)
    # Extract base domain (e.g., bandcamp.com from rocksteadydisco.bandcamp.com)
    domain_parts = parsed.netloc.split('.')
    if len(domain_parts) > 2:
        # Handle subdomains like www.example.com or sub.example.co.uk
        # This logic might need adjustment for complex TLDs like .co.uk
        # For now, assume simple cases like example.com or sub.example.com
        base_domain = '.'.join(domain_parts[-2:])
    else:
        base_domain = parsed.netloc

    # Always try base domain first, then fallback to netloc (for legacy configs)
    config = CUSTOM_FETCH_CONFIG.get(base_domain)
    if not config:
        config = CUSTOM_FETCH_CONFIG.get(parsed.netloc)
    
    # Special case for keithcu.com RSS feed
    if not config and "keithcu.com" in base_domain:
        config = KEITHCU_RSS_CONFIG
    
    if not config:
        g_logger.info(f"Configuration for base domain '{base_domain}' (from URL '{url}') not found.")
        return {
            'entries': [],
            'etag': "",
            'modified': datetime.now(timezone.utc),
            'feed': {'title': url, 'link': url, 'description': ''},
            'href': url,
            'status': 404
        }

    etag = ""
    modified = datetime.now(timezone.utc)
    entries = []
    status = 200

    if config.needs_selenium:
        if config.use_random_user_agent:
            # Use random user agent to avoid detection (reuse existing REDDIT_USER_AGENT)
            user_agent = g_cs.get("REDDIT_USER_AGENT")

        # Acquire the fetch lock before starting the fetch operation
        lock_acquired = False
        try:
            lock_acquired = SharedSeleniumDriver.acquire_fetch_lock()
            if not lock_acquired:
                g_logger.warning(f"Failed to acquire fetch lock for {url}, skipping...")
                status = 503
                return {
                    'entries': [],
                    'etag': etag,
                    'modified': modified,
                    'feed': {'title': url, 'link': url, 'description': ''},
                    'href': url,
                    'status': status
                }

            driver = SharedSeleniumDriver.get_driver(config.needs_tor, user_agent)
            if not driver:
                g_logger.error(f"Failed to get driver for {url}")
                status = 503
                return {
                    'entries': [],
                    'etag': etag,
                    'modified': modified,
                    'feed': {'title': url, 'link': url, 'description': ''},
                    'href': url,
                    'status': status
                }
                
            try:
                driver.get(url)
                if base_domain == "reddit.com":
                    pass
                else:
                    try:
                        WebDriverWait(driver, WEBDRIVER_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, config.post_container)))
                    except Exception as wait_error:
                        g_logger.warning(f"Timeout waiting for elements on {url}: {wait_error}")
                        # Continue anyway, might still find some content

                g_logger.info(f"Some content loaded for {url} with agent: {user_agent}")
                posts = driver.find_elements(By.CSS_SELECTOR, config.post_container)
                if not posts:
                    snippet = driver.page_source[:500]
                    g_logger.info(f"No posts found. Page source snippet: {snippet}")
                    status = 204  # No content
                else:
                    for post in posts:
                        try:
                            entry_data = extract_post_data(post, config, url, use_selenium=True)
                            if entry_data:
                                # Handle both single entry and list of entries
                                if isinstance(entry_data, list):
                                    entries.extend(entry_data)
                                else:
                                    entries.append(entry_data)
                        except Exception as e:
                            g_logger.error(f"Error extracting post data: {e}")
                            continue
                            
            except Exception as e:
                g_logger.error(f"Error on {url}: {e}")
                status = 500
                
        finally:
            # Always release the fetch lock, even if an error occurs
            if lock_acquired:
                SharedSeleniumDriver.release_fetch_lock()
    else:
        g_logger.info(f"Fetching {base_domain} using requests (no Selenium)")

        # Handle user agent for requests
        request_headers = {}
        if config.use_random_user_agent:
            request_headers['User-Agent'] = g_cs.get("REDDIT_USER_AGENT")
        else:
            request_headers['User-Agent'] = user_agent

        try:
            response = requests.get(url, timeout=HTTP_REQUEST_TIMEOUT, headers=request_headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            posts = soup.select(config.post_container)
            for post in posts:
                try:
                    entry = extract_post_data(post, config, url, use_selenium=False)
                    if entry:
                        entries.append(entry)
                except Exception as e:
                    g_logger.error(f"Error extracting post data: {e}")
                    continue

        except Exception as e:
            g_logger.error(f"Error fetching {base_domain} with requests: {e}")
            status = 500

    result = {
        'entries': entries,
        'etag': etag,
        'modified': modified,
        'feed': {
            'title': url,
            'link': url,
            'description': ''
        },
        'href': url,
        'status': status
    }

    return result