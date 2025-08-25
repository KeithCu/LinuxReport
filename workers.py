"""
RSS Feed Worker Module

This module contains worker functions for fetching and processing RSS feeds in parallel.
It provides thread-safe feed fetching, domain-based parallel processing, and intelligent
caching mechanisms with object storage support.

Key Features:
- Parallel RSS feed fetching with domain-based throttling
- Thread-safe operations using distributed locking
- Object storage integration for feed caching
- Specialized handling for LWN.net feeds
- Reddit feed processing with TOR support
- Feed deduplication and similarity filtering

Author: LinuxReport System
License: See LICENSE file
"""

# Standard library imports
from datetime import datetime, timedelta
import concurrent.futures
import itertools
import os
import re
from time import mktime
import threading
from timeit import default_timer as timer
from urllib.parse import urlparse
from collections import defaultdict
import pickle
from abc import ABC, abstractmethod

# Third-party imports
import feedparser
from fake_useragent import UserAgent

# Local application imports
from feedfilter import merge_entries
from seleniumfetch import fetch_site_posts
from shared import (
    ALL_URLS, EXPIRE_WEEK, MAX_ITEMS, TZ,
    USER_AGENT, RssFeed, g_c, g_cs, g_cm, get_lock, GLOBAL_FETCH_MODE_LOCK_KEY,
    ENABLE_OBJECT_STORE_FEEDS, OBJECT_STORE_FEED_TIMEOUT,
    ENABLE_OBJECT_STORE_FEED_PUBLISH, g_logger
)
from Tor import fetch_via_tor
from app_config import DEBUG, USE_TOR
from object_storage_sync import smart_fetch, publish_bytes

# =============================================================================
# GLOBAL CONSTANTS AND CONFIGURATION
# =============================================================================

# Initialize UserAgent for Reddit requests
ua = UserAgent()

# Reddit user agent configuration - Reddit is sensitive to user agents
if not g_cs.has("REDDIT_USER_AGENT"):
    g_cs.put("REDDIT_USER_AGENT", ua.random, timeout=shared.EXPIRE_YEARS)

USER_AGENT_RANDOM = g_cs.get("REDDIT_USER_AGENT")

# Regular expression for extracting links from HTML content
LINK_REGEX = re.compile(r'href=["\\]["\\](.*?)["\\]["\\]')

# =============================================================================
# FETCHER STRATEGY PATTERN
# =============================================================================

class FetcherStrategy(ABC):
    """Abstract base class for a feed fetching strategy."""

    @abstractmethod
    def fetch(self, url, rss_info):
        """
        Fetches and processes a feed.

        Args:
            url (str): The URL of the feed to fetch.
            rss_info (RssInfo): The RssInfo object for the feed.

        Returns:
            list: A list of processed feed entries.
        """
        pass

class DefaultFetcher(FetcherStrategy):
    """The default strategy for fetching standard RSS/Atom feeds."""

    def fetch(self, url, rss_info):
        res = feedparser.parse(url, agent=USER_AGENT)
        if not res:
            return []
        
        new_entries = res['entries']
        return list(itertools.islice(new_entries, MAX_ITEMS))

class LwnFetcher(FetcherStrategy):
    """Strategy for handling the unique paywall logic of LWN.net feeds."""

    def fetch(self, url, rss_info):
        pending = g_c.get("lwn_pending") or {}
        displayed = g_c.get("lwn_displayed") or set()
        res = feedparser.parse(url, agent=USER_AGENT)
        now = datetime.now(TZ)
        ready = []
        
        for entry in res.entries:
            link = entry.link
            title = entry.get('title', '')
            pub = datetime.fromtimestamp(mktime(entry.published_parsed), tz=TZ)
            
            if title.startswith("[$]"):
                if link not in pending and link not in displayed:
                    pending[link] = {'title': title, 'published': pub}
                    g_logger.info(f"[LWN] Article locked, saving for future: {title} ({link}) at {pub.isoformat()}")
            else:
                if link not in displayed:
                    ready.append({'link': link, 'title': title, 'html_content': '', 'published': pub, 'published_parsed': entry.published_parsed})
                    displayed.add(link)
                    pending.pop(link, None)
        
        for link, info in list(pending.items()):
            if now - info['published'] >= timedelta(days=15):
                title = info['title']
                if title.startswith("[$]"):
                    title = title[3:].strip()
                
                import time
                ready.append({'link': link, 'title': title, 'html_content': '', 'published': now})
                displayed.add(link)
                pending.pop(link)
                g_logger.info(f"[LWN] Article now available for free: {info['title']} ({link}) at {now.isoformat()}")
        
        ready.sort(key=lambda x: x['published'])
        g_c.put("lwn_pending", pending)
        g_c.put("lwn_displayed", displayed)
        return ready

