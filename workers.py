# This file contains worker functions for fetching and processing RSS feeds.
# Functions include parallel fetching, thread management, and feed processing.

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

# Third-party imports
import feedparser
from fake_useragent import UserAgent
ua = UserAgent()

# Local application imports
import shared
from feedfilter import filter_similar_titles, merge_entries, prefilter_news
from seleniumfetch import fetch_site_posts
from shared import (
    ALL_URLS, EXPIRE_WEEK, MAX_ITEMS, TZ,
    USER_AGENT, RssFeed, g_c, g_cs, g_cm, get_lock, GLOBAL_FETCH_MODE_LOCK_KEY
)
from Tor import fetch_via_tor
from models import DEBUG, USE_TOR

 #Reddit is a pain, so hide user_agent
if not g_cs.has("REDDIT_USER_AGENT"):
    g_cs.put("REDDIT_USER_AGENT", ua.random, timeout = shared.EXPIRE_YEARS)

USER_AGENT_RANDOM = g_cs.get("REDDIT_USER_AGENT")

LINK_REGEX = re.compile(r'href=["\'](.*?)["\']')

# Worker function to fetch and process a single RSS feed.
def load_url_worker(url):
    """Background worker to fetch a URL. Handles locking."""
    rss_info = ALL_URLS[url]
    lock_key = f"feed_fetch:{url}"

    # Use the DiskcacheSqliteLock to ensure only one process fetches this URL at a time
    with get_lock(lock_key, owner_prefix=f"feed_worker_{os.getpid()}") as lock:
        if not lock.locked():
            print(f"Could not acquire lock for {url}, another process is fetching.")
            return

        start = timer()
        rssfeed = None
        res = None  # Ensure res is always defined

        if "lwn.net" in url:
            new_entries = handle_lwn_feed(url)
        else:
            # Standard feed parsing logic
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
            new_entries = prefilter_news(url, res)
            new_entries = filter_similar_titles(url, new_entries)
            #Trim the entries to the limit before compare so it doesn't find 500 new entries.
            new_entries = list(itertools.islice(new_entries, MAX_ITEMS))

        # Added detailed logging when no entries are found
        if len(new_entries) == 0:
            if res is not None:
                http_status = res.get("status", "unknown") if hasattr(res, "get") else "unknown"
                bozo_exception = res.get("bozo_exception", "None") if hasattr(res, "get") else "None"
            else:
                http_status = "N/A (LWN feed)"
                bozo_exception = "N/A (LWN feed)"
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
        old_feed = g_c.get(url)
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
        g_c.put(url, rssfeed, timeout=EXPIRE_WEEK)
        g_c.set_last_fetch(url, datetime.now(TZ), timeout=EXPIRE_WEEK)

        if len(entries) > 2:
            g_cm.delete(rss_info.site_url)

        end = timer()
        print(f"Parsing from: {url}, in {end - start:f}.")
        # Lock is automatically released by the 'with' statement

def handle_lwn_feed(url):
    pending = g_c.get("lwn_pending") or {}
    displayed = g_c.get("lwn_displayed") or set()
    res = feedparser.parse(url, agent=USER_AGENT)
    now = datetime.now(TZ)
    ready = []
    for entry in res.entries:
        link = entry.link
        title = entry.get('title','')
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
    # sort by publication/availability date for interleaving
    ready.sort(key=lambda x: x['published'])
    g_c.put("lwn_pending", pending)
    g_c.put("lwn_displayed", displayed)
    return ready

def wait_and_set_fetch_mode():
    """Acquires a global lock to prevent thundering herd for fetch cycles."""
    # Attempt to acquire the lock, waiting if necessary
    lock = get_lock(GLOBAL_FETCH_MODE_LOCK_KEY, owner_prefix=f"fetch_mode_{os.getpid()}")
    if lock.acquire(timeout_seconds=60, wait=True): # Wait up to 60 seconds
        print("Acquired global fetch lock.")
        return lock
    else:
        print("Failed to acquire global fetch lock after waiting.")
        return None

def get_domain(url):
    """Extract domain from URL."""
    try:
        return urlparse(url).netloc
    except:
        return url

def process_domain_urls(urls):
    """Process URLs from the same domain sequentially."""
    for url in urls:
        try:
            load_url_worker(url)
        except Exception as exc:  # noqa: E722
            print(f'{url} generated an exception: {exc}')

def process_urls_in_parallel(urls, description="processing"):
    """Process URLs in parallel while ensuring no domain gets multiple simultaneous requests.
    
    Args:
        urls: List of URLs to process
        description: Description of the operation for logging purposes
    """
    # Group URLs by domain
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

def fetch_urls_parallel(urls):
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
    lock = wait_and_set_fetch_mode()
    if not lock:
        print("Aborting refresh thread due to inability to acquire global lock.")
        return

    try:
        # Collect URLs that need refreshing
        urls_to_refresh = []
        for url, rss_info in ALL_URLS.items():
            if g_c.has_feed_expired(url) and rss_info.logo_url != "Custom.png":
                urls_to_refresh.append(url)

        if not urls_to_refresh:
            print("No feeds need refreshing in this cycle.")
            return

        process_urls_in_parallel(urls_to_refresh, "refreshing")
    finally:
        lock.release()
        print("Released global fetch lock after refresh.")

# Start a background thread to refresh RSS feeds.
def fetch_urls_thread():
    # Check if a fetch/refresh operation is already running using the global lock.
    
    # Create a lock instance just for checking, don't hold it long.
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