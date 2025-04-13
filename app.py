import sys
import os
import json
from datetime import datetime
from timeit import default_timer as timer
from flask import Flask
from flask_mobility import Mobility

# Ensured shared module is correctly imported
import shared
from shared import EXPIRE_WEEK, Mode, g_c, MODE, DEBUG
from workers import load_url_worker, refresh_thread
from forms import ConfigForm, UrlForm, CustomRSSForm

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

# Configuration variables are now set dynamically
ALL_URLS = shared.ALL_URLS
site_urls = shared.site_urls
USER_AGENT = shared.USER_AGENT
URL_IMAGES = shared.URL_IMAGES
FAVICON = shared.FAVICON
LOGO_URL = shared.LOGO_URL
WEB_DESCRIPTION = shared.WEB_DESCRIPTION
WEB_TITLE = shared.WEB_TITLE
ABOVE_HTML_FILE = shared.ABOVE_HTML_FILE
WELCOME_HTML = shared.WELCOME_HTML
STANDARD_ORDER_STR = shared.STANDARD_ORDER_STR

# Import routes and pass the app instance
import routes
routes.init_app(g_app)

