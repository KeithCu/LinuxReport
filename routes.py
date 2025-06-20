"""
routes.py

This file contains all the Flask route handlers for the application, including the main index page, configuration page, and weather API.
"""

# Standard library imports
import os
import json
from timeit import default_timer as timer
import datetime
import html
import uuid
import ipaddress
import time

# Third-party imports
from flask import g, jsonify, render_template, request, make_response, Response, flash, redirect, url_for
from markupsafe import Markup
from werkzeug.utils import secure_filename
from flask_cors import CORS
from flask_login import login_user, logout_user, login_required, current_user

from forms import ConfigForm, CustomRSSForm, UrlForm, LoginForm
from models import RssInfo, DEBUG, get_admin_password, User
# Local imports
from shared import (ABOVE_HTML_FILE, ALL_URLS, EXPIRE_MINUTES, EXPIRE_DAY, EXPIRE_HOUR, EXPIRE_YEARS,
                    FAVICON, LOGO_URL, STANDARD_ORDER_STR,
                    URL_IMAGES, URLS_COOKIE_VERSION, WEB_DESCRIPTION,
                    WEB_TITLE, WELCOME_HTML, g_c, g_cm, SITE_URLS, MODE, PATH, format_last_updated, 
                    get_chat_cache, MODE_MAP, clear_page_caches,
                    ENABLE_URL_CUSTOMIZATION, ALLOWED_DOMAINS, ENABLE_CORS, ALLOWED_REQUESTER_DOMAINS,
                    ENABLE_URL_IMAGE_CDN_DELIVERY, CDN_IMAGE_URL, WEB_BOT_USER_AGENTS,
                    INFINITE_SCROLL_MOBILE, INFINITE_SCROLL_DEBUG)
from weather import get_default_weather_html, get_weather_data, DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON
from workers import fetch_urls_parallel, fetch_urls_thread
from caching import get_cached_file_content, _file_cache

# Global setting for background refreshes
ENABLE_BACKGROUND_REFRESH = True

