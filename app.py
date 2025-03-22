import sys
import os
import time
import requests
import json
import threading
import itertools
import concurrent.futures
from datetime import datetime
from timeit import default_timer as timer

import feedparser
import socket
import socks
import urllib.request
from flask import Flask, render_template, request, g, jsonify

from flask_mobility import Mobility
from wtforms import Form, BooleanField, FormField, FieldList, StringField, IntegerField, validators
from markupsafe import Markup

sys.path.insert(0, "/srv/http/CovidReport2")

from feedfilter import prefilter_news, filter_similar_titles, merge_entries
import shared
from shared import RssFeed, RssInfo, EXPIRE_YEARS, EXPIRE_WEEK, EXPIRE_HOUR, EXPIRE_MINUTES, TZ, MODE, Mode, g_c
from seleniumfetch import fetch_site_posts

g_app = Flask(__name__)
Mobility(g_app)
application = g_app

DEBUG = False

if DEBUG or g_app.debug:
    EXPIRE_MINUTES = 1
    print("Warning, in debug mode")

g_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = shared.EXPIRE_WEEK

MAX_ITEMS = 40
RSS_TIMEOUT = 30

#Mechanism to throw away old URL cookies if the feeds change.
URLS_COOKIE_VERSION = "2"

WEATHER_API_KEY = "YOUR_WEATHER_API_KEY"  # Replace with your actual API key
WEATHER_CACHE_TIMEOUT = 3600 * 12  # 12 hours in seconds
FAKE_API = True  # Fake Weather API calls

# Add default coordinates for weather (e.g., San Francisco)
DEFAULT_WEATHER_LAT = "37.7749"
DEFAULT_WEATHER_LON = "-122.4194"

#Reddit has permanently blocked my IP address even though I was only make a few requests per hour
#far below their rate limits. 
# So use a user agent that looks like a Firefox browser and route the requests through Tor.
USER_AGENT_REDDIT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0"


proxies = {
    'https': 'socks5h://127.0.0.1:9050'
}

ALL_URLS = {}
config_settings = {}

if MODE == Mode.LINUX_REPORT:
    import linux_report_settings
    config_settings = linux_report_settings.CONFIG
elif MODE == Mode.COVID_REPORT:
    import covid_report_settings
    config_settings = covid_report_settings.CONFIG
elif MODE == Mode.TECHNO_REPORT:
    import techno_report_settings
    config_settings = techno_report_settings.CONFIG
elif MODE == Mode.AI_REPORT:
    import ai_report_settings
    config_settings = ai_report_settings.CONFIG
elif MODE == Mode.TRUMP_REPORT:
    import trump_report_settings
    config_settings = trump_report_settings.CONFIG
elif MODE == Mode.SPACE_REPORT:
    import space_report_settings
    config_settings = space_report_settings.CONFIG

ALL_URLS = config_settings.ALL_URLS
site_urls = config_settings.site_urls
USER_AGENT = config_settings.USER_AGENT
URL_IMAGES = config_settings.URL_IMAGES
FAVICON = config_settings.FAVICON
LOGO_URL = config_settings.LOGO_URL
WEB_DESCRIPTION = config_settings.WEB_DESCRIPTION
WEB_TITLE = config_settings.WEB_TITLE
ABOVE_HTML_FILE = config_settings.ABOVE_HTML_FILE
WELCOME_HTML =     ('<font size="4">(Displays instantly, refreshes hourly) - Fork me on <a target="_blank"'
                     'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
                     'href = "https://gitlab.com/keithcu/linuxreport">GitLab. </a></font>')



def get_tor_proxy_handler():
    """Create a ProxyHandler for Tor"""
    proxy_handler = urllib.request.ProxyHandler({
        "https": "socks5h://127.0.0.1:9050"
    })
    return proxy_handler


HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
    "Host": "www.reddit.com",
    "Connection": "keep-alive"
}
    
