"""
caching.py

Various caching routines for file content. Provides efficient caching mechanisms
for file content with automatic invalidation.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
from functools import lru_cache
import hashlib
import os
import datetime
import time

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from shared import PATH, EXPIRE_HOUR, g_cm, clear_page_caches
from app_config import DEBUG

# =============================================================================
# GLOBAL VARIABLES AND CONSTANTS
# =============================================================================

_file_cache = {}
_FILE_CHECK_INTERVAL_SECONDS = 5 * 60  # 5 minutes

# =============================================================================
# FILE CACHING FUNCTIONS
# =============================================================================

def get_cached_file_content(file_path, encoding='utf-8'):
    """
    Return content of any file, caching and invalidating when it changes.
    
    Checks mtime only if _FILE_CHECK_INTERVAL_SECONDS have passed since the last check.
    This provides a balance between performance and freshness.
    
    Args:
        file_path (str): Path to the file to read and cache
        encoding (str): File encoding to use when reading (default: 'utf-8')
        
    Returns:
        str: File content, or empty string if file doesn't exist or is inaccessible
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
        if entry:  # Remove stale entry if it exists
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
        mtime = -1  # Or some other indicator that it's gone

    _file_cache[file_path] = {'mtime': mtime, 'content': content, 'last_check_time': now}
    return content

# =============================================================================
# CACHE MANAGEMENT FUNCTIONS
# =============================================================================

# Note: Compression caching has been moved to routes.py as a simple cache key modifier
# No additional cache management functions are needed for the simplified approach
