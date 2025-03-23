import io
import socket

import urllib.request
from timeit import default_timer as timer
import traceback
import subprocess

import socks
import feedparser

#Generate fake but valid user-agents for Reddit
from fake_useragent import UserAgent
ua = UserAgent()

PASSWORD = "TESTPASSWORD"

USER_AGENT_REDDIT = ua.random
print (f"User agent for Reddit: {USER_AGENT_REDDIT}")

HEADERS = {
    "User-Agent": USER_AGENT_REDDIT,
    "Accept": "*/*",
    "Host": "www.reddit.com",
    "Connection": "keep-alive"
}

def fetch_via_pysocks(url):
    """Fetch Reddit RSS feeds using PySocks for TOR routing."""
    print(f"Using PySocks TOR method for: {url}")
    original_socket = socket.socket
    result = None
    
    try:
        # Use PROXY_TYPE_SOCKS5 instead of PROXY_TYPE_SOCKS5_HOSTNAME which isn't available in all versions
        socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 9050)
        socket.socket = socks.socksocket
        
        # Build opener with our headers
        opener = urllib.request.build_opener()
        opener.addheaders = [(k, v) for k, v in HEADERS.items()]
        urllib.request.install_opener(opener)
        
        print(f"Making request through TOR with headers: {HEADERS}")
        start_time = timer()
        
        result = feedparser.parse(url, request_headers=HEADERS)
        elapsed = timer() - start_time
        
        # Log response details
        status = result.get('status', 'unknown') if hasattr(result, 'get') else 'unknown'
        entries_count = len(result.get('entries', [])) if hasattr(result, 'get') else 0
        
        print(f"TOR PySocks request completed in {elapsed:.2f}s - Status: {status}, Entries: {entries_count}")
        
        if entries_count == 0:
            raise Exception("No entries found with PySocks method")
            
    except Exception as e:
        print(f"PySocks TOR method failed: {str(e)}")
        result = None
    finally:
        # Always restore original socket
        socket.socket = original_socket
        urllib.request.install_opener(None)  # Reset opener
        print("TOR socket and opener reset to defaults")
        
    return result

def fetch_via_curl(url):
    """Fetch Reddit RSS feeds using curl subprocess through TOR."""
    print(f"Using curl TOR method for: {url}")
    result = None
    
    try:        
        cmd = [
            "curl", "-s",
            "--socks5-hostname", "127.0.0.1:9050",
            "-A", USER_AGENT_REDDIT,
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
                        print(f"Content appears to be XML/RSS: {'<?xml' in content_str[:100]}")
                        
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

def fetch_via_tor(url):
    """Fetch Reddit RSS using TOR with multiple fallback methods."""
    # This fails with TOR proxy, so use curl fallback directly for now
    #result = fetch_via_pysocks(url)
    
    result = None
    # If primary method fails, try fallback
    if result is None or len(result.get('entries', [])) == 0:
        #print("Primary TOR method failed, trying curl fallback...")
        result = fetch_via_curl(url)
    
    if result is None:
        print ("Curl failed, renewing TOR IP and trying again...")
        renew_tor_ip()
        result = fetch_via_curl(url)
    
    # If all methods fail, return empty result
    if result is None:
        print("All TOR methods failed, returning empty result")
        result = {'entries': [], 'status': 'failed', 'bozo_exception': 'All TOR methods failed'}
        
    return result
