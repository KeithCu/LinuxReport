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
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from shared import g_cs, CUSTOM_FETCH_CONFIG, g_logger
from app_config import FetchConfig

# =============================================================================
# CONSTANTS
# =============================================================================
PLAYWRIGHT_TIMEOUT = 30000
NETWORK_TIMEOUT = 20
DRIVER_RECYCLE_TIMEOUT = 300 # For backward compatibility

# =============================================================================
# SPECIAL SITE CONFIGURATIONS
# =============================================================================
class KeithcuRssFetchConfig(FetchConfig):
    def __new__(cls):
        return super().__new__(
            cls,
            needs_selenium=True,
            needs_tor=False,
            post_container="pre",
            title_selector="title",
            link_selector="link",
            link_attr="text",
            filter_pattern="",
            use_random_user_agent=False,
            published_selector=None
        )

KEITHCU_RSS_CONFIG = KeithcuRssFetchConfig()

# =============================================================================
# PLAYWRIGHT HELPER
# =============================================================================
def create_browser_context(playwright, use_tor, user_agent):
    g_logger.info(f"Creating Playwright browser with Tor: {use_tor}, User-Agent: {user_agent[:50]}...")
    try:
        browser = playwright.chromium.launch(headless=True)
        context_options = {
            "user_agent": user_agent,
            "viewport": {"width": 1920, "height": 1080},
            "ignore_https_errors": True,
            "java_script_enabled": True,
        }
        if use_tor:
            context_options["proxy"] = {"server": "socks5://127.0.0.1:9050"}
        context = browser.new_context(**context_options)
        return browser, context
    except Exception as e:
        g_logger.error(f"Error creating Playwright browser: {e}")
        raise

# =============================================================================
# BACKWARD COMPATIBILITY SHIMS
# =============================================================================
def cleanup_playwright_browsers():
    """No-op for backward compatibility."""
    pass

class SharedPlaywrightBrowser:
    """Placeholder for backward compatibility."""
    @staticmethod
    def get_browser_context(use_tor, user_agent): return None, None
    @staticmethod
    def force_cleanup(): pass

# =============================================================================
# CONTENT EXTRACTION
# =============================================================================
def extract_post_data(post, config, url, use_playwright):
    if use_playwright and config.post_container == "pre":
        try:
            xml_content = post.text_content()
            xml_soup = BeautifulSoup(xml_content, 'lxml-xml')
            items = xml_soup.find_all('item')
            results = []
            for item in items:
                title_tag, link_tag = item.find('title'), item.find('link')
                if title_tag and link_tag:
                    title, link = title_tag.get_text().strip(), link_tag.get_text().strip()
                    if len(title.split()) >= 2:
                        results.append({"title": title, "link": link, "id": link, "summary": title})
            return results
        except Exception as e:
            g_logger.error(f"Error parsing RSS content: {e}")
            return None

    try:
        title, link = None, None
        if use_playwright:
            title_element = post.locator(config.title_selector).first
            title = title_element.text_content().strip()
            link_element = post.locator(config.link_selector).first
            link = link_element.get_attribute(config.link_attr)
        else:
            title_element = post.select_one(config.title_selector)
            title = title_element.text.strip() if title_element else ""
            link_element = post.select_one(config.link_selector)
            link = link_element.get(config.link_attr) if link_element else ""

        if len(title.split()) < 2: return None
        if link and link.startswith('/'): link = urljoin(url, link)

        return {"title": title, "link": link, "id": link, "summary": title}
    except Exception as e:
        g_logger.error(f"Error extracting data with selector '{config.title_selector}': {e}")
        return None

# =============================================================================
# MAIN FETCHING FUNCTION
# =============================================================================
def fetch_site_posts(url, user_agent):
    parsed = urlparse(url)
    domain_parts = parsed.netloc.split('.')
    base_domain = '.'.join(domain_parts[-2:]) if len(domain_parts) > 2 else parsed.netloc
    config = CUSTOM_FETCH_CONFIG.get(base_domain) or CUSTOM_FETCH_CONFIG.get(parsed.netloc)
    
    if not config and "keithcu.com" in base_domain:
        config = KEITHCU_RSS_CONFIG
    
    if not config:
        g_logger.info(f"Configuration for '{base_domain}' not found.")
        return {'entries': [], 'status': 404}

    entries, status = [], 200

    if config.needs_selenium:
        if config.use_random_user_agent:
            user_agent = g_cs.get("REDDIT_USER_AGENT")

        with sync_playwright() as p:
            browser = None
            try:
                browser, context = create_browser_context(p, config.needs_tor, user_agent)
                page = context.new_page()
                page.goto(url, timeout=PLAYWRIGHT_TIMEOUT)

                if base_domain != "reddit.com":
                    page.wait_for_selector(config.post_container, timeout=15000)

                posts = page.locator(config.post_container).all()
                if not posts:
                    status = 204
                else:
                    for post in posts:
                        entry_data = extract_post_data(post, config, url, use_playwright=True)
                        if entry_data:
                            if isinstance(entry_data, list):
                                entries.extend(entry_data)
                            else:
                                entries.append(entry_data)
            except Exception as e:
                g_logger.error(f"Playwright error for {url}: {e}")
                status = 500
            finally:
                if browser: browser.close()
    else:
        headers = {'User-Agent': user_agent}
        try:
            response = requests.get(url, timeout=NETWORK_TIMEOUT, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            for post in soup.select(config.post_container):
                entry = extract_post_data(post, config, url, use_playwright=False)
                if entry:
                    entries.append(entry)
        except requests.RequestException as e:
            g_logger.error(f"Request error for {base_domain}: {e}")
            status = 500

    g_logger.info(f"Fetched {len(entries)} entries from {url}")
    return {
        'entries': entries, 'etag': "", 'modified': datetime.now(timezone.utc),
        'feed': {'title': url, 'link': url, 'description': ''},
        'href': url, 'status': status
    }