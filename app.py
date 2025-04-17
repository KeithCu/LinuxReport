"""
app.py

Main entry point for the Flask application. Initializes the Flask app, configures extensions, loads shared settings, and registers routes.
"""
import sys

# Third-party imports
from flask import Flask
from flask_mobility import Mobility

sys.path.insert(0, "/srv/http/LinuxReport2")

# Local imports
from shared import EXPIRE_WEEK, DEBUG

# Initialize Flask app
g_app = Flask(__name__)
Mobility(g_app)
application = g_app

if DEBUG or g_app.debug:
    print("Warning, in debug mode")

g_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = EXPIRE_WEEK

# Mechanism to throw away old URL cookies if the feeds change.
URLS_COOKIE_VERSION = "2"

USE_TOR = True

# Available theme choices
THEME_CHOICES = ['light', 'dark', 'solarized']

# Theme choice: global variable (choose one from THEME_CHOICES)
THEME = 'light'
g_app.jinja_env.globals['THEME'] = THEME

# Import routes and pass the app instance
import routes
routes.init_app(g_app)
