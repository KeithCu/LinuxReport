"""
app.py

Main entry point for the Flask application. Initializes the Flask app, configures extensions, loads shared settings, and registers routes.
"""
import sys
import os
import hashlib

# Third-party imports
from flask import Flask
from flask_mobility import Mobility

sys.path.insert(0, "/srv/http/LinuxReport2")

# Local imports
from shared import EXPIRE_WEEK, PATH

DEBUG = False
USE_TOR = True

# Initialize Flask app
g_app = Flask(__name__)
Mobility(g_app)
application = g_app

if DEBUG or g_app.debug:
    print("Warning, in debug mode")

g_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = EXPIRE_WEEK
g_app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Limit uploads to 5MB

# Mechanism to throw away old URL cookies if the feeds change.
URLS_COOKIE_VERSION = "2"

def get_file_hash(filepath):
    """Get a hash of the file contents"""
    try:
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except:
        return 'dev'

def static_file_hash(filename):
    """Get the hash for a specific static file"""
    static_dir = os.path.join(PATH, 'static')
    filepath = os.path.join(static_dir, filename)
    return get_file_hash(filepath)

# Make static_file_hash available to all templates
g_app.jinja_env.globals['static_file_hash'] = static_file_hash

# Import routes and pass the app instance
import routes

routes.init_app(g_app)
