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
import gzip
import hashlib

# Third-party imports
from flask import g, jsonify, render_template, request, make_response, Response, flash, redirect, url_for
from markupsafe import Markup
from werkzeug.utils import secure_filename
from flask_cors import CORS
from flask_login import login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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
                    INFINITE_SCROLL_MOBILE, INFINITE_SCROLL_DEBUG, FLASK_DASHBOARD,
                    ENABLE_COMPRESSION_CACHING, get_ip_prefix)
from weather import get_default_weather_html, get_weather_data, DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON, init_weather_routes
from workers import fetch_urls_parallel, fetch_urls_thread
from caching import get_cached_file_content, _file_cache
from admin_stats import update_performance_stats, get_admin_stats_html
from old_headlines import init_old_headlines_routes
from chat import init_chat_routes

# Global setting for background refreshes
ENABLE_BACKGROUND_REFRESH = True

# Compression caching constants
COMPRESSION_CACHE_TTL = EXPIRE_HOUR  # Cache compressed responses for 1 hour
COMPRESSION_LEVEL = 6  # Balance between speed and compression ratio

def get_compression_cache_key(content, encoding_type='gzip'):
    """Generate a cache key for compressed content."""
    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    return f"compressed_{encoding_type}_{content_hash}"

def get_cached_compressed_response(content, encoding_type='gzip'):
    """Get cached compressed response if available."""
    cache_key = get_compression_cache_key(content, encoding_type)
    return g_cm.get(cache_key)

def cache_compressed_response(content, compressed_data, encoding_type='gzip'):
    """Cache compressed response data."""
    cache_key = get_compression_cache_key(content, encoding_type)
    g_cm.set(cache_key, compressed_data, ttl=COMPRESSION_CACHE_TTL)

def create_compressed_response(content, encoding_type='gzip'):
    """Create compressed response with caching."""
    # Check cache first
    cached_response = get_cached_compressed_response(content, encoding_type)
    if cached_response is not None:
        return cached_response
    
    # Compress content
    if encoding_type == 'gzip':
        compressed_data = gzip.compress(content.encode('utf-8'), compresslevel=COMPRESSION_LEVEL)
    else:
        # Fallback to uncompressed
        compressed_data = content.encode('utf-8')
    
    # Cache the compressed data
    cache_compressed_response(content, compressed_data, encoding_type)
    
    return compressed_data

def get_cached_response_for_client(content, supports_gzip):
    """Get cached response (compressed or uncompressed) based on client capabilities."""
    if supports_gzip:
        # Try to get cached compressed response
        cached_compressed = get_cached_compressed_response(content, 'gzip')
        if cached_compressed is not None:
            if DEBUG:
                print(f"Compression cache HIT - returning cached gzip data ({len(cached_compressed)} bytes)")
            return cached_compressed, True  # Return compressed data and flag as compressed
        
        # Create and cache compressed response
        if DEBUG:
            print(f"Compression cache MISS - creating new gzip data")
        compressed_data = create_compressed_response(content, 'gzip')
        return compressed_data, True
    else:
        # For clients that don't support gzip, return uncompressed
        # We don't cache uncompressed responses since they're just the original content
        if DEBUG:
            print(f"Client doesn't support gzip - returning uncompressed data ({len(content)} bytes)")
        # Return the content directly as bytes to avoid unnecessary encoding
        return content.encode('utf-8'), False

def clear_compression_cache():
    """Clear all compression cache entries."""
    # This is a simple approach - in a more sophisticated system, you might want to
    # track compression cache keys and clear them individually
    # For now, we'll rely on TTL expiration
    pass

def clear_page_caches_with_compression():
    """Clear page caches and compression cache."""
    clear_page_caches()
    if ENABLE_COMPRESSION_CACHING:
        clear_compression_cache()

def get_rate_limit_key():
    """Get rate limit key based on user type and IP."""
    ip = get_remote_address()
    
    # Check if user is authenticated (admin)
    if current_user.is_authenticated:
        return f"admin:{ip}"
    
    # Check if request is from a web bot
    user_agent = request.headers.get('User-Agent', '')
    is_web_bot = any(bot in user_agent for bot in WEB_BOT_USER_AGENTS)
    
    if is_web_bot:
        return f"bot:{ip}"
    
    return f"user:{ip}"

def dynamic_rate_limit():
    """Return rate limit based on user type."""
    key = get_rate_limit_key()
    
    if key.startswith("admin:"):
        return "500 per minute"  # Higher limits for admins
    elif key.startswith("bot:"):
        return "20 per minute"    # Lower limits for bots
    else:
        return "100 per minute"  # Standard limits for users

def get_cached_above_html():
    """Return content of ABOVE_HTML_FILE using generic cache."""
    return get_cached_file_content(os.path.join(PATH, ABOVE_HTML_FILE))


