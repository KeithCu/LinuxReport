#!/usr/bin/env python3
"""
Simple Proxy Server for LinuxReport

A lightweight HTTP proxy server that can be used to proxy requests
for the LinuxReport application. Supports basic authentication
and can proxy to any target URL.

Usage:
    python simple_proxy.py

Configuration:
    - Host: 127.0.0.1
    - Port: 8080
    - Username/Password: Set via environment variables or defaults

Author: LinuxReport System
License: See LICENSE file
"""

import os
import base64
import requests
from flask import Flask, request, Response, abort
from app_config import get_proxy_server, get_proxy_username, get_proxy_password

app = Flask(__name__)

# Configuration - load from config.yaml via app_config.py
PROXY_SERVER = get_proxy_server()
PROXY_USERNAME = get_proxy_username()
PROXY_PASSWORD = get_proxy_password()

# Validate required configuration
if not PROXY_SERVER:
    print("ERROR: proxy.server not configured in config.yaml")
    print("Please add the following to your config.yaml:")
    print("proxy:")
    print("  server: \"127.0.0.1:8080\"")
    print("  username: \"your-username\"")
    print("  password: \"your-password\"")
    exit(1)

# Extract port from server address
if ':' in PROXY_SERVER:
    PROXY_PORT = int(PROXY_SERVER.split(':')[1])
else:
    print(f"ERROR: Invalid proxy server format: {PROXY_SERVER}")
    print("Expected format: host:port (e.g., 127.0.0.1:8080)")
    exit(1)

def check_auth():
    """Check if the request has valid basic authentication."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        return False
    
    try:
        # Decode the base64 encoded credentials
        encoded_credentials = auth_header.split(' ')[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode('ascii')
        username, password = decoded_credentials.split(':', 1)
        
        return username == PROXY_USERNAME and password == PROXY_PASSWORD
    except (ValueError, IndexError):
        return False

def require_auth():
    """Require basic authentication for the request."""
    if not check_auth():
        response = Response('Unauthorized', 401)
        response.headers['WWW-Authenticate'] = 'Basic realm="Proxy Server"'
        abort(response)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def proxy(path):
    """
    Proxy requests to target URLs.
    
    Query parameters:
        url: Target URL to proxy to (required)
        timeout: Request timeout in seconds (optional, default: 30)
    """
    # Check authentication if username/password are configured
    if PROXY_USERNAME and PROXY_PASSWORD:
        require_auth()
    
    # Get target URL from query parameter
    target_url = request.args.get('url')
    if not target_url:
        return Response('Missing "url" query parameter', 400)
    
    # Get timeout from query parameter or use default
    timeout = int(request.args.get('timeout', 30))
    
    try:
        # Forward the request to the target URL
        resp = requests.get(
            target_url, 
            stream=True, 
            timeout=timeout,
            headers={
                'User-Agent': request.headers.get('User-Agent', 'SimpleProxy/1.0'),
                'Accept': request.headers.get('Accept', '*/*'),
            }
        )
        
        # Create response with the same content and headers
        response = Response(
            resp.content, 
            status=resp.status_code, 
            headers=dict(resp.headers)
        )
        
        # Remove any problematic headers
        response.headers.pop('Transfer-Encoding', None)
        response.headers.pop('Connection', None)
        
        return response
        
    except requests.exceptions.Timeout:
        return Response('Request timeout', 408)
    except requests.exceptions.RequestException as e:
        return Response(f'Proxy error: {str(e)}', 502)
    except Exception as e:
        return Response(f'Internal error: {str(e)}', 500)

@app.route('/health')
def health():
    """Health check endpoint."""
    return Response('OK', 200)

@app.route('/info')
def info():
    """Information endpoint showing proxy configuration."""
    info_data = {
        'proxy_server': PROXY_SERVER,
        'proxy_username': PROXY_USERNAME or 'Not configured',
        'proxy_password_set': bool(PROXY_PASSWORD),
        'proxy_port': PROXY_PORT,
        'authentication_required': bool(PROXY_USERNAME and PROXY_PASSWORD),
        'config_source': 'config.yaml via app_config.py'
    }
    return Response(str(info_data), 200, mimetype='text/plain')

if __name__ == '__main__':
    print(f"Starting Simple Proxy Server on {PROXY_SERVER}")
    print(f"Configuration loaded from: config.yaml via app_config.py")
    print(f"Username: {PROXY_USERNAME or 'Not configured'}")
    print(f"Password: {'*' * len(PROXY_PASSWORD) if PROXY_PASSWORD else 'Not configured'}")
    print(f"Authentication required: {bool(PROXY_USERNAME and PROXY_PASSWORD)}")
    print("\nUsage examples:")
    print(f"  curl 'http://{PROXY_SERVER}/?url=https://httpbin.org/ip'")
    if PROXY_USERNAME and PROXY_PASSWORD:
        print(f"  curl -u {PROXY_USERNAME}:{PROXY_PASSWORD} 'http://{PROXY_SERVER}/?url=https://httpbin.org/ip'")
    else:
        print("  # Authentication not configured - no username/password required")
    print(f"  curl 'http://{PROXY_SERVER}/health'")
    print(f"  curl 'http://{PROXY_SERVER}/info'")
    
    app.run(host='127.0.0.1', port=PROXY_PORT, debug=False)
