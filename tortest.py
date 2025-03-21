#!/usr/bin/env python3
"""
A simple command-line tool to test fetching RSS feeds through Tor using feedparser.
"""

import sys
import argparse
import urllib.request
import time
import feedparser

# Default Reddit user agent that appears like a normal Firefox browser
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0"

def get_tor_proxy_handler():
    """Create a ProxyHandler for Tor"""
    proxy_handler = urllib.request.ProxyHandler({
        "https": "socks5h://127.0.0.1:9050"
    })
    return proxy_handler

def fetch_feed(url, use_tor=True, verbose=False):
    """Fetch an RSS feed, optionally through Tor"""
    start_time = time.time()
    
    if verbose:
        print(f"Fetching feed: {url}")
        print(f"Using Tor: {use_tor}")
    
    try:
        if use_tor:
            tor_proxy_handler = get_tor_proxy_handler()
            if verbose:
                print("Using Tor proxy handler")
            result = feedparser.parse(url, handlers=[tor_proxy_handler], agent=USER_AGENT)
        else:
            if verbose:
                print("Using direct connection")
            result = feedparser.parse(url, agent=USER_AGENT)
        
        elapsed = time.time() - start_time
        
        if verbose:
            print(f"Request completed in {elapsed:.2f} seconds")
        
        return result
    except Exception as e:
        print(f"Error fetching feed: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Test RSS feed fetching through Tor.')
    parser.add_argument('--url', default='https://www.reddit.com/r/linux/.rss',
                        help='URL of the RSS feed (default: Reddit Linux)')
    parser.add_argument('--no-tor', action='store_true',
                        help='Disable Tor and use direct connection')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show verbose output')
    parser.add_argument('--max-entries', '-n', type=int, default=5,
                        help='Maximum number of entries to display (default: 5)')
    
    args = parser.parse_args()
    
    print(f"Fetching feed: {args.url}")
    print(f"Using Tor: {not args.no_tor}")
    
    feed = fetch_feed(args.url, use_tor=not args.no_tor, verbose=args.verbose)
    
    if not feed:
        print("Failed to fetch feed")
        return 1
    
    if hasattr(feed, 'status') and feed.status != 200:
        print(f"Feed returned status code: {feed.status}")
    
    if hasattr(feed, 'bozo_exception') and feed.bozo_exception:
        print(f"Feed has errors: {feed.bozo_exception}")
    
    print("\nFeed information:")
    if hasattr(feed.feed, 'title'):
        print(f"Title: {feed.feed.title}")
    
    if hasattr(feed.feed, 'description'):
        print(f"Description: {feed.feed.description}")
    
    if hasattr(feed, 'entries'):
        print(f"\nFound {len(feed.entries)} entries")
        
        for i, entry in enumerate(feed.entries[:args.max_entries]):
            print(f"\nEntry {i+1}:")
            if hasattr(entry, 'title'):
                print(f"  Title: {entry.title}")
            if hasattr(entry, 'link'):
                print(f"  Link: {entry.link}")
            if hasattr(entry, 'published'):
                print(f"  Published: {entry.published}")
    else:
        print("No entries found in feed")
    
    return 0

if __name__ == "__main__":
    # Make sure to have the 'socks' Python package installed:
    # pip install pysocks
    try:
        import socks
    except ImportError:
        print("Error: PySocks package not installed. Please install it with:")
        print("pip install pysocks")
        sys.exit(1)
        
    sys.exit(main())