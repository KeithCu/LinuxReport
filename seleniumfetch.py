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
import os
import time
import threading
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
from shared import g_cs, CUSTOM_FETCH_CONFIG

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
KEITHCU_RSS_CONFIG = {
    "needs_selenium": True,  # RSS feeds don't need Selenium
    "needs_tor": False,
    "post_container": "item",  # RSS items are wrapped in <item> tags
    "title_selector": "title",
    "link_selector": "link", 
    "link_attr": "text",  # RSS links are text content, not href attributes
    "filter_pattern": ""
}

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

    service = Service(ChromeDriverManager(
        chrome_type=ChromeType.CHROMIUM).install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Set timeouts to prevent hanging
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)  # 30 second page load timeout
    driver.set_script_timeout(SCRIPT_TIMEOUT)     # 30 second script timeout
    
    # Disable compression by setting Accept-Encoding to identity via CDP
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Accept-Encoding": "identity"}})
    return driver

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
    """
    
    _instance = None
    _lock = threading.Lock()
    _fetch_lock = threading.Lock()  # New lock for synchronizing fetch operations
    _timer = None
    _timeout = DRIVER_RECYCLE_TIMEOUT  # 5 minutes

    def __init__(self, use_tor, user_agent):
        """
        Initialize a new SharedSeleniumDriver instance.
        
        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the driver
        """
        self.driver = create_driver(use_tor, user_agent)
        self.last_used = time.time()
        self.use_tor = use_tor
        self.user_agent = user_agent

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
            if cls._instance is None or not cls._instance._is_valid(use_tor, user_agent):
                if cls._instance:
                    try:
                        cls._instance.driver.quit()
                    except Exception as e:
                        print(f"Error quitting old driver: {e}")
                        try:
                            cls._instance.driver.close()
                        except Exception as e2:
                            print(f"Error closing old driver: {e2}")
                    finally:
                        cls._instance = None
                
                try:
                    cls._instance = SharedSeleniumDriver(use_tor, user_agent)
                except Exception as e:
                    print(f"Error creating new driver: {e}")
                    return None
            
            if cls._instance:
                cls._instance.last_used = time.time()
                cls._reset_timer()
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
            print(f"Error acquiring fetch lock: {e}")
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
    def _is_valid(cls, use_tor, user_agent):
        """
        Check if the current driver instance is valid for the given configuration.
        
        Args:
            use_tor (bool): Required Tor configuration
            user_agent (str): Required user agent string
            
        Returns:
            bool: True if current instance matches configuration
        """
        # Only reuse if config matches
        if not (cls._instance and
                cls._instance.use_tor == use_tor and
                cls._instance.user_agent == user_agent and
                hasattr(cls._instance, 'driver')):
            return False
        
        # Check if driver is still responsive
        try:
            # Try to get current URL to test if driver is alive
            cls._instance.driver.current_url
            return True
        except Exception as e:
            print(f"Driver health check failed: {e}")
            return False

    @classmethod
    def _reset_timer(cls):
        """
        Reset the cleanup timer for automatic driver recycling.
        
        Cancels any existing timer and starts a new one to ensure
        the driver is cleaned up after the timeout period.
        """
        try:
            if cls._timer:
                cls._timer.cancel()
                cls._timer = None
                print(f"Timer cancelled, timeout was {cls._timeout} seconds")
        except Exception as e:
            print(f"Error cancelling timer: {e}")
        
        try:
            cls._timer = threading.Timer(cls._timeout, cls._shutdown)
            cls._timer.daemon = True
            cls._timer.start()
            print(f"New timer started with {cls._timeout} second timeout")
        except Exception as e:
            print(f"Error creating timer: {e}")
            # If timer creation fails, try to shutdown immediately
            cls._shutdown()

    @classmethod
    def _shutdown(cls):
        """
        Shutdown and cleanup the current driver instance.
        
        Safely closes the WebDriver and resets the singleton instance
        to allow for fresh driver creation.
        """
        print(f"Shutdown called - instance exists: {cls._instance is not None}")
        with cls._lock:
            if cls._instance:
                try:
                    # Close all windows and quit the driver
                    cls._instance.driver.quit()
                    print("WebDriver quit successfully")
                except Exception as e:
                    print(f"Error quitting WebDriver: {e}")
                    try:
                        # Fallback: try to close the driver
                        cls._instance.driver.close()
                        print("WebDriver closed successfully")
                    except Exception as e2:
                        print(f"Error closing WebDriver: {e2}")
                finally:
                    cls._instance = None
                    print("Instance set to None")
            
            # Cancel any existing timer
            try:
                if cls._timer:
                    cls._timer.cancel()
                    print("Timer cancelled during shutdown")
            except Exception as e:
                print(f"Error cancelling timer during shutdown: {e}")
            finally:
                cls._timer = None
                print("Timer set to None")

    @classmethod
    def force_cleanup(cls):
        """
        Shutdown and cleanup the current driver instance.
        
        This method can be called manually to ensure the WebDriver
        is properly shut down, useful for debugging or emergency cleanup.
        """
        print("Forcing WebDriver cleanup...")
        cls._shutdown()

# =============================================================================
# GLOBAL CLEANUP FUNCTION
# =============================================================================

def cleanup_selenium_drivers():
    """
    Global cleanup function to ensure all Selenium drivers are properly shut down.
    
    This function can be called from other modules or during application shutdown
    to ensure no WebDriver instances are left running.
    """
    print("Cleaning up all Selenium drivers...")
    SharedSeleniumDriver.force_cleanup()

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
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"No attribute '{key}'")

# =============================================================================
# CONTENT EXTRACTION FUNCTIONS
# =============================================================================

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
        dict: Extracted post data with title, link, id, and summary, or None if extraction fails
    """
    try:
        if use_selenium:
            title_element = post.find_element(By.CSS_SELECTOR, config["title_selector"])
            title = title_element.text.strip()
        else:
            title_element = post.select_one(config["title_selector"])
            if not title_element:
                return None
            title = title_element.text.strip()
    except Exception:
        return None
    
    if len(title.split()) < 2:
        return None
    
    try:
        if use_selenium:
            link_element = post.find_element(By.CSS_SELECTOR, config["link_selector"])
            link = link_element.get_attribute(config["link_attr"])
        else:
            link_element = post.select_one(config["link_selector"])
            if not link_element:
                return None
            # Handle RSS feeds where links are text content, not href attributes
            if config["link_attr"] == "text":
                link = link_element.get_text().strip()
            else:
                link = link_element.get(config["link_attr"])
            if link and link.startswith('/'):
                link = urljoin(url, link)
    except Exception:
        return None
    
    filter_pattern = config.get("filter_pattern", "")
    if filter_pattern and filter_pattern not in link:
        return None
    
    return {"title": title, "link": link, "id": link, "summary": post.text.strip()}

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
        print(f"Configuration for base domain '{base_domain}' (from URL '{url}') not found.")
        return []

    etag = ""
    modified = datetime.now(timezone.utc)
    entries = []

    if config.get("needs_selenium", True):
        if "reddit" in base_domain:
            user_agent = g_cs.get("REDDIT_USER_AGENT")
        
        # Acquire the fetch lock before starting the fetch operation
        if not SharedSeleniumDriver.acquire_fetch_lock():
            print(f"Failed to acquire fetch lock for {url}, skipping...")
            return []
        
        try:
            driver = SharedSeleniumDriver.get_driver(config["needs_tor"], user_agent)
            if not driver:
                print(f"Failed to get driver for {url}")
                return []
            try:
                driver.get(url)
                if base_domain == "reddit.com":
                    pass
                else:
                    try:
                        WebDriverWait(driver, WEBDRIVER_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, config["post_container"])))
                    except Exception as wait_error:
                        print(f"Timeout waiting for elements on {url}: {wait_error}")
                        # Continue anyway, might still find some content
                
                print(f"Some content loaded for {url} with agent: {user_agent}")
                posts = driver.find_elements(By.CSS_SELECTOR, config["post_container"])
                if not posts:
                    snippet = driver.page_source[:500]
                    print("No posts found. Page source snippet:", snippet)
                    raise Exception("No posts found")
                for post in posts:
                    entry = extract_post_data(post, config, url, use_selenium=True)
                    if entry:
                        entries.append(entry)
            except Exception as e:
                print(f"Error on {url}: {e}")
        finally:
            # Always release the fetch lock, even if an error occurs
            SharedSeleniumDriver.release_fetch_lock()
    else:
        print(f"Fetching {base_domain} using requests (no Selenium)")
        try:
            response = requests.get(url, timeout=HTTP_REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            posts = soup.select(config["post_container"])
            for post in posts:
                entry = extract_post_data(post, config, url, use_selenium=False)
                if entry:
                    entries.append(entry)
        except Exception as e:
            print(f"Error fetching {base_domain} with requests: {e}")

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
        'status': 200  # Mimics a successful fetch
    }

    return result