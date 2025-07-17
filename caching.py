"""
caching.py

Various caching routines for file content. Provides efficient caching mechanisms
for file content with automatic invalidation.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
import time

# =============================================================================
# LOCAL IMPORTS
# =============================================================================

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


_page_cache = {}


def get_cached_page(page_name, render_function, file_path=None):
    """
    Cache a rendered page, only updating if the underlying file changes.
    Only check the file's mtime every _FILE_CHECK_INTERVAL_SECONDS to avoid excess stat ops.

    Args:
        page_name (str): Unique cache name
        render_function (callable): Function that returns the rendered HTML
        file_path (str, optional): Path to a file to track for changes

    Returns:
        str: Cached HTML or newly rendered if file changed
    """
    now = time.time()
    cache_entry = _page_cache.get(page_name)

    if cache_entry:
        last_check = cache_entry.get('last_checked', 0)
        # Only check mtime every _FILE_CHECK_INTERVAL_SECONDS
        if now - last_check < _FILE_CHECK_INTERVAL_SECONDS:
            # Don't check mtime until interval has elapsed
            return cache_entry['html']
        
        # Time to check if file changed
        if file_path:
            try:
                mtime = os.path.getmtime(file_path)
            except OSError:
                mtime = None
        else:
            mtime = None
            
        cached_mtime = cache_entry.get('file_mtime')
        if mtime == cached_mtime:
            # File unchanged, only update 'last_checked'
            cache_entry['last_checked'] = now
            return cache_entry['html']
        # File changed! Will fall through and re-render.
    else:
        # No cache, get mtime for initial cache
        if file_path:
            try:
                mtime = os.path.getmtime(file_path)
            except OSError:
                mtime = None
        else:
            mtime = None

    # No cache, or file changed, or missing
    html = render_function()
    _page_cache[page_name] = {
        'html': html,
        'file_mtime': mtime,
        'last_checked': now
    }
    return html
# =============================================================================
# CACHE MANAGEMENT FUNCTIONS
# =============================================================================

# Note: Compression caching has been moved to routes.py as a simple cache key modifier
# No additional cache management functions are needed for the simplified approach
