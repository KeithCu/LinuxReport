import os
import json
from flask import request, render_template, make_response, flash
from flask_login import current_user
from shared import (
    limiter, dynamic_rate_limit, PATH, ABOVE_HTML_FILE,
    ENABLE_URL_CUSTOMIZATION, SITE_URLS, ALL_URLS, FAVICON,
    EXPIRE_YEARS, URLS_COOKIE_VERSION, clear_page_caches
)
from forms import ConfigForm, UrlForm, CustomRSSForm
from caching import _file_cache

def init_config_routes(app):
    @app.route('/config', methods=['GET', 'POST'], strict_slashes=False)
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
            form = ConfigForm()
            
            # Validate form with CSRF protection
            if not form.validate():
                # Form validation failed, re-render with errors
                flash('Please correct the errors below.', 'error')
                page = render_template('config.html', form=form, is_admin=is_admin, 
                                      favicon=FAVICON, enable_url_customization=ENABLE_URL_CUSTOMIZATION)
                return page
            
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
                    flash('Headlines saved successfully.', 'success')
                except Exception as e:
                    print(f"Error saving headlines file: {e}")
                    flash('Error saving headlines. Please try again.', 'error')

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
