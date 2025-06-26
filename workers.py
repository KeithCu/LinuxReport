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

# Third-party imports
import feedparser
from fake_useragent import UserAgent

# Local application imports
import shared
from feedfilter import filter_similar_titles, merge_entries, prefilter_news
from seleniumfetch import fetch_site_posts
from shared import (
    ALL_URLS, EXPIRE_WEEK, MAX_ITEMS, TZ,
    USER_AGENT, RssFeed, g_c, g_cs, g_cm, get_lock, GLOBAL_FETCH_MODE_LOCK_KEY,
    ENABLE_OBJECT_STORE_FEEDS, OBJECT_STORE_FEED_TIMEOUT,
    ENABLE_OBJECT_STORE_FEED_PUBLISH
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
LINK_REGEX = re.compile(r'href=["\'](.*?)["\']')

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
    - Publishes processed feeds to object storage
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
            print(f"Could not acquire lock for {url}, another process is fetching.")
            return

        start = timer()
        rssfeed = None
        res = None  # Ensure res is always defined for error handling

        # =====================================================================
        # OBJECT STORAGE RETRIEVAL (if enabled)
        # =====================================================================
        use_object_store = ENABLE_OBJECT_STORE_FEEDS
        if use_object_store:
            # Use smart_fetch to get feed content with metadata
            content, metadata = smart_fetch(url, cache_expiry=OBJECT_STORE_FEED_TIMEOUT)
            if content:
                try:
                    # Parse the pickled RssFeed object from object store
                    rssfeed = pickle.loads(content)
                    if isinstance(rssfeed, RssFeed):
                        # Store directly in cache since it's already processed
                        g_c.put(url, rssfeed, timeout=EXPIRE_WEEK)
                        g_c.set_last_fetch(url, datetime.now(TZ), timeout=EXPIRE_WEEK)
                        print(f"Successfully fetched processed feed from object store: {url}")
                        return
                    else:
                        print(f"Invalid feed data type from object store for {url}")
                        return
                except Exception as e:
                    print(f"Error parsing object store feed for {url}: {e}")
                    return
            else:
                print(f"No content found in object store for {url}")
                return

        # =====================================================================
        # STANDARD RSS FEED PARSING
        # =====================================================================
        if "lwn.net" in url:
            new_entries = handle_lwn_feed(url)
        else:
            # Standard feed parsing logic
            if not use_object_store:  # Only use standard parsing if not using object store
                if USE_TOR and "reddit" in url:
                    print(f"Using TOR proxy for Reddit URL: {url}")
                    res = fetch_via_tor(url, rss_info.site_url)
                elif "fakefeed" in url:
                    res = fetch_site_posts(rss_info.site_url, USER_AGENT)
                else:
                    user_a = USER_AGENT
                    if "reddit" in url:
                        user_a = USER_AGENT_RANDOM
                    res = feedparser.parse(url, agent=user_a)

            if res:
                new_entries = prefilter_news(url, res)
                new_entries = filter_similar_titles(url, new_entries)
                # Trim the entries to the limit before comparison to avoid finding 500 new entries
                new_entries = list(itertools.islice(new_entries, MAX_ITEMS))
            else:
                new_entries = []

        # =====================================================================
        # ERROR HANDLING AND LOGGING
        # =====================================================================
        # Added detailed logging when no entries are found
        if len(new_entries) == 0:
            if res is not None:
                http_status = res.get("status", "unknown") if hasattr(res, "get") else "unknown"
                bozo_exception = res.get("bozo_exception", "None") if hasattr(res, "get") else "None"
            else:
                http_status = "N/A (LWN feed)"
                bozo_exception = "N/A (LWN feed)"
            print(f"No entries found for {url}. HTTP status: {http_status}. Bozo exception: {bozo_exception}")

        # =====================================================================
        # ENTRY PROCESSING AND ENHANCEMENT
        # =====================================================================
        for entry in new_entries:
            entry['underlying_url'] = entry.get('origin_link', entry.get('link', ''))
            if 'content' in entry and entry['content']:
                entry['html_content'] = entry['content'][0].get('value', '')
            else:
                entry['html_content'] = entry.get('summary', '')

            # Special handling for Reddit feeds - override links to external content
            if "reddit" in url:
                if "reddit" not in entry.get('underlying_url'):
                    entry['link'] = entry['underlying_url']
                else:
                    links = LINK_REGEX.findall(entry.get('html_content', ''))
                    # Filter out reddit links to get external content
                    links = [lnk for lnk in links if 'reddit' not in lnk]
                    if links:
                        # Pick the first match for now
                        entry['link'] = links[0]

        # =====================================================================
        # CACHE MERGING AND ENTRY LIMITING
        # =====================================================================
        # Merge with cached entries (if any) to retain history
        old_feed = g_c.get(url)
        new_count = len(new_entries)
        if old_feed and old_feed.entries:
            new_count = len(set(e.get('link') for e in new_entries) - set(e.get('link') for e in old_feed.entries))
            entries = merge_entries(new_entries, old_feed.entries)
        else:
            entries = new_entries

        # Trim the limit again after merge
        entries = list(itertools.islice(entries, MAX_ITEMS))

        shared.history.update_fetch(url, new_count)

        # =====================================================================
        # TOP ARTICLES PRESERVATION
        # =====================================================================
        top_articles = []
        if old_feed and old_feed.entries:
            previous_top_5 = set(e['link'] for e in old_feed.entries[:5])
            current_top_5 = set(e['link'] for e in entries[:5])
            if previous_top_5 == current_top_5:
                top_articles = old_feed.top_articles

        rssfeed = RssFeed(entries, top_articles=top_articles)

        # =====================================================================
        # OBJECT STORAGE PUBLISHING
        # =====================================================================
        # Publish feed to object store if enabled - publish exactly what we store locally
        if ENABLE_OBJECT_STORE_FEED_PUBLISH:
            try:
                # Pickle the RssFeed object for storage
                feed_data = pickle.dumps(rssfeed)
                publish_bytes(feed_data, url)
                print(f"Successfully published feed to object store: {url}")
            except Exception as e:
                print(f"Error publishing feed to object store for {url}: {e}")

        # =====================================================================
        # CACHE UPDATES AND CLEANUP
        # =====================================================================
        g_c.put(url, rssfeed, timeout=EXPIRE_WEEK)
        g_c.set_last_fetch(url, datetime.now(TZ), timeout=EXPIRE_WEEK)

        if len(entries) > 2:
            g_cm.delete(rss_info.site_url)
            
        end = timer()
        print(f"Parsing from: {url}, in {end - start:f}.")
        # Lock is automatically released by the 'with' statement

# =============================================================================
# SPECIALIZED FEED HANDLERS
# =============================================================================

def handle_lwn_feed(url):
    """
    Specialized handler for LWN.net feeds.
    
    LWN.net has a unique paywall system where articles are initially marked with [$]
    and become available after 15 days. This function manages the pending and
    displayed article states to handle this behavior.
    
    Args:
        url (str): The LWN.net RSS feed URL
        
    Returns:
        list: List of ready-to-display article entries
    """
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
                print(f"[LWN] Article locked, saving for future: {title} ({link}) at {pub.isoformat()}")
        else:
            if link not in displayed:
                ready.append({'link': link, 'title': title, 'html_content': '', 'published': pub})
                displayed.add(link)
                pending.pop(link, None)
    
    # Check for articles that have aged out of the paywall (15 days)
    for link, info in list(pending.items()):
        if now - info['published'] >= timedelta(days=15):
            title = info['title']
            # Remove [$] prefix if present
            if title.startswith("[$]"):
                title = title[3:].strip()
            ready.append({'link': link, 'title': title, 'html_content': '', 'published': now})
            displayed.add(link)
            pending.pop(link)
            print(f"[LWN] Article now available for free: {info['title']} ({link}) at {now.isoformat()}")
    
    # Sort by publication/availability date for proper interleaving
    ready.sort(key=lambda x: x['published'])
    g_c.put("lwn_pending", pending)
    g_c.put("lwn_displayed", displayed)
    return ready

# =============================================================================
# LOCKING AND THREADING UTILITIES
# =============================================================================

def wait_and_set_fetch_mode():
    """
    Acquires a global lock to prevent thundering herd for fetch cycles.
    
    This function implements a distributed locking mechanism to ensure that
    only one fetch operation runs at a time across all processes/threads.
    
    Returns:
        SqliteLock or None: The acquired lock object, or None if acquisition failed
    """
    # Attempt to acquire the lock, waiting if necessary
    lock = get_lock(GLOBAL_FETCH_MODE_LOCK_KEY, owner_prefix=f"fetch_mode_{os.getpid()}")
    if lock.acquire(timeout_seconds=60, wait=True):  # Wait up to 60 seconds
        print("Acquired global fetch lock.")
        return lock
    else:
        print("Failed to acquire global fetch lock after waiting.")
        return None

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
            print(f'{url} generated an exception: {exc}')

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

    print(f"{description.capitalize()} {len(urls)} URLs with domain-based parallel processing...")
    
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
                print(f'Domain processing generated an exception during {description}: {exc}')

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
    lock = wait_and_set_fetch_mode()
    if not lock:
        print("Aborting parallel fetch due to inability to acquire global lock.")
        return

    try:
        process_urls_in_parallel(urls, "fetching")
    finally:
        lock.release()  # Ensure lock is released
        print("Released global fetch lock.")

def refresh_thread():
    """
    Background thread function to refresh expired RSS feeds.
    
    This function:
    - Checks all configured RSS feeds for expiration
    - Identifies feeds that need refreshing
    - Processes them in parallel with domain-based throttling
    - Maintains proper locking throughout the operation
    """
    lock = wait_and_set_fetch_mode()
    if not lock:
        print("Aborting refresh thread due to inability to acquire global lock.")
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
            print("No feeds need refreshing in this cycle.")
            return

        process_urls_in_parallel(urls_to_refresh, "refreshing")
    finally:
        lock.release()
        print("Released global fetch lock after refresh.")

def fetch_urls_thread():
    """
    Start a background thread to refresh RSS feeds.
    
    This function implements a safety check to prevent multiple refresh
    operations from running simultaneously. It only starts a new refresh
    thread if no other fetch/refresh operation is currently running.
    """
    # Check if a fetch/refresh operation is already running using the global lock
    
    # Create a lock instance just for checking, don't hold it long
    check_lock = get_lock(GLOBAL_FETCH_MODE_LOCK_KEY, owner_prefix=f"fetch_check_{os.getpid()}")

    if not check_lock.acquire(wait=False):
        print("Fetch/refresh operation already in progress. Skipping background refresh trigger.")
        return
    else:
        # If acquire returns True, it means no fetch/refresh was running *at this moment*.
        # We acquired the lock, but we don't need to hold it. Release it immediately
        # so the actual refresh_thread (or a parallel fetch) can acquire it.
        check_lock.release()
        print("No fetch operation running. Starting background refresh thread...")
        t = threading.Thread(target=refresh_thread, args=())
        t.daemon = True
        t.start()