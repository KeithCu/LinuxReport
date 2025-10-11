"""
Tor.py

Tor network integration module for fetching Reddit RSS feeds through the Tor network.
Provides functionality for fetching content via curl through Tor SOCKS proxy and
managing Tor circuit renewal for IP rotation.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import traceback
import io
import random
import socket
import sqlite3
import subprocess
import threading
import time
import traceback
from timeit import default_timer as timer
from xml.parsers import expat

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import feedparser
from fake_useragent import UserAgent

# =============================================================================
# LOCAL IMPORTS
# =============================================================================

from shared import g_cs, g_logger, EXPIRE_YEARS, WORKER_PROXYING, PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD
from browser_fetch import fetch_site_posts
from app_config import get_tor_password

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# =============================================================================
# GLOBAL VARIABLES AND INITIALIZATION
# =============================================================================

ua = UserAgent()

# Initialize Reddit user agent if not already set
if not g_cs.has("REDDIT_USER_AGENT"):
    g_cs.put("REDDIT_USER_AGENT", ua.random, timeout=EXPIRE_YEARS)

# Initialize Reddit method preference if not already set
if not g_cs.has("REDDIT_METHOD"):
    g_cs.put("REDDIT_METHOD", "curl", timeout=EXPIRE_YEARS)

# Thread lock for Tor fetch operations
tor_fetch_lock = threading.Lock()

# =============================================================================
# TOR NETWORK OPERATIONS
# =============================================================================

def fetch_via_curl(url):
    """
    Fetch Reddit RSS feeds using curl subprocess through Tor SOCKS proxy.

    Args:
        url (str): The URL to fetch via Tor network

    Returns:
        feedparser.FeedParserDict or None: Parsed RSS feed data or None if failed
    """
    g_logger.info(f"=== FETCH_VIA_CURL START ===")
    g_logger.info(f"Function called with URL: {url}")
    g_logger.info(f"Using curl TOR method for: {url}")

    result = None

    try:
        cmd = [
            "curl", "-s",
            "--socks5-hostname", "127.0.0.1:9050",
            "-A", g_cs.get("REDDIT_USER_AGENT"),
            "-H", "Accept: */*",
        ]
        
        # Add proxy headers if proxying is enabled
        if WORKER_PROXYING and PROXY_SERVER:
            cmd.extend(["-H", f"X-Forwarded-For: {PROXY_SERVER.split(':')[0]}"])
            if PROXY_USERNAME and PROXY_PASSWORD:
                import base64
                auth_string = f"{PROXY_USERNAME}:{PROXY_PASSWORD}"
                auth_bytes = auth_string.encode('ascii')
                auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
                cmd.extend(["-H", f"Proxy-Authorization: Basic {auth_b64}"])
        
        cmd.append(url)

        g_logger.debug(f"Executing curl command: {' '.join(cmd)}")
        start_time = timer()
        
        # Use text=False to get bytes directly
        process_result = subprocess.run(cmd, capture_output=True, text=False, timeout=30)
        elapsed = timer() - start_time
        
        if process_result.returncode == 0 and process_result.stdout:
            content_bytes = process_result.stdout
            content_length = len(content_bytes)
            g_logger.info(f"Curl succeeded in {elapsed:.2f}s, content length: {content_length}")
                        
            try:
                # First try parsing it as bytes directly
                result = feedparser.parse(content_bytes)
                entries_count = len(result.get('entries', [])) if hasattr(result, 'get') else 0
                g_logger.debug(f"Parsed {entries_count} entries from curl result (bytes mode)")

                # If no entries, try string conversion
                if entries_count == 0:
                    # Convert bytes to string with explicit UTF-8 decoding
                    content_str = content_bytes.decode('utf-8', errors='replace')

                    # Try parsing as string
                    result = feedparser.parse(content_str)
                    entries_count = len(result.get('entries', [])) if hasattr(result, 'get') else 0
                    g_logger.debug(f"Parsed {entries_count} entries from curl result (string mode)")

                    # If still no entries, save the first part of the content for debugging
                    if entries_count == 0 and content_length > 1000:
                        g_logger.debug(f"Failed to parse content. First 200 chars: {content_str[:200]}")
                        g_logger.debug(f"Content appears to be XML/RSS: {'<?xml' in content_str[:10]}")

                        # Last attempt: try using StringIO
                        result = feedparser.parse(io.BytesIO(content_bytes))
                        entries_count = len(result.get('entries', [])) if hasattr(result, 'get') else 0
                        g_logger.debug(f"BytesIO parsing attempt: {entries_count} entries")

                        if entries_count == 0:
                            result = None
            except (expat.ExpatError, TypeError) as parse_error:
                g_logger.error(f"Error parsing curl content: {str(parse_error)}")
                g_logger.error(f"Exception type: {type(parse_error).__name__}")
                g_logger.error(f"Traceback: {traceback.format_exc()}")

                result = None
        else:
            stderr = process_result.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode('utf-8', errors='replace')
            g_logger.error(f"Curl failed with error: {stderr}")
            result = None

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        g_logger.warning(f"Curl TOR method failed: {str(e)}, falling back to cached data")
        # Fall back to cached data if proxying fails
        cached_feed = g_cs.get(f"tor_cache:{url}")
        if cached_feed and cached_feed.get('entries'):
            result = cached_feed
            g_logger.info(f"Using cached TOR data for {url}: {len(result.get('entries', []))} entries")
        else:
            result = None
        
    return result

def renew_tor_ip():
    """
    Generate a new user agent and request a new Tor IP address.
    
    This function authenticates with the Tor control port and requests a new circuit
    to obtain a fresh IP address. It also generates a new user agent for additional
    anonymity. Waits 20-30 seconds for the new circuit to be established.
    """
    # Generate new user agent
    g_cs.put("REDDIT_USER_AGENT", ua.random, timeout=EXPIRE_YEARS)

    g_logger.info("Requesting a new TOR IP address...")

    host = "127.0.0.1"
    port = 9051

    # Create socket and connect to Tor control port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        s.send(f'AUTHENTICATE "{get_tor_password()}"\r\n'.encode())

        response = s.recv(1024).decode()
        if "250 OK" not in response:
            g_logger.error(f"Authentication failed: {response}")
            exit(1)
        s.send(b"SIGNAL NEWNYM\r\n")
        response = s.recv(1024).decode()
        g_logger.info(f"New circuit requested: {response}")

    # Wait 20-30 seconds to give time for a circuit to be re-established
    time.sleep(random.uniform(20, 30))

# =============================================================================
# MAIN FETCH FUNCTION
# =============================================================================

def fetch_via_tor(url, site_url):
    """
    Fetch content via Tor network with automatic fallback and retry logic.

    This function attempts to fetch content using the last successful method first,
    then falls back to alternative methods. If all attempts fail, it renews the
    Tor IP address and retries. Supports both curl and selenium methods.

    Args:
        url (str): The RSS feed URL to fetch
        site_url (str): The site URL for selenium-based fetching

    Returns:
        dict: Parsed feed data with entries, or empty result dict if all methods fail
    """
    g_logger.info(f"=== FETCH_VIA_TOR START ===")
    g_logger.info(f"Function called with URL: {url}, site_url: {site_url}")

    try:
        last_success_method = g_cs.get("REDDIT_LAST_METHOD")
        g_logger.info(f"Successfully got REDDIT_LAST_METHOD: {last_success_method}")
    except (sqlite3.Error, IOError) as e:
        g_logger.error(f"CRITICAL ERROR: Failed to access g_cs.get(): {e}")
        g_logger.error(f"Exception type: {type(e).__name__}")
        g_logger.error(f"Full traceback: {traceback.format_exc()}")
        g_logger.error("This is likely the source of the 'shared' error!")
        return {
            'entries': [],
            'status': 'failed',
            'bozo_exception': f'g_cs access failed: {str(e)}'
        }

    with tor_fetch_lock:
        max_attempts = 3  # Define how many attempts we try
        result = None
        
        for attempt in range(max_attempts):
            # On first try use last_success_method, otherwise start with selenium after renew_tor_ip
            default_method = last_success_method if (attempt == 0 and last_success_method) else "selenium"
            
            # Try default method
            if default_method == "curl":
                result_default = fetch_via_curl(url)
            else:
                result_default = fetch_site_posts(site_url, None)
                
            if result_default is not None and len(result_default.get("entries", [])) > 0:
                g_cs.put("REDDIT_METHOD", default_method, EXPIRE_YEARS)
                result = result_default
                break
            
            # Try alternative method
            alternative_method = "selenium" if default_method == "curl" else "curl"
            if alternative_method == "curl":
                result_alternative = fetch_via_curl(url)
            else:
                result_alternative = fetch_site_posts(site_url, None)
                
            if result_alternative is not None and len(result_alternative.get("entries", [])) > 0:
                g_cs.put("REDDIT_METHOD", alternative_method, EXPIRE_YEARS)
                result = result_alternative
                break
            
            g_logger.info(f"Attempt {attempt + 1} failed, renewing TOR and trying again...")
            renew_tor_ip()

        if result is None:
            g_logger.error("All TOR methods failed, returning empty result")
            result = {
                'entries': [],
                'status': 'failed',
                'bozo_exception': 'All TOR methods failed'
            }
            
        return result
