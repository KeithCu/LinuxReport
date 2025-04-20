# This file contains worker functions for fetching and processing RSS feeds.
# Functions include parallel fetching, thread management, and feed processing.

from datetime import datetime
import concurrent.futures
import itertools
# Standard library imports
import os
import re
import threading
from timeit import default_timer as timer

# Third-party imports
import feedparser

import shared
from feedfilter import filter_similar_titles, merge_entries, prefilter_news
from seleniumfetch import fetch_site_posts
# Local application imports
from shared import (
    ALL_URLS, DEBUG, EXPIRE_WEEK, MAX_ITEMS, TZ,
    USE_TOR, USER_AGENT, RssFeed, g_c, DiskcacheSqliteLock, GLOBAL_FETCH_MODE_LOCK_KEY
)
from Tor import fetch_via_tor

LINK_REGEX = re.compile(r'href=["\'](.*?)["\']')

# Worker function to fetch and process a single RSS feed.
def load_url_worker(url):
    """Background worker to fetch a URL. Handles locking."""
    rss_info = ALL_URLS[url]
    lock_key = f"feed_fetch:{url}"

    # Use the DiskcacheSqliteLock to ensure only one process fetches this URL at a time
    with DiskcacheSqliteLock(lock_key, owner_prefix=f"feed_worker_{os.getpid()}") as lock:
        if not lock.locked():
            print(f"Could not acquire lock for {url}, another process might be fetching.")
            # Optionally wait briefly or return, depending on desired behavior
            # For now, just return, assuming the other process will succeed.
            return

        # --- Start of locked section ---
        start = timer()
        rssfeed = None

        if USE_TOR and "reddit" in url:
            print(f"Using TOR proxy for Reddit URL: {url}")
            res = fetch_via_tor(url, rss_info.site_url)
        elif "fakefeed" in url:
            res = fetch_site_posts(rss_info.site_url, USER_AGENT)
        else:
            res = feedparser.parse(url, agent=USER_AGENT)

        new_entries = prefilter_news(url, res)
        new_entries = filter_similar_titles(url, new_entries)

        #Trim the entries to the limit before compare so it doesn't find 500 new entries.
        new_entries = list(itertools.islice(new_entries, MAX_ITEMS))

        # Added detailed logging when no entries are found
        if len(new_entries) == 0:
            http_status = res.get("status", "unknown") if hasattr(res, "get") else "unknown"
            bozo_exception = res.get("bozo_exception", "None") if hasattr(res, "get") else "None"
            print(f"No entries found for {url}. HTTP status: {http_status}. Bozo exception: {bozo_exception}")

        for entry in new_entries:
            entry['underlying_url'] = entry.get('origin_link', entry.get('link', ''))
            if 'content' in entry and entry['content']:
                entry['html_content'] = entry['content'][0].get('value', '')
            else:
                entry['html_content'] = entry.get('summary', '')

            # If processing a Reddit feed, override the link
            if "reddit" in url:
                if "reddit" not in entry.get('underlying_url'):
                    entry['link'] = entry['underlying_url']
                    #del entry['origin_link']
                else:
                    links = LINK_REGEX.findall(entry.get('html_content', ''))
                    # Filter out reddit links:
                    links = [lnk for lnk in links if 'reddit' not in lnk]
                    if links:
                        #Pick the first match for now
                        entry['link'] = links[0]
                        #print (entry['link'])

        # Merge with cached entries (if any) to retain history.
        old_feed = g_c.get_feed(url)
        new_count = len(new_entries)
        if old_feed and old_feed.entries:
            new_count = len(set(e.get('link') for e in new_entries) - set(e.get('link') for e in old_feed.entries))
            entries = merge_entries(new_entries, old_feed.entries)
        else:
            entries = new_entries

        #Trim the limit again after merge.
        entries = list(itertools.islice(entries, MAX_ITEMS))

        shared.history.update_fetch(url, new_count)

        top_articles = []
        if old_feed and old_feed.entries:
            previous_top_5 = set(e['link'] for e in old_feed.entries[:5])
            current_top_5 = set(e['link'] for e in entries[:5])
            if previous_top_5 == current_top_5:
                top_articles = old_feed.top_articles

        rssfeed = RssFeed(entries, top_articles=top_articles)
        g_c.set_feed(url, rssfeed, timeout=EXPIRE_WEEK)
        g_c.set_last_fetch(url, datetime.now(TZ), timeout=EXPIRE_WEEK)

        if len(entries) > 2:
            g_c.delete(rss_info.site_url) # Delete template cache

        # No need to delete FETCHPID anymore
        end = timer()
        print(f"Parsing from: {url}, in {end - start:f}.")
        # --- End of locked section ---
        # Lock is automatically released by the 'with' statement

def wait_and_set_fetch_mode():
    """Acquires a global lock to prevent thundering herd for fetch cycles."""
    # Attempt to acquire the lock, waiting if necessary
    lock = DiskcacheSqliteLock(GLOBAL_FETCH_MODE_LOCK_KEY, owner_prefix=f"fetch_mode_{os.getpid()}")
    if lock.acquire(wait=True, max_wait_seconds=60): # Wait up to 60 seconds
        print("Acquired global fetch lock.")
        return lock # Return the acquired lock object
    else:
        print("Failed to acquire global fetch lock after waiting.")
        return None # Indicate failure

# Fetch multiple RSS feeds in parallel.
def fetch_urls_parallel(urls):
    lock = wait_and_set_fetch_mode()
    if not lock:
        print("Aborting parallel fetch due to inability to acquire global lock.")
        return

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10 if not DEBUG else 1) as executor:
            future_to_url = {executor.submit(load_url_worker, url): url for url in urls}

            for future in concurrent.futures.as_completed(future_to_url):
                try:
                    future.result() # Ensure exceptions in workers are raised
                except Exception as exc:
                    print(f'{future_to_url[future]} generated an exception: {exc}')
    finally:
        lock.release() # Ensure lock is released
        print("Released global fetch lock.")

# Refresh all expired RSS feeds in a separate thread.
def refresh_thread():
    lock = wait_and_set_fetch_mode()
    if not lock:
        print("Aborting refresh thread due to inability to acquire global lock.")
        return

    try:
        urls_to_refresh = []
        for url, rss_info in ALL_URLS.items():
            if g_c.has_feed_expired(url) and rss_info.logo_url != "Custom.png":
                urls_to_refresh.append(url)

        if not urls_to_refresh:
            print("No feeds need refreshing in this cycle.")
            return

        print(f"Refreshing {len(urls_to_refresh)} expired feeds sequentially...")
        for url in urls_to_refresh:
            try:
                load_url_worker(url)
            except Exception as exc:
                print(f'{url} generated an exception during refresh: {exc}')

    finally:
        lock.release()
        print("Released global fetch lock after refresh.")

# Start a background thread to refresh RSS feeds.
def fetch_urls_thread():
    # Check if a fetch/refresh operation is already running using the global lock.
    
    # Create a lock instance just for checking, don't hold it long.
    check_lock = DiskcacheSqliteLock(GLOBAL_FETCH_MODE_LOCK_KEY, owner_prefix=f"fetch_check_{os.getpid()}")

    # Try to acquire the lock without waiting.
    if not check_lock.acquire(wait=False):
        # If acquire returns False, it means the lock is held by another process/thread.
        print("Fetch/refresh operation already in progress. Skipping background refresh trigger.")
        # No need to release check_lock here as it was never acquired.
        return
    else:
        # If acquire returns True, it means no fetch/refresh was running *at this moment*.
        # We acquired the lock, but we don't need to hold it. Release it immediately
        # so the actual refresh_thread (or a parallel fetch) can acquire it.
        check_lock.release()
        print("No fetch operation running. Starting background refresh thread...")
        # Proceed to start the thread. refresh_thread will acquire the lock properly (waiting if needed).
        t = threading.Thread(target=refresh_thread, args=())
        t.daemon = True
        t.start()