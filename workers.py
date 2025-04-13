# This file contains worker functions for fetching and processing RSS feeds.
# Functions include parallel fetching, thread management, and feed processing.

import os
import time
import itertools
from timeit import default_timer as timer
import concurrent.futures
from shared import ALL_URLS, g_c, RSS_TIMEOUT, MAX_ITEMS, DEBUG, USE_TOR, USER_AGENT
from feedfilter import prefilter_news, filter_similar_titles, merge_entries
from seleniumfetch import fetch_site_posts
from Tor import fetch_via_tor
from shared import RssFeed, TZ
from datetime import datetime
import feedparser
import threading

# Worker function to fetch and process a single RSS feed.
def load_url_worker(url):
    rss_info = ALL_URLS[url]

    feedpid = None

    # Ensure only one process fetches the feed at a time.
    if not g_c.has(url + "FETCHPID"):
        g_c.put(url + "FETCHPID", os.getpid(), timeout=RSS_TIMEOUT)
        feedpid = g_c.get(url + "FETCHPID")

    if feedpid == os.getpid():
        start = timer()
        rssfeed = g_c.get(url)

        # Fetch the feed using the appropriate method.
        if USE_TOR and "reddit" in url:
            res = fetch_via_tor(url, rss_info.site_url)
        elif "fakefeed" in url:
            res = fetch_site_posts(rss_info.site_url, USER_AGENT)
        else:
            res = feedparser.parse(url, agent = USER_AGENT)

        # Process the fetched feed entries.
        new_entries = prefilter_news(url, res)
        new_entries = filter_similar_titles(url, new_entries)
        new_entries = list(itertools.islice(new_entries, MAX_ITEMS))

        old_feed = g_c.get(url)
        new_count = len(new_entries)

        if old_feed and old_feed.entries:
            new_count = len(set(e.get('link') for e in new_entries) - set(e.get('link') for e in old_feed.entries))
            entries = merge_entries(new_entries, old_feed.entries)
        else:
            entries = new_entries

        entries = list(itertools.islice(entries, MAX_ITEMS))

        # Cache the processed feed.
        rssfeed = RssFeed(entries)
        g_c.put(url, rssfeed, timeout=RSS_TIMEOUT)
        g_c.put(url + ":last_fetch", datetime.now(TZ), timeout=RSS_TIMEOUT)

        g_c.delete(url + "FETCHPID")
        end = timer()
        print(f"Parsing from: {url}, in {end - start:f}.")
    else:
        while g_c.has(url + "FETCHPID"):
            time.sleep(0.1)

# Wait for the fetch mode to be available and set it.
def wait_and_set_fetch_mode():
    if g_c.has("FETCHMODE"):
        while g_c.has("FETCHMODE"):
            time.sleep(0.1)

    g_c.put("FETCHMODE", "FETCHMODE", timeout=30)

# Fetch multiple RSS feeds in parallel.
def fetch_urls_parallel(urls):
    wait_and_set_fetch_mode()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10 if not DEBUG else 1) as executor:
        future_to_url = {executor.submit(load_url_worker, url): url for url in urls}

        for future in concurrent.futures.as_completed(future_to_url):
            future.result()

    g_c.delete("FETCHMODE")

# Refresh all expired RSS feeds in a separate thread.
def refresh_thread():
    for url, rss_info in ALL_URLS.items():
        if g_c.has_feed_expired(url) and rss_info.logo_url != "Custom.png":
            wait_and_set_fetch_mode()
            load_url_worker(url)
            g_c.delete("FETCHMODE")
            time.sleep(0.2)

# Start a background thread to refresh RSS feeds.
def fetch_urls_thread():
    t = threading.Thread(target=refresh_thread, args=())
    t.daemon = True
    t.start()