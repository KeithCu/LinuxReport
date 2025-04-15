"""
routes.py

This file contains all the Flask route handlers for the application, including the main index page, configuration page, and weather API.
"""

# Third-party imports
from flask import render_template, request, g, jsonify
from markupsafe import Markup

# Standard library imports
import json
from timeit import default_timer as timer

# Local imports
from shared import ALL_URLS, URLS_COOKIE_VERSION, site_urls, DEBUG, g_c, STANDARD_ORDER_STR, EXPIRE_MINUTES, EXPIRE_WEEK, URL_IMAGES, LOGO_URL, WEB_TITLE, WEB_DESCRIPTION, FAVICON, WELCOME_HTML, ABOVE_HTML_FILE
from models import RssInfo
from forms import ConfigForm, UrlForm, CustomRSSForm
from weather import get_weather_data, get_default_weather_html
import shared
from workers import fetch_urls_parallel, fetch_urls_thread


# Function to initialize routes
app = None
def init_app(flask_app):
    global app
    app = flask_app

    @app.route('/')
    def index():
        # Retrieve user preferences from cookies.
        dark_mode = request.cookies.get('DarkMode')
        no_underlines = request.cookies.get("NoUnderlines", "1") == "1"
        sans_serif = request.cookies.get("SansSerif", "1") == "1"

        # Determine the order of RSS feeds to display.
        page_order = None
        if request.cookies.get('UrlsVer') == URLS_COOKIE_VERSION:
            page_order = request.cookies.get('RssUrls')
            if page_order is not None:
                page_order = json.loads(page_order)

        if page_order is None:
            page_order = site_urls

        page_order_s = str(page_order)

        # Determine display settings based on user preferences and device type.
        suffix = ""
        single_column = False

        if g.is_mobile:
            suffix = ":MOBILE"
            single_column = True

        if dark_mode:
            suffix = suffix + ":DARK"
        if no_underlines:
            suffix = suffix + ":NOUND"
        if sans_serif:
            suffix = suffix + ":SANS"

        # Check if a cached version of the page exists.
        full_page = g_c.get(page_order_s + suffix)
        if not DEBUG and full_page is not None:
            return full_page

        # Prepare the page layout.
        if single_column:
            result = [[]]
        else:
            result = [[], [], []]

        cur_col = 0

        needed_urls = []
        need_fetch = False

        # 1. See if we need to fetch any RSS feeds
        for url in page_order:
            rss_info = ALL_URLS.get(url, None)

            if rss_info is None:
                rss_info = RssInfo("Custom.png", "Custom site", url + "HTML")
                ALL_URLS[url] = rss_info

            expired_rss = g_c.has_feed_expired(url)

            if not g_c.has(rss_info.site_url) and expired_rss:
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

            template = g_c.get(rss_info.site_url)
            if DEBUG or template is None:
                feed = g_c.get(url)
                last_fetch = g_c.get(url + ":last_fetch")
                last_fetch_str = shared.format_last_updated(last_fetch)
                if feed is not None:
                    entries = feed.entries
                    top_images = {article['url']: article['image_url'] for article in feed.top_articles if article['image_url']}
                else:
                    entries = []
                    top_images = {}
                template = render_template('sitebox.html', top_images=top_images, entries=entries, logo=URL_IMAGES + rss_info.logo_url,
                                           alt_tag=rss_info.logo_alt, link=rss_info.site_url, last_fetch = last_fetch_str, feed_id = rss_info.site_url,
                                           error_message=("Feed could not be loaded." if feed is None else None))

                g_c.put(rss_info.site_url, template, timeout=EXPIRE_MINUTES * 12)

            result[cur_col].append(template)

            if not single_column:
                cur_col += 1
                cur_col %= 3

        result[0] = Markup(''.join(result[0]))

        if not single_column:
            result[1] = Markup(''.join(result[1]))
            result[2] = Markup(''.join(result[2]))

        # Set page colors and styles based on user preferences.
        if dark_mode:
            back_color = '#1e1e1e'
            text_color = '#d4d4d4'
        else:
            back_color = '#f6f5f4'
            text_color = 'black'

        text_font_style = ""
        if sans_serif:
            text_font_style = "font-family: sans-serif;"

        # Include additional HTML content if available.
        try:
            with open(ABOVE_HTML_FILE, 'r', encoding='utf-8') as f:
                above_html = f.read()
        except FileNotFoundError:
            above_html = ""

        if not single_column:
            above_html = above_html.replace("<hr/>", "")

        # Get weather HTML
        weather_html = get_default_weather_html()

        # Render the final page.
        page = render_template('page.html', columns=result, text_color=text_color,
                               logo_url=LOGO_URL, back_color=back_color, title=WEB_TITLE,
                               description=WEB_DESCRIPTION, favicon=FAVICON,
                               welcome_html=Markup(WELCOME_HTML), no_underlines = no_underlines,
                               text_font_style=text_font_style, above_html=Markup(above_html),
                               weather_html=Markup(weather_html))

        # Cache the rendered page if appropriate.
        if page_order_s == STANDARD_ORDER_STR:
            expire = EXPIRE_MINUTES
            if need_fetch:
                expire = 30

            g_c.put(page_order_s + suffix, page, timeout=expire)

        # Trigger background fetching if needed.
        if need_fetch and not g_c.has("FETCHMODE"):
            fetch_urls_thread()

        return page

    @app.route('/config', methods=['GET', 'POST'], strict_slashes=False)
    def config():

        if request.method == 'GET':
            # Render the configuration form with current settings.
            form = ConfigForm()

            dark_mode = request.cookies.get('DarkMode')
            if dark_mode:
                form.dark_mode.data = True

            no_underlines_cookie = request.cookies.get('NoUnderlines', "1")
            form.no_underlines.data = no_underlines_cookie == "1"

            sans_serif_cookie = request.cookies.get('SansSerif', "1")
            form.sans_serif.data = sans_serif_cookie == "1"

            page_order = request.cookies.get('RssUrls')
            if page_order is not None:
                page_order = json.loads(page_order)
            else:
                page_order = site_urls

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

            for i in range(custom_count, 5):
                rssf = CustomRSSForm()
                rssf.url = "http://"
                rssf.pri = (i + 30) * 10
                form.url_custom.append_entry(rssf)

            page = render_template('config.html', form=form)
            return page
        else:
            # Process the submitted configuration form.
            form = ConfigForm(request.form)
            if form.delete_cookie.data:
                template = render_template('configdone.html', message="Deleted cookies.")
                resp = app.make_response(template)
                resp.delete_cookie('RssUrls')
                resp.delete_cookie('DarkMode')
                resp.delete_cookie('NoUnderlines')
                resp.delete_cookie('SansSerif')
                return resp

            page_order = []

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

            template = render_template('configdone.html', message="Cookies saved for later.")
            resp = app.make_response(template)

            if page_order != site_urls:
                cookie_str = json.dumps(page_order)
                resp.set_cookie('RssUrls', cookie_str, max_age=EXPIRE_MINUTES)
                resp.set_cookie('UrlsVer', URLS_COOKIE_VERSION, max_age=EXPIRE_MINUTES)
            else:
                resp.delete_cookie('RssUrls')
                resp.delete_cookie('UrlsVer')

            if form.dark_mode.data:
                resp.set_cookie('DarkMode', "1", max_age=EXPIRE_MINUTES)
            else:
                resp.delete_cookie('DarkMode')

            resp.set_cookie("NoUnderlines", "1" if form.no_underlines.data else "0", max_age=EXPIRE_MINUTES)
            resp.set_cookie("SansSerif", "1" if form.sans_serif.data else "0", max_age=EXPIRE_MINUTES)

            return resp

    @app.route('/api/weather')
    def get_weather():
        # Use the user's IP address for weather lookup
        ip = request.remote_addr
        weather_data, status_code = get_weather_data(ip=ip)
        return jsonify(weather_data), status_code