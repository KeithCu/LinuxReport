"""
app.py

Main entry point for the Flask application. Initializes the Flask app, configures extensions, loads shared settings, and registers routes.
"""
import sys
import os
import datetime
import hashlib

# Third-party imports
from flask import Flask
from flask_mobility import Mobility
from flask_assets import Environment, Bundle
from flask_assets import Filter
from flask_compress import Compress
from flask_login import LoginManager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Local imports
from shared import EXPIRE_WEEK, _JS_MODULES, FLASK_DASHBOARD, FLASK_DASHBOARD_USERNAME, FLASK_DASHBOARD_PASSWORD, limiter
from models import DEBUG, User, get_secret_key

# Custom filter to add header information
class HeaderFilter(Filter):
    """Add header information to compiled files"""

    def __init__(self, source_files, file_type="JavaScript"):
        super().__init__()
        self.source_files = source_files
        self.file_type = file_type

    def apply(self, _in, out):
        # Get timestamp
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Read the content
        content = _in.read()

        try:
            file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:8]
        except:
            # Return 'dev' plus a timestamp on error
            file_hash = f'dev{int(datetime.datetime.now().timestamp())}'

        # Write header
        out.write(f'// Compiled: {timestamp}\n')
        out.write(f'// Hash: {file_hash}\n')
        out.write(f'// Source files: {", ".join(self.source_files)}\n\n')

        # Write the actual content
        out.write(content)

# Initialize Flask app
g_app = Flask(__name__)
Mobility(g_app)
Compress(g_app)  # Initialize Flask-Compress for response compression
application = g_app

if DEBUG or g_app.debug:
    print("Warning, in debug mode")

g_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = EXPIRE_WEEK
g_app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Limit uploads to 5MB
g_app.config['DEBUG'] = DEBUG

# Add a secret key for Flask-Login (required for session security)
g_app.config['SECRET_KEY'] = get_secret_key()

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(g_app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login."""
    return User.get(user_id)

# Initialize Flask-MonitoringDashboard if enabled
if FLASK_DASHBOARD:
    import flask_monitoringdashboard as dashboard
    from flask_monitoringdashboard.core.config import Config

    # Configure Flask-MonitoringDashboard
    config = Config()
    config.USERNAME = FLASK_DASHBOARD_USERNAME
    config.PASSWORD = FLASK_DASHBOARD_PASSWORD

    # Set database to use SQLite file (persistent storage)
    config.DATABASE = 'sqlite:///flask_monitoringdashboard.db'

    # Initialize with custom configuration
    dashboard.bind(g_app, config)

# Mechanism to throw away old URL cookies if the feeds change.
URLS_COOKIE_VERSION = "2"

# Initialize Flask-Assets
assets = Environment(g_app)
assets.url = g_app.static_url_path

# Create JS bundle from individual modules in templates directory
# Use absolute paths since files are in templates/ not static/templates/
js_files = [os.path.join(os.path.dirname(__file__), 'templates', module) for module in _JS_MODULES]

# Only minify in production (not in debug mode)
filters_list = [HeaderFilter(_JS_MODULES, "JavaScript")]
# Note: jsmin doesn't support ES6 class syntax, so we're not using it
# if not DEBUG and not g_app.debug:
#     filters_list.append('jsmin')

js_bundle = assets.register('js_all', Bundle(
    *js_files,
    filters=filters_list,
    output='linuxreport.js'
))

# Create CSS bundle for cache busting only (no modification)
css_bundle = assets.register('css_all', Bundle(
    'linuxreport.css',
    output='linuxreport.css'
))

limiter.init_app(g_app)

# Build assets on startup
with g_app.app_context():
    try:
        js_bundle.build()
        print("JavaScript bundle built successfully")
        css_bundle.build()
        print("CSS cache busting configured successfully")
    except Exception as e:
        print(f"Warning: Failed to build assets: {e}")

# Make assets available to templates
g_app.jinja_env.globals['assets'] = assets

# Import only init_app to avoid circular import
from routes import init_app

init_app(g_app)