class RedditFetcher(FetcherStrategy):
    """Strategy for fetching Reddit feeds, with optional Tor support."""

    def fetch(self, url, rss_info):
        if USE_TOR:
            g_logger.info(f"Using TOR proxy for Reddit URL: {url}")
            res = fetch_via_tor(url, rss_info.site_url)
        else:
            res = feedparser.parse(url, agent=USER_AGENT_RANDOM)

        if not res:
            return []

        new_entries = res['entries']
        return list(itertools.islice(new_entries, MAX_ITEMS))

class SeleniumFetcher(FetcherStrategy):
    """Strategy for feeds that require JavaScript rendering, using Selenium."""

    def fetch(self, url, rss_info):
        res = fetch_site_posts(rss_info.site_url, USER_AGENT)
        if not res:
            return []
        
        new_entries = res['entries']
        return list(itertools.islice(new_entries, MAX_ITEMS))

def get_fetcher(url):
    """
    Factory function that returns the appropriate fetcher strategy for a given URL.
    """
    if "lwn.net" in url:
        return LwnFetcher()
    if "reddit" in url:
        return RedditFetcher()
    if "fakefeed" in url:
        return SeleniumFetcher()
    return DefaultFetcher()

# =============================================================================
# CORE WORKER FUNCTIONS
# =============================================================================

