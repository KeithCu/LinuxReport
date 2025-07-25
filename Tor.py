"""
Tor.py

Tor network integration module for fetching Reddit RSS feeds through the Tor network.
Provides functionality for fetching content via curl through Tor SOCKS proxy and
managing Tor circuit renewal for IP rotation.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import io
import random
import socket
import subprocess
import threading
import time
import traceback
from timeit import default_timer as timer

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import feedparser
from fake_useragent import UserAgent

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
import shared
from shared import g_cs
from seleniumfetch import fetch_site_posts

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

PASSWORD = "TESTPASSWORD"

# =============================================================================
# GLOBAL VARIABLES AND INITIALIZATION
# =============================================================================

ua = UserAgent()

# Initialize Reddit user agent if not already set
if not g_cs.has("REDDIT_USER_AGENT"):
    g_cs.put("REDDIT_USER_AGENT", ua.random, timeout=shared.EXPIRE_YEARS)

# Initialize Reddit method preference if not already set
if not g_cs.has("REDDIT_METHOD"):
    g_cs.put("REDDIT_METHOD", "curl", timeout=shared.EXPIRE_YEARS)

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
    print(f"Using curl TOR method for: {url}")
    result = None
    
    try:        
        cmd = [
            "curl", "-s",
            "--socks5-hostname", "127.0.0.1:9050",
            "-A", g_cs.get("REDDIT_USER_AGENT"),
            "-H", "Accept: */*",
            url
        ]
        
        print(f"Executing curl command: {' '.join(cmd)}")
        start_time = timer()
        
        # Use text=False to get bytes directly
        process_result = subprocess.run(cmd, capture_output=True, text=False, timeout=30)
        elapsed = timer() - start_time
        
        if process_result.returncode == 0 and process_result.stdout:
            content_bytes = process_result.stdout
            content_length = len(content_bytes)
            print(f"Curl succeeded in {elapsed:.2f}s, content length: {content_length}")
                        
            try:
                # First try parsing it as bytes directly
                result = feedparser.parse(content_bytes)
                entries_count = len(result.get('entries', [])) if hasattr(result, 'get') else 0
                print(f"Parsed {entries_count} entries from curl result (bytes mode)")
                
                # If no entries, try string conversion
                if entries_count == 0:
                    # Convert bytes to string with explicit UTF-8 decoding
                    content_str = content_bytes.decode('utf-8', errors='replace')
                    
                    # Try parsing as string 
                    result = feedparser.parse(content_str)
                    entries_count = len(result.get('entries', [])) if hasattr(result, 'get') else 0
                    print(f"Parsed {entries_count} entries from curl result (string mode)")
                    
                    # If still no entries, save the first part of the content for debugging
                    if entries_count == 0 and content_length > 1000:
                        print(f"Failed to parse content. First 200 chars: {content_str[:200]}")
                        print(f"Content appears to be XML/RSS: {'<?xml' in content_str[:10]}")
                        
                        # Last attempt: try using StringIO
                        result = feedparser.parse(io.BytesIO(content_bytes))
                        entries_count = len(result.get('entries', [])) if hasattr(result, 'get') else 0
                        print(f"BytesIO parsing attempt: {entries_count} entries")
                        
                        if entries_count == 0:
                            result = None
            except Exception as parse_error:
                print(f"Error parsing curl content: {str(parse_error)}")                
                print(f"Exception type: {type(parse_error).__name__}")
                traceback.print_exc()
                
                result = None
        else:
            stderr = process_result.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode('utf-8', errors='replace')
            print(f"Curl failed with error: {stderr}")
            result = None
            
    except Exception as e:
        print(f"Curl TOR method failed: {str(e)}")
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
    g_cs.put("REDDIT_USER_AGENT", ua.random, timeout=shared.EXPIRE_YEARS)

    print("Requesting a new TOR IP address...")

    host = "127.0.0.1"
    port = 9051

    # Create socket and connect to Tor control port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        s.send(f'AUTHENTICATE "{PASSWORD}"\r\n'.encode())

        response = s.recv(1024).decode()
        if "250 OK" not in response:
            print("Authentication failed:", response)
            exit(1)
        s.send(b"SIGNAL NEWNYM\r\n")
        response = s.recv(1024).decode()
        print("New circuit requested:", response)

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
    last_success_method = g_cs.get("REDDIT_LAST_METHOD")

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
                g_cs.put("REDDIT_METHOD", default_method, shared.EXPIRE_YEARS)
                result = result_default
                break
            
            # Try alternative method
            alternative_method = "selenium" if default_method == "curl" else "curl"
            if alternative_method == "curl":
                result_alternative = fetch_via_curl(url)
            else:
                result_alternative = fetch_site_posts(site_url, None)
                
            if result_alternative is not None and len(result_alternative.get("entries", [])) > 0:
                g_cs.put("REDDIT_METHOD", alternative_method, shared.EXPIRE_YEARS)
                result = result_alternative
                break
            
            print(f"Attempt {attempt + 1} failed, renewing TOR and trying again...")
            renew_tor_ip()
        
        if result is None:
            print("All TOR methods failed, returning empty result")
            result = {
                'entries': [], 
                'status': 'failed', 
                'bozo_exception': 'All TOR methods failed'
            }
            
        return result