def load_url_worker(url):
    """Background worker to fetch a URL. Handles """
    rss_info = ALL_URLS[url]

    feedpid = None

    #This FETCHPID logic is to prevent race conditions of
    #multiple Python processes fetching an expired RSS feed.
    #This isn't as useful anymore given the FETCHMODE.
    if not g_c.has(url + "FETCHPID"):
        g_c.put(url + "FETCHPID", os.getpid(), timeout=RSS_TIMEOUT)
        feedpid = g_c.get(url + "FETCHPID") #Check to make sure it's us

    if feedpid == os.getpid():
        start = timer()
        rssfeed = None

        rssfeed = g_c.get(url)

        if "fakefeed" in url:
            res = fetch_site_posts(rss_info.site_url)
        else:
            if "reddit" in url:
                original_socket = socket.socket
                socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 9050)
                socket.socket = socks.socksocket
                try:
                    # Pass headers and disable HTTP/2 explicitly
                    opener = urllib.request.build_opener()
                    opener.addheaders = [(k, v) for k, v in HEADERS.items()]
                    urllib.request.install_opener(opener)
                    res = feedparser.parse(url, request_headers=HEADERS)
                finally:
                    socket.socket = original_socket
                    urllib.request.install_opener(None)  # Reset opener
            else:
                user_agent = USER_AGENT
                res = feedparser.parse(url, agent=user_agent)

        new_entries = prefilter_news(url, res)
        new_entries = filter_similar_titles(url, new_entries)

        if len(new_entries) == 0:
            print (f"No entries found for {url}.")
        #Trim the entries to the limit before compare so it doesn't find 500 new entries.
        new_entries = list(itertools.islice(new_entries, MAX_ITEMS))

        # Merge with cached entries (if any) to retain history.
        old_feed = g_c.get(url)

        new_count = len(new_entries)

        if old_feed and old_feed.entries:
            new_count = len(set(e.get('link') for e in new_entries) - set(e.get('link') for e in old_feed.entries))
            entries = merge_entries(new_entries, old_feed.entries)
        else:
            entries = new_entries

        #Trim the limit again after merge.
        entries = list(itertools.islice(entries, MAX_ITEMS))

        shared.history.update_fetch(url, new_count)

        top_articles = []

        if old_feed and old_feed.entries:
            previous_top_5 = set(e['link'] for e in old_feed.entries[:5])
            current_top_5 = set(e['link'] for e in entries[:5])
            if previous_top_5 == current_top_5:
                top_articles = old_feed.top_articles

        rssfeed = RssFeed(entries, top_articles=top_articles)

        g_c.put(url, rssfeed, timeout=EXPIRE_WEEK)
        g_c.put(url + ":last_fetch", datetime.now(TZ), timeout=EXPIRE_WEEK)

        if len(entries) > 2:
            g_c.delete(rss_info.site_url)

        g_c.delete(url + "FETCHPID")
        end = timer()
        print(f"Parsing from: {url}, in {end - start:f}.")
    else:
        print(f"Waiting for someone else to parse remote site {url}.")

        # Someone else is fetching, so wait
        while g_c.has(url + "FETCHPID"):
            time.sleep(0.1)

        print(f"Done waiting for someone else to parse {url}.")

def wait_and_set_fetch_mode():
    #If any other process is fetching feeds, then we should just wait a bit.
    #This prevents a thundering herd of threads.
    if g_c.has("FETCHMODE"):
        print("Waiting on another process to finish fetching.")
        while g_c.has("FETCHMODE"):
            time.sleep(0.1)
        print("Done waiting.")

    g_c.put("FETCHMODE", "FETCHMODE", timeout=RSS_TIMEOUT)

def fetch_urls_parallel(urls):
    wait_and_set_fetch_mode()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10 if not DEBUG else 1) as executor:
        future_to_url = {executor.submit(load_url_worker, url): url for url in urls}

        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            future.result()

    g_c.delete("FETCHMODE")

def refresh_thread():
    for url, rss_info in ALL_URLS.items():
        if g_c.has_feed_expired(url) and rss_info.logo_url != "Custom.png":
            wait_and_set_fetch_mode()
            load_url_worker(url)
            g_c.delete("FETCHMODE")
            time.sleep(0.2)  # Give time for other processes to run

