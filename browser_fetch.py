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
from app_config import FetchConfig

# =============================================================================
# SHARED CONSTANTS
# =============================================================================

# Network operation timeouts - for HTTP requests and element waiting
NETWORK_TIMEOUT = 20  # 20 seconds for HTTP requests and browser operations

# Thread synchronization timeout - for coordinating fetch operations
FETCH_LOCK_TIMEOUT = 30  # 30 seconds for acquiring fetch lock (longer due to thread coordination)

# Unified browser operation timeouts
BROWSER_TIMEOUT = 30  # 30 seconds for browser operations (page load, script execution)
BROWSER_WAIT_TIMEOUT = 25  # 25 seconds for waiting for elements

# =============================================================================
# UNIFIED BROWSER INTERFACE
# =============================================================================

class BrowserInterface:
    """
    Unified interface for browser operations that both Selenium and Playwright can implement.
    This provides a consistent API regardless of the underlying browser engine.
    """
    
    def __init__(self, use_tor, user_agent):
        self.use_tor = use_tor
        self.user_agent = user_agent
        self.last_used = time.time()
    
    def get_page_content(self, url):
        """
        Navigate to URL and return page content.
        
        Args:
            url (str): URL to navigate to
            
        Returns:
            tuple: (page_content, status_code) where page_content is the HTML content
                   and status_code is the HTTP status
        """
        raise NotImplementedError("Subclasses must implement get_page_content")
    
    def find_elements(self, selector):
        """
        Find elements matching the given CSS selector.
        
        Args:
            selector (str): CSS selector to find elements
            
        Returns:
            list: List of elements matching the selector
        """
        raise NotImplementedError("Subclasses must implement find_elements")
    
    def wait_for_elements(self, selector, timeout=None):
        """
        Wait for elements matching the selector to appear.
        
        Args:
            selector (str): CSS selector to wait for
            timeout (float, optional): Timeout in seconds
            
        Returns:
            bool: True if elements found, False if timeout
        """
        raise NotImplementedError("Subclasses must implement wait_for_elements")
    
    def close(self):
        """Close the browser instance."""
        raise NotImplementedError("Subclasses must implement close")
    
    def is_valid(self):
        """
        Check if the browser instance is still valid and responsive.
        
        Returns:
            bool: True if browser is valid, False otherwise
        """
        raise NotImplementedError("Subclasses must implement is_valid")

class SeleniumBrowserWrapper(BrowserInterface):
    """
    Wrapper for Selenium WebDriver that implements the unified BrowserInterface.
    """
    
    def __init__(self, driver, use_tor, user_agent):
        super().__init__(use_tor, user_agent)
        self.driver = driver
    
    def get_page_content(self, url):
        """Navigate to URL and return page content using Selenium."""
        try:
            self.driver.get(url)
            return self.driver.page_source, 200
        except Exception as e:
            g_logger.error(f"Selenium navigation error: {e}")
            return "", 500
    
    def find_elements(self, selector):
        """Find elements using Selenium."""
        try:
            from selenium.webdriver.common.by import By
            return self.driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception as e:
            g_logger.error(f"Selenium find elements error: {e}")
            return []
    
    def wait_for_elements(self, selector, timeout=None):
        """Wait for elements using Selenium."""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            
            if timeout is None:
                timeout = BROWSER_WAIT_TIMEOUT
            
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            return True
        except Exception as e:
            g_logger.debug(f"Selenium wait for elements timeout: {e}")
            return False
    
    def close(self):
        """Close Selenium driver."""
        try:
            self.driver.quit()
        except Exception as e:
            g_logger.error(f"Error closing Selenium driver: {e}")
    
    def is_valid(self):
        """Check if Selenium driver is valid."""
        try:
            self.driver.execute_script("return document.readyState;")
            return True
        except Exception:
            return False

