"""
routes.py

This file contains all the Flask route handlers for the application, including the main index page, 
configuration page, weather API, authentication, and various utility endpoints.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
import json
import sqlite3
import datetime
import time

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
from flask import g, jsonify, render_template, request, make_response, flash, redirect, url_for
from markupsafe import Markup
from flask_cors import CORS
from flask_login import login_user, logout_user, login_required, current_user
from flask_limiter.util import get_remote_address
from flask_restful import Resource

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from forms import LoginForm
from models import RssInfo, User
from app_config import DEBUG
from shared import (
    limiter, dynamic_rate_limit, ABOVE_HTML_FILE, ALL_URLS, EXPIRE_MINUTES, 
    EXPIRE_DAY, EXPIRE_YEARS, FAVICON, LOGO_URL, STANDARD_ORDER_STR,
    URL_IMAGES, URLS_COOKIE_VERSION, WEB_DESCRIPTION, WEB_TITLE, WELCOME_HTML, 
    g_c, g_cm, SITE_URLS, PATH, format_last_updated, ALLOWED_DOMAINS, ENABLE_CORS, 
    ALLOWED_REQUESTER_DOMAINS, ENABLE_URL_IMAGE_CDN_DELIVERY, CDN_IMAGE_URL, 
    INFINITE_SCROLL_MOBILE, INFINITE_SCROLL_DEBUG, API, MODE, DISABLE_CLIENT_GEOLOCATION
)
from request_utils import is_web_bot
from weather import get_default_weather_html, init_weather_routes, get_cached_geolocation
from workers import fetch_urls_parallel, fetch_urls_thread
from caching import get_cached_file_content
from admin_stats import update_performance_stats, get_admin_stats_html, track_rate_limit_event
from old_headlines import init_old_headlines_routes
from chat import init_chat_routes
from config import init_config_routes
from feedback import init_feedback_routes
from shared import g_logger

# =============================================================================
# GLOBAL CONFIGURATION
# =============================================================================

# Global setting for background refreshes
ENABLE_BACKGROUND_REFRESH = True

# Pre-computed security headers for performance
def _build_security_headers():
    """Pre-compute security headers at app startup to avoid string operations per request."""
    # Build CSP domains string once
    csp_domains = " ".join(ALLOWED_DOMAINS)
    
    # Build CSP header with conditional CDN
    img_src = "'self' data:"
    default_src = "'self'"
    if ENABLE_URL_IMAGE_CDN_DELIVERY:
        img_src += f" {CDN_IMAGE_URL}"
        default_src += f" {CDN_IMAGE_URL}"
    
    csp_policy = (
        f"default-src {default_src}; "
        f"connect-src 'self' {csp_domains}; "
        f"img-src {img_src} *; "
        f"script-src 'self' 'unsafe-inline'; "
        f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        f"font-src 'self' https://fonts.gstatic.com; "
        f"frame-ancestors 'none';"
    )
    
    return {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Content-Security-Policy': csp_policy,
        'Access-Control-Expose-Headers': 'X-Client-IP'
    }

# Pre-compute headers at module load
SECURITY_HEADERS = _build_security_headers()

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_cached_above_html():
    """
    Return content of ABOVE_HTML_FILE using generic cache.
    
    Returns:
        str: Cached HTML content from the above HTML file
    """
    return get_cached_file_content(os.path.join(PATH, ABOVE_HTML_FILE))

class RateLimitStatsResource(Resource):
    """
    Resource for handling GET requests to /api/rate_limit_stats.
    Provides rate limit statistics for admin monitoring.
    """
    
    @login_required
    def get(self):
        """
        Get rate limit statistics for admin monitoring.
        """
        # Get events from disk cache (persistent)
        rate_limit_events_key = "rate_limit_events"
        events = g_c.get(rate_limit_events_key) or []
        
        # Get stats from disk cache (persistent)
        rate_limit_stats_key = "rate_limit_stats"
        stats = g_c.get(rate_limit_stats_key) or {
            "by_ip": {},
            "by_endpoint": {}
        }
        
        # Combine data - use single time call for current_time
        current_time = time.time()
        result = {
            "events": events,
            "by_ip": stats.get("by_ip", {}),
            "by_endpoint": stats.get("by_endpoint", {}),
            "current_time": current_time,
            "total_events": len(events),
            "unique_ips": len(stats.get("by_ip", {})),
            "unique_endpoints": len(stats.get("by_endpoint", {}))
        }
        
        return result, 200

# =============================================================================
# ROUTE INITIALIZATION
# =============================================================================

def init_app(flask_app):
    """
    Initialize Flask routes and configure the application.
    
    This function sets up all route handlers, security headers, CORS configuration,
    and initializes routes from other modules.
    
    Args:
        flask_app (Flask): The Flask application instance to configure
    """
    # Initialize routes from other modules
    _register_main_routes(flask_app)
    _register_authentication_routes(flask_app)
    init_weather_routes(flask_app)
    init_old_headlines_routes(flask_app)
    init_chat_routes(flask_app, limiter, dynamic_rate_limit)
    init_config_routes(flask_app)
    init_feedback_routes(flask_app, limiter, dynamic_rate_limit)
    
    # Configure CORS and security headers only if enabled
    if ENABLE_CORS:
        # Configure CORS to allow requests from any domain for weather API
        # Note: CORS cannot be completely disabled as it's needed for multiple servers 
        # to communicate with linuxreport.net for weather data
        CORS(flask_app, resources={
            r"/api/weather": {  # Allow CORS for weather API from any domain
                "origins": "*",  # Allow all origins
                "methods": ["GET", "OPTIONS"],
                "allow_headers": ["Content-Type"],
                "expose_headers": ["Content-Type"],
                "supports_credentials": False,  # Must be False when origins is "*"
                "max_age": 3600  # Cache preflight requests for 1 hour
            }
        })
        
        # Add security headers to HTML responses only
        @flask_app.after_request
        def add_security_headers(response):
            # Only add security headers to HTML responses
            if response.content_type and 'text/html' in response.content_type:
                # Apply pre-computed security headers
                for header, value in SECURITY_HEADERS.items():
                    response.headers[header] = value
            
            return response

    # Register Flask-RESTful resources
    API.add_resource(RateLimitStatsResource, '/api/rate_limit_stats')

# =============================================================================
# AUTHENTICATION ROUTES
# =============================================================================

def _register_authentication_routes(flask_app):
    """
    Register authentication-related routes.
    
    Args:
        flask_app (Flask): The Flask application instance
    """
    
    @flask_app.route('/login', methods=['GET', 'POST'])
    def login():
        """Handle user login."""
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            form = LoginForm()
            if form.validate():
                user = User.authenticate(form.username.data, form.password.data)
                if user:
                    login_user(user, remember=form.remember_me.data)
                    next_page = request.args.get('next')
                    if not next_page or not next_page.startswith('/'):
                        next_page = url_for('index')
                    return redirect(next_page)
                else:
                    flash('Invalid username or password', 'error')
            else:
                # Form validation failed
                flash('Please correct the errors below.', 'error')
        else:
            form = LoginForm()
        
        return render_template('login.html', form=form)

    @flask_app.route('/logout')
    @login_required
    def logout():
        """Handle user logout."""
        logout_user()
        return redirect(url_for('index'))

# =============================================================================
# MAIN APPLICATION ROUTES
# =============================================================================

def _register_main_routes(flask_app):
    """
    Register main application routes including the index page.
    
    Args:
        flask_app (Flask): The Flask application instance
    """
    
    @flask_app.route('/')
    @limiter.limit(dynamic_rate_limit)
    def index():
        """
        Main page of LinuxReport.
        
        This is the primary route that handles the main page display. It includes
        sophisticated caching, performance tracking, RSS feed management, and
        background refresh capabilities.
        """
        # Check if admin mode is enabled for performance tracking using Flask-Login
        is_admin = current_user.is_authenticated

        # Single kernel time call at start - use time.time() as unified time format
        start_time = time.time()

        # Get user agent and check if it's a bot (including our custom deploy bot)
        user_agent = request.headers.get('User-Agent', '')
        is_deploy_bot = 'DeployBot' in user_agent
        is_bot = is_web_bot(user_agent)

        # Determine the order of RSS feeds to display.
        page_order = None
        if request.cookies.get('UrlsVer') == URLS_COOKIE_VERSION:
            page_order = request.cookies.get('RssUrls')
            if page_order is not None:
                page_order = json.loads(page_order)

        if page_order is None:
            page_order = SITE_URLS

        page_order_s = str(page_order)

        # Determine display settings based on user preferences and device type
        suffix = ""
        single_column = False

        if g.is_mobile:
            suffix = ":MOBILE"
            single_column = True

        # Try full response cache using only page order and mobile flag (but not for admin mode)
        cache_key = f"response-cache:{page_order_s}{suffix}"
        cached_response = g_cm.get(cache_key) if not is_admin else None
        if not DEBUG and not is_admin and cached_response is not None:
            # Track performance stats for cache hit - NO additional kernel calls
            if not is_admin:
                # For cache hits, use tiny fixed time since they're very fast
                render_time = 0.001  # 1 millisecond fixed time for cache hits
                update_performance_stats(render_time, start_time)
            
            # For cached responses, make a copy and add user-specific location headers
            from copy import deepcopy
            response = deepcopy(cached_response)
            
            # Get cached location for this IP to pass to client (only if client geolocation is enabled)
            client_ip = request.remote_addr
            if not DISABLE_CLIENT_GEOLOCATION:
                cached_lat, cached_lon = get_cached_geolocation(client_ip)
                
                # Add location headers if we have cached coordinates
                if cached_lat is not None and cached_lon is not None:
                    response.headers['X-Weather-Lat'] = str(cached_lat)
                    response.headers['X-Weather-Lon'] = str(cached_lon)
            
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
            # Use current start_time to avoid additional kernel calls for fetch timing
            fetch_urls_parallel(needed_urls)
            # We could calculate fetch time using end_time later, but for now just log the count
            g_logger.info(f"Fetched {len(needed_urls)} feeds.")

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

        # Get cached location for this IP for template rendering (only if client geolocation is enabled)
        client_ip = request.remote_addr
        if DISABLE_CLIENT_GEOLOCATION:
            template_lat, template_lon = None, None
        else:
            template_lat, template_lon = get_cached_geolocation(client_ip)
        
        # Render the final page.
        page = render_template('page.html', columns=result,
                               logo_url=LOGO_URL, title=WEB_TITLE,
                               description=WEB_DESCRIPTION, favicon=FAVICON,
                               welcome_html=Markup(WELCOME_HTML),
                               above_html=Markup(above_html),
                               weather_html=Markup(weather_html),
                               INFINITE_SCROLL_MOBILE=INFINITE_SCROLL_MOBILE,
                               INFINITE_SCROLL_DEBUG=INFINITE_SCROLL_DEBUG,
                               weather_lat=template_lat, weather_lon=template_lon)

        # Trigger background fetching if needed
        if need_fetch and ENABLE_BACKGROUND_REFRESH and not is_bot:
            fetch_urls_thread()

        # Single kernel time call at end and track performance stats
        end_time = time.time()
        # Don't track stats only for deploy bot (other bots should count as users)
        if not is_admin and not is_deploy_bot:
            render_time = end_time - start_time
            update_performance_stats(render_time, end_time)
        
        # Still show stats for admin users
        if is_admin:
            stats_html = get_admin_stats_html()
            if stats_html:
                page = page.replace('</body>', f'{stats_html}</body>')
        
        # Create response
        response = make_response(page)
        response.headers['Content-Length'] = str(len(page.encode('utf-8')))
        
        # Add user-specific location headers for uncached responses (only if client geolocation is enabled)
        client_ip = request.remote_addr
        if not DISABLE_CLIENT_GEOLOCATION:
            cached_lat, cached_lon = get_cached_geolocation(client_ip)
            
            # Add location headers if we have cached coordinates
            if cached_lat is not None and cached_lon is not None:
                response.headers['X-Weather-Lat'] = str(cached_lat)
                response.headers['X-Weather-Lon'] = str(cached_lon)
        
        # Add cache control headers for 15 minutes (900 seconds)
        # Use the end_time we already calculated to avoid additional time calls
        if not is_admin:
            # Use max-age for relative caching (more reliable than Expires)
            response.headers['Cache-Control'] = 'public, max-age=900'
        
        # Store full response cache (but not for admin mode) - cache the response with standard headers
        if not is_admin and page_order_s == STANDARD_ORDER_STR:
            expire = EXPIRE_MINUTES
            if need_fetch:
                expire = 30
            
            # Cache the response with standard headers (no user-specific headers)
            g_cm.set(cache_key, response, ttl=expire)
        
        return response

    @flask_app.route('/robots.txt')
    def robots():
        """Serve robots.txt file for search engine crawlers."""
        robots_content = f"""User-agent: *
Allow: /
Disallow: /admin/
Disallow: /login
Disallow: /logout
Disallow: /config/

Sitemap: {request.host_url.rstrip('/')}/sitemap.xml
"""
        response = make_response(robots_content)
        response.headers['Content-Type'] = 'text/plain'
        return response

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
            # Add RSS feed
            urls.append(f'<url><loc>{domain}/rss</loc><changefreq>hourly</changefreq><priority>0.9</priority></url>')
            # Add JSON API
            urls.append(f'<url><loc>{domain}/api/headlines</loc><changefreq>hourly</changefreq><priority>0.8</priority></url>')

        sitemap_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>'''

        g_cm.set(cache_key, sitemap_xml, ttl=EXPIRE_YEARS)

        response = make_response(sitemap_xml)
        response.headers['Content-Type'] = 'application/xml'
        return response

    def _get_headlines_data():
        """
        Shared function to get current headlines data from cache.
        
        Returns:
            list: List of headline dictionaries with title, link, description, 
                  published, source, and source_url keys.
        """
        # Check cache first for headlines data
        cache_key = f'headlines-data:{MODE.value}'
        cached_headlines = g_cm.get(cache_key)
        if cached_headlines:
            return cached_headlines
        
        headlines = []
        for url in SITE_URLS:
            rss_info = ALL_URLS.get(url)
            if not rss_info:
                continue
                
            # Get cached feed data
            feed_data = g_c.get(url)
            if not feed_data or not feed_data.entries:
                continue
                
            # Add entries from this feed
            for entry in feed_data.entries[:10]:  # Limit to 10 per feed
                if entry.get('title') and entry.get('link'):
                    headlines.append({
                        'title': entry['title'],
                        'link': entry['link'],
                        'description': entry.get('summary', ''),
                        'published': entry.get('published_parsed'),
                        'source': rss_info.logo_alt,
                        'source_url': rss_info.site_url
                    })

        # Sort by publication date (newest first)
        headlines.sort(key=lambda x: x['published'] or (0, 0, 0, 0, 0, 0, 0, 0, 0), reverse=True)
        
        # Limit to 50 total headlines
        headlines = headlines[:50]
        
        # Cache the headlines data for 10 minutes
        g_cm.set(cache_key, headlines, ttl=EXPIRE_MINUTES * 2)
        
        return headlines

    @flask_app.route('/rss')
    @flask_app.route('/rss/')
    @limiter.limit(dynamic_rate_limit)
    def rss_feed():
        """
        Generate RSS feed for the current report type.
        
        Returns an RSS 2.0 feed containing the latest headlines from all sources.
        The feed is cached for performance and includes proper headers for feed readers.
        """
        # Check cache first
        cache_key = f'rss-feed:{MODE.value}'
        cached_feed = g_cm.get(cache_key)
        if cached_feed:
            response = make_response(cached_feed)
            response.headers['Content-Type'] = 'application/rss+xml; charset=utf-8'
            response.headers['Cache-Control'] = 'public, max-age=900'  # 15 minutes
            return response

        # Get headlines using shared function
        headlines = _get_headlines_data()

        # Generate RSS XML
        rss_items = []
        for headline in headlines:
            # Format date for RSS
            if headline['published']:
                pub_date = datetime.datetime(*headline['published'][:6]).strftime('%a, %d %b %Y %H:%M:%S %z')
            else:
                pub_date = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
            
            # Clean description
            description = headline['description']
            if description:
                # Remove HTML tags and limit length
                import re
                description = re.sub(r'<[^>]+>', '', description)
                description = description[:300] + '...' if len(description) > 300 else description
            else:
                description = f"Read more at {headline['source']}"
            
            rss_items.append(f'''  <item>
    <title>{headline['title']}</title>
    <link>{headline['link']}</link>
    <description>{description}</description>
    <pubDate>{pub_date}</pubDate>
    <source url="{headline['source_url']}">{headline['source']}</source>
  </item>''')

        # Build RSS feed
        current_time = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
        rss_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{WEB_TITLE}</title>
    <link>{request.host_url.rstrip('/')}</link>
    <description>{WEB_DESCRIPTION}</description>
    <language>en-us</language>
    <lastBuildDate>{current_time}</lastBuildDate>
    <atom:link href="{request.url}" rel="self" type="application/rss+xml" />
{chr(10).join(rss_items)}
  </channel>
</rss>'''

        # Cache the feed
        g_cm.set(cache_key, rss_xml, ttl=900)  # 15 minutes

        response = make_response(rss_xml)
        response.headers['Content-Type'] = 'application/rss+xml; charset=utf-8'
        response.headers['Cache-Control'] = 'public, max-age=900'
        return response

    @flask_app.route('/api/headlines')
    @flask_app.route('/api/headlines/')
    @limiter.limit(dynamic_rate_limit)
    def api_headlines():
        """
        Generate JSON API endpoint for current headlines.
        
        Returns a JSON response containing the latest headlines from all sources.
        The response is cached for performance and includes proper headers for API consumers.
        """
        # Check cache first
        cache_key = f'json-headlines:{MODE.value}'
        cached_response = g_cm.get(cache_key)
        if cached_response:
            response = make_response(cached_response)
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            response.headers['Cache-Control'] = 'public, max-age=900'  # 15 minutes
            return response

        # Get headlines using shared function
        headlines = _get_headlines_data()

        # Convert to JSON-friendly format
        json_headlines = []
        for headline in headlines:
            # Format date for JSON (ISO 8601)
            if headline['published']:
                pub_date = datetime.datetime(*headline['published'][:6]).isoformat() + 'Z'
            else:
                pub_date = datetime.datetime.now().isoformat() + 'Z'
            
            # Clean description
            description = headline['description']
            if description:
                # Remove HTML tags and limit length
                import re
                description = re.sub(r'<[^>]+>', '', description)
                description = description[:300] + '...' if len(description) > 300 else description
            else:
                description = f"Read more at {headline['source']}"
            
            json_headlines.append({
                'title': headline['title'],
                'link': headline['link'],
                'description': description,
                'published': pub_date,
                'source': headline['source'],
                'source_url': headline['source_url']
            })

        # Build JSON response
        json_response = {
            'title': WEB_TITLE,
            'description': WEB_DESCRIPTION,
            'url': request.host_url.rstrip('/'),
            'last_updated': datetime.datetime.now().isoformat() + 'Z',
            'headlines': json_headlines
        }

        # Cache the response
        json_string = json.dumps(json_response, indent=2)
        g_cm.set(cache_key, json_string, ttl=900)  # 15 minutes

        response = make_response(json_string)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        response.headers['Cache-Control'] = 'public, max-age=900'
        return response

    @flask_app.route('/search')
    @limiter.limit(dynamic_rate_limit)
    def search():
        """
        Search headlines by keyword.
        
        Searches through cached headlines using case-insensitive text matching.
        Supports searching in title, description, and source fields.
        Results are cached for performance.
        """
        query = request.args.get('q', '').strip()
        
        if not query:
            # Return empty results if no query
            return render_template('search.html', 
                                 query='',
                                 results=[],
                                 result_count=0,
                                 title=WEB_TITLE,
                                 favicon=FAVICON)
        
        # Check cache first (use query as-is for cache key, hash might vary across Python runs)
        cache_key = f'search-results:{MODE.value}:{query.lower()}'
        cached_results = g_cm.get(cache_key)
        if cached_results:
            return render_template('search.html',
                                 query=query,
                                 results=cached_results['results'],
                                 result_count=cached_results['count'],
                                 title=WEB_TITLE,
                                 favicon=FAVICON)
        
        # Get headlines using shared function
        headlines = _get_headlines_data()
        
        # Filter headlines by search query (case-insensitive)
        query_lower = query.lower()
        results = []
        for headline in headlines:
            # Search in title, description, and source
            title_match = query_lower in headline.get('title', '').lower()
            desc_match = query_lower in headline.get('description', '').lower()
            source_match = query_lower in headline.get('source', '').lower()
            
            if title_match or desc_match or source_match:
                results.append(headline)
        
        # Cache the results for 5 minutes
        cached_data = {
            'results': results,
            'count': len(results)
        }
        g_cm.set(cache_key, cached_data, ttl=300)  # 5 minutes
        
        return render_template('search.html',
                             query=query,
                             results=results,
                             result_count=len(results),
                             title=WEB_TITLE,
                             favicon=FAVICON)

    @flask_app.route('/api/force_refresh_feed', methods=['POST'])
    @login_required
    def force_refresh_feed():
        """Force refresh a specific RSS feed by marking it as expired."""
        try:
            feed_url = request.json.get('feed_url')
            if not feed_url:
                return jsonify({'error': 'feed_url parameter is required'}), 400

            # Find the corresponding ALL_URLS key for this site_url
            all_urls_key = None
            for url_key, rss_info in ALL_URLS.items():
                if rss_info.site_url == feed_url:
                    all_urls_key = url_key  # This is the ALL_URLS key
                    cache_key = rss_info.site_url  # This is what we use for cache
                    break

            if not cache_key or not all_urls_key:
                return jsonify({'error': 'Invalid feed URL'}), 400

            from datetime import datetime, timedelta

            # Clear the cached template from memory cache so it will be re-rendered
            g_cm.delete(cache_key)
            # Clear the render time cache
            g_cm.delete(f"{cache_key}_render_time")

            # Set the last fetch time to be a week old - definitely enough to trigger a refresh
            week_ago = datetime.now() - timedelta(days=7)
            g_c.set_last_fetch(all_urls_key, week_ago)

            # Fetch the feed directly using the worker function (no threading needed for single feed)
            try:
                from workers import load_url_worker
                load_url_worker(all_urls_key)
            except ImportError as e:
                g_logger.error(f"Error refreshing feed {all_urls_key}: {e}")

            return jsonify({'success': True, 'message': f'Force refresh initiated for {feed_url}'})

        except (TypeError, ValueError, sqlite3.Error, IOError) as e:
            g_logger.error(f"Error in force refresh for {feed_url}: {e}")
            return jsonify({'error': 'Internal server error'}), 500

    # Rate limit error handler
    @flask_app.errorhandler(429)
    def ratelimit_handler(e):
        """Handle rate limit exceeded errors."""
        # Track the rate limit event
        ip = get_remote_address()
        endpoint = request.endpoint or request.path
        track_rate_limit_event(ip, endpoint)
        
        return jsonify({
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": getattr(e, 'retry_after', 60)
        }), 429