def fetch_urls_thread():
    t = threading.Thread(target=refresh_thread, args=())
    t.daemon = True #It's okay to kill this thread when the process is trying to exit.
    t.start()

STANDARD_ORDER_STR = str(site_urls)

#The main page
@g_app.route('/')
def index():
    #page_start = timer()

    # socket.setdefaulttimeout(RSS_TIMEOUT)

    dark_mode = request.cookies.get('DarkMode')
    no_underlines = request.cookies.get("NoUnderlines", "1") == "1"
    sans_serif = request.cookies.get("SansSerif", "1") == "1"

    page_order = None
    if request.cookies.get('UrlsVer') == URLS_COOKIE_VERSION:
        page_order = request.cookies.get('RssUrls')
        if page_order is not None:
            page_order = json.loads(page_order)

    if page_order is None:
        page_order = site_urls

    page_order_s = str(page_order)

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

    full_page = g_c.get(page_order_s + suffix)
    if not DEBUG and full_page is not None:
        return full_page # Typically, the Python is finished here

    if single_column:
        result = [[]]
    else:
        result = [[], [], []]

    cur_col = 0

    # 2 phase process:
    # 1. Go through URLs and collect the needed feeds.
    needed_urls = []
    need_fetch = False

    for url in page_order:
        rss_info = ALL_URLS.get(url, None)

        if rss_info is None:
            rss_info = RssInfo("Custom.png", "Custom site", url + "HTML")
            ALL_URLS[url] = rss_info

        expired_rss = g_c.has_feed_expired(url)

        # If don't have template or RSS, have to fetch now
        if not g_c.has(rss_info.site_url) and expired_rss:
            needed_urls.append(url)
        elif expired_rss:
            need_fetch = True

    # Fetch all needed feeds
    if len(needed_urls) > 0:
        start = timer()
        fetch_urls_parallel(needed_urls)
        end = timer()
        print(f"Fetched {len(needed_urls)} feeds in {end - start} sec.")

    #2. Now we've got all the data, go through again to build the page
    for url in page_order:
        rss_info = ALL_URLS[url]

        template = g_c.get(rss_info.site_url)
        if DEBUG or template is None:
            feed = g_c.get(url)
            last_fetch = g_c.get(url + ":last_fetch")
            last_fetch_str = shared.format_last_updated(last_fetch, TZ)
            entries = feed.entries
            top_images = {article['url']: article['image_url'] for article in feed.top_articles if article['image_url']}
            template = render_template('sitebox.html', top_images=top_images, entries=entries, logo=URL_IMAGES + rss_info.logo_url,
                                       alt_tag=rss_info.logo_alt, link=rss_info.site_url, last_fetch = last_fetch_str, feed_id = rss_info.site_url)

            g_c.put(rss_info.site_url, template, timeout=EXPIRE_HOUR * 12)

        result[cur_col].append(template)

        if not single_column:
            cur_col += 1
            cur_col %= 3

    result[0] = Markup(''.join(result[0]))

    if not single_column:
        result[1] = Markup(''.join(result[1]))
        result[2] = Markup(''.join(result[2]))

    if dark_mode:
        back_color = '#1e1e1e'
        text_color = '#d4d4d4'
    else:
        back_color = '#f6f5f4'
        text_color = 'black'

    text_decoration = ""
    if no_underlines:
        text_decoration = "text-decoration:none;"

    text_font_style = ""
    if sans_serif:
        text_font_style = "font-family: sans-serif;"

    try:
        print(os.getcwd())
        with open(ABOVE_HTML_FILE, 'r') as f:
            above_html = f.read()
    except FileNotFoundError:
        above_html = ""

    if not single_column:
        above_html = above_html.replace("<hr/>", "")

