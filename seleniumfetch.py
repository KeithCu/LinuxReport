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
import random
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
from shared import g_cs, CUSTOM_FETCH_CONFIG, g_logger, WORKER_PROXYING, PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD

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
WEBDRIVER_TIMEOUT = 30  # 30 seconds for page load and script execution

# Network operation timeouts - for HTTP requests and element waiting
NETWORK_TIMEOUT = 20  # 20 seconds for HTTP requests and WebDriverWait operations

# Thread synchronization timeout - for coordinating fetch operations
FETCH_LOCK_TIMEOUT = 30  # 30 seconds for acquiring fetch lock (longer due to thread coordination)

# Driver lifecycle timeout - for resource management
DRIVER_RECYCLE_TIMEOUT = 300  # 5 minutes - timeout for driver recycling


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
        # Anti-detection measures (these ARE detectable via JS)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        # NOTE: We DON'T disable useAutomationExtension as that would break Selenium!
        # Use a consistent, common window size to avoid detection patterns
        # Random window sizes can actually make detection easier as servers look for unusual patterns
        # Full HD (1920x1080) is the most common desktop resolution and appears natural
        options.add_argument("--window-size=1920,1080")
        # Keep performance optimizations - server can't see these!
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
        driver.set_page_load_timeout(WEBDRIVER_TIMEOUT)  # 30 second page load timeout
        driver.set_script_timeout(WEBDRIVER_TIMEOUT)     # 30 second script timeout

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

    Provides centralized management of Chrome WebDriver instances with TTL-based
    cleanup and thread synchronization. Implements lazy initialization and
    periodic driver recycling for resource efficiency.

    Attributes:
        _instances: Dictionary of driver instances by (use_tor, user_agent) key
        _lock: Thread lock for instance management
        _fetch_lock: Thread lock for synchronizing fetch operations
        _ttl_timeout: Time-to-live for driver instances (seconds)
        _instance: Backward compatibility - points to first instance
        _shutdown_initiated: Backward compatibility flag
        _timeout: Backward compatibility timeout
    """

    _instances = {}  # (use_tor, user_agent) -> (driver_instance, last_used_time)
    _lock = threading.Lock()
    _fetch_lock = threading.Lock()
    _ttl_timeout = DRIVER_RECYCLE_TIMEOUT  # 5 minutes

    # Backward compatibility attributes
    _instance = None  # Points to first instance for compatibility
    _shutdown_initiated = False  # Backward compatibility flag
    _timeout = DRIVER_RECYCLE_TIMEOUT  # Backward compatibility timeout

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

        Returns an existing driver if configuration matches and is still valid,
        or creates a new one if needed. Uses TTL-based cleanup for resource management.

        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the driver

        Returns:
            webdriver.Chrome: Configured Chrome WebDriver instance, or None if creation fails
        """
        key = (use_tor, user_agent)
        now = time.time()

        with cls._lock:
            # Clean up expired instances periodically
            cls._cleanup_expired_instances(now)

            # Check if we have a valid instance for this configuration
            if key in cls._instances:
                instance, last_used = cls._instances[key]
                if cls._is_instance_valid(instance) and (now - last_used) < cls._ttl_timeout:
                    instance.last_used = now
                    return instance.driver

                # Instance is expired or invalid, clean it up
                cls._cleanup_instance(instance)
                del cls._instances[key]

            # Create new instance
            try:
                g_logger.info(f"Creating new SharedSeleniumDriver instance for Tor: {use_tor}")
                new_instance = SharedSeleniumDriver(use_tor, user_agent)
                cls._instances[key] = (new_instance, now)
                # Update backward compatibility instance (first one created)
                if cls._instance is None:
                    cls._instance = new_instance
                return new_instance.driver
            except Exception as e:
                g_logger.error(f"Error creating new driver: {e}")
                import traceback
                g_logger.error(f"Full traceback: {traceback.format_exc()}")
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
            return cls._fetch_lock.acquire(timeout=FETCH_LOCK_TIMEOUT)
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
    def _is_instance_valid(cls, instance):
        """
        Check if a driver instance is still valid and responsive.

        Args:
            instance: The SharedSeleniumDriver instance to validate

        Returns:
            bool: True if instance is valid
        """
        try:
            if not (instance and hasattr(instance, 'driver')):
                return False

            # Quick health check - don't fail if this throws an exception
            instance.driver.execute_script("return document.readyState;")
            return True
        except Exception as e:
            g_logger.debug(f"Driver health check failed: {e}")
            return False

    @classmethod
    def _cleanup_expired_instances(cls, now):
        """
        Clean up instances that have exceeded their TTL.

        Args:
            now (float): Current timestamp
        """
        expired_keys = []

        for key, (instance, last_used) in cls._instances.items():
            if (now - last_used) >= cls._ttl_timeout:
                expired_keys.append(key)

        for key in expired_keys:
            instance, _ = cls._instances[key]
            cls._cleanup_instance(instance)
            del cls._instances[key]
            g_logger.debug(f"Cleaned up expired driver instance for {key}")

            # Update backward compatibility instance
            if cls._instance == instance:
                cls._instance = None


    @classmethod
    def _cleanup_instance(cls, instance):
        """
        Clean up a driver instance safely.

        Uses a two-tier approach: first tries quit(), then close() if quit() fails.
        As a final fallback, if the driver service process is still alive,
        attempts to terminate/kill it to avoid lingering Chromium processes.

        Args:
            instance: The SharedSeleniumDriver instance to clean up
        """
        if not instance or not hasattr(instance, 'driver'):
            return

        driver = instance.driver

        did_cleanup_call = False

        try:
            # Primary cleanup: quit the driver with proper timeout handling
            if hasattr(driver, 'quit'):
                try:
                    driver.set_page_load_timeout(5)
                    driver.set_script_timeout(5)
                except:
                    pass

                driver.quit()
                did_cleanup_call = True
                g_logger.debug("WebDriver quit successfully")
                time.sleep(0.5)
        except Exception as e:
            g_logger.warning(f"Primary cleanup failed: {e}")

        # Fallback: try to close the driver if quit failed
        if not did_cleanup_call:
            try:
                if hasattr(driver, 'close'):
                    driver.close()
                    did_cleanup_call = True
                    g_logger.debug("WebDriver closed successfully")
                    time.sleep(0.5)
            except Exception as e:
                g_logger.warning(f"Secondary cleanup failed: {e}")

        # Final safeguard: ensure the chromedriver process is terminated
        try:
            service = getattr(driver, 'service', None)
            proc = getattr(service, 'process', None)
            pid = getattr(proc, 'pid', None) if proc else None
            if proc and hasattr(proc, 'poll') and proc.poll() is None:
                g_logger.info(f"Cleanup: chromedriver pid {pid} still alive after quit/close; terminating...")
                try:
                    proc.terminate()
                    time.sleep(1.0)
                    if proc.poll() is None:
                        proc.kill()
                    g_logger.info(f"Cleanup: chromedriver pid {pid} terminated")
                except Exception as kill_e:
                    g_logger.warning(f"Cleanup: failed to terminate chromedriver pid {pid}: {kill_e}")
        except Exception as e:
            g_logger.debug(f"Cleanup: unable to inspect/terminate driver service process: {e}")

        if not did_cleanup_call:
            g_logger.warning("All cleanup methods failed - driver may be in an inconsistent state")

    @classmethod
    def force_cleanup(cls):
        """
        Force shutdown and cleanup of all driver instances.

        This method can be called manually to ensure all WebDrivers
        are properly shut down, useful for debugging or emergency cleanup.
        """
        g_logger.info("Forcing WebDriver cleanup...")
        with cls._lock:
            for instance, _ in cls._instances.values():
                cls._cleanup_instance(instance)
            cls._instances.clear()
            # Reset backward compatibility attributes
            cls._instance = None
            cls._shutdown_initiated = False
            g_logger.info("Force cleanup completed")

    @classmethod
    def reset_for_testing(cls):
        """
        Reset the class state for testing purposes.
        """
        g_logger.info("Resetting SharedSeleniumDriver for testing...")
        cls.force_cleanup()

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

