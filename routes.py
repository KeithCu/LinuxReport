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

# Third-party imports
# Removed unused send_from_directory
from flask import g, jsonify, render_template, request, make_response
from markupsafe import Markup
from werkzeug.utils import secure_filename # For secure file uploads

from forms import ConfigForm, CustomRSSForm, UrlForm
from models import RssInfo
# Local imports
from shared import (ABOVE_HTML_FILE, ALL_URLS, DEBUG, EXPIRE_MINUTES,
                    FAVICON, LOGO_URL, STANDARD_ORDER_STR,
                    URL_IMAGES, URLS_COOKIE_VERSION, WEB_DESCRIPTION,
                    WEB_TITLE, WELCOME_HTML, g_c, site_urls, Mode, MODE, PATH, format_last_updated)
from weather import get_default_weather_html, get_weather_data
from workers import fetch_urls_parallel, fetch_urls_thread

# Constants for Chat Feature
MAX_COMMENTS = 1000
COMMENTS_KEY = "chat_comments"
BANNED_IPS_KEY = "banned_ips" # Store as a set in cache
UPLOAD_FOLDER = 'static/uploads' # Define upload folder relative to app root
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
            # Return only the first octet for IPv4
            return ip_str.split('.')[0]
        elif isinstance(ip, ipaddress.IPv6Address):
            # Return the first block for IPv6
            return ip_str.split(':')[0]
    except ValueError:
        return "Invalid IP" # Should not happen with request.remote_addr
    return None # Fallback

