"""
app.py

Main entry point for the Flask application. Initializes the Flask app, configures extensions, loads shared settings, and registers routes.
"""
import sys
import os
import hashlib
from functools import lru_cache
import datetime
import glob

# Third-party imports
from flask import Flask
from flask_mobility import Mobility

sys.path.insert(0, "/srv/http/LinuxReport2")

# Local imports
from shared import EXPIRE_WEEK, PATH
from models import DEBUG

# Initialize Flask app
g_app = Flask(__name__)
Mobility(g_app)
application = g_app

if DEBUG or g_app.debug:
    print("Warning, in debug mode")

g_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = EXPIRE_WEEK
g_app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Limit uploads to 5MB
g_app.config['DEBUG'] = DEBUG

# Mechanism to throw away old URL cookies if the feeds change.
URLS_COOKIE_VERSION = "2"

# Define JS modules in order
_JS_MODULES = [
    'core.js',
    'weather.js',
    'chat.js',
    'config.js'
]

def get_combined_hash():
    """Get hash of all source files combined"""
    templates_dir = os.path.join(PATH, 'templates')
    combined_hash = hashlib.md5()
    for module_file in _JS_MODULES:
        file_path = os.path.join(templates_dir, module_file)
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
    file_hash = get_combined_hash()
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
        file_hash = get_combined_hash()
        if file_hash is None:
            # If any file can't be read, use timestamp
            now = datetime.datetime.now()
            return f'dev{int(now.timestamp())}'
        return file_hash
    
    # Normal file hashing for other files
    filepath = os.path.join(static_dir, filename)
    return get_file_hash(filepath)

# Make static_file_hash available to all templates
g_app.jinja_env.globals['static_file_hash'] = static_file_hash

# Compile JS files on startup
if compile_js_files():
    print("Successfully compiled linuxreport.js")
else:
    print("Warning: Failed to compile linuxreport.js")

# Import only init_app to avoid circular import
from routes import init_app

init_app(g_app)