def _log_debugging_info(post, use_selenium, context):
    """
    Log debugging information for failed element extraction.

    Args:
        post: The post element being processed
        use_selenium (bool): Whether using Selenium or BeautifulSoup
        context (str): Context for the debugging info (e.g., "title", "link")
    """
    try:
        # Show what text content is available for debugging
        if use_selenium:
            all_text = post.text[:200] + "..." if len(post.text) > 200 else post.text
        else:
            all_text = post.get_text()[:200] + "..." if len(post.get_text()) > 200 else post.get_text()
        g_logger.info(f"Available text content for {context}: {all_text}")

        # Show available links and classes for debugging
        try:
            all_links = post.find_all('a') if not use_selenium else post.find_elements(By.TAG_NAME, "a")
            links_info = [a.get('href', 'NO_HREF') for a in all_links[:3]]
            g_logger.info(f"Available links for {context}: {links_info}")

            if not use_selenium:
                g_logger.info(f"Available classes for {context}: {post.get('class', [])}")
        except Exception as link_error:
            g_logger.debug(f"Error getting link info for {context}: {link_error}")
    except Exception as debug_e:
        g_logger.debug(f"Error during debug output for {context}: {debug_e}")


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
                _log_debugging_info(post, use_selenium, "title")
                return None
            title = title_element.text.strip()
    except Exception as e:
        g_logger.error(f"Error extracting title with selector '{config.title_selector}': {e}")
        _log_debugging_info(post, use_selenium, "title")
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
                _log_debugging_info(post, use_selenium, "link")
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
        _log_debugging_info(post, use_selenium, "link")
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
                # Server sees this GET request immediately - timing detection happens here

                if base_domain == "reddit.com":
                    pass
                else:
                    try:
                        # Use random timeout to avoid predictable patterns
                        random_timeout = random.uniform(15, 25)
                        WebDriverWait(driver, random_timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, config.post_container)))
                    except Exception as wait_error:
                        g_logger.warning(f"Timeout waiting for elements on {url}: {wait_error}")
                        # Continue anyway, might still find some content

                posts = driver.find_elements(By.CSS_SELECTOR, config.post_container)
                if not posts:
                    snippet = driver.page_source[:500]
                    g_logger.info(f"No posts found for {url}. Page source snippet: {snippet}")
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

        # Handle user agent for requests
        request_headers = {}
        if config.use_random_user_agent:
            request_headers['User-Agent'] = g_cs.get("REDDIT_USER_AGENT")
        else:
            request_headers['User-Agent'] = user_agent

        try:
            # Add proxy headers if proxying is enabled
            if WORKER_PROXYING and PROXY_SERVER:
                request_headers['X-Forwarded-For'] = PROXY_SERVER.split(':')[0]
                if PROXY_USERNAME and PROXY_PASSWORD:
                    import base64
                    auth_string = f"{PROXY_USERNAME}:{PROXY_PASSWORD}"
                    auth_bytes = auth_string.encode('ascii')
                    auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
                    request_headers['Proxy-Authorization'] = f'Basic {auth_b64}'
            
            response = requests.get(url, timeout=NETWORK_TIMEOUT, headers=request_headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            posts = soup.select(config.post_container)

            # Extract post data with consolidated error handling
            for post in posts:
                try:
                    entry = extract_post_data(post, config, url, use_selenium=False)
                    if entry:
                        entries.append(entry)
                except Exception as e:
                    g_logger.error(f"Error extracting post data: {e}")

        except requests.exceptions.RequestException as e:
            g_logger.error(f"Request error for {base_domain}: {e}")
            status = 500
        except Exception as e:
            g_logger.error(f"Error fetching {base_domain} with requests: {e}")
            status = 500

    g_logger.info(f"Fetched {len(entries)} entries from {url}")

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