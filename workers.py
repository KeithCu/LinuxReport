# This file contains worker functions for fetching and processing RSS feeds.
# Functions include parallel fetching, thread management, and feed processing.

import os
import time
import itertools
import re
from timeit import default_timer as timer
import concurrent.futures
from shared import ALL_URLS, SPATH, DiskCacheWrapper, RSS_TIMEOUT, MAX_ITEMS, DEBUG, USE_TOR, USER_AGENT, EXPIRE_WEEK
from feedfilter import prefilter_news, filter_similar_titles, merge_entries
from seleniumfetch import fetch_site_posts
from Tor import fetch_via_tor
from shared import RssFeed, TZ
from datetime import datetime
import feedparser
import threading
import shared

g_c = DiskCacheWrapper(SPATH)

# Worker function to fetch and process a single RSS feed.
def load_url_worker(url):
    """Background worker to fetch a URL. Handles """
    rss_info = ALL_URLS[url]
    feedpid = None
    
    #This FETCHPID logic is to prevent race conditions of
    #multiple Python processes fetching an expired RSS feed.
    #This isn't as useful anymore given the FETCHMODE.
    if not g_c.has(url + "FETCHPID"):
        g_c.put(url + "FETCHPID", os.getpid(), timeout=RSS_TIMEOUT)
        feedpid = g_c.get(url + "FETCHPID") #Check to make sure it's us

    if feedpid == os.getpid():
        start = timer()
        rssfeed = None
        rssfeed = g_c.get(url)

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
                    links = re.findall(r'href=["\'](.*?)["\']', entry.get('html_content', ''))
                    # Filter out reddit links:
                    links = [lnk for lnk in links if 'reddit' not in lnk]
                    if links:
                        #Pick the first match for now
                        entry['link'] = links[0]
                        print (entry['link'])

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
        g_c.put(url + ":last_fetch", datetime.now(TZ), timeout=EXPIRE_WEEK)

        if len(entries) > 2:
            g_c.delete(rss_info.site_url)

        g_c.delete(url + "FETCHPID")
        end = timer()
        print(f"Parsing from: {url}, in {end - start:f}.")
    else:
        print(f"Waiting for someone else to parse remote site {url}.")
        # Someone else is fetching, so wait
        while g_c.has(url + "FETCHPID"):
            time.sleep(0.1)
        print(f"Done waiting for someone else to parse {url}.")

def wait_and_set_fetch_mode():
    #If any other process is fetching feeds, then we should just wait a bit.
    #This prevents a thundering herd of threads.
    if g_c.has("FETCHMODE"):
        print("Waiting on another process to finish fetching.")
        while g_c.has("FETCHMODE"):
            time.sleep(0.1)
        print("Done waiting.")
    g_c.put("FETCHMODE", "FETCHMODE", timeout=RSS_TIMEOUT)

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