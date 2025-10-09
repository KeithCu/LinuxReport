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
import re
import requests
from bs4 import BeautifulSoup
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
from shared import g_cs, CUSTOM_FETCH_CONFIG, g_logger, WORKER_PROXYING, PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD

# =============================================================================
# FEATURE FLAGS
# =============================================================================


# =============================================================================
# TIMEOUT CONSTANTS
# =============================================================================

# WebDriver timeouts - for browser operations
WEBDRIVER_TIMEOUT = 30  # 30 seconds for page load and script execution

# Network operation timeouts - for HTTP requests and element waiting
NETWORK_TIMEOUT = 20  # 20 seconds for HTTP requests and WebDriverWait operations

# Thread synchronization timeout - for coordinating fetch operations
FETCH_LOCK_TIMEOUT = 30  # 30 seconds for acquiring fetch lock (longer due to thread coordination)


# =============================================================================
# SPECIAL SITE CONFIGURATIONS
# =============================================================================

# Import the FetchConfig for creating configurations
from app_config import FetchConfig

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
        
    except (WebDriverException, OSError, ValueError) as e:
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

    Provides simple singleton pattern with thread synchronization.
    """

    _instance = None
    _lock = threading.Lock()
    _fetch_lock = threading.Lock()

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
    def force_cleanup(cls):
        """
        Force shutdown and cleanup of the WebDriver instance.
        """
        g_logger.info("Forcing WebDriver cleanup...")
        with cls._lock:
            cls._cleanup_instance()
            g_logger.info("Force cleanup completed")

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
# UTILITY FUNCTIONS
# =============================================================================

def extract_base_domain(url):
    """
    Extract the base domain from a URL for configuration lookup.

    Handles subdomains by extracting the main domain (e.g., example.com from sub.example.com).

    Args:
        url (str): The URL to parse

    Returns:
        str: Base domain for configuration lookup
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
    return base_domain


def get_site_config(url):
    """
    Get the configuration for a given URL.

    Looks up configuration in CUSTOM_FETCH_CONFIG using both base domain and full netloc.

    Args:
        url (str): URL to get configuration for

    Returns:
        config or FetchConfig: Site-specific configuration, or None if not found
    """
    base_domain = extract_base_domain(url)
    parsed = urlparse(url)

    # Always try base domain first, then fallback to netloc (for legacy configs)
    config = CUSTOM_FETCH_CONFIG.get(base_domain)
    if not config:
        config = CUSTOM_FETCH_CONFIG.get(parsed.netloc)

    # Special case for keithcu.com RSS feed
    if not config and "keithcu.com" in base_domain:
        config = FetchConfig(
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

    return config, base_domain


def build_feed_result(entries, url, status=200, etag="", modified=None):
    """
    Build a standardized feed result dictionary.

    Args:
        entries (list): List of post entries
        url (str): Source URL
        status (int): HTTP status code
        etag (str): ETag for caching
        modified (datetime): Last modified timestamp

    Returns:
        dict: Standardized feed result
    """
    if modified is None:
        modified = datetime.now(timezone.utc)

    return {
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


def safe_find_element(post, selector, use_selenium, attr=None):
    """
    Safely extract an element or attribute from a post using either Selenium or BeautifulSoup.

    Args:
        post: WebElement (Selenium) or Tag (BeautifulSoup) containing post data
        selector (str): CSS selector to find the element
        use_selenium (bool): Whether using Selenium or BeautifulSoup
        attr (str, optional): Attribute to extract instead of text content

    Returns:
        str or None: Extracted text/attribute value, or None if extraction fails
    """
    try:
        if use_selenium:
            element = post.find_element(By.CSS_SELECTOR, selector)
            if attr:
                return element.get_attribute(attr)
            else:
                return element.text.strip()
        else:
            element = post.select_one(selector)
            if not element:
                return None
            if attr == "text":
                return element.get_text().strip()
            elif attr:
                return element.get(attr)
            else:
                return element.text.strip()
    except (WebDriverException, AttributeError):
        return None


def clean_patriots_title(title):
    """
    Clean patriots.win specific metadata from post titles.

    Removes common patterns like timestamps, user info, action buttons, etc.
    that appear at the end of patriots.win posts.

    Args:
        title (str): Raw title text to clean

    Returns:
        str: Cleaned title text
    """
    if not title:
        return title

    # Convert to string if needed
    title = str(title)

    # Clean up patriots.win metadata from the end of posts
    # Remove patterns like "posted X ago by username X comments award share report block"
    # Remove leading numbers/IDs like "546 "
    title = re.sub(r'^\d+\s+', '', title)

    # Remove "posted X ago by..." and everything after it
    title = re.sub(r'\s*posted\s+\d+\s+(?:hour|minute|second|day)s?\s+ago\s+by\s+.*', '', title, flags=re.IGNORECASE)

    # Remove remaining metadata patterns
    title = re.sub(r'\s*\d+\s+comments?\s+.*', '', title, flags=re.IGNORECASE)

    # Remove action buttons and user tags - remove known patterns from end
    title = re.sub(r'\s+PRO\s+share\s+report\s+block\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+share\s+report\s+block\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+share\s+download\s+report\s+block\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+TRUMP\s+TRUTH\s+share\s+download\s+report\s+block\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+TRUMP\s+TRUTH\s*$', '', title, flags=re.IGNORECASE)  # Remove TRUMP TRUTH tags
    title = re.sub(r'\s+PRO\s*$', '', title, flags=re.IGNORECASE)

    # Remove any remaining trailing punctuation and whitespace
    title = re.sub(r'[.\s]+$', '', title).strip()

    return title

# =============================================================================
# CONTENT EXTRACTION FUNCTIONS
# =============================================================================


def extract_rss_data(post, config):
    """
    Extract data from RSS feeds loaded through Selenium.

    Args:
        post: Selenium WebElement containing RSS XML
        config: Configuration object

    Returns:
        list: List of post entries, or None if extraction fails
    """
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

    except (WebDriverException, AttributeError) as e:
        g_logger.error(f"Error parsing RSS content: {e}")
        return None


def extract_title(post, config, url, use_selenium):
    """
    Extract title from a post element.

    Args:
        post: WebElement (Selenium) or Tag (BeautifulSoup) containing post data
        config: Configuration object
        url: Base URL for context
        use_selenium: Whether using Selenium or BeautifulSoup

    Returns:
        str: Extracted title, or None if extraction fails
    """
    # Special case: if title_selector equals post_container, use the post element itself
    if config.title_selector == config.post_container:
        g_logger.info(f"Using special case title extraction for {url}: title_selector='{config.title_selector}' == post_container='{config.post_container}'")
        title = post.text.strip()
        # Fallbacks for anchors or elements with empty visible text
        if not title:
            try:
                # Selenium WebElement path
                get_attr = getattr(post, 'get_attribute', None)
                if callable(get_attr):
                    title = get_attr('title') or get_attr('innerText') or ''
                    title = (title or '').strip()
            except Exception:
                pass
        g_logger.debug(f"Raw post text: {repr(title)}")
        title = clean_patriots_title(title)
        g_logger.debug(f"Cleaned post title: {repr(title)}")
    else:
        title = safe_find_element(post, config.title_selector, use_selenium)
        if not title:
            g_logger.debug(f"No title element found with selector '{config.title_selector}'")
            _log_debugging_info(post, use_selenium, "title")
            return None

    return title


def extract_link(post, config, url, use_selenium):
    """
    Extract link from a post element.

    Args:
        post: WebElement (Selenium) or Tag (BeautifulSoup) containing post data
        config: Configuration object
        url: Base URL for resolving relative links
        use_selenium: Whether using Selenium or BeautifulSoup

    Returns:
        str: Extracted link, or None if extraction fails
    """
    link = safe_find_element(post, config.link_selector, use_selenium, config.link_attr)
    if not link:
        g_logger.info(f"No link element found with selector '{config.link_selector}'")
        _log_debugging_info(post, use_selenium, "link")
        return None

    # Resolve relative URLs
    if link and link.startswith('/'):
        link = urljoin(url, link)

    return link


def create_post_entry(title, link, summary):
    """
    Create a standardized post entry dictionary.

    Args:
        title: Post title
        link: Post link
        summary: Post summary text

    Returns:
        dict: Standardized post entry
    """
    published_parsed = time.gmtime()
    published = time.strftime('%a, %d %b %Y %H:%M:%S GMT', published_parsed)

    return {
        "title": title,
        "link": link,
        "id": link,
        "summary": summary,
        "published": published,
        "published_parsed": published_parsed
    }


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
        except (WebDriverException, AttributeError) as link_error:
            g_logger.debug(f"Error getting link info for {context}: {link_error}")
    except (WebDriverException, AttributeError) as debug_e:
        g_logger.debug(f"Error during debug output for {context}: {debug_e}")


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
    # Special handling for RSS feeds loaded through Selenium
    if use_selenium and config.post_container == "pre":
        return extract_rss_data(post, config)

    # Regular processing for non-RSS content
    title = extract_title(post, config, url, use_selenium)
    if not title or len(title.split()) < 2:
        return None

    link = extract_link(post, config, url, use_selenium)
    if not link:
        return None

    filter_pattern = config.filter_pattern
    if filter_pattern and filter_pattern not in link:
        return None

    return create_post_entry(title, link, post.text.strip())

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
    config, base_domain = get_site_config(url)

    if not config:
        g_logger.info(f"Configuration for base domain '{base_domain}' (from URL '{url}') not found.")
        return build_feed_result([], url, status=404)

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
                return build_feed_result([], url, status=503)

            driver = SharedSeleniumDriver.get_driver(config.needs_tor, user_agent)
            if not driver:
                g_logger.error(f"Failed to get driver for {url}")
                return build_feed_result([], url, status=503)
                
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
                    except (TimeoutException, WebDriverException) as wait_error:
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
                        except WebDriverException as e:
                            g_logger.error(f"Error extracting post data: {e}")
                            continue
                            
            except WebDriverException as e:
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
                except AttributeError as e:
                    g_logger.error(f"Error extracting post data: {e}")

        except requests.exceptions.RequestException as e:
            g_logger.error(f"Request error for {base_domain}: {e}")
            status = 500
        except AttributeError as e:
            g_logger.error(f"Error fetching {base_domain} with requests: {e}")
            status = 500

    g_logger.info(f"Fetched {len(entries)} entries from {url}")
    return build_feed_result(entries, url, status)