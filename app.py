import sys
import os
import time
import json
import socket
import random
import threading
import itertools
import concurrent.futures
from datetime import datetime, timedelta, timezone
from timeit import default_timer as timer
import difflib
import zoneinfo

import feedparser
from flask import Flask, render_template, request, g
from flask_mobility import Mobility
from wtforms import Form, BooleanField, FormField, FieldList, StringField, IntegerField, validators
from markupsafe import Markup
from autoscraper import AutoScraper

from pathlib import Path
import diskcache


sys.path.insert(0, "/srv/http/CovidReport2")

from feedfilter import prefilter_news, filter_similar_titles, merge_entries
import shared
from shared import RssFeed, RssInfo, EXPIRE_YEARS, EXPIRE_WEEK, EXPIRE_DAY, EXPIRE_HOUR, EXPIRE_MINUTES, TZ, MODE, Mode, g_c
import auto_update
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
RSS_TIMEOUT = 15

#Mechanism to throw away old cookies.
URLS_COOKIE_VERSION = "1"

ALL_URLS = {}


if MODE == Mode.LINUX_REPORT:
    from linux_report_settings import *
elif MODE == Mode.COVID_REPORT:
    from covid_report_settings import *
elif MODE == Mode.TECHNO_REPORT:
    from techno_report_settings import *
elif MODE == Mode.AI_REPORT:
    from ai_report_settings import *
elif MODE == Mode.TRUMP_REPORT:
    from trump_report_settings import *

feedparser.USER_AGENT = USER_AGENT


def load_url_worker(url):
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
            res = feedparser.parse(url)

        new_entries = prefilter_news(url, res)
        new_entries = filter_similar_titles(url, new_entries)
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

        # OpenAI's code doesn't work with sub-interpreters so disable for now.
        # if len(top_articles) == 0:
        #     prompt = shared.modetoprompt2[MODE]
        #     articles = [{"title": e["title"], "url": e["link"]} for e in entries[:5]]
        #     model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
        #     ai_response = shared.ask_ai_top_articles(articles, model)
        #     top_titles = shared.extract_top_titles_from_ai(ai_response)
        #     for title in top_titles:
        #         for article in articles:
        #             if shared.normalize(title) == shared.normalize(article["title"]):
        #                 image_url = auto_update.fetch_largest_image(article["url"])
        #                 top_articles.append({
        #                     "title": article["title"],
        #                     "url": article["url"],
        #                     "image_url": image_url
        #                 })
        #                 break

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

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
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

g_standard_order_s = str(site_urls)

#The main page
@g_app.route('/')
def index():
    #page_start = timer()

    # socket.setdefaulttimeout(RSS_TIMEOUT)

    dark_mode = request.cookies.get('DarkMode') 
    no_underlines = (request.cookies.get("NoUnderlines", "1") == "1") 
    sans_serif = (request.cookies.get("SansSerif", "1") == "1") 

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
        print("Fetched %d feeds in %f sec." % (len(needed_urls), end - start))

    #2. Now we've got all the data, go through again to build the page
    for url in page_order:
        rss_info = ALL_URLS[url]

        template = g_c.get(rss_info.site_url)
        if DEBUG or template is None:
            feed = g_c.get(url)
            entries = feed.entries
            top_images = {article['url']: article['image_url'] for article in feed.top_articles if article['image_url']}
            template = render_template('sitebox.html', top_images=top_images, entries=entries, logo=URL_IMAGES + rss_info.logo_url,
                                       alt_tag=rss_info.logo_alt, link=rss_info.site_url, feed_id = rss_info.site_url)

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

    page = render_template('page.html', columns=result, text_color=text_color,
                           logo_url=LOGO_URL, back_color=back_color, title=WEB_TITLE,
                           description=WEB_DESCRIPTION, favicon=FAVICON,
                           welcome_html=Markup(WELCOME_HTML), a_text_decoration=text_decoration,
                           text_font_style=text_font_style, above_html=Markup(above_html))

    # Only cache standard order
    if page_order_s == g_standard_order_s:

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
