'''Various misc caching routines'''
from functools import lru_cache
import hashlib
import os
import datetime
import time

from shared import PATH, EXPIRE_HOUR, ENABLE_COMPRESSION_CACHING, g_cm, clear_page_caches
from models import DEBUG

_file_cache = {}
_FILE_CHECK_INTERVAL_SECONDS = 5 * 60 # 5 minutes

def get_cached_file_content(file_path, encoding='utf-8'):
    """Return content of any file, caching and invalidating when it changes.
    Checks mtime only if _FILE_CHECK_INTERVAL_SECONDS have passed since the last check.
    """
    now = time.monotonic()
    entry = _file_cache.get(file_path)

    # Check if cache entry exists and if we should skip the mtime check
    if entry and (now - entry.get('last_check_time', 0)) < _FILE_CHECK_INTERVAL_SECONDS:
        return entry['content']

    # Proceed with mtime check or initial load
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        # File doesn't exist or inaccessible
        if entry: # Remove stale entry if it exists
            del _file_cache[file_path]
        return ''

    # If cache entry exists and mtime matches, update check time and return content
    if entry and entry['mtime'] == mtime:
        entry['last_check_time'] = now
        return entry['content']

    # Read file fresh or because mtime changed
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
    except FileNotFoundError:
        content = ''
        # Ensure mtime reflects the non-existent state if we somehow got here
        mtime = -1 # Or some other indicator that it's gone

    _file_cache[file_path] = {'mtime': mtime, 'content': content, 'last_check_time': now}
    return content


# Compression caching constants
COMPRESSION_CACHE_TTL = EXPIRE_HOUR  # Cache compressed responses for 1 hour
COMPRESSION_LEVEL = 6  # Balance between speed and compression ratio

def get_compression_cache_key(content, encoding_type='gzip'):
    """Generate a cache key for compressed content."""
    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    return f"compressed_{encoding_type}_{content_hash}"

def get_cached_compressed_response(content, encoding_type='gzip'):
    """Get cached compressed response if available."""
    cache_key = get_compression_cache_key(content, encoding_type)
    return g_cm.get(cache_key)

def cache_compressed_response(content, compressed_data, encoding_type='gzip'):
    """Cache compressed response data."""
    cache_key = get_compression_cache_key(content, encoding_type)
    g_cm.set(cache_key, compressed_data, ttl=COMPRESSION_CACHE_TTL)

def create_compressed_response(content, encoding_type='gzip'):
    """Create compressed response with caching."""
    # Check cache first
    cached_response = get_cached_compressed_response(content, encoding_type)
    if cached_response is not None:
        return cached_response
    
    # Compress content
    if encoding_type == 'gzip':
        compressed_data = gzip.compress(content.encode('utf-8'), compresslevel=COMPRESSION_LEVEL)
    else:
        # Fallback to uncompressed
        compressed_data = content.encode('utf-8')
    
    # Cache the compressed data
    cache_compressed_response(content, compressed_data, encoding_type)
    
    return compressed_data

def get_cached_response_for_client(content, supports_gzip):
    """Get cached response (compressed or uncompressed) based on client capabilities."""
    if supports_gzip:
        # Try to get cached compressed response
        cached_compressed = get_cached_compressed_response(content, 'gzip')
        if cached_compressed is not None:
            if DEBUG:
                print(f"Compression cache HIT - returning cached gzip data ({len(cached_compressed)} bytes)")
            return cached_compressed, True  # Return compressed data and flag as compressed
        
        # Create and cache compressed response
        if DEBUG:
            print(f"Compression cache MISS - creating new gzip data")
        compressed_data = create_compressed_response(content, 'gzip')
        return compressed_data, True
    else:
        # For clients that don't support gzip, return uncompressed
        # We don't cache uncompressed responses since they're just the original content
        if DEBUG:
            print(f"Client doesn't support gzip - returning uncompressed data ({len(content)} bytes)")
        # Return the content directly as bytes to avoid unnecessary encoding
        return content.encode('utf-8'), False

def clear_compression_cache():
    """Clear all compression cache entries."""
    # This is a simple approach - in a more sophisticated system, you might want to
    # track compression cache keys and clear them individually
    # For now, we'll rely on TTL expiration
    pass

def clear_page_caches_with_compression():
    """Clear page caches and compression cache."""
    clear_page_caches()
    if ENABLE_COMPRESSION_CACHING:
        clear_compression_cache()
