"""
app.py

Main entry point for the Flask application. Initializes the Flask app, configures extensions, loads shared settings, and registers routes.
"""
import sys
import os

# Third-party imports
from flask import Flask
from flask_mobility import Mobility

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Local imports
from shared import EXPIRE_WEEK
from models import DEBUG
from caching import static_file_hash, compile_js_files

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