def load_url_worker(url):
    """
    Background worker to fetch and process a single RSS feed URL.
    
    This function handles the complete lifecycle of RSS feed processing:
    - Acquires thread-safe locks to prevent duplicate fetching
    - Attempts object storage retrieval first (if enabled)
    - Falls back to standard RSS parsing if needed
    - Processes and filters feed entries
    - Handles special cases (LWN.net, Reddit)
    - Publishes processed feeds to object store
    - Updates local cache with results
    
    Args:
        url (str): The RSS feed URL to process
        
    Returns:
        None: Results are stored in the global cache
    """
    rss_info = ALL_URLS[url]
    lock_key = f"feed_fetch:{url}"

    # Use distributed locking to ensure only one process fetches this URL at a time
    with get_lock(lock_key, owner_prefix=f"feed_worker_{os.getpid()}") as lock:
        if not lock.locked():
            g_logger.warning(f"Could not acquire lock for {url}, another process is fetching.")
            return

        start = timer()

        if ENABLE_OBJECT_STORE_FEEDS:
            content, _ = smart_fetch(url, cache_expiry=OBJECT_STORE_FEED_TIMEOUT)
            if content:
                try:
                    rssfeed = pickle.loads(content)
                    if isinstance(rssfeed, RssFeed):
                        g_c.put(url, rssfeed, timeout=EXPIRE_WEEK)
                        g_c.set_last_fetch(url, datetime.now(TZ), timeout=EXPIRE_WEEK)
                        g_logger.info(f"Successfully fetched processed feed from object store: {url}")
                        return
                except Exception as e:
                    g_logger.error(f"Error parsing object store feed for {url}: {e}")

        fetcher = get_fetcher(url)
        new_entries = fetcher.fetch(url, rss_info)

        if not new_entries:
            g_logger.warning(f"No entries found for {url}.")
            # Continue processing - let the rest of the function handle empty entries

        for entry in new_entries:
            entry['underlying_url'] = entry.get('origin_link', entry.get('link', ''))
            if 'content' in entry and entry['content']:
                entry['html_content'] = entry['content'][0].get('value', '')
            else:
                entry['html_content'] = entry.get('summary', '')

            if not entry.get('published_parsed'):
                import time
                entry['published_parsed'] = time.gmtime()
                entry['published'] = time.strftime('%a, %d %b %Y %H:%M:%S GMT', entry['published_parsed'])

            if "reddit" in url:
                if "reddit" not in entry.get('underlying_url', ''):
                    entry['link'] = entry['underlying_url']
                else:
                    links = LINK_REGEX.findall(entry.get('html_content', ''))
                    links = [lnk for lnk in links if 'reddit.com' not in lnk]
                    if links:
                        entry['link'] = links[0]

        old_feed = g_c.get(url)
        new_count = len(new_entries)
        if old_feed and old_feed.entries:
            new_count = len(set(e.get('link') for e in new_entries) - set(e.get('link') for e in old_feed.entries))
            entries = merge_entries(new_entries, old_feed.entries)
        else:
            entries = new_entries

        entries = list(itertools.islice(entries, MAX_ITEMS))
        shared.history.update_fetch(url, new_count)

        top_articles = []
        if old_feed and old_feed.entries:
            previous_top_5 = set(e['link'] for e in old_feed.entries[:5])
            current_top_5 = set(e['link'] for e in entries[:5])
            if previous_top_5 == current_top_5:
                top_articles = old_feed.top_articles

        rssfeed = RssFeed(entries, top_articles=top_articles)

        if ENABLE_OBJECT_STORE_FEED_PUBLISH:
            try:
                feed_data = pickle.dumps(rssfeed)
                publish_bytes(feed_data, url)
                g_logger.info(f"Successfully published feed to object store: {url}")
            except Exception as e:
                g_logger.error(f"Error publishing feed to object store for {url}: {e}")

        g_c.put(url, rssfeed, timeout=EXPIRE_WEEK)
        g_c.set_last_fetch(url, datetime.now(TZ), timeout=EXPIRE_WEEK)

        if len(entries) > 2:
            g_cm.delete(rss_info.site_url)
            
        end = timer()
        g_logger.info(f"Parsing from: {url}, in {end - start:f}.")

# =============================================================================
# LOCKING AND THREADING UTILITIES
# =============================================================================

def _acquire_fetch_lock():
    """
    Acquire the global fetch lock with timeout.
    
    Returns:
        SqliteLock or None: The acquired lock object, or None if acquisition failed
    """
    lock = get_lock(GLOBAL_FETCH_MODE_LOCK_KEY, owner_prefix=f"fetch_mode_{os.getpid()}")
    if lock.acquire(timeout_seconds=60, wait=True):
        g_logger.info("Acquired global fetch lock.")
        return lock
    else:
        g_logger.warning("Failed to acquire global fetch lock after waiting.")
        return None

def _check_fetch_lock_available():
    """
    Check if fetch lock is available without acquiring it.
    
    Returns:
        bool: True if lock is available, False otherwise
    """
    check_lock = get_lock(GLOBAL_FETCH_MODE_LOCK_KEY, owner_prefix=f"fetch_check_{os.getpid()}")
    if check_lock.acquire(wait=False):
        check_lock.release()
        return True
    return False

# =============================================================================
# DOMAIN PROCESSING UTILITIES
# =============================================================================

def get_domain(url):
    """
    Extract base domain from URL for grouping purposes.
    
    Args:
        url (str): The URL to extract domain from
        
    Returns:
        str: The base domain (e.g., 'bandcamp.com' from 'https://news.bandcamp.com/feed')
    """
    try:
        netloc = urlparse(url).netloc
        # Split the netloc into parts
        parts = netloc.split('.')
        # Return the last two parts as the base domain (e.g., bandcamp.com)
        return '.'.join(parts[-2:]) if len(parts) > 1 else netloc
    except:
        return url

