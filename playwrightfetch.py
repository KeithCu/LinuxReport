"""
playwrightfetch.py

Playwright-based web scraping system for JavaScript-rendered content and dynamic sites.
Provides functions to fetch and parse posts from sites requiring JavaScript rendering
or special handling, using Playwright and BeautifulSoup. Includes site-specific
configurations, shared browser management, and thread-safe operations.
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
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

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

# Playwright timeouts - for browser operations
PLAYWRIGHT_TIMEOUT = 30000  # 30 seconds for page load and script execution

# Network operation timeouts - for HTTP requests and element waiting
NETWORK_TIMEOUT = 20  # 20 seconds for HTTP requests

# Thread synchronization timeout - for coordinating fetch operations
FETCH_LOCK_TIMEOUT = 30  # 30 seconds for acquiring fetch lock (longer due to thread coordination)

# Browser lifecycle timeout - for resource management
BROWSER_RECYCLE_TIMEOUT = 300  # 5 minutes - timeout for browser recycling

# Backward compatibility constant
DRIVER_RECYCLE_TIMEOUT = BROWSER_RECYCLE_TIMEOUT


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
            needs_selenium=True,  # Using Playwright for testing purposes
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
# PLAYWRIGHT CONFIGURATION AND CREATION
# =============================================================================

def create_browser_context(playwright, use_tor, user_agent):
    """
    Create and configure a Playwright browser context.
    
    Sets up a browser context with appropriate options for web scraping,
    including proxy configuration for Tor if enabled and custom user agent.
    
    Args:
        playwright: Playwright instance
        use_tor (bool): Whether to use Tor proxy for connections
        user_agent (str): User agent string to use for requests
        
    Returns:
        tuple: (browser, context) - Configured browser and context instances
    """
    try:
        g_logger.info(f"Creating Playwright browser with Tor: {use_tor}, User-Agent: {user_agent[:50]}...")

        # Launch browser with appropriate options
        # Use Playwright's Chromium directly (no system fallback for now)
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-plugins",
                "--disable-images",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=TranslateUI",
                "--disable-ipc-flooding-protection",
                "--memory-pressure-off",
                "--max_old_space_size=4096",
                "--window-size=1920,1080"
            ]
        )

        # Create context with user agent and proxy settings
        context_options = {
            "user_agent": user_agent,
            "viewport": {"width": 1920, "height": 1080},
            "ignore_https_errors": True,
            "java_script_enabled": True,
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            }
        }

        if use_tor:
            context_options["proxy"] = {
                "server": "socks5://127.0.0.1:9050"
            }

        context = browser.new_context(**context_options)

        # Add stealth measures
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            window.chrome = {
                runtime: {},
            };
        """)

        g_logger.info("Playwright browser setup completed successfully")
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
    Thread-safe singleton manager for Playwright browser instances.

    Provides centralized management of Playwright browser instances with TTL-based
    cleanup and thread synchronization. Implements lazy initialization and
    periodic browser recycling for resource efficiency.

    Attributes:
        _instances: Dictionary of browser instances by (use_tor, user_agent) key
        _lock: Thread lock for instance management
        _fetch_lock: Thread lock for synchronizing fetch operations
        _ttl_timeout: Time-to-live for browser instances (seconds)
        _playwright: Global Playwright instance
        _instance: Backward compatibility - points to first instance
        _shutdown_initiated: Backward compatibility flag
        _timeout: Backward compatibility timeout
    """

    _instances = {}  # (use_tor, user_agent) -> (browser_instance, context, last_used_time)
    _lock = threading.Lock()
    _fetch_lock = threading.Lock()
    _ttl_timeout = BROWSER_RECYCLE_TIMEOUT  # 5 minutes
    _playwright = None

    # Backward compatibility attributes
    _instance = None  # Points to first instance for compatibility
    _shutdown_initiated = False  # Backward compatibility flag
    _timeout = BROWSER_RECYCLE_TIMEOUT  # Backward compatibility timeout

    def __init__(self, use_tor, user_agent):
        """
        Initialize a new SharedPlaywrightBrowser instance.

        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the browser
        """
        g_logger.debug(f"Initializing SharedPlaywrightBrowser with Tor: {use_tor}")
        try:
            # Initialize Playwright if not already done
            if SharedPlaywrightBrowser._playwright is None:
                SharedPlaywrightBrowser._playwright = sync_playwright().start()
            
            self.browser, self.context = create_browser_context(
                SharedPlaywrightBrowser._playwright, use_tor, user_agent
            )
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
        Get or create a browser context with the specified configuration.

        Returns an existing browser/context if configuration matches and is still valid,
        or creates a new one if needed. Uses TTL-based cleanup for resource management.

        Args:
            use_tor (bool): Whether to use Tor proxy
            user_agent (str): User agent string for the browser

        Returns:
            tuple: (browser, context) - Configured browser and context instances, or (None, None) if creation fails
        """
        key = (use_tor, user_agent)
        now = time.time()

        with cls._lock:
            # Clean up expired instances periodically
            cls._cleanup_expired_instances(now)
            # Also clean up any lingering browser processes (only every 5 minutes)
            if not hasattr(cls, '_last_cleanup_time') or (now - cls._last_cleanup_time) > 300:
                cls._cleanup_lingering_processes()
                cls._last_cleanup_time = now

            # Check if we have a valid instance for this configuration
            if key in cls._instances:
                instance, context, last_used = cls._instances[key]
                if cls._is_instance_valid(instance) and (now - last_used) < cls._ttl_timeout:
                    instance.last_used = now
                    return instance.browser, context

                # Instance is expired or invalid, clean it up
                cls._cleanup_instance(instance, context)
                del cls._instances[key]

            # Create new instance
            try:
                g_logger.info(f"Creating new SharedPlaywrightBrowser instance for Tor: {use_tor}")
                new_instance = SharedPlaywrightBrowser(use_tor, user_agent)
                cls._instances[key] = (new_instance, new_instance.context, now)
                # Update backward compatibility instance (first one created)
                if cls._instance is None:
                    cls._instance = new_instance
                return new_instance.browser, new_instance.context
            except Exception as e:
                g_logger.error(f"Error creating new browser: {e}")
                import traceback
                g_logger.error(f"Full traceback: {traceback.format_exc()}")
                return None, None

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
        except RuntimeError as e:
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
        Check if a browser instance is still valid and responsive.

        Args:
            instance: The SharedPlaywrightBrowser instance to validate

        Returns:
            bool: True if instance is valid
        """
        try:
            if not (instance and hasattr(instance, 'browser')):
                return False

            # Quick health check - don't fail if this throws an exception
            # Check if browser is still connected
            return instance.browser.is_connected()
        except Exception as e:
            g_logger.debug(f"Browser health check failed: {e}")
            return False

    @classmethod
    def _cleanup_expired_instances(cls, now):
        """
        Clean up instances that have exceeded their TTL.

        Args:
            now (float): Current timestamp
        """
        expired_keys = []

        for key, (instance, context, last_used) in cls._instances.items():
            if (now - last_used) >= cls._ttl_timeout:
                expired_keys.append(key)

        for key in expired_keys:
            instance, context, _ = cls._instances[key]
            cls._cleanup_instance(instance, context)
            del cls._instances[key]
            g_logger.debug(f"Cleaned up expired browser instance for {key}")

            # Update backward compatibility instance
            if cls._instance == instance:
                cls._instance = None

    @classmethod
    def _cleanup_instance(cls, instance, context):
        """
        Clean up a browser instance safely.

        Uses a two-tier approach: first tries to close context, then browser.
        Handles cleanup errors gracefully to avoid hanging processes.

        Args:
            instance: The SharedPlaywrightBrowser instance to clean up
            context: The browser context to clean up
        """
        if not instance or not hasattr(instance, 'browser'):
            return

        browser = instance.browser

        try:
            # Close context first
            if context:
                try:
                    context.close()
                    g_logger.debug("Browser context closed successfully")
                    time.sleep(0.5)
                except Exception as e:
                    g_logger.warning(f"Context cleanup failed: {e}")

            # Close browser
            if hasattr(browser, 'close'):
                try:
                    browser.close()
                    g_logger.debug("Browser closed successfully")
                    time.sleep(0.5)
                except Exception as e:
                    g_logger.warning(f"Browser cleanup failed: {e}")

        except Exception as e:
            g_logger.warning(f"All cleanup methods failed: {e}")

    @classmethod
    def _cleanup_lingering_processes(cls):
        """
        Clean up only truly orphaned browser processes.
        Only kill processes that are very old (>5 minutes) and appear to be orphans.
        This is called periodically to prevent accumulation without being too aggressive.
        """
        try:
            import subprocess
            import os
            import time as time_module

            current_time = time_module.time()

            # Find browser processes and check their age
            browser_result = subprocess.run(['pgrep', '-f', 'chrome.*--'], capture_output=True, text=True, timeout=5)
            browser_count = 0
            if browser_result.returncode == 0 and browser_result.stdout.strip():
                browser_pids = browser_result.stdout.strip().split('\n')

                for browser_pid in browser_pids:
                    try:
                        # Check if this process belongs to our current process tree
                        our_pgid = os.getpgid(os.getpid())
                        try:
                            process_pgid = os.getpgid(int(browser_pid))
                            # If it's not in our process group, it might be from another request/session
                            # Be more conservative - only kill processes that are very old
                            if process_pgid != our_pgid:
                                # Check process age using /proc filesystem
                                try:
                                    with open(f'/proc/{browser_pid}/stat', 'r') as f:
                                        stat_data = f.read().split()
                                        start_time_ticks = int(stat_data[21])
                                        # Convert jiffies to seconds (rough approximation)
                                        start_time_seconds = start_time_ticks / 100.0
                                        process_age = current_time - start_time_seconds

                                        # Only kill if process is older than 5 minutes (300 seconds)
                                        if process_age > 300:
                                            g_logger.warning(f"Cleanup: killing old orphaned browser process {browser_pid} (age: {process_age:.1f}s)")
                                            try:
                                                os.kill(int(browser_pid), 9)  # SIGKILL
                                                browser_count += 1
                                                time.sleep(0.1)
                                            except (OSError, ProcessLookupError):
                                                pass  # Process might have already died
                                except (FileNotFoundError, ValueError):
                                    # Process might have died, skip it
                                    pass
                        except (OSError, ProcessLookupError):
                            # Process might have died, skip it
                            pass
                    except (OSError, ValueError):
                        # Process might have died, skip it
                        pass

            if browser_count > 0:
                g_logger.info(f"Cleanup: killed {browser_count} old orphaned browser processes")
            else:
                g_logger.debug("Cleanup: no old orphaned browser processes found")

        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            g_logger.debug(f"Cleanup: unable to check for orphaned browser processes: {e}")

    @classmethod
    def force_cleanup(cls):
        """
        Force shutdown and cleanup of all browser instances.

        This method can be called manually to ensure all browsers
        are properly shut down, useful for debugging or emergency cleanup.
        """
        g_logger.info("Forcing Playwright browser cleanup...")
        with cls._lock:
            for instance, context, _ in cls._instances.values():
                cls._cleanup_instance(instance, context)
            cls._instances.clear()
            # Reset backward compatibility attributes
            cls._instance = None
            cls._shutdown_initiated = False
            
            # Stop Playwright
            if cls._playwright:
                try:
                    cls._playwright.stop()
                    cls._playwright = None
                except Exception as e:
                    g_logger.warning(f"Error stopping Playwright: {e}")
            
            g_logger.info("Force cleanup completed")

    @classmethod
    def reset_for_testing(cls):
        """
        Reset the class state for testing purposes.
        """
        g_logger.info("Resetting SharedPlaywrightBrowser for testing...")
        cls.force_cleanup()

# =============================================================================
# GLOBAL CLEANUP FUNCTION
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
        
    except (ValueError, AttributeError) as e:
        g_logger.error(f"Error parsing relative time '{time_text}': {e}")
        return None, None

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
                all_links = post.query_selector_all('a')
                links_info = [a.get_attribute('href') or 'NO_HREF' for a in all_links[:3]]
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


def extract_post_data(post, config, url, use_playwright):
    """
    Extract post data from a web element using the provided configuration.
    
    Parses title, link, and other metadata from a post element using either
    Playwright Locator or BeautifulSoup object depending on the extraction method.
    
    Args:
        post: Locator (Playwright) or Tag (BeautifulSoup) containing post data
        config (dict): Configuration dictionary with selectors and settings
        url (str): Base URL for resolving relative links
        use_playwright (bool): Whether using Playwright or BeautifulSoup for extraction
        
    Returns:
        dict: Extracted post data with title, link, id, summary, and timestamps, or None if extraction fails
    """
    # Special handling for RSS feeds loaded through Playwright
    if use_playwright and config.post_container == "pre":
        try:
            # Get the raw XML content from the pre tag
            xml_content = post.text_content()
            
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
        # Special case: if title_selector equals post_container, use the post element itself
        if config.title_selector == config.post_container:
            g_logger.info(f"Using special case title extraction for {url}: title_selector='{config.title_selector}' == post_container='{config.post_container}'")
            title = post.text_content().strip()
            # Fallbacks for anchors or elements with empty visible text
            if not title:
                try:
                    # Playwright Locator path
                    title = post.get_attribute('title') or post.get_attribute('innerText') or ''
                    title = (title or '').strip()
                except Exception:
                    pass
            g_logger.debug(f"Raw post text: {repr(title)}")
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
            title = title.strip()
            g_logger.debug(f"Cleaned post title: {repr(title)}")
        elif use_playwright:
            title_element = post.locator(config.title_selector).first
            title = title_element.text_content().strip()
        else:
            title_element = post.select_one(config.title_selector)
            if not title_element:
                g_logger.debug(f"No title element found with selector '{config.title_selector}'")
                _log_debugging_info(post, use_playwright, "title")
                return None
            title = title_element.text.strip()
    except Exception as e:
        g_logger.error(f"Error extracting title with selector '{config.title_selector}': {e}")
        _log_debugging_info(post, use_playwright, "title")
        return None
    
    if len(title.split()) < 2:
        return None
    
    try:
        if use_playwright:
            link_element = post.locator(config.link_selector).first
            link = link_element.get_attribute(config.link_attr)
        else:
            link_element = post.select_one(config.link_selector)
            if not link_element:
                g_logger.info(f"No link element found with selector '{config.link_selector}'")
                _log_debugging_info(post, use_playwright, "link")
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
        _log_debugging_info(post, use_playwright, "link")
        return None
    
    filter_pattern = config.filter_pattern
    if filter_pattern and filter_pattern not in link:
        return None
    
    # Extract published date if feature is enabled and selector is provided
    published_parsed = None
    published = None
    
    if ENABLE_DATE_EXTRACTION and "published_selector" in config:
        try:
            if use_playwright:
                # Handle XPath selectors (starting with .// or //)
                if config.published_selector.startswith(('.//', '//')):
                    date_element = post.locator(f"xpath={config.published_selector}").first
                    date_text = date_element.text_content().strip()
                else:
                    # Handle CSS selectors
                    date_element = post.locator(config.published_selector).first
                    date_text = date_element.text_content().strip()
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
        "summary": post.text_content().strip() if use_playwright else post.text.strip(),
        "published": published,
        "published_parsed": published_parsed
    }

# =============================================================================
# MAIN SITE FETCHING FUNCTION
# =============================================================================

def fetch_site_posts(url, user_agent):
    """
    Fetch posts from a website using appropriate method based on configuration.
    
    Determines the best method to fetch content (Playwright vs requests) based on
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

    if config.needs_selenium:  # Note: still using needs_selenium flag for compatibility
        if config.use_random_user_agent:
            # Use random user agent to avoid detection (reuse existing REDDIT_USER_AGENT)
            user_agent = g_cs.get("REDDIT_USER_AGENT")

        # Acquire the fetch lock before starting the fetch operation
        lock_acquired = False
        try:
            lock_acquired = SharedPlaywrightBrowser.acquire_fetch_lock()
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

            browser, context = SharedPlaywrightBrowser.get_browser_context(config.needs_tor, user_agent)
            if not browser or not context:
                g_logger.error(f"Failed to get browser for {url}")
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
                page = context.new_page()
                page.goto(url, timeout=PLAYWRIGHT_TIMEOUT)
                # Server sees this GET request immediately - timing detection happens here

                if base_domain == "reddit.com":
                    pass
                else:
                    try:
                        # Use random timeout to avoid predictable patterns
                        random_timeout = random.uniform(15000, 25000)  # milliseconds
                        page.wait_for_selector(config.post_container, timeout=random_timeout)
                    except PlaywrightTimeoutError as wait_error:
                        g_logger.warning(f"Timeout waiting for elements on {url}: {wait_error}")
                        # Continue anyway, might still find some content

                posts = page.locator(config.post_container).all()
                if not posts:
                    content = page.content()
                    snippet = content[:500]
                    g_logger.info(f"No posts found for {url}. Page content snippet: {snippet}")
                    status = 204  # No content
                else:
                    for post in posts:
                        try:
                            entry_data = extract_post_data(post, config, url, use_playwright=True)
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
                SharedPlaywrightBrowser.release_fetch_lock()
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
                    entry = extract_post_data(post, config, url, use_playwright=False)
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
