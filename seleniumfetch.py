"""
seleniumfetch.py

Provides functions to fetch and parse posts from sites requiring JavaScript rendering or special handling, using Selenium and BeautifulSoup. Includes site-specific configurations and helpers.
"""

import os
import time
import threading
# Standard library imports
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

# Third-party imports
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

# Local imports
from shared import g_cs, CUSTOM_FETCH_CONFIG

def create_driver(use_tor, user_agent):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={user_agent}")
    if use_tor:
        options.add_argument("--proxy-server=socks5://127.0.0.1:9050")

    service = Service(ChromeDriverManager(
        chrome_type=ChromeType.CHROMIUM).install())
    driver = webdriver.Chrome(service=service, options=options)
    # Disable compression by setting Accept-Encoding to identity via CDP
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Accept-Encoding": "identity"}})
    return driver

class SharedSeleniumDriver:
    _instance = None
    _lock = threading.Lock()
    _fetch_lock = threading.Lock()  # New lock for synchronizing fetch operations
    _timer = None
    _timeout = 300  # 5 minutes

    def __init__(self, use_tor, user_agent):
        self.driver = create_driver(use_tor, user_agent)
        self.last_used = time.time()
        self.use_tor = use_tor
        self.user_agent = user_agent

    @classmethod
    def get_driver(cls, use_tor, user_agent):
        with cls._lock:
            if cls._instance is None or not cls._instance._is_valid(use_tor, user_agent):
                if cls._instance:
                    try:
                        cls._instance.driver.quit()
                    except Exception:
                        pass
                cls._instance = SharedSeleniumDriver(use_tor, user_agent)
            cls._instance.last_used = time.time()
            cls._reset_timer()
            return cls._instance.driver

    @classmethod
    def acquire_fetch_lock(cls):
        """Acquire the fetch lock to synchronize fetch operations"""
        return cls._fetch_lock.acquire()

    @classmethod
    def release_fetch_lock(cls):
        """Release the fetch lock after fetch operation is complete"""
        try:
            cls._fetch_lock.release()
        except RuntimeError:
            # Lock was not acquired, ignore
            pass

    @classmethod
    def _is_valid(cls, use_tor, user_agent):
        # Only reuse if config matches
        return (
            cls._instance and
            cls._instance.use_tor == use_tor and
            cls._instance.user_agent == user_agent and
            hasattr(cls._instance, 'driver')
        )

    @classmethod
    def _reset_timer(cls):
        if cls._timer:
            cls._timer.cancel()
        cls._timer = threading.Timer(cls._timeout, cls._shutdown)
        cls._timer.daemon = True
        cls._timer.start()

    @classmethod
    def _shutdown(cls):
        with cls._lock:
            if cls._instance:
                try:
                    cls._instance.driver.quit()
                except Exception:
                    pass
                cls._instance = None
                cls._timer = None

class FeedParserDict(dict):
    """Mimic feedparser's FeedParserDict for compatibility"""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"No attribute '{key}'")

# New helper function to extract post data
def extract_post_data(post, config, url, use_selenium):
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
            link = link_element.get(config["link_attr"])
            if link and link.startswith('/'):
                link = urljoin(url, link)
    except Exception:
        return None
    filter_pattern = config.get("filter_pattern", "")
    if filter_pattern and filter_pattern not in link:
        return None
    return {"title": title, "link": link, "id": link, "summary": post.text.strip()}

def fetch_site_posts(url, user_agent):
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
        SharedSeleniumDriver.acquire_fetch_lock()
        try:
            driver = SharedSeleniumDriver.get_driver(config["needs_tor"], user_agent)
            try:
                driver.get(url)
                if base_domain == "reddit.com":
                    pass
                else:
                    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, config["post_container"])))
                print(f"Some content loaded for {url} with agent: {user_agent}")
                posts = driver.find_elements(By.CSS_SELECTOR, config["post_container"])
                if not posts:
                    snippet = driver.page_source[:1000]
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
            response = requests.get(url, timeout=10)
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