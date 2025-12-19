"""
app.py

Main entry point for the Flask application. Initializes the Flask app, configures extensions,
loads shared settings, and registers routes.
"""

# =============================================================================
# DEBUG: Show which Python is being used
# =============================================================================
import sys
print(f"🐍 Flask app starting with Python: {sys.executable}", file=sys.stderr)
print(f"🐍 Python path starts with: {sys.path[:2]}", file=sys.stderr)

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
import datetime
import hashlib
from pathlib import Path

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
from flask import Flask
from flask_mobility import Mobility
from flask_assets import Environment, Bundle, Filter
from flask_compress import Compress
from flask_login import LoginManager
from flask_restful import Api
from flask_wtf.csrf import CSRFProtect

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
# Add current directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from shared import (
    EXPIRE_WEEK, FLASK_DASHBOARD,
    limiter, ALL_URLS, get_lock, g_c, EXPIRE_YEARS,
    set_flask_restful_api, g_logger
)
from app_config import DEBUG, get_secret_key, get_dashboard_credentials
from models import User

# Define the order of JavaScript modules for loading
JS_MODULES = [
    'app.js',
    'infinitescroll.js',
    'core.js',
    'weather.js',
    'chat.js',
    'config.js',
]

# Define the order of CSS modules for loading
CSS_MODULES = [
    'themes.css',
    'core.css',
    'weather.css',
    'chat.css',
    'config.css',
]

# URLS_COOKIE_VERSION is now imported from shared.py

# =============================================================================
# CUSTOM FILTERS AND UTILITIES
# =============================================================================

def timestamp_to_int(timestamp):
    """
    Convert a time.struct_time object to an integer timestamp.
    
    Args:
        timestamp: time.struct_time object or None
        
    Returns:
        int: Unix timestamp as integer, or 0 if timestamp is None
    """
    if timestamp is None:
        return 0
    try:
        import time
        return int(time.mktime(timestamp))
    except (TypeError, ValueError):
        return 0

def run_one_time_last_fetch_migration(all_urls):
    """
    Performs a one-time migration of last_fetch times from old cache keys to the
    new unified 'all_last_fetches' cache. This is controlled by a flag to ensure
    it only runs once.
    
    Args:
        all_urls (list): List of all URLs to migrate
    """
    with get_lock("last_fetch_migration_lock"):
        if not g_c.has('last_fetch_migration_complete'):
            g_logger.info("Running one-time migration for last_fetch times...")
            all_fetches = g_c.get('all_last_fetches') or {}
            updated = False
            
            for url in all_urls:
                if url not in all_fetches:
                    old_last_fetch = g_c.get(url + ":last_fetch")
                    if old_last_fetch:
                        g_logger.info(f"Migrating last_fetch for {url}.")
                        all_fetches[url] = old_last_fetch
                        updated = True
            
            if updated:
                g_c.put('all_last_fetches', all_fetches, timeout=EXPIRE_YEARS)
                
            # Set the flag to indicate migration is complete
            g_c.put('last_fetch_migration_complete', True, timeout=EXPIRE_YEARS)
            g_logger.info("Last_fetch migration complete.")

# =============================================================================
# FLASK APPLICATION INITIALIZATION
# =============================================================================

def create_app():
    """
    Factory function to create and configure the Flask application.
    
    Returns:
        Flask: Configured Flask application instance
    """
    # Initialize Flask app
    app = Flask(__name__)
    
    # Apply basic configuration
    app.config.update({
        'SEND_FILE_MAX_AGE_DEFAULT': EXPIRE_WEEK,
        'MAX_CONTENT_LENGTH': 5 * 1024 * 1024,  # 5MB upload limit
        'DEBUG': DEBUG,
        'SECRET_KEY': get_secret_key()
    })
    
    # Register custom Jinja2 filters
    app.jinja_env.filters['timestamp_to_int'] = timestamp_to_int
    
    return app

# Create the main application instance
g_app = create_app()

# Logging is now handled in shared.py and imported

# =============================================================================
# FLASK EXTENSIONS INITIALIZATION
# =============================================================================

def initialize_extensions(app):
    """
    Initialize all Flask extensions.
    
    Args:
        app (Flask): Flask application instance
    """
    # Initialize Flask-Mobility for mobile detection
    Mobility(app)
    
    # Initialize Flask-Compress for response compression
    # Compress(app)
    # NOTE: Compression is currently handled by Apache mod_deflate/mod_brotli at the server level,
    # which is more efficient than application-level compression. If deploying with Gunicorn,
    # nginx, or another WSGI server without compression, uncomment the line above to enable
    # Flask-Compress for gzip/brotli compression of Flask responses only.
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user for Flask-Login."""
        return User.get(user_id)
    
    # Initialize rate limiter
    limiter.init_app(app)
    
    # Initialize Flask-RESTful API
    api_instance = Api(app)
    set_flask_restful_api(api_instance)
    
    # Initialize Flask-WTF CSRF protection
    csrf = CSRFProtect()
    csrf.init_app(app)
    
    # Disable CSRF protection for API endpoints
    app.config['WTF_CSRF_ENABLED'] = False
    
    return login_manager

# Initialize extensions
g_login_manager = initialize_extensions(g_app)

# =============================================================================
# MONITORING DASHBOARD CONFIGURATION
# =============================================================================

def setup_monitoring_dashboard(app):
    """
    Set up Flask-MonitoringDashboard if enabled.
    
    Args:
        app (Flask): Flask application instance
    """
    if not FLASK_DASHBOARD:
        return
    
    try:
        import flask_monitoringdashboard as dashboard
        from flask_monitoringdashboard.core.config import Config
        
        # Configure Flask-MonitoringDashboard
        dashboard_credentials = get_dashboard_credentials()
        config = Config()
        config.USERNAME = dashboard_credentials.get('username')
        config.PASSWORD = dashboard_credentials.get('password')
        config.DATABASE = 'sqlite:///flask_monitoringdashboard.db'
        
        # Initialize with custom configuration
        dashboard.bind(app, config)
        g_logger.info("Flask-MonitoringDashboard initialized successfully")
        
    except ImportError:
        g_logger.warning("Flask-MonitoringDashboard not available")
    except (AttributeError, TypeError) as e:
        g_logger.warning(f"Failed to initialize Flask-MonitoringDashboard: {e}")

# Set up monitoring dashboard
setup_monitoring_dashboard(g_app)

# =============================================================================
# ASSET BUNDLING CONFIGURATION
# =============================================================================

def setup_asset_bundles(app):
    """
    Set up Flask-Assets for JavaScript and CSS bundling.
    
    Args:
        app (Flask): Flask application instance
        
    Returns:
        tuple: (js_bundle, css_bundle) - Configured asset bundles
    """
    # Initialize Flask-Assets
    g_assets = Environment(app)
    g_assets.url = app.static_url_path
    
    # Create JS bundle from individual modules
    js_files = [
        str(Path(__file__).parent / 'templates' / module)
        for module in JS_MODULES
    ]

    # Register JavaScript bundle
    g_js_bundle = g_assets.register('js_all', Bundle(
        *js_files,
        output='linuxreport.js'
    ))

    # Create CSS bundle from individual modules
    css_files = [
        str(Path(__file__).parent / 'templates' / module)
        for module in CSS_MODULES
    ]

    # Register CSS bundle for cache busting
    g_css_bundle = g_assets.register('css_all', Bundle(
        *css_files,
        output='linuxreport.css'
    ))
    
    # Make assets available to templates
    app.jinja_env.globals['assets'] = g_assets
    
    return g_assets, g_js_bundle, g_css_bundle

# Set up asset bundles
g_assets, g_js_bundle, g_css_bundle = setup_asset_bundles(g_app)

# =============================================================================
# APPLICATION STARTUP TASKS
# =============================================================================

def _process_bundle(app, bundle, output_name, modules, comment_style='js'):
    """
    Process an asset bundle: check hash, rebuild if changed, and add header.
    
    Args:
        app: Flask application instance
        bundle: The asset bundle to process
        output_name: Filename of the output bundle (e.g., 'linuxreport.js')
        modules: List of module filenames included in the bundle
        comment_style: 'js' for // or 'css' for /* ... */
    """
    output_path = Path(app.static_folder) / output_name
    label = "JavaScript" if comment_style == 'js' else "CSS"
    
    # 1. Get existing hash from header
    existing_hash = None
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                # Read first few lines to find hash
                for _ in range(5):
                    line = f.readline()
                    if not line: break
                    prefix = '// Hash: ' if comment_style == 'js' else '/* Hash: '
                    if line.startswith(prefix):
                        existing_hash = line.split(prefix)[1].strip().split(' ')[0]
                        break
        except IOError as e:
            g_logger.warning(f"Could not read existing {label} bundle: {e}")

    # 2. Calculate hash of source files
    source_content = ""
    for module in modules:
        source_path = Path(__file__).parent / 'templates' / module
        if source_path.exists():
            with open(source_path, 'r', encoding='utf-8') as f:
                source_content += f.read()

    new_hash = hashlib.md5(source_content.encode('utf-8')).hexdigest()[:8]

    # 3. Only rebuild if hash changed or file doesn't exist
    if not existing_hash or existing_hash != new_hash:
        if output_path.exists():
            output_path.unlink()
            g_logger.info(f"Removed existing {label} bundle for fresh build")

        bundle.build()
        g_logger.info(f"{label} bundle built successfully")

        # Add header information
        if output_path.exists():
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()

            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if comment_style == 'js':
                header = f'// Compiled: {timestamp}\n'
                header += f'// Hash: {new_hash}\n'
                header += f'// Source files: {", ".join(modules)}\n\n'
            else:
                header = f'/* Compiled: {timestamp} */\n'
                header += f'/* Hash: {new_hash} */\n'
                header += f'/* Source files: {", ".join(modules)} */\n\n'

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(header + content)

            g_logger.info(f"{label} content changed (new hash: {new_hash}), updated with new header")
        else:
            g_logger.warning(f"{label} bundle was not created after build")
    else:
        g_logger.info(f"{label} content unchanged (hash: {new_hash}), reusing existing file")

def perform_startup_tasks(app, js_bundle, css_bundle):
    """
    Perform necessary startup tasks like building assets and running migrations.

    Args:
        app (Flask): Flask application instance
        js_bundle: JavaScript asset bundle
        css_bundle: CSS asset bundle
    """
    with app.app_context():
        try:
            # Process JavaScript bundle
            _process_bundle(app, js_bundle, 'linuxreport.js', JS_MODULES, comment_style='js')

            # Process CSS bundle
            _process_bundle(app, css_bundle, 'linuxreport.css', CSS_MODULES, comment_style='css')

            # Run one-time migration of last_fetch times
            run_one_time_last_fetch_migration(ALL_URLS.keys())

        except (IOError, OSError, RuntimeError) as e:
            g_logger.warning(f"Failed to complete startup tasks: {e}")

# Perform startup tasks
perform_startup_tasks(g_app, g_js_bundle, g_css_bundle)

# =============================================================================
# ROUTE REGISTRATION
# =============================================================================

# Import and initialize routes (avoid circular import)
from routes import init_app
init_app(g_app)

# =============================================================================
# DEBUG MODE WARNINGS
# =============================================================================

if DEBUG or g_app.debug:
    g_logger.warning("Application is running in debug mode")

# =============================================================================
# WSGI ENTRY POINT
# =============================================================================

# WSGI entry point - set after all initialization is complete
# This ensures the application is fully configured before being used by WSGI servers
# Compatible with both mod_wsgi (Apache) and Gunicorn
# Use 'app:application' as the WSGI callable in Gunicorn configs
application = g_app

