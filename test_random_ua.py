#!/usr/bin/env python3
"""
Test script to verify random user agent functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from browser_fetch import fetch_site_posts
from ai_report_settings import CONFIG
from shared import g_cs

def test_random_user_agent():
    """Test that random user agent is working"""

    print("Testing random user agent functionality...")

    # Check if we have a random user agent cached (REDDIT_USER_AGENT)
    if g_cs.has("REDDIT_USER_AGENT"):
        cached_ua = g_cs.get("REDDIT_USER_AGENT")
        print(f"Found cached random user agent: {cached_ua[:50]}...")
    else:
        print("No cached random user agent found")

    # Test the config
    venturebeat_config = CONFIG.CUSTOM_FETCH_CONFIG.get("venturebeat.com")
    if venturebeat_config:
        print(f"VentureBeat config has use_random_user_agent: {venturebeat_config.use_random_user_agent}")

    reddit_config = CONFIG.CUSTOM_FETCH_CONFIG.get("reddit.com")
    if reddit_config:
        print(f"Reddit config has use_random_user_agent: {reddit_config.use_random_user_agent}")

    print("✅ Random user agent configuration test completed!")

if __name__ == "__main__":
    test_random_user_agent()
