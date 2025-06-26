"""
request_utils.py

Provides utilities related to handling and identifying incoming web requests,
including rate limiting logic and web bot detection.
"""

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
    "Coccocbot"
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