def track_rate_limit_event(ip, endpoint, limit_type="exceeded"):
    """
    Track rate limit events for long-term monitoring and security analysis.
    
    This function is called ONLY when rate limits are exceeded (rare events),
    so it can be slower and use disk cache for persistence across restarts.
    
    Args:
        ip: IP address that hit the rate limit
        endpoint: Flask endpoint that was rate limited
        limit_type: Type of rate limit violation (default: "exceeded")
    """
    # Store events in disk cache for persistence across restarts
    rate_limit_events_key = "rate_limit_events"
    events = g_c.get(rate_limit_events_key) or []
    
    current_time = time.time()
    # Keep event data minimal - details can be found in Apache logs
    event = {
        "timestamp": current_time,
        "ip": ip,
        "endpoint": endpoint
    }
    
    # Add to events list (keep last 1000 events)
    events.append(event)
    if len(events) > 1000:
        events = events[-1000:]
    
    # Clean up old events (older than 30 days)
    cutoff_time = current_time - (30 * 24 * 3600)  # 30 days
    events = [e for e in events if e["timestamp"] > cutoff_time]
    
    # Store events in disk cache for persistence
    g_c.put(rate_limit_events_key, events, timeout=EXPIRE_YEARS)
    
    # Keep minimal stats in disk cache for long-term tracking
    rate_limit_stats_key = "rate_limit_stats"
    stats = g_c.get(rate_limit_stats_key) or {
        "by_ip": {},
        "by_endpoint": {}
    }
    
    # Track by IP and endpoint
    for key, data_dict in [("by_ip", ip), ("by_endpoint", endpoint)]:
        if data_dict not in stats[key]:
            stats[key][data_dict] = {"count": 0, "last_seen": current_time}
        stats[key][data_dict]["count"] += 1
        stats[key][data_dict]["last_seen"] = current_time
    
    g_c.put(rate_limit_stats_key, stats, timeout=EXPIRE_YEARS)  # Store in disk cache for persistence


# Initialize Flask-Limiter with your cache
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=["50 per minute"],
    strategy="fixed-window"
)

# Function to initialize routes
def init_app(flask_app):
    """Initialize Flask routes."""
    # Initialize Flask-Limiter with your cache system
    limiter.init_app(flask_app)
    
    # Initialize routes from other modules
    init_weather_routes(flask_app)
    init_old_headlines_routes(flask_app)
    init_chat_routes(flask_app, limiter, dynamic_rate_limit)
    
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
            default_src = "'self'"
            if ENABLE_URL_IMAGE_CDN_DELIVERY:
                img_src += f" {CDN_IMAGE_URL}"
                default_src += f" {CDN_IMAGE_URL}"
            
            csp_domains = " ".join(ALLOWED_DOMAINS)
            response.headers['Content-Security-Policy'] = (
                f"default-src {default_src}; "
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
    @limiter.limit(dynamic_rate_limit)
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
            # Track performance stats for cache hit
            if not is_admin:
                render_time = timer() - start_time
                update_performance_stats(render_time)
            
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
        
        # Check if client accepts gzip compression
        accept_encoding = request.headers.get('Accept-Encoding', '')
        supports_gzip = 'gzip' in accept_encoding.lower()
        
        # Create response with compression caching (only if enabled)
        if ENABLE_COMPRESSION_CACHING and supports_gzip and not is_admin:  # Don't compress admin responses for debugging
            # Get or create compressed response
            response_data, is_compressed = get_cached_response_for_client(page, supports_gzip)
            response = make_response(response_data)
            if is_compressed:
                response.headers['Content-Encoding'] = 'gzip'
            response.headers['Content-Length'] = str(len(response_data))
        else:
            # Return uncompressed response (original behavior)
            response = make_response(page)
            response.headers['Content-Length'] = str(len(page.encode('utf-8')))
        
        # Add cache control headers for 30 minutes (1800 seconds)
        response.headers['Cache-Control'] = 'public, max-age=1800'
        response.headers['Expires'] = (datetime.datetime.utcnow() + datetime.timedelta(hours=0.5)).strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response

    @flask_app.route('/config', methods=['GET', 'POST'], strict_slashes=False)
    @limiter.limit(dynamic_rate_limit)
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
                clear_page_caches_with_compression()
                
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



    @flask_app.route('/api/rate_limit_stats')
    @login_required
    def get_rate_limit_stats():
        """Get rate limit statistics for admin monitoring."""
        # Get events from disk cache (persistent)
        rate_limit_events_key = "rate_limit_events"
        events = g_c.get(rate_limit_events_key) or []
        
        # Get stats from disk cache (persistent)
        rate_limit_stats_key = "rate_limit_stats"
        stats = g_c.get(rate_limit_stats_key) or {
            "by_ip": {},
            "by_endpoint": {}
        }
        
        # Combine data
        result = {
            "events": events,
            "by_ip": stats.get("by_ip", {}),
            "by_endpoint": stats.get("by_endpoint", {}),
            "current_time": time.time(),
            "total_events": len(events),
            "unique_ips": len(stats.get("by_ip", {})),
            "unique_endpoints": len(stats.get("by_endpoint", {}))
        }
        
        return jsonify(result)


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

    # Rate limit error handler
    @flask_app.errorhandler(429)
    def ratelimit_handler(e):
        """Handle rate limit exceeded errors."""
        # Track the rate limit event
        ip = get_remote_address()
        endpoint = request.endpoint or request.path
        track_rate_limit_event(ip, endpoint, "exceeded")
        
        return jsonify({
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": getattr(e, 'retry_after', 60)
        }), 429
