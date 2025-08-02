"""
request_utils.py

Provides utilities related to handling and identifying incoming web requests,
including rate limiting logic and web bot detection.
"""

import ipaddress
from typing import Optional
import datetime

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
from flask import request
from flask_login import current_user
from flask_limiter.util import get_remote_address

# =============================================================================
# WEB BOT DETECTION
# =============================================================================

# Common web bot user agents that should not trigger background refreshes or OpenWeather queries
WEB_BOT_USER_AGENTS = [
    # Google Crawlers
    "Googlebot",
    "Google-InspectionTool",
    "Google-Site-Verification",
    "Google-Extended",

    # Bing Crawlers
    "Bingbot",
    "AdIdxBot",
    "MicrosoftPreview",

    # Yandex Crawlers
    "YandexBot",
    "YandexMobileBot",
    "YandexImages",

    # AI-Related Crawlers
    "GPTBot",
    "ClaudeBot",
    "CCBot",
    "Bytespider",
    "Applebot",

    # Other Common Crawlers
    "Baiduspider",
    "DuckDuckBot",
    "AhrefsBot",
    "SemrushBot",
    "MJ12bot",
    "KeybaseBot",
    "Lemmy",
    "CookieHubScan",
    "Hydrozen.io",
    "SummalyBot",
    "DotBot",
    "Coccocbot",
    "LinuxReportDeployBot",
]

# =============================================================================
# RATE LIMITING CONFIGURATION
# =============================================================================

def get_rate_limit_key():
    """
    Get rate limit key based on user type and IP address.
    
    This function determines the appropriate rate limiting key based on:
    - Whether the user is authenticated (admin)
    - Whether the request is from a known web bot
    - The remote IP address
    
    Returns:
        str: Rate limit key in format "type:ip_address"
    """
    # Check if user is authenticated (admin)
    if current_user.is_authenticated:
        return f"admin:{get_remote_address()}"

    # Check if request is from a web bot
    user_agent = request.headers.get('User-Agent', '')
    is_web_bot = any(bot in user_agent for bot in WEB_BOT_USER_AGENTS)
    
    if is_web_bot:
        return f"bot:{get_remote_address()}"
    
    return f"user:{get_remote_address()}"

def dynamic_rate_limit():
    """
    Return rate limit based on user type.
    
    Provides different rate limits for different types of users:
    - Admins: Higher limits for administrative functions
    - Bots: Lower limits to prevent abuse
    - Regular users: Standard limits
    
    Returns:
        str: Rate limit string in format "X per minute"
    """
    key = get_rate_limit_key()
    
    if key.startswith("admin:"):
        return "50 per minute"  # Higher limits for admins
    elif key.startswith("bot:"):
        return "10 per minute"    # Lower limits for bots
    else:
        return "20 per minute"  # Standard limits for users

def get_ip_prefix(ip_str):
    """
    Extract the first part of IPv4 or the first block of IPv6 for grouping purposes.
    
    Args:
        ip_str (str): IP address string to process
        
    Returns:
        str: First octet of IPv4 or first block of IPv6, or "Invalid IP" on error
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        if isinstance(ip, ipaddress.IPv4Address):
            return ip_str.split('.')[0]
        elif isinstance(ip, ipaddress.IPv6Address):
            return ip_str.split(':')[0]
    except ValueError:
        return "Invalid IP"
    return None

def format_last_updated(last_fetch: Optional[datetime.datetime]) -> str:
    """
    Format the last fetch time as UTC ISO format for frontend timezone conversion.
    
    Args:
        last_fetch (Optional[datetime.datetime]): Timestamp to format
        
    Returns:
        str: UTC ISO formatted timestamp or "Unknown" if no timestamp
    """
    if not last_fetch:
        print(f"format_last_updated: last_fetch is None or falsy")
        return "Unknown"
    
    try:
        # Convert to UTC and return ISO format for frontend timezone conversion
        utc_time = last_fetch.astimezone(datetime.timezone.utc).isoformat()
        # The isoformat() method already produces the correct format for UTC
        # It will be something like "2025-07-25T19:20:06.860595+00:00"
        # JavaScript can parse this format correctly
        #print(f"format_last_updated: converted {last_fetch} to {utc_time}")
        return utc_time
    except Exception as e:
        print(f"format_last_updated: error converting {last_fetch}: {e}")
        return "Unknown"