# Constants for Chat Feature
MAX_COMMENTS = 1000
COMMENTS_KEY = "chat_comments"
BANNED_IPS_KEY = "banned_ips" # Store as a set in cache
WEB_UPLOAD_PATH = '/static/uploads' # Define the web-accessible path prefix
UPLOAD_FOLDER = PATH + WEB_UPLOAD_PATH # Define absolute upload folder for server deployment
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'} # Allowed image types
MAX_IMAGE_SIZE = 5 * 1024 * 1024 # 5 MB

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Helper function to get IP prefix
def get_ip_prefix(ip_str):
    """Extracts the first part of IPv4 or the first block of IPv6."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if isinstance(ip, ipaddress.IPv4Address):
            return ip_str.split('.')[0]
        elif isinstance(ip, ipaddress.IPv6Address):
            return ip_str.split(':')[0]
    except ValueError:
        return "Invalid IP"
    return None

def get_cached_above_html():
    """Return content of ABOVE_HTML_FILE using generic cache."""
    return get_cached_file_content(os.path.join(PATH, ABOVE_HTML_FILE))

def update_performance_stats(render_time):
    """Update performance statistics for admin mode."""
    stats_key = "admin_performance_stats"
    stats = g_cm.get(stats_key) or {
        "times": [],
        "count": 0,
        "hourly_requests": {},  # Track requests per hour
        "first_request_time": time.time()
    }
    
    current_time = time.time()
    current_hour = int(current_time / 3600)  # Get current hour timestamp
    
    # Initialize hourly request count if not exists
    if current_hour not in stats["hourly_requests"]:
        stats["hourly_requests"][current_hour] = 0
    
    # Update hourly request count
    stats["hourly_requests"][current_hour] += 1
    
    # Clean up old hourly data (keep last 24 hours)
    old_hour = current_hour - 24
    stats["hourly_requests"] = {h: count for h, count in stats["hourly_requests"].items() if h > old_hour}
    
    stats["count"] += 1
    
    # Skip the first request (cold start)
    if stats["count"] > 1:
        stats["times"].append(render_time)
        
        # Keep only last 100 measurements
        if len(stats["times"]) > 100:
            stats["times"] = stats["times"][-100:]
    
    # Store back
    g_cm.set(stats_key, stats, ttl=EXPIRE_DAY)

def get_admin_stats_html():
    """Generate HTML for admin performance stats."""
    stats_key = "admin_performance_stats"
    stats = g_cm.get(stats_key)
    
    if not stats or not stats.get("times"):
        return None
    
    times = stats["times"]
    if len(times) < 3:
        return None
    
    # Calculate statistics
    sorted_times = sorted(times)
    min_time = min(sorted_times)
    max_time = max(sorted_times)
    avg_time = sum(times) / len(times)
    count = stats.get("count", len(times))
    
    # Calculate request counts for different time windows
    current_time = time.time()
    current_hour = int(current_time / 3600)
    
    # Get request counts for different time windows
    hourly_requests = stats.get("hourly_requests", {})
    requests_1h = sum(count for hour, count in hourly_requests.items() if hour == current_hour)
    requests_6h = sum(count for hour, count in hourly_requests.items() if hour >= current_hour - 6)
    requests_12h = sum(count for hour, count in hourly_requests.items() if hour >= current_hour - 12)
    
    # Calculate uptime
    first_request_time = stats.get("first_request_time", time.time())
    uptime_seconds = time.time() - first_request_time
    uptime_str = str(datetime.timedelta(seconds=int(uptime_seconds)))
    
    return f'''
    <div style="position: fixed; top: 10px; right: 10px; background: #ccc; color: #333; padding: 10px; 
                border-radius: 5px; font-family: monospace; font-size: 12px; z-index: 9999; 
                border: 1px solid #999; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <strong>Admin Stats (Page Render)</strong><br>
        Uptime: {uptime_str}<br>
        Total Requests: {count}<br>
        Requests (1h): {requests_1h}<br>
        Requests (6h): {requests_6h}<br>
        Requests (12h): {requests_12h}<br>
        Min: {min_time:.3f}s<br>
        Max: {max_time:.3f}s<br>
        Avg: {avg_time:.3f}s
    </div>
    '''

# Function to initialize routes
def init_app(flask_app):
    """Initialize Flask routes."""
    # Configure CORS and security headers only if enabled
    if ENABLE_CORS:
        # Configure CORS to allow requests from specified domains
        CORS(flask_app, resources={
            r"/api/weather": {  # Only allow CORS for weather API
                "origins": ALLOWED_REQUESTER_DOMAINS,
                "methods": ["GET", "OPTIONS"],
                "allow_headers": ["Content-Type"],
                "expose_headers": ["Content-Type"],
                "supports_credentials": True,
                "max_age": 3600  # Cache preflight requests for 1 hour
            }
        })
        
        # Add security headers to all responses
        @flask_app.after_request
        def add_security_headers(response):
            # Add CORS headers only for weather API
            if request.path == '/api/weather':
                origin = request.headers.get('Origin')
                if origin in ALLOWED_REQUESTER_DOMAINS:
                    response.headers['Access-Control-Allow-Origin'] = origin
                    response.headers['Access-Control-Allow-Credentials'] = 'true'
                    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
                    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            
            # Add other security headers
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            
            # Add CSP header that allows connections to this domain and CDN if enabled
            img_src = "'self' data:"
            if ENABLE_URL_IMAGE_CDN_DELIVERY:
                img_src += f" {CDN_IMAGE_URL}"
            
            csp_domains = " ".join(ALLOWED_DOMAINS)
            response.headers['Content-Security-Policy'] = (
                f"default-src 'self'; "
                f"connect-src 'self' {csp_domains}; "  # Allow connections to all allowed domains
                f"img-src {img_src} *; "  # Allow images from any domain
                f"script-src 'self' 'unsafe-inline'; "
                f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "  # Allow Google Fonts stylesheets
                f"font-src 'self' https://fonts.gstatic.com; "  # Allow Google Fonts files
                f"frame-ancestors 'none';"
            )
            
            return response

    # Login route
    @flask_app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            form = LoginForm(request.form)
            if form.validate():
                user = User.authenticate(form.username.data, form.password.data)
                if user:
                    login_user(user, remember=form.remember_me.data)
                    next_page = request.args.get('next')
                    if not next_page or not next_page.startswith('/'):
                        next_page = url_for('index')
                    return redirect(next_page)
                else:
                    flash('Invalid username or password')
        else:
            form = LoginForm()
        
        return render_template('login.html', form=form)

    # Logout route
    @flask_app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))

    # The main page of LinuxReport. Most of the time, it won't need to hit the disk to return the page
    # even if the page cache is expired.
    @flask_app.route('/')
    def index():
        # Check if admin mode is enabled for performance tracking using Flask-Login
        is_admin = current_user.is_authenticated

        # Calculate performance stats for non-admin requests
        if not is_admin:
            start_time = timer()
        
        # Determine the order of RSS feeds to display.
        page_order = None
        if request.cookies.get('UrlsVer') == URLS_COOKIE_VERSION:
            page_order = request.cookies.get('RssUrls')
            if page_order is not None:
                page_order = json.loads(page_order)

        if page_order is None:
            page_order = SITE_URLS

        page_order_s = str(page_order)

        # Determine display settings based on user preferences and device type.
        suffix = ""
        single_column = False

        if g.is_mobile:
            suffix = ":MOBILE"
            single_column = True

        # Try full page cache using only page order and mobile flag (but not for admin mode)
        cache_key = f"page-cache:{page_order_s}{suffix}"
        full_page = g_cm.get(cache_key) if not is_admin else None
        if not DEBUG and not is_admin and full_page is not None:
            response = make_response(full_page)
            return response

        # Prepare the page layout.
        if single_column:
            result = [[]]
        else:
            result = [[], [], []]

        cur_col = 0

        needed_urls = []
        need_fetch = False
        last_fetch_cache = {}  # Cache for last_fetch results

        # 1. See if we need to fetch any RSS feeds
        for url in page_order:
            rss_info = ALL_URLS.get(url, None)

            if rss_info is None:
                rss_info = RssInfo("Custom.png", "Custom site", url + "HTML")
                ALL_URLS[url] = rss_info

            # Cache the last_fetch result for later use
            last_fetch = g_c.get_last_fetch(url)
            last_fetch_cache[url] = last_fetch
            
            expired_rss = ENABLE_BACKGROUND_REFRESH and g_c.has_feed_expired(url, last_fetch)

            if not g_c.has(url):
                needed_urls.append(url)
            elif expired_rss:
                need_fetch = True

        # 2. Fetch any needed feeds
        if len(needed_urls) > 0:
            start = timer()
            fetch_urls_parallel(needed_urls)
            end = timer()
            print(f"Fetched {len(needed_urls)} feeds in {end - start} sec.")

        # 3. Render the RSS feeds into the page layout.
        for url in page_order:
            rss_info = ALL_URLS[url]

            template = g_cm.get(rss_info.site_url)
            # Check if the feed has been updated since we rendered this template
            render_time = g_cm.get(f"{rss_info.site_url}_render_time")
            last_fetch = last_fetch_cache.get(url)  # Use cached value instead of calling get_last_fetch again
            if render_time != last_fetch:
                # Feed was updated, treat as if template doesn't exist
                template = None

            if DEBUG or template is None:
                feed = g_c.get(url)
                last_fetch_str = format_last_updated(last_fetch)
                if feed is not None:
                    entries = feed.entries
                    top_images = {article['url']: article['image_url'] for article in feed.top_articles if article['image_url']}
                else:
                    entries = []
                    top_images = {}
                template = render_template('sitebox.html', top_images=top_images, entries=entries, logo=URL_IMAGES + rss_info.logo_url,
                                           alt_tag=rss_info.logo_alt, link=rss_info.site_url, last_fetch = last_fetch_str, feed_id = rss_info.site_url,
                                           error_message=("Feed could not be loaded." if feed is None else None))

                # Cache entry deleted by worker thread after fetch, however, that only effects the same process.
                g_cm.set(rss_info.site_url, template, ttl=EXPIRE_HOUR)
                # Store the last fetch time when we rendered this template
                g_cm.set(f"{rss_info.site_url}_render_time", last_fetch, ttl=EXPIRE_DAY)

            result[cur_col].append(template)

            if not single_column:
                cur_col += 1
                cur_col %= 3

        result[0] = Markup(''.join(result[0]))

        if not single_column:
            result[1] = Markup(''.join(result[1]))
            result[2] = Markup(''.join(result[2]))

        above_html = get_cached_above_html()

        if not single_column:
            above_html = above_html.replace("<hr/>", "")

        weather_html = get_default_weather_html()

        # Render the final page.
        page = render_template('page.html', columns=result,
                               logo_url=LOGO_URL, title=WEB_TITLE,
                               description=WEB_DESCRIPTION, favicon=FAVICON,
                               welcome_html=Markup(WELCOME_HTML),
                               above_html=Markup(above_html),
                               weather_html=Markup(weather_html),
                               INFINITE_SCROLL_MOBILE=INFINITE_SCROLL_MOBILE,
                               INFINITE_SCROLL_DEBUG=INFINITE_SCROLL_DEBUG)

        # Store full page cache (but not for admin mode)
        if not is_admin and page_order_s == STANDARD_ORDER_STR:
            expire = EXPIRE_MINUTES
            if need_fetch:
                expire = 30
            g_cm.set(cache_key, page, ttl=expire)

        # Track performance stats for non-admin mode
        if not is_admin:
            render_time = timer() - start_time
            update_performance_stats(render_time)
        else:
            # Add stats display to the page for admin mode
            stats_html = get_admin_stats_html()
            if stats_html:
                page = page.replace('</body>', f'{stats_html}</body>')

        # Trigger background fetching if needed
        if need_fetch and ENABLE_BACKGROUND_REFRESH:
            # Check if the request is from a web bot
            user_agent = request.headers.get('User-Agent', '')
            is_web_bot = any(bot in user_agent for bot in WEB_BOT_USER_AGENTS)
            
            if not is_web_bot:
                fetch_urls_thread()
        
        response = make_response(page)
        # Add cache control headers for 30 minutes (1800 seconds)
        response.headers['Cache-Control'] = 'public, max-age=1800'
        response.headers['Expires'] = (datetime.datetime.utcnow() + datetime.timedelta(hours=0.5)).strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response

    @flask_app.route('/config', methods=['GET', 'POST'], strict_slashes=False)
    def config():
        # Use Flask-Login for admin authentication
        is_admin = current_user.is_authenticated

        if request.method == 'GET':
            form = ConfigForm()

            no_underlines_cookie = request.cookies.get('NoUnderlines', "1")
            form.no_underlines.data = no_underlines_cookie == "1"

            # Load headlines HTML if in admin mode
            if is_admin:
                try:
                    above_html_path = os.path.join(PATH, ABOVE_HTML_FILE)

                    with open(above_html_path, 'r', encoding='utf-8') as f:
                        form.headlines.data = f.read()
                except Exception as e:
                    print(f"Error reading headlines file: {e}")
                    form.headlines.data = ""

            # Only add URL customization options if enabled
            if ENABLE_URL_CUSTOMIZATION:
                page_order = request.cookies.get('RssUrls')
                if page_order is not None:
                    page_order = json.loads(page_order)
                else:
                    page_order = SITE_URLS

                custom_count = 0
                for i, p_url in enumerate(page_order):
                    rss_info = ALL_URLS.get(p_url, None)
                    if rss_info is not None and rss_info.logo_url != "Custom.png":
                        urlf = UrlForm()
                        urlf.pri = (i + 1) * 10
                        urlf.url = p_url
                        form.urls.append_entry(urlf)
                    else:
                        custom_count += 1
                        rssf = CustomRSSForm()
                        rssf.url = p_url
                        rssf.pri = (i + 1) * 10
                        form.url_custom.append_entry(rssf)

                # Only add empty custom URL entries if customization is enabled
                for i in range(custom_count, 5):
                    rssf = CustomRSSForm()
                    rssf.url = "http://"
                    rssf.pri = (i + 30) * 10
                    form.url_custom.append_entry(rssf)

            page = render_template('config.html', form=form, is_admin=is_admin, 
                                  favicon=FAVICON, enable_url_customization=ENABLE_URL_CUSTOMIZATION)
            return page
        else:
            form = ConfigForm(request.form)
            if form.delete_cookie.data:
                template = render_template('configdone.html', message="Deleted cookies.")
                resp = make_response(template)
                resp.delete_cookie('RssUrls')
                resp.delete_cookie('Theme')
                resp.delete_cookie('NoUnderlines')
                return resp

            # Use Flask-Login authentication - no need for manual password checking
            is_admin = current_user.is_authenticated

            # Save headlines if in admin mode and headlines were provided
            if is_admin and form.headlines.data:
                try:
                    above_html_path = os.path.join(PATH, ABOVE_HTML_FILE)
                    with open(above_html_path, 'w', encoding='utf-8') as f:
                        f.write(form.headlines.data)
                    print(f"Saved headlines to {above_html_path}.")
                except Exception as e:
                    print(f"Error saving headlines file: {e}")

                # Clear the cache for the above HTML file (in-memory and diskcache)
                above_html_full_path = os.path.join(PATH, ABOVE_HTML_FILE)
                if above_html_full_path in _file_cache:
                    del _file_cache[above_html_full_path]
                # Clear all page caches since headlines have changed
                clear_page_caches()
                
            page_order = []

            # Only process URL customization if enabled
            if ENABLE_URL_CUSTOMIZATION:
                urls = list(form.urls)
                url_custom = list(form.url_custom)
                
                for site in url_custom:
                    if len(site.url.data) > 10 and len(site.url.data) < 120:
                        urls.append(site)

                urls.sort(key=lambda x: x.pri.data)

                for urlf in urls:
                    if isinstance(urlf.form, UrlForm):
                        page_order.append(urlf.url.data)
                    elif isinstance(urlf.form, CustomRSSForm):
                        page_order.append(urlf.url.data)
            else:
                # Use default site URLs if customization is disabled
                page_order = SITE_URLS

            template = render_template('configdone.html', message="Cookies saved for later.")
            resp = make_response(template)

            if page_order != SITE_URLS:
                cookie_str = json.dumps(page_order)
                resp.set_cookie('RssUrls', cookie_str, max_age=EXPIRE_YEARS)
                resp.set_cookie('UrlsVer', URLS_COOKIE_VERSION, max_age=EXPIRE_YEARS)
            else:
                resp.delete_cookie('RssUrls')
                resp.delete_cookie('UrlsVer')

            resp.set_cookie("NoUnderlines", "1" if form.no_underlines.data else "0", max_age=EXPIRE_YEARS)

            return resp

    @flask_app.route('/api/weather')
    def get_weather():
        ip = request.remote_addr
        units = request.args.get('units', 'imperial')
        
        # Check if request is from a web bot
        user_agent = request.headers.get('User-Agent', '')
        is_web_bot = any(bot in user_agent for bot in WEB_BOT_USER_AGENTS)
        
        # For web bots or requests from news.thedetroitilove.com, use default (Detroit) coordinates
        referrer = request.headers.get('Referer', '')
        if is_web_bot or 'news.thedetroitilove.com' in referrer:
            lat = DEFAULT_WEATHER_LAT
            lon = DEFAULT_WEATHER_LON
        else:
            lat = request.args.get('lat')
            lon = request.args.get('lon')
            # Convert lat/lon to float if provided
            if lat is not None and lon is not None:
                try:
                    lat = float(lat)
                    lon = float(lon)
                except ValueError:
                    # If conversion fails, fall back to IP-based location
                    lat = lon = None
        
        weather_data, status_code = get_weather_data(lat=lat, lon=lon, ip=ip, units=units)
        
        response = jsonify(weather_data)
        # Add cache control headers for 4 hours (14400 seconds)
        response.headers['Cache-Control'] = 'public, max-age=14400'
        response.headers['Expires'] = (datetime.datetime.utcnow() + datetime.timedelta(hours=4)).strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response, status_code

    @flask_app.route('/old_headlines')
    def old_headlines():
        mode_str = MODE_MAP.get(MODE)
        archive_file = os.path.join(PATH, f"{mode_str}report_archive.jsonl")
        headlines = []
        try:
            with open(archive_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        # Convert timestamp to datetime object for grouping
                        if 'timestamp' in entry:
                            entry['date'] = datetime.datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00')).date()
                        headlines.append(entry)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            pass
        except IOError as e:
            print(f"Error reading archive file {archive_file}: {e}")

        # Sort headlines by timestamp
        headlines.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # Skip the first 3 headlines (most recent)
        if len(headlines) > 3:
            headlines = headlines[3:]
        else:
            headlines = []

        # Group headlines by date
        grouped_headlines = {}
        for headline in headlines:
            date = headline.get('date')
            if date:
                date_str = date.strftime('%B %d, %Y')  # Format: January 1, 2024
                if date_str not in grouped_headlines:
                    grouped_headlines[date_str] = []
                grouped_headlines[date_str].append(headline)

        # Convert to list of tuples (date, headlines) and sort by date
        grouped_headlines_list = [(date, headlines) for date, headlines in grouped_headlines.items()]
        grouped_headlines_list.sort(key=lambda x: datetime.datetime.strptime(x[0], '%B %d, %Y'), reverse=True)

        # Use Flask-Login for admin authentication
        is_admin = current_user.is_authenticated
        return render_template(
            'old_headlines.html',
            grouped_headlines=grouped_headlines_list,
            mode=mode_str,
            title=f"Old Headlines - {mode_str.title()}Report",
            favicon=FAVICON,
            logo_url=LOGO_URL,
            description=WEB_DESCRIPTION,
            is_admin=is_admin
        )

    @flask_app.route('/api/delete_headline', methods=['POST'])
    @login_required
    def delete_headline():
        data = request.get_json()
        url = data.get('url')
        timestamp = data.get('timestamp')
        mode_str = MODE_MAP.get(MODE)
        archive_file = os.path.join(PATH, f"{mode_str}report_archive.jsonl")
        try:
            with open(archive_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            deleted = False
            for line in lines:
                try:
                    entry = json.loads(line)
                    if entry.get('url') == url and entry.get('timestamp') == timestamp:
                        deleted = True
                        continue
                except Exception:
                    pass
                new_lines.append(line)
            if deleted:
                with open(archive_file, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'Not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @flask_app.route('/api/comments', methods=['GET'])
    def get_comments():
        chat_cache = get_chat_cache()
        comments = chat_cache.get(COMMENTS_KEY) or []
        needs_update = False
        for c in comments:
            updated = False
            if 'id' not in c:
                c['id'] = str(uuid.uuid4())
                updated = True
            if 'ip_prefix' not in c and 'ip' in c:
                c['ip_prefix'] = get_ip_prefix(c['ip'])
                c.pop('ip', None)
                updated = True
            elif 'ip' in c:
                c.pop('ip', None)
                updated = True
            if updated:
                needs_update = True

        if needs_update:
            chat_cache.put(COMMENTS_KEY, comments)

        return jsonify(comments)

    @flask_app.route('/api/comments/stream')
    def stream_comments():
        def event_stream():
            last_data_sent = None
            chat_cache = get_chat_cache()
            while True:
                try:
                    current_comments = chat_cache.get(COMMENTS_KEY) or []
                    current_data = json.dumps(current_comments)
                    if current_data != last_data_sent:
                        yield f"event: new_comment\ndata: {current_data}\n\n"
                        last_data_sent = current_data
                    time.sleep(2)
                except GeneratorExit:
                    break
                except Exception as e:
                    print(f"SSE Error: {e}")
                    break
        return Response(event_stream(), mimetype='text/event-stream')

    @flask_app.route('/api/comments', methods=['POST'])
    def post_comment():
        ip = request.remote_addr
        chat_cache = get_chat_cache()
        banned_ips = chat_cache.get(BANNED_IPS_KEY) or set()

        if ip in banned_ips:
            return jsonify({"error": "Banned"}), 403

        data = request.get_json()
        text = data.get('text', '').strip()
        image_url = data.get('image_url', '').strip()

        if not text and not image_url:
            return jsonify({"error": "Comment cannot be empty"}), 400

        sanitized_text = html.escape(text).replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')

        valid_image_url = None
        if image_url:
            is_local_upload = image_url.startswith(WEB_UPLOAD_PATH + '/')
            is_external_url = image_url.startswith('http://') or image_url.startswith('https://')
            is_data_url = image_url.startswith('data:image/')

            if is_local_upload or is_external_url or is_data_url:
                if not is_data_url:
                    has_valid_extension = image_url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
                    if has_valid_extension:
                        valid_image_url = image_url
                else:
                    valid_image_url = image_url

        comment_id = str(uuid.uuid4())
        ip_prefix = get_ip_prefix(ip)

        comment = {
            "id": comment_id,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "ip_prefix": ip_prefix,
            "text": sanitized_text,
            "image_url": valid_image_url
        }

        comments = chat_cache.get(COMMENTS_KEY) or []
        comments.append(comment)
        comments = comments[-MAX_COMMENTS:]
        chat_cache.put(COMMENTS_KEY, comments)

        return jsonify({"success": True}), 201

    @flask_app.route('/api/comments/<comment_id>', methods=['DELETE'])
    @login_required
    def delete_comment(comment_id):
        chat_cache = get_chat_cache()
        comments = chat_cache.get(COMMENTS_KEY) or []
        initial_length = len(comments)

        comments_after_delete = [c for c in comments if c.get('id') != comment_id]
        final_length = len(comments_after_delete)

        if final_length < initial_length:
            try:
                chat_cache.put(COMMENTS_KEY, comments_after_delete)
                return jsonify({"success": True}), 200
            except Exception as e:
                return jsonify({"error": "Failed to update cache after deletion"}), 500
        else:
            return jsonify({"error": "Comment not found"}), 404

    @flask_app.route('/api/upload_image', methods=['POST'])
    def upload_image():
        ip = request.remote_addr
        chat_cache = get_chat_cache()
        banned_ips = chat_cache.get(BANNED_IPS_KEY) or set()

        if ip in banned_ips:
            return jsonify({"error": "Banned"}), 403

        if 'image' not in request.files:
            return jsonify({"error": "No image file part"}), 400

        file = request.files['image']

        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if file and allowed_file(file.filename):
            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            if file_length > MAX_IMAGE_SIZE:
                return jsonify({"error": "File size exceeds limit"}), 400
            file.seek(0)

            _, ext = os.path.splitext(file.filename)
            filename = secure_filename(f"{uuid.uuid4()}{ext}")
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            try:
                file.save(filepath)
                file_url = f"{WEB_UPLOAD_PATH}/{filename}"
                return jsonify({"success": True, "url": file_url}), 201
            except (IOError, OSError) as e:
                return jsonify({"error": "Failed to save image"}), 500
        else:
            return jsonify({"error": "Invalid file type"}), 400

    @flask_app.route('/sitemap.xml')
    def sitemap():
        # Try to get cached sitemap
        cache_key = 'sitemap.xml'
        cached_sitemap = g_cm.get(cache_key)
        if cached_sitemap:
            response = make_response(cached_sitemap)
            response.headers['Content-Type'] = 'application/xml'
            return response

        # Generate sitemap XML
        urls = []
        for domain in ALLOWED_REQUESTER_DOMAINS:
            # Add main page
            urls.append(f'<url><loc>{domain}/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>')
            # Add old_headlines page
            urls.append(f'<url><loc>{domain}/old_headlines</loc><changefreq>daily</changefreq><priority>0.8</priority></url>')

        sitemap_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>'''

        g_cm.set(cache_key, sitemap_xml, ttl=EXPIRE_YEARS)

        response = make_response(sitemap_xml)
        response.headers['Content-Type'] = 'application/xml'
        return response

    # If UPLOAD_FOLDER is 'static/uploads', Flask handles this automatically.
    # If it were outside 'static', you'd need something like this:
    # @flask_app.route('/uploads/<filename>')
    # def uploaded_file(filename):
    #     return send_from_directory(UPLOAD_FOLDER, filename)