#    weather_html = get_weather_html()

    page = render_template('page.html', columns=result, text_color=text_color,
                           logo_url=LOGO_URL, back_color=back_color, title=WEB_TITLE,
                           description=WEB_DESCRIPTION, favicon=FAVICON,
                           welcome_html=Markup(WELCOME_HTML), a_text_decoration=text_decoration,
                           text_font_style=text_font_style, above_html=Markup(above_html)) #, weather_html = Markup(weather_html))

    # Only cache standard order
    if page_order_s == STANDARD_ORDER_STR:

        expire = EXPIRE_MINUTES
        if need_fetch:
            expire = 30 #Page is already out of date, so cache for 30 seconds

        g_c.put(page_order_s + suffix, page, timeout=expire)

    # Spin up a thread to fetch all the expired feeds
    if need_fetch and not g_c.has("FETCHMODE"):
        fetch_urls_thread()

    #print("Rendered page in %f sec." % (timer() - page_start))

    return page


class UrlForm(Form):
    pri = IntegerField('Priority')
    url = StringField(' ', render_kw={"readonly": True, "style": "width: 300px;"})

class CustomRSSForm(Form):
    pri = IntegerField('Priority')
    url = StringField(' ', render_kw={"style": "width: 300px;"}, validators=[validators.Length(min=10, max=120)])

class ConfigForm(Form):
    delete_cookie = BooleanField(label="Delete cookies")
    dark_mode = BooleanField(label="Dark Mode")
    no_underlines = BooleanField(label="No Underlines")
    sans_serif = BooleanField(label="Sans Serif Font")
    urls = FieldList(FormField(UrlForm))
    url_custom = FieldList(FormField(CustomRSSForm))

@g_app.route('/config', methods=['GET', 'POST'], strict_slashes=False)
def config():
    if request.method == 'GET':
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
    else: #request.method == 'POST'
        form = ConfigForm(request.form)
        if form.delete_cookie.data:
            template = render_template('configdone.html', message="Deleted cookies.")
            resp = g_app.make_response(template)
            resp.delete_cookie('RssUrls')
            resp.delete_cookie('DarkMode')
            resp.delete_cookie('NoUnderlines')
            resp.delete_cookie('SansSerif')
            return resp

        page_order = []

        urls = list(form.urls)

        url_custom = list(form.url_custom)
        for site in url_custom:
            if len(site.url.data) > 10 and len(site.url.data) < 120: #URLs 10 - 120
                urls.append(site)

        urls.sort(key=lambda x: x.pri.data)

        for urlf in urls:
            if isinstance(urlf.form, UrlForm):
                page_order.append(urlf.url.data)
            elif isinstance(urlf.form, CustomRSSForm):
                page_order.append(urlf.url.data)

        template = render_template('configdone.html', message="Cookies saved for later.")
        resp = g_app.make_response(template)

        if page_order != site_urls:
            #Pickle this stuff to a string to send as a cookie
            cookie_str = json.dumps(page_order)
            resp.set_cookie('RssUrls', cookie_str, max_age=EXPIRE_YEARS)
            resp.set_cookie('UrlsVer', URLS_COOKIE_VERSION, max_age=EXPIRE_YEARS)
        else:
            resp.delete_cookie('RssUrls')
            resp.delete_cookie('UrlsVer')

        if form.dark_mode.data:
            resp.set_cookie('DarkMode', "1", max_age=EXPIRE_YEARS)
        else:
            resp.delete_cookie('DarkMode')

        resp.set_cookie("NoUnderlines", "1" if form.no_underlines.data else "0", max_age=EXPIRE_YEARS)
        resp.set_cookie("SansSerif", "1" if form.sans_serif.data else "0", max_age=EXPIRE_YEARS)

        return resp