# Function to initialize routes
def init_app(flask_app):
     
    @flask_app.route('/')
    def index():
        # removed server-side theme and style reading; client JS applies these dynamically

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

        # removed server-side text_color and text_font_style; handled in CSS variables and JS

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
        if need_fetch and not g_c.has("FETCHMODE"):
            fetch_urls_thread()

        return page

    @flask_app.route('/config', methods=['GET', 'POST'], strict_slashes=False)
    def config():

        if request.method == 'GET':
            # Render the configuration form with current settings.
            form = ConfigForm()

            # Load theme preference
            form.theme.data = request.cookies.get('Theme', 'light')

            no_underlines_cookie = request.cookies.get('NoUnderlines', "1")
            form.no_underlines.data = no_underlines_cookie == "1"

            sans_serif_cookie = request.cookies.get('SansSerif', "1")
            form.sans_serif.data = sans_serif_cookie == "1"

            # Load admin mode preference from cookie
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
            # Process the submitted configuration form.
            form = ConfigForm(request.form)
            if form.delete_cookie.data:
                template = render_template('configdone.html', message="Deleted cookies.")
                resp = make_response(template) # Use make_response
                resp.delete_cookie('RssUrls')
                resp.delete_cookie('Theme')
                resp.delete_cookie('NoUnderlines')
                resp.delete_cookie('SansSerif')
                resp.delete_cookie('isAdmin') # Delete admin cookie too
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
            resp = make_response(template) # Use make_response

            if page_order != site_urls:
                cookie_str = json.dumps(page_order)
                resp.set_cookie('RssUrls', cookie_str, max_age=EXPIRE_MINUTES)
                resp.set_cookie('UrlsVer', URLS_COOKIE_VERSION, max_age=EXPIRE_MINUTES)
            else:
                resp.delete_cookie('RssUrls')
                resp.delete_cookie('UrlsVer')

            # Save theme preference
            resp.set_cookie('Theme', form.theme.data, max_age=EXPIRE_MINUTES)

            resp.set_cookie("NoUnderlines", "1" if form.no_underlines.data else "0", max_age=EXPIRE_MINUTES)
            resp.set_cookie("SansSerif", "1" if form.sans_serif.data else "0", max_age=EXPIRE_MINUTES)

            # Set or delete admin cookie based on form data
            if form.admin_mode.data:
                resp.set_cookie('isAdmin', '1', max_age=EXPIRE_MINUTES)
            else:
                # Ensure the cookie is deleted if unchecked
                resp.delete_cookie('isAdmin')

            return resp

    @flask_app.route('/api/weather')
    def get_weather():
        # Use the user's IP address for weather lookup
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
                    except json.JSONDecodeError: # Catch specific JSON error
                        # Optionally log this error
                        # print(f"Skipping invalid JSON line: {line.strip()}")
                        continue
        except FileNotFoundError:
            pass # File not existing is okay
        except IOError as e: # Catch potential file reading errors
            print(f"Error reading archive file {archive_file}: {e}")
            pass # Or handle differently
        headlines.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        # Remove the 3 most recent headlines
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
        comments = g_c.get(COMMENTS_KEY) or []
        # Ensure comments have IDs and prefixes (for older comments if schema changed)
        # This is a simple migration, a dedicated script might be better for large datasets
        needs_update = False
        for c in comments:
            updated = False
            if 'id' not in c:
                c['id'] = str(uuid.uuid4()) # Assign ID if missing
                updated = True
            if 'ip_prefix' not in c and 'ip' in c: # Add prefix if missing but IP exists
                c['ip_prefix'] = get_ip_prefix(c['ip']) # Corrected indentation
                c.pop('ip', None) # Corrected indentation
                updated = True # Corrected indentation
            elif 'ip' in c: # If prefix exists but old IP field is still there
                c.pop('ip', None) # Remove the old full IP field
                updated = True
            if updated:
                needs_update = True

        # If any comment was updated, save the changes back to cache
        if needs_update:
            g_c.put(COMMENTS_KEY, comments)

        return jsonify(comments)

    @flask_app.route('/api/comments', methods=['POST'])
    def post_comment():
        ip = request.remote_addr
        banned_ips = g_c.get(BANNED_IPS_KEY) or set()

        if ip in banned_ips:
            return jsonify({"error": "Banned"}), 403

        data = request.get_json()
        text = data.get('text', '').strip()
        image_url = data.get('image_url', '').strip()

        if not text and not image_url:
            return jsonify({"error": "Comment cannot be empty"}), 400

        # Basic sanitization: escape HTML, allow <b> and <img>
        sanitized_text = html.escape(text).replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')

        # Validate image URL (very basic)
        print(f"Received image_url: '{image_url}'") # DEBUG
        valid_image_url = None
        if image_url:
            # Allow relative paths starting with the upload folder or absolute URLs or data URLs
            is_local_upload = image_url.startswith(f'/{UPLOAD_FOLDER}/')
            is_external_url = image_url.startswith('http://') or image_url.startswith('https://')
            is_data_url = image_url.startswith('data:image/')

            print(f"Validation check: is_local={is_local_upload}, is_external={is_external_url}, is_data={is_data_url}") # DEBUG
            print(f"Checking startswith: '/{UPLOAD_FOLDER}/'") # DEBUG

            if is_local_upload or is_external_url or is_data_url:
                 # Basic check for common image extensions for non-data URLs
                if not is_data_url:
                    has_valid_extension = image_url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
                    print(f"Extension check: valid={has_valid_extension}") # DEBUG
                    if not has_valid_extension:
                         print(f"Validation failed: Invalid extension for {image_url}") # DEBUG
                         pass # Invalid extension for local/external URL - valid_image_url remains None
                    else:
                         print(f"Validation passed for: {image_url}") # DEBUG
                         valid_image_url = image_url
                else: # Is data URL
                    print(f"Validation passed (data URL): {image_url[:50]}...") # DEBUG
                    valid_image_url = image_url
            else:
                 print(f"Validation failed: URL type not recognized for {image_url}") # DEBUG

        comment_id = str(uuid.uuid4()) # Generate unique ID
        ip_prefix = get_ip_prefix(ip) # Get IP prefix

        comment = {
            "id": comment_id, # Add ID
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "ip_prefix": ip_prefix, # Store prefix
            "text": sanitized_text,
            "image_url": valid_image_url # Use the validated URL
            # Removed "ip": ip - no longer storing full IP in comment object
        }
        print(f"Final valid_image_url being saved: '{valid_image_url}'") # DEBUG

        comments = g_c.get(COMMENTS_KEY) or []
        comments.append(comment)
        # Keep only the latest MAX_COMMENTS
        comments = comments[-MAX_COMMENTS:]
        g_c.put(COMMENTS_KEY, comments) # Store indefinitely or add timeout

        return jsonify({"success": True, "comment": comment}), 201

    # Add new delete route
    @flask_app.route('/api/comments/delete/<comment_id>', methods=['DELETE'])
    def delete_comment(comment_id):
        # Check for admin cookie
        is_admin = request.cookies.get('isAdmin') == '1'
        if not is_admin:
            return jsonify({"error": "Unauthorized"}), 403

        comments = g_c.get(COMMENTS_KEY) or []
        initial_length = len(comments)

        # Find and remove the comment by ID
        comments_after_delete = [c for c in comments if c.get('id') != comment_id]

        if len(comments_after_delete) < initial_length:
            g_c.put(COMMENTS_KEY, comments_after_delete)
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Comment not found"}), 404

    @flask_app.route('/api/upload_image', methods=['POST'])
    def upload_image():
        ip = request.remote_addr
        banned_ips = g_c.get(BANNED_IPS_KEY) or set()

        if ip in banned_ips:
            return jsonify({"error": "Banned"}), 403

        if 'image' not in request.files:
            return jsonify({"error": "No image file part"}), 400

        file = request.files['image']

        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if file and allowed_file(file.filename):
            if len(file.read()) > MAX_IMAGE_SIZE:
                return jsonify({"error": "File size exceeds limit"}), 400
            file.seek(0)  # Reset file pointer after size check
            # Create a unique filename to prevent overwrites and use secure_filename
            _, ext = os.path.splitext(file.filename)
            filename = secure_filename(f"{uuid.uuid4()}{ext}")
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            try:
                file.save(filepath)
                # Return the URL path to the uploaded file
                file_url = f"/{UPLOAD_FOLDER}/{filename}" # Construct URL path
                return jsonify({"success": True, "url": file_url}), 201
            except (IOError, OSError) as e: # Catch specific file saving errors
                # Log the error server-side (optional)
                print(f"Error saving file {filepath}: {e}")
                return jsonify({"error": "Failed to save image"}), 500
        else:
            return jsonify({"error": "Invalid file type"}), 400

    # Route to serve uploaded files (needed if UPLOAD_FOLDER is not directly under static)
    # If UPLOAD_FOLDER is 'static/uploads', Flask handles this automatically.
    # If it were outside 'static', you'd need something like this:
    # @flask_app.route('/uploads/<filename>')
    # def uploaded_file(filename):
    #     return send_from_directory(UPLOAD_FOLDER, filename)