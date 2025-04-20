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
import uuid # For unique filenames
import ipaddress # Add ipaddress import
import time # Import time for SSE sleep

# Third-party imports
from flask import g, jsonify, render_template, request, make_response, Response
from markupsafe import Markup
from werkzeug.utils import secure_filename # For secure file uploads

from forms import ConfigForm, CustomRSSForm, UrlForm
from models import RssInfo
# Local imports
from shared import (ABOVE_HTML_FILE, ALL_URLS, DEBUG, EXPIRE_MINUTES,
                    FAVICON, LOGO_URL, STANDARD_ORDER_STR,
                    URL_IMAGES, URLS_COOKIE_VERSION, WEB_DESCRIPTION,
                    WEB_TITLE, WELCOME_HTML, g_c, site_urls, Mode, MODE, PATH, format_last_updated, get_chat_cache)
from weather import get_default_weather_html, get_weather_data
from workers import fetch_urls_parallel, fetch_urls_thread

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

# Function to initialize routes
def init_app(flask_app):
    
    @flask_app.route('/')
    def index():
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

        # Try full page cache using only page order and mobile flag
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

            template = g_c.get_template(rss_info.site_url)
            if DEBUG or template is None:
                feed = g_c.get_feed(url)
                last_fetch = g_c.get_last_fetch(url)
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

                g_c.set_template(rss_info.site_url, template, timeout=EXPIRE_MINUTES * 12)

            result[cur_col].append(template)

            if not single_column:
                cur_col += 1
                cur_col %= 3

        result[0] = Markup(''.join(result[0]))

        if not single_column:
            result[1] = Markup(''.join(result[1]))
            result[2] = Markup(''.join(result[2]))

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
        page = render_template('page.html', columns=result,
                               logo_url=LOGO_URL, title=WEB_TITLE,
                               description=WEB_DESCRIPTION, favicon=FAVICON,
                               welcome_html=Markup(WELCOME_HTML),
                               above_html=Markup(above_html),
                               weather_html=Markup(weather_html))

        # Store full page cache
        if page_order_s == STANDARD_ORDER_STR:
            expire = EXPIRE_MINUTES
            if need_fetch:
                expire = 30
            g_c.put(page_order_s + suffix, page, timeout=expire)

        # Trigger background fetching if needed.
        if need_fetch:
            fetch_urls_thread()

        return page

    @flask_app.route('/config', methods=['GET', 'POST'], strict_slashes=False)
    def config():

        if request.method == 'GET':
            form = ConfigForm()

            form.theme.data = request.cookies.get('Theme', 'light')

            no_underlines_cookie = request.cookies.get('NoUnderlines', "1")
            form.no_underlines.data = no_underlines_cookie == "1"

            sans_serif_cookie = request.cookies.get('SansSerif', "1")
            form.sans_serif.data = sans_serif_cookie == "1"

            form.admin_mode.data = request.cookies.get('isAdmin') == '1'

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
            form = ConfigForm(request.form)
            if form.delete_cookie.data:
                template = render_template('configdone.html', message="Deleted cookies.")
                resp = make_response(template)
                resp.delete_cookie('RssUrls')
                resp.delete_cookie('Theme')
                resp.delete_cookie('NoUnderlines')
                resp.delete_cookie('SansSerif')
                resp.delete_cookie('isAdmin')
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
            resp = make_response(template)

            if page_order != site_urls:
                cookie_str = json.dumps(page_order)
                resp.set_cookie('RssUrls', cookie_str, max_age=EXPIRE_MINUTES)
                resp.set_cookie('UrlsVer', URLS_COOKIE_VERSION, max_age=EXPIRE_MINUTES)
            else:
                resp.delete_cookie('RssUrls')
                resp.delete_cookie('UrlsVer')

            resp.set_cookie('Theme', form.theme.data, max_age=EXPIRE_MINUTES)

            resp.set_cookie("NoUnderlines", "1" if form.no_underlines.data else "0", max_age=EXPIRE_MINUTES)
            resp.set_cookie("SansSerif", "1" if form.sans_serif.data else "0", max_age=EXPIRE_MINUTES)

            if form.admin_mode.data:
                resp.set_cookie('isAdmin', '1', max_age=EXPIRE_MINUTES)
            else:
                resp.delete_cookie('isAdmin')

            return resp

    @flask_app.route('/api/weather')
    def get_weather():
        ip = request.remote_addr
        weather_data, status_code = get_weather_data(ip=ip)
        return jsonify(weather_data), status_code

    @flask_app.route('/old_headlines')
    def old_headlines():
        mode_map = {
            Mode.LINUX_REPORT: 'linux',
            Mode.COVID_REPORT: 'covid',
            Mode.TECHNO_REPORT: 'techno',
            Mode.AI_REPORT: 'ai',
            Mode.TRUMP_REPORT: 'trump',
        }
        mode_str = mode_map.get(MODE)
        archive_file = os.path.join(PATH, f"{mode_str}report_archive.jsonl")
        headlines = []
        try:
            with open(archive_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        headlines.append(entry)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            pass
        except IOError as e:
            print(f"Error reading archive file {archive_file}: {e}")
        headlines.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        if len(headlines) > 3:
            headlines = headlines[3:]
        else:
            headlines = []
        return render_template(
            'old_headlines.html',
            headlines=headlines,
            mode=mode_str,
            title=f"Old Headlines - {mode_str.title()}Report",
            favicon=FAVICON,
            logo_url=LOGO_URL,
            description=WEB_DESCRIPTION
        )

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
    def delete_comment(comment_id):
        is_admin = request.cookies.get('isAdmin') == '1'
        if not is_admin:
            return jsonify({"error": "Unauthorized"}), 403

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

    # If UPLOAD_FOLDER is 'static/uploads', Flask handles this automatically.
    # If it were outside 'static', you'd need something like this:
    # @flask_app.route('/uploads/<filename>')
    # def uploaded_file(filename):
    #     return send_from_directory(UPLOAD_FOLDER, filename)