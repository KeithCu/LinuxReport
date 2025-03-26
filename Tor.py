import io
import socket
import random
import threading
import time

import urllib.request
from timeit import default_timer as timer
import traceback
import subprocess

import socks
import feedparser

import shared
from seleniumfetch import fetch_site_posts

#Generate fake but valid user-agents to make Reddit happy.
from fake_useragent import UserAgent
ua = UserAgent()

PASSWORD = "TESTPASSWORD"

g_cache = shared.DiskCacheWrapper("/tmp")

if not g_cache.has("REDDIT_USER_AGENT"):
    g_cache.put("REDDIT_USER_AGENT", ua.random, timeout = shared.EXPIRE_YEARS)

tor_fetch_lock = threading.Lock()

def fetch_via_curl(url):
    """Fetch Reddit RSS feeds using curl subprocess through TOR."""
    print(f"Using curl TOR method for: {url}")
    result = None
    
    try:        
        cmd = [
            "curl", "-s",
            #"--socks5-hostname", "127.0.0.1:9050",
            "-A", g_cache.get("REDDIT_USER_AGENT"),
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
    '''Generate a new user agent, a new IP address and try again!'''
    g_cache.put("REDDIT_USER_AGENT", ua.random, timeout = shared.EXPIRE_YEARS)

    print("Requesting a new TOR IP address...")

    host = "127.0.0.1"
    port = 9051

    # Create socket and connect
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

    # Wait 20-30 seconds to give time for a circuit to be re-established.
    time.sleep(random.uniform(20, 30))

def fetch_via_tor(url, site_url):
    with tor_fetch_lock:
        max_attempts = 3  # define how many attempts we try
        result = None
        
        for attempt in range(max_attempts):
            result = fetch_via_curl(url)
            if result is not None:
                break
            print(f"Curl attempt {attempt + 1} failed, trying selenium...")
            result = fetch_site_posts(site_url, None)
            if len(result["entries"]) > 0:
                break
            print(f"Selenium attempt {attempt + 1} failed, renewing Tor and trying again...")
            renew_tor_ip()
        
        if result is None:
            print("All TOR methods failed, returning empty result")
            result = {'entries': [], 'status': 'failed', 'bozo_exception': 'All TOR methods failed'}
            
        return result