@g_app.route('/api/weather')
def get_weather():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    
    if not lat or not lon:
        return jsonify({"error": "Missing latitude or longitude"}), 400
    
    cache_key = f"weather:{lat}:{lon}"
    
    # Check if we have cached weather data
    cached_weather = g_c.get(cache_key)
    if cached_weather:
        return jsonify(cached_weather)
    
    # If using fake API data 
    if FAKE_API:
        fake_data = {
            "daily": [
                {
                    "dt": int(datetime.now().timestamp()) + i * 86400,
                    "temp_min": 10 + i,
                    "temp_max": 20 + i,
                    "precipitation": 5 * i,
                    "weather": "Clear" if i % 2 == 0 else "Cloudy",
                    "weather_icon": "01d" if i % 2 == 0 else "02d"
                } for i in range(5)
            ]
        }
        g_c.put(cache_key, fake_data, timeout=WEATHER_CACHE_TIMEOUT)
        return jsonify(fake_data)
    
    # If not in cache, fetch from weather API
    try:
        # Using OpenWeatherMap API for 5-day forecast
        # You can replace this with your preferred weather API
        url = f"https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&exclude=current,minutely,hourly,alerts&units=metric&appid={WEATHER_API_KEY}"
        response = requests.get(url, timeout=10)
        weather_data = response.json()
        
        # Process and simplify the data
        processed_data = {
            "daily": []
        }
        
        for day in weather_data.get("daily", [])[:5]:  # 5 days forecast
            processed_data["daily"].append({
                "dt": day.get("dt"),
                "temp_min": day.get("temp", {}).get("min"),
                "temp_max": day.get("temp", {}).get("max"),
                "precipitation": day.get("pop", 0) * 100,  # Convert to percentage
                "weather": day.get("weather", [{}])[0].get("main"),
                "weather_icon": day.get("weather", [{}])[0].get("icon")
            })
        
        # Cache the processed weather data
        g_c.put(cache_key, processed_data, timeout=WEATHER_CACHE_TIMEOUT)
        
        return jsonify(processed_data)
    
    except Exception as e:
        print(f"Error fetching weather data: {e}")
        return jsonify({"error": "Failed to fetch weather data"}), 500

# Add this function to check if we need to add weather HTML to the page
def get_weather_html():
    default_lat = DEFAULT_WEATHER_LAT
    default_lon = DEFAULT_WEATHER_LON
    cache_key = f"weather:{default_lat}:{default_lon}"

        # If using fake API data 
    if FAKE_API:
        fake_data = {
            "daily": [
                {
                    "dt": int(datetime.now().timestamp()) + i * 86400,
                    "temp_min": 10 + i,
                    "temp_max": 20 + i,
                    "precipitation": 5 * i,
                    "weather": "Clear" if i % 2 == 0 else "Cloudy",
                    "weather_icon": "01d" if i % 2 == 0 else "02d"
                } for i in range(5)
            ]
        }
        g_c.put(cache_key, fake_data, timeout=WEATHER_CACHE_TIMEOUT)
        weather_data = fake_data
    else:
        weather_data = g_c.get(cache_key)

    if weather_data and "daily" in weather_data and len(weather_data["daily"]) > 0:
        forecast_html = '<div id="weather-forecast" class="weather-forecast">'
        for day in weather_data["daily"]:
            d = datetime.fromtimestamp(day["dt"])
            day_name = "Today" if d.date() == datetime.now().date() else d.strftime("%a")
            forecast_html += f'''
                <div class="weather-day">
                    <div class="weather-day-name">{day_name}</div>
                    <img class="weather-icon" src="https://openweathermap.org/img/wn/{day["weather_icon"]}.png" alt="{day["weather"]}">
                    <div class="weather-temp">
                        <span class="temp-max">{round(day["temp_max"])}°</span> / 
                        <span class="temp-min">{round(day["temp_min"])}°</span>
                    </div>
                    <div class="weather-precip">{round(day["precipitation"])}% precip</div>
                </div>
            '''
        forecast_html += '</div>'
        return f'''
        <div id="weather-container" class="weather-container">
            <h3>5-Day Weather</h3>
            {forecast_html}
        </div>
        '''
    else:
        # Fallback: client-side JS will fetch real data via geolocation.
        return """
        <div id="weather-container" class="weather-container">
            <h3>5-Day Weather</h3>
            <div id="weather-loading">Loading weather data...</div>
            <div id="weather-error" style="display: none; color: red;">Failed to load weather data</div>
            <div id="weather-forecast" style="display: none;"></div>
        </div>
        """