class PlaywrightBrowserWrapper(BrowserInterface):
    """
    Wrapper for Playwright browser that implements the unified BrowserInterface.
    """
    
    def __init__(self, browser, context, use_tor, user_agent):
        super().__init__(use_tor, user_agent)
        self.browser = browser
        self.context = context
        self.page = None
    
    def get_page_content(self, url):
        """Navigate to URL and return page content using Playwright."""
        try:
            self.page = self.context.new_page()
            self.page.goto(url, timeout=BROWSER_TIMEOUT * 1000)  # Playwright uses milliseconds
            return self.page.content(), 200
        except Exception as e:
            g_logger.error(f"Playwright navigation error: {e}")
            return "", 500
    
    def find_elements(self, selector):
        """Find elements using Playwright."""
        try:
            if self.page:
                return self.page.locator(selector).all()
            return []
        except Exception as e:
            g_logger.error(f"Playwright find elements error: {e}")
            return []
    
    def wait_for_elements(self, selector, timeout=None):
        """Wait for elements using Playwright."""
        try:
            if timeout is None:
                timeout = BROWSER_WAIT_TIMEOUT
            
            if self.page:
                self.page.wait_for_selector(selector, timeout=int(timeout * 1000))  # Playwright uses milliseconds
                return True
            return False
        except Exception as e:
            g_logger.debug(f"Playwright wait for elements timeout: {e}")
            return False
    
    def close(self):
        """Close Playwright page and context."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
        except Exception as e:
            g_logger.error(f"Error closing Playwright browser: {e}")
    
    def is_valid(self):
        """Check if Playwright context is valid."""
        try:
            if self.context:
                pages = self.context.pages
                return True
            return False
        except Exception:
            return False

# =============================================================================
# SHARED UTILITY FUNCTIONS
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
        tuple: (config, base_domain) where config is site-specific configuration or None
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
            needs_selenium=True,  # Using browser for testing purposes
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


def extract_rss_data(post, config, get_text_func):
    """
    Extract data from RSS feeds loaded through browser.

    Args:
        post: Browser element containing RSS XML
        config: Configuration object
        get_text_func: Function to get text content (browser-specific)

    Returns:
        list: List of post entries, or None if extraction fails
    """
    try:
        # Get the raw XML content from the pre tag
        xml_content = get_text_func(post)

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


def safe_find_element(post, selector, use_browser, attr=None, find_func=None, get_attr_func=None, get_text_func=None):
    """
    Safely extract an element or attribute from a post using browser-specific functions.

    Args:
        post: Browser element containing post data
        selector (str): CSS selector to find the element
        use_browser (bool): Whether using browser or BeautifulSoup
        attr (str, optional): Attribute to extract instead of text content
        find_func: Browser-specific function to find elements
        get_attr_func: Browser-specific function to get attributes
        get_text_func: Browser-specific function to get text content

    Returns:
        str or None: Extracted text/attribute value, or None if extraction fails
    """
    try:
        if use_browser and find_func and get_attr_func and get_text_func:
            element = find_func(post, selector)
            if not element:
                return None
            if attr:
                return get_attr_func(element, attr)
            else:
                return get_text_func(element).strip()
        else:
            # BeautifulSoup fallback
            element = post.select_one(selector)
            if not element:
                return None
            if attr == "text":
                return element.get_text().strip()
            elif attr:
                return element.get(attr)
            else:
                return element.text.strip()
    except Exception:
        return None


def extract_title(post, config, url, use_browser, get_text_func=None, get_attr_func=None, find_func=None):
    """
    Extract title from a post element.

    Args:
        post: Browser element containing post data
        config: Configuration object
        url: Base URL for context
        use_browser: Whether using browser or BeautifulSoup
        get_text_func: Browser-specific function to get text content
        get_attr_func: Browser-specific function to get attributes
        find_func: Browser-specific function to find elements

    Returns:
        str: Extracted title, or None if extraction fails
    """
    # Special case: if title_selector equals post_container, use the post element itself
    if config.title_selector == config.post_container:
        g_logger.info(f"Using special case title extraction for {url}: title_selector='{config.title_selector}' == post_container='{config.post_container}'")
        if use_browser and get_text_func:
            title = get_text_func(post).strip()
        else:
            title = post.text.strip()
        # Fallbacks for anchors or elements with empty visible text
        if not title:
            try:
                if use_browser and get_attr_func:
                    title = get_attr_func(post, 'title') or get_attr_func(post, 'innerText') or ''
                else:
                    # For BeautifulSoup, get_attribute might not work the same way
                    title = post.get('title', '') or post.get_text() or ''
                title = (title or '').strip()
            except Exception:
                pass
        g_logger.debug(f"Raw post text: {repr(title)}")
        title = clean_patriots_title(title)
        g_logger.debug(f"Cleaned post title: {repr(title)}")
    else:
        title = safe_find_element(post, config.title_selector, use_browser, find_func=find_func, get_attr_func=get_attr_func, get_text_func=get_text_func)
        if not title:
            g_logger.debug(f"No title element found with selector '{config.title_selector}'")
            return None

    return title


def extract_link(post, config, url, use_browser, find_func=None, get_attr_func=None, get_text_func=None):
    """
    Extract link from a post element.

    Args:
        post: Browser element containing post data
        config: Configuration object
        url: Base URL for resolving relative links
        use_browser: Whether using browser or BeautifulSoup
        find_func: Browser-specific function to find elements
        get_attr_func: Browser-specific function to get attributes
        get_text_func: Browser-specific function to get text content

    Returns:
        str: Extracted link, or None if extraction fails
    """
    link = safe_find_element(post, config.link_selector, use_browser, config.link_attr, find_func=find_func, get_attr_func=get_attr_func, get_text_func=get_text_func)
    if not link:
        g_logger.info(f"No link element found with selector '{config.link_selector}'")
        return None

    # Resolve relative URLs
    if link and link.startswith('/'):
        link = urljoin(url, link)

    return link


def extract_post_data(post, config, url, use_browser, get_text_func=None, find_func=None, get_attr_func=None):
    """
    Extract post data from a web element using the provided configuration.

    Parses title, link, and other metadata from a post element using browser-specific functions.

    Args:
        post: Browser element containing post data
        config: Configuration object with selectors and settings
        url (str): Base URL for resolving relative links
        use_browser (bool): Whether using browser or BeautifulSoup for extraction
        get_text_func: Browser-specific function to get text content
        find_func: Browser-specific function to find elements
        get_attr_func: Browser-specific function to get attributes

    Returns:
        dict or list: Extracted post data with title, link, id, summary, and timestamps,
                     or None if extraction fails. For RSS feeds, returns a list of entries.
    """
    # Special handling for RSS feeds loaded through browser
    if use_browser and config.post_container == "pre" and get_text_func:
        return extract_rss_data(post, config, get_text_func)

    # Regular processing for non-RSS content
    title = extract_title(post, config, url, use_browser, get_text_func=get_text_func, get_attr_func=get_attr_func, find_func=find_func)
    if not title or len(title.split()) < 2:
        return None

    link = extract_link(post, config, url, use_browser, find_func=find_func, get_attr_func=get_attr_func, get_text_func=get_text_func)
    if not link:
        return None

    filter_pattern = config.filter_pattern
    if filter_pattern and filter_pattern not in link:
        return None

    if use_browser and get_text_func:
        summary = get_text_func(post).strip()
    else:
        summary = post.text.strip()

    return create_post_entry(title, link, summary)

# =============================================================================
# COMMON FETCH LOGIC
# =============================================================================

def _prepare_request_headers(config, user_agent):
    """
    Prepare HTTP request headers for non-browser requests.
    
    Args:
        config: Configuration object
        user_agent (str): User agent string
        
    Returns:
        dict: Request headers
    """
    request_headers = {}
    
    if config.use_random_user_agent:
        request_headers['User-Agent'] = g_cs.get("REDDIT_USER_AGENT")
    else:
        request_headers['User-Agent'] = user_agent

    # Add proxy headers if proxying is enabled
    if WORKER_PROXYING and PROXY_SERVER:
        request_headers['X-Forwarded-For'] = PROXY_SERVER.split(':')[0]
        if PROXY_USERNAME and PROXY_PASSWORD:
            import base64
            auth_string = f"{PROXY_USERNAME}:{PROXY_PASSWORD}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            request_headers['Proxy-Authorization'] = f'Basic {auth_b64}'
    
    return request_headers

def _fetch_with_requests(url, config, user_agent):
    """
    Fetch content using requests library for non-JavaScript sites.
    
    Args:
        url (str): URL to fetch
        config: Configuration object
        user_agent (str): User agent string
        
    Returns:
        tuple: (entries, status) where entries is list of post entries and status is HTTP status
    """
    entries = []
    status = 200
    
    try:
        request_headers = _prepare_request_headers(config, user_agent)
        response = requests.get(url, timeout=NETWORK_TIMEOUT, headers=request_headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        posts = soup.select(config.post_container)

        # Extract post data with consolidated error handling
        for post in posts:
            try:
                entry = extract_post_data(post, config, url, use_browser=False)
                if entry:
                    entries.append(entry)
            except Exception as e:
                g_logger.error(f"Error extracting post data: {e}")

    except requests.exceptions.RequestException as e:
        g_logger.error(f"Request error for {url}: {e}")
        status = 500
    except Exception as e:
        g_logger.error(f"Error fetching {url} with requests: {e}")
        status = 500
    
    return entries, status

def _fetch_with_browser(url, config, user_agent, browser_instance):
    """
    Fetch content using browser automation for JavaScript sites.
    
    Args:
        url (str): URL to fetch
        config: Configuration object
        user_agent (str): User agent string
        browser_instance: Browser instance implementing BrowserInterface
        
    Returns:
        tuple: (entries, status) where entries is list of post entries and status is HTTP status
    """
    entries = []
    status = 200
    
    try:
        # Navigate to the page
        page_content, nav_status = browser_instance.get_page_content(url)
        if nav_status != 200:
            return [], nav_status
        
        # Wait for elements if not Reddit (Reddit has special handling)
        base_domain = extract_base_domain(url)
        if base_domain != "reddit.com":
            try:
                # Use random timeout to avoid predictable patterns
                random_timeout = random.uniform(15, BROWSER_WAIT_TIMEOUT)
                browser_instance.wait_for_elements(config.post_container, timeout=random_timeout)
            except Exception as wait_error:
                g_logger.warning(f"Timeout waiting for elements on {url}: {wait_error}")
                # Continue anyway, might still find some content

        posts = browser_instance.find_elements(config.post_container)
        if not posts:
            g_logger.info(f"No posts found for {url}. Page content snippet: {page_content[:500]}")
            status = 204  # No content
        else:
            for post in posts:
                try:
                    # Use browser-specific extraction
                    entry_data = _extract_post_data_browser(post, config, url, browser_instance)
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
    
    return entries, status

def _extract_post_data_browser(post, config, url, browser_instance):
    """
    Extract post data using browser-specific methods.
    
    Args:
        post: Browser element
        config: Configuration object
        url (str): Base URL
        browser_instance: Browser instance
        
    Returns:
        dict or list: Extracted post data
    """
    # This will be implemented by the specific browser modules
    # For now, delegate to the existing extract_post_data function
    # The browser modules will provide the appropriate get_text_func, find_func, get_attr_func
    return extract_post_data(post, config, url, use_browser=True)

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

def _get_browser_instance(use_tor, user_agent):
    """
    Get a browser instance using the configured browser engine.
    
    Args:
        use_tor (bool): Whether to use Tor proxy
        user_agent (str): User agent string for the browser
        
    Returns:
        BrowserInterface: Browser instance implementing the unified interface
    """
    browser_module = _get_browser_module()
    
    if USE_PLAYWRIGHT:
        try:
            browser, context = browser_module.SharedPlaywrightBrowser.get_browser_context(use_tor, user_agent)
            if browser and context:
                return PlaywrightBrowserWrapper(browser, context, use_tor, user_agent)
        except AttributeError:
            g_logger.error("Playwright SharedPlaywrightBrowser not available")
    else:
        try:
            driver = browser_module.SharedSeleniumDriver.get_driver(use_tor, user_agent)
            if driver:
                return SeleniumBrowserWrapper(driver, use_tor, user_agent)
        except AttributeError:
            g_logger.error("Selenium SharedSeleniumDriver not available")
    
    return None

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
    config, base_domain = get_site_config(url)

    if not config:
        g_logger.info(f"Configuration for base domain '{base_domain}' (from URL '{url}') not found.")
        return build_feed_result([], url, status=404)

    entries = []
    status = 200

    if config.needs_selenium:
        # Use browser automation
        if config.use_random_user_agent:
            # Use random user agent to avoid detection (reuse existing REDDIT_USER_AGENT)
            user_agent = g_cs.get("REDDIT_USER_AGENT")

        # Acquire the fetch lock before starting the fetch operation
        lock_acquired = False
        try:
            lock_acquired = acquire_fetch_lock()
            if not lock_acquired:
                g_logger.warning(f"Failed to acquire fetch lock for {url}, skipping...")
                return build_feed_result([], url, status=503)

            browser_instance = _get_browser_instance(config.needs_tor, user_agent)
            if not browser_instance:
                g_logger.error(f"Failed to get browser instance for {url}")
                return build_feed_result([], url, status=503)
                
            entries, status = _fetch_with_browser(url, config, user_agent, browser_instance)
                
        finally:
            # Always release the fetch lock, even if an error occurs
            if lock_acquired:
                release_fetch_lock()
    else:
        # Use requests for non-JavaScript sites
        entries, status = _fetch_with_requests(url, config, user_agent)

    g_logger.info(f"Fetched {len(entries)} entries from {url}")
    return build_feed_result(entries, url, status)

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
    'release_fetch_lock',
    # Shared utility functions
    'extract_base_domain',
    'get_site_config',
    'build_feed_result',
    'clean_patriots_title',
    'create_post_entry',
    'extract_rss_data',
    'safe_find_element',
    'extract_title',
    'extract_link',
    'extract_post_data',
    # Unified browser interface
    'BrowserInterface',
    'SeleniumBrowserWrapper',
    'PlaywrightBrowserWrapper',
    # Shared constants
    'NETWORK_TIMEOUT',
    'FETCH_LOCK_TIMEOUT',
    'BROWSER_TIMEOUT',
    'BROWSER_WAIT_TIMEOUT'
]
