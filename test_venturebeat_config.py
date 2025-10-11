#!/usr/bin/env python3
"""
Test script to verify VentureBeat HTML parsing configuration
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from browser_fetch import fetch_site_posts
from ai_report_settings import CONFIG

def test_venturebeat_parsing():
    """Test the VentureBeat HTML parsing configuration"""

    # Get the VentureBeat URL from the config
    venturebeat_url = None
    for url in CONFIG.SITE_URLS:
        if "venturebeat.com" in url:
            venturebeat_url = url
            break

    if not venturebeat_url:
        print("ERROR: VentureBeat URL not found in SITE_URLS")
        return

    print(f"Testing VentureBeat URL: {venturebeat_url}")

    # Use the user agent from the config
    user_agent = CONFIG.USER_AGENT
    print(f"Using User-Agent: {user_agent}")

    # Temporarily override CUSTOM_FETCH_CONFIG in seleniumfetch module
    import seleniumfetch
    original_config = seleniumfetch.CUSTOM_FETCH_CONFIG
    seleniumfetch.CUSTOM_FETCH_CONFIG = CONFIG.CUSTOM_FETCH_CONFIG
    print(f"Overriding CUSTOM_FETCH_CONFIG with: {CONFIG.CUSTOM_FETCH_CONFIG}")

    try:
        # Fetch posts using the seleniumfetch function
        result = fetch_site_posts(venturebeat_url, user_agent)
    finally:
        # Restore original config
        seleniumfetch.CUSTOM_FETCH_CONFIG = original_config

    print("\nFetch Result:")
    print(f"Status: {result['status']}")
    print(f"Found {len(result['entries'])} entries")

    if result['entries']:
        print("\nFirst 3 entries:")
        for i, entry in enumerate(result['entries'][:3]):
            print(f"\nEntry {i+1}:")
            print(f"  Title: {entry['title']}")
            print(f"  Link: {entry['link']}")
            print(f"  Published: {entry['published']}")
            print(f"  Summary: {entry['summary'][:100]}...")

        print("\n✅ SUCCESS: VentureBeat HTML parsing is working!")
    else:
        print("❌ ERROR: No entries found")
        print(f"Feed status: {result['status']}")
        if result['status'] == 404:
            print("The URL might not be accessible or the configuration needs adjustment")

if __name__ == "__main__":
    test_venturebeat_parsing()
