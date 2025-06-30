"""
app.py

Main entry point for the Flask application. Initializes the Flask app, configures extensions, 
loads shared settings, and registers routes.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import sys
import os
import datetime
import hashlib

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import (
    EXPIRE_WEEK, JS_MODULES, FLASK_DASHBOARD, 
    FLASK_DASHBOARD_USERNAME, FLASK_DASHBOARD_PASSWORD, 
    limiter, ALL_URLS, get_lock, g_c, EXPIRE_YEARS,
    API, set_flask_restful_api
)
from app_config import DEBUG, get_secret_key
from models import User

# =============================================================================
# COOKIE VERSIONING
# =============================================================================

# Mechanism to invalidate old URL cookies if feeds change
URLS_COOKIE_VERSION = "2"


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
            print("Running one-time migration for last_fetch times...")
            all_fetches = g_c.get('all_last_fetches') or {}
            updated = False
            
            for url in all_urls:
                if url not in all_fetches:
                    old_last_fetch = g_c.get(url + ":last_fetch")
                    if old_last_fetch:
                        print(f"Migrating last_fetch for {url}.")
                        all_fetches[url] = old_last_fetch
                        updated = True
            
            if updated:
                g_c.put('all_last_fetches', all_fetches, timeout=EXPIRE_YEARS)
                
            # Set the flag to indicate migration is complete
            g_c.put('last_fetch_migration_complete', True, timeout=EXPIRE_YEARS)
            print("Last_fetch migration complete.")

def add_header_to_file(file_path, file_type, source_files):
    """
    Add header information to a compiled file.
    
    Args:
        file_path (str): Path to the compiled file
        file_type (str): Type of file ('JavaScript' or 'CSS')
        source_files (list): List of source files that were compiled
    """
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Generate header information
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:8]
        except Exception:
            file_hash = f'dev{int(datetime.datetime.now().timestamp())}'
        
        # Create header based on file type
        if file_type == 'JavaScript':
            header = f'// Compiled: {timestamp}\n'
            header += f'// Hash: {file_hash}\n'
            header += f'// Source files: {", ".join(source_files)}\n\n'
        else:  # CSS
            header = f'/* Compiled: {timestamp} */\n'
            header += f'/* Hash: {file_hash} */\n'
            header += f'/* Source files: {", ".join(source_files)} */\n\n'
        
        # Write back with header
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(header + content)
        
        print(f"Header information added to {file_type} bundle")
    else:
        print(f"Warning: {file_type} bundle was not created after build")

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
application = g_app  # WSGI entry point

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
    Compress(app)
    
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
login_manager = initialize_extensions(g_app)

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
        config = Config()
        config.USERNAME = FLASK_DASHBOARD_USERNAME
        config.PASSWORD = FLASK_DASHBOARD_PASSWORD
        config.DATABASE = 'sqlite:///flask_monitoringdashboard.db'
        
        # Initialize with custom configuration
        dashboard.bind(app, config)
        print("Flask-MonitoringDashboard initialized successfully")
        
    except ImportError:
        print("Warning: Flask-MonitoringDashboard not available")
    except Exception as e:
        print(f"Warning: Failed to initialize Flask-MonitoringDashboard: {e}")

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
    assets = Environment(app)
    assets.url = app.static_url_path
    
    # Create JS bundle from individual modules
    js_files = [
        os.path.join(os.path.dirname(__file__), 'templates', module) 
        for module in JS_MODULES
    ]
    
    # Register JavaScript bundle
    js_bundle = assets.register('js_all', Bundle(
        *js_files,
        output='linuxreport.js'
    ))
    
    # Register a single CSS bundle including main and component CSS
    css_bundle = assets.register('css_all', Bundle(
        'css/themes/Themes.css',
        'css/linuxreport.css',
        'css/components/Typography.css',
        'css/components/Forms.css',
        'css/components/Layout.css',
        'css/components/WeatherWidget.css',
        'css/components/Navigation.css',
        'css/components/ChatWindow.css',
        'css/components/ConfigPage.css',
        'css/components/MainContent.css',
        'css/components/Responsive.css',
        output='linuxreport.css'
    ))
    
    # Make assets available to templates
    app.jinja_env.globals['assets'] = assets
    
    return assets, js_bundle, css_bundle

# Set up asset bundles
assets, js_bundle, css_bundle = setup_asset_bundles(g_app)

# =============================================================================
# APPLICATION STARTUP TASKS
# =============================================================================

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
            # Clear existing compiled JS file to ensure fresh build
            js_output_path = os.path.join(app.static_folder, 'linuxreport.js')
            if os.path.exists(js_output_path):
                os.remove(js_output_path)
                print("Removed existing JavaScript bundle for fresh build")
            
            # Build asset bundles (this should create a fresh file)
            js_bundle.build()
            print("JavaScript bundle built successfully")
            
            # Add header information to the freshly compiled JS file
            add_header_to_file(js_output_path, 'JavaScript', JS_MODULES)
            
            css_bundle.build()
            print("CSS bundle built successfully")
            
            # Add header information to the compiled CSS file
            css_output_path = os.path.join(app.static_folder, 'linuxreport.css')
            css_source_files = ['Themes.css', 'linuxreport.css', 'Typography.css', 'Forms.css', 'Layout.css', 'WeatherWidget.css', 'Navigation.css', 'ChatWindow.css', 'ConfigPage.css', 'MainContent.css', 'Responsive.css']
            add_header_to_file(css_output_path, 'CSS', css_source_files)
            
            # Run one-time migration of last_fetch times
            run_one_time_last_fetch_migration(ALL_URLS.keys())
            
        except Exception as e:
            print(f"Warning: Failed to complete startup tasks: {e}")

# Perform startup tasks
perform_startup_tasks(g_app, js_bundle, css_bundle)

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
    print("Warning: Application is running in debug mode")