def process_domain_urls(urls):
    """
    Process URLs from the same domain sequentially to avoid overwhelming servers.
    
    Args:
        urls (list): List of URLs from the same domain to process
    """
    for url in urls:
        try:
            load_url_worker(url)
        except Exception as exc:  # noqa: E722
            g_logger.error(f'{url} generated an exception: {exc}')

def process_urls_in_parallel(urls, description="processing"):
    """
    Process URLs in parallel while ensuring no domain gets multiple simultaneous requests.
    
    This function implements intelligent parallel processing that:
    - Groups URLs by domain to prevent server overload
    - Processes different domains in parallel
    - Processes URLs from the same domain sequentially
    - Uses thread pools for efficient resource management
    
    Args:
        urls (list): List of URLs to process
        description (str): Description of the operation for logging purposes
    """
    # Group URLs by domain for intelligent parallel processing
    domain_to_urls = defaultdict(list)
    for url in urls:
        domain = get_domain(url)
        domain_to_urls[domain].append(url)

    g_logger.info(f"{description.capitalize()} {len(urls)} URLs with domain-based parallel processing...")
    
    # Process each domain's URLs sequentially, but different domains in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=10 if not DEBUG else 1) as executor:
        futures = []
        for domain, domain_urls in domain_to_urls.items():
            # Submit a task for each domain that will process its URLs sequentially
            future = executor.submit(process_domain_urls, domain_urls)
            futures.append(future)

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()  # Ensure exceptions in workers are raised
            except Exception as exc:  # noqa: E722
                g_logger.error(f'Domain processing generated an exception during {description}: {exc}')

# =============================================================================
# MAIN FETCH OPERATIONS
# =============================================================================

def fetch_urls_parallel(urls):
    """
    Fetch multiple URLs in parallel with proper locking and domain management.
    
    This is the main entry point for parallel URL fetching. It ensures
    thread safety and efficient resource usage.
    
    Args:
        urls (list): List of URLs to fetch in parallel
    """
    lock = _acquire_fetch_lock()
    if not lock:
        g_logger.warning("Aborting parallel fetch due to inability to acquire global lock.")
        return

    try:
        process_urls_in_parallel(urls, "fetching")
    finally:
        lock.release()
        g_logger.info("Released global fetch lock.")

def refresh_thread():
    """
    Background thread function to refresh expired RSS feeds.
    
    This function:
    - Checks all configured RSS feeds for expiration
    - Identifies feeds that need refreshing
    - Processes them in parallel with domain-based throttling
    - Maintains proper locking throughout the operation
    """
    lock = _acquire_fetch_lock()
    if not lock:
        g_logger.warning("Aborting refresh thread due to inability to acquire global lock.")
        return

    try:
        # Collect URLs that need refreshing
        urls_to_refresh = []

        all_urls = list(ALL_URLS.keys())
        last_fetch_cache = g_c.get_all_last_fetches(all_urls)
        
        for url, rss_info in ALL_URLS.items():
            if rss_info.logo_url != "Custom.png":
                
                last_fetch = last_fetch_cache.get(url)
                
                # Only check expiration if we have a feed or if we're checking a non-custom site
                if g_c.has_feed_expired(url, last_fetch):
                    urls_to_refresh.append(url)

        if not urls_to_refresh:
            g_logger.info("No feeds need refreshing in this cycle.")
            return

        process_urls_in_parallel(urls_to_refresh, "refreshing")
    finally:
        lock.release()
        g_logger.info("Released global fetch lock after refresh.")

def fetch_urls_thread():
    """
    Start a background thread to refresh RSS feeds.
    
    This function implements a safety check to prevent multiple refresh
    operations from running simultaneously. It only starts a new refresh
    thread if no other fetch/refresh operation is currently running.
    """
    if not _check_fetch_lock_available():
        g_logger.info("Fetch/refresh operation already in progress. Skipping background refresh trigger.")
        return

    g_logger.info("No fetch operation running. Starting background refresh thread...")
    t = threading.Thread(target=refresh_thread, args=())
    t.daemon = True
    t.start()