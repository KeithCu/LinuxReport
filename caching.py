'''Various misc caching routines'''
from functools import lru_cache
import hashlib
import os
import datetime
import time

from shared import PATH, _JS_MODULES

def get_file_hash(filepath):
    """Get a hash of the file contents"""
    try:
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except:
        # Return 'dev' plus a timestamp on error (useful for dev environments)
        now = datetime.datetime.now()
        return f'dev{int(now.timestamp())}'

@lru_cache()
def static_file_hash(filename):
    """Get the hash for a specific static file. If the files change, service must be restarted."""
    static_dir = os.path.join(PATH, 'static')
    
    # Special handling for linuxreport.js - hash all source files
    if filename == 'linuxreport.js':
        file_hash = get_combined_hash(_JS_MODULES, os.path.join(PATH, 'templates'))
        if file_hash is None:
            # If any file can't be read, use timestamp
            now = datetime.datetime.now()
            return f'dev{int(now.timestamp())}'
        return file_hash
    
    # Normal file hashing for other files
    filepath = os.path.join(static_dir, filename)
    return get_file_hash(filepath)


def get_combined_hash(files, base_path):
    """Get hash of all source files combined
    
    Args:
        files (list): List of filenames to hash
        base_path (str): Base directory path containing the files
        
    Returns:
        str: MD5 hash of combined files, or None if any file can't be read
    """
    combined_hash = hashlib.md5()
    for file in files:
        file_path = os.path.join(base_path, file)
        try:
            with open(file_path, 'rb') as f:
                combined_hash.update(f.read())
        except:
            return None
    return combined_hash.hexdigest()[:8]

def compile_js_files():
    """Compile individual JS files into linuxreport.js"""
    static_dir = os.path.join(PATH, 'static')
    templates_dir = os.path.join(PATH, 'templates')
    output_file = os.path.join(static_dir, 'linuxreport.js')
    
    # Get hash and timestamp for header
    file_hash = get_combined_hash(_JS_MODULES, templates_dir)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Read and combine all files
    combined_content = []
    for module_file in _JS_MODULES:
        file_path = os.path.join(templates_dir, module_file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                combined_content.append(f.read())
        except Exception as e:
            print(f"Error reading {module_file}: {e}")
            return False
    
    # Write combined content to linuxreport.js with header
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f'// Compiled: {timestamp}\n')
            f.write(f'// Hash: {file_hash}\n')
            f.write('// Source files: ' + ', '.join(_JS_MODULES) + '\n\n')
            f.write('\n'.join(combined_content))
        return True
    except Exception as e:
        print(f"Error writing linuxreport.js: {e}")
        return False


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

