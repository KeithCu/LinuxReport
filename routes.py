"""
routes.py

This file contains all the Flask route handlers for the application, including the main index page, configuration page, and weather API.
"""

# Standard library imports
import os
import json
from timeit import default_timer as timer
import datetime
import time

# Third-party imports
from flask import g, jsonify, render_template, request, make_response, flash, redirect, url_for
from markupsafe import Markup
from flask_cors import CORS
from flask_login import login_user, logout_user, login_required, current_user
from flask_limiter.util import get_remote_address

from forms import LoginForm
from models import RssInfo, DEBUG, User
# Local imports
from shared import (limiter, dynamic_rate_limit, ABOVE_HTML_FILE, ALL_URLS, EXPIRE_MINUTES, EXPIRE_DAY, EXPIRE_HOUR, EXPIRE_YEARS,
                    FAVICON, LOGO_URL, STANDARD_ORDER_STR,
                    URL_IMAGES, URLS_COOKIE_VERSION, WEB_DESCRIPTION,
                    WEB_TITLE, WELCOME_HTML, g_c, g_cm, SITE_URLS, PATH, format_last_updated,
                    ALLOWED_DOMAINS, ENABLE_CORS, ALLOWED_REQUESTER_DOMAINS,
                    ENABLE_URL_IMAGE_CDN_DELIVERY, CDN_IMAGE_URL, WEB_BOT_USER_AGENTS,
                    INFINITE_SCROLL_MOBILE, INFINITE_SCROLL_DEBUG,
                    ENABLE_COMPRESSION_CACHING)
from weather import get_default_weather_html, init_weather_routes
from workers import fetch_urls_parallel, fetch_urls_thread
from caching import get_cached_file_content, get_cached_response_for_client
from admin_stats import update_performance_stats, get_admin_stats_html, track_rate_limit_event
from old_headlines import init_old_headlines_routes
from chat import init_chat_routes
from config import init_config_routes

# Global setting for background refreshes
ENABLE_BACKGROUND_REFRESH = True


def get_cached_above_html():
    """Return content of ABOVE_HTML_FILE using generic cache."""
    return get_cached_file_content(os.path.join(PATH, ABOVE_HTML_FILE))

# Function to initialize routes
def init_app(flask_app):
    """Initialize Flask routes."""
    # Initialize Flask-Limiter with your cache system - It's already initialized in app.py
    # limiter.init_app(flask_app)
    
    # Initialize routes from other modules
    init_weather_routes(flask_app)
    init_old_headlines_routes(flask_app)
    init_chat_routes(flask_app, limiter, dynamic_rate_limit)
    init_config_routes(flask_app)
    
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
                # For cache hits, use tiny fixed time since they're very fast
                render_time = 0.0001  # 100 microseconds
                update_performance_stats(render_time, start_time)
            
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

        # 1. See if we need to fetch any RSS feeds
        last_fetch_cache = g_c.get_all_last_fetches(page_order)
        for url in page_order:
            rss_info = ALL_URLS.get(url, None)

            if rss_info is None:
                rss_info = RssInfo("Custom.png", "Custom site", url + "HTML")
                ALL_URLS[url] = rss_info

            last_fetch = last_fetch_cache.get(url)
            
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
                g_cm.set(rss_info.site_url, template, ttl=EXPIRE_DAY)
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
            end_time = timer()
            render_time = end_time - start_time
            update_performance_stats(render_time, end_time)
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
        # Use the end_time we already calculated for performance stats to avoid another timer() call
        if not is_admin:
            # Convert timer() time to datetime for the Expires header
            response.headers['Cache-Control'] = 'public, max-age=1800'
            expires_time = datetime.datetime.fromtimestamp(end_time) + datetime.timedelta(hours=0.5)
            response.headers['Expires'] = expires_time.strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response




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
