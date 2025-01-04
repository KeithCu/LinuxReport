import sys
import os
import time
import json
import socket
import random
import threading
import itertools
import concurrent.futures
from enum import Enum
from datetime import datetime, timedelta
from timeit import default_timer as timer
import difflib

import feedparser
from flask import Flask, render_template, request
from flask_mobility import Mobility
from flask_caching import Cache
from wtforms import Form, BooleanField, FormField, FieldList, StringField, IntegerField, validators
from markupsafe import Markup
from autoscraper import AutoScraper

from feedfilter import prefilter_news
from shared import RssFeed, RssInfo, EXPIRE_MINUTES, EXPIRE_HOUR, EXPIRE_DAY, EXPIRE_WEEK, EXPIRE_YEARS

class Mode(Enum):
    LINUX_REPORT = 1
    COVID_REPORT = 2
    TECHNO_REPORT = 3

MODE = Mode.LINUX_REPORT

sys.path.insert(0, '/srv/http/LinuxReport2/')

DEBUG = False

g_app = Flask(__name__)
Mobility(g_app)
application = g_app

if DEBUG or g_app.debug:
    EXPIRE_MINUTES = 1
    print("Warning, in debug mode")

g_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = EXPIRE_WEEK

MAX_ITEMS = 8

#Mechanism to throw away old cookies.
URLS_COOKIE_VERSION = "1"

ALL_URLS = {}

if MODE == Mode.LINUX_REPORT:
    from linux_report_settings import *
elif MODE == Mode.COVID_REPORT:
    from covid_report_settings import *
elif MODE == Mode.TECHNO_REPORT:
    from techno_report_settings import *

feedparser.USER_AGENT = USER_AGENT
EXPIRE_FILE = False
class FSCache():
    def __init__(self):
        self._cache = Cache(g_app, config={'CACHE_TYPE': 'filesystem',
                                           'CACHE_DIR' : '/tmp/linuxreport/',
                                           'CACHE_DEFAULT_TIMEOUT' : EXPIRE_DAY,
                                           'CACHE_THRESHOLD' : 0})

    #This deserializes entire feed, just to get the timestamp
    #Not called too often so doesn't matter currently.
    def has_feed_expired(self, url):
        feed_info = g_c.get(url)
        if not isinstance(feed_info, RssFeed):
            return True
        return feed_info.expiration < datetime.utcnow()

    #This should be faster, but needs extra files to be created
    #EXPIRE_FILE = True
    def has_feed_expiredfast(self, url):
        expires = g_c.get(url + ":EXPIRES")
        if expires is None:
            return True
        return expires < datetime.utcnow()

    def put(self, url, template, timeout):
        self._cache.set(url, template, timeout)

    def has(self, url):
        return self._cache.cache.has(url)

    def get(self, url):
        return self._cache.get(url)

    def delete(self, url):
        self._cache.delete(url)

#If we've seen this title in other feeds, then filter it.
def filtersimilarTitles(url, entries):
    feed_alt = None

    if url == "https://www.reddit.com/r/Coronavirus/rising/.rss":
        feed_alt = g_c.get("https://www.reddit.com/r/China_Flu/rising/.rss")

    if url == "https://www.reddit.com/r/China_Flu/rising/.rss":
        feed_alt = g_c.get("https://www.reddit.com/r/Coronavirus/rising/.rss")

    if feed_alt:
        entries_c = entries.copy()

        for entry in entries_c:
            entry_words = sorted(entry.title.split())
            for entry_alt in feed_alt.entries:
                entry_alt_words = sorted(entry_alt.title.split())
                similarity = difflib.SequenceMatcher(None, entry_words, entry_alt_words).ratio()
                if similarity > 0.7:  # Adjust the threshold as needed
                    print(f"Similar title: 1: {entry.title}, 2: {entry_alt.title}, similarity: {similarity}.")
                    try:  # Entry could have been removed by another similar title
                        entries.remove(entry)
                    except:
                        pass
                    else:
                        print("Deleted title.")

    return entries


def load_url_worker(url):
    rss_info = ALL_URLS[url]

    expire_time = rss_info.expire_time

    #This FETCHPID logic is to prevent race conditions of
    #multiple Python processes / threads fetching an expired RSS feed.
    #This isn't as useful anymore given the FETCHMODE.
    if not g_c.has(url + "FETCHPID"):
        g_c.put(url + "FETCHPID", (os.getpid(), threading.get_ident()), timeout=10)
        feedpid = g_c.get(url + "FETCHPID") #Check to make sure it's us

    if feedpid == (os.getpid(), threading.get_ident()):
        start = timer()
        rssfeed = None

        if "Women" in url: #Special work for the women...
            pass
            scraper = AutoScraper()

            result2 = []
            try:
                scraper.load('/tmp/wowax-scrape')
                result2 = scraper.get_result_similar(url, grouped=True)

            except:
                #Special strings to trigger the proper auto-parsing for Women On Wax
                url_wow = 'https://keithcu.com/WomenOnWaxTest/'
                wanted_list = ['https://www.traxsource.com/title/1492869/blind-amerikkka',
                                'Blind Amerikkka']
                result = scraper.build(url=url_wow, wanted_list=wanted_list)
                result2 = scraper.get_result_similar(url_wow, grouped=True)
                scraper.save('/tmp/wowax-scrape')

            #Format received: dictionary containing two lists
            #Format needed: list containing dictionary entries for title and link                
            rules = list(result2.keys())
            rule1 = rules[0]
            rule2 = rules[1]

            rss_feed = []
            for entry_url, entry_title in zip(result2[rule1], result2[rule2]):
                entry_dict = {"title" : entry_title, "link" : entry_url}
                rss_feed.append(entry_dict)

            #Put them in reverse order
            entries = list(reversed(rss_feed))
            entries = list(itertools.islice(entries, MAX_ITEMS))

            rssfeed = RssFeed(entries)
            rssfeed.expiration = datetime.utcnow() + timedelta(seconds=expire_time)

            g_c.put(url, rssfeed, timeout=EXPIRE_WEEK)

        elif "bandcamp" in url or "keithcu" in url:
            pass
            scraper = AutoScraper()

            result2 = []
            try:
                scraper.load('/tmp/bandcamp-scrape')
                result2 = scraper.get_result_similar(url, grouped=True)

            except:
                #Special strings to trigger the proper auto-parsing for bandcamp
                #Hard-coded for Rocksteady disco.
                url_rocksteady = 'https://keithcu.com/BandcampTestRS/'
                wanted_list = ['https://keithcu.com/album/rsd020-abc-versions',
                                'RSD020 // ABC Versions']
                result = scraper.build(url=url_rocksteady, wanted_list=wanted_list)
                result2 = scraper.get_result_similar(url_rocksteady, grouped=True)
                scraper.save('/tmp/bandcamp-scrape')

                #Now that the model is build, try again for the proper URL
                scraper = AutoScraper()
                scraper.load('/tmp/bandcamp-scrape')
                #result = scraper.build(url=url, wanted_list=wanted_list)
                result2 = scraper.get_result_similar(url, grouped=True)

            #Format received: dictionary containing two lists
            #Format needed: list containing dictionary entries for title and link                
            rules = list(result2.keys())
            rule1 = rules[0]
            rule2 = rules[1]

            rss_feed = []
            for entry_url, entry_title in zip(result2[rule1], result2[rule2]):
                entry_dict = {"title" : entry_title, "link" : entry_url}
                rss_feed.append(entry_dict)

            entries = list(itertools.islice(rss_feed, MAX_ITEMS))

            rssfeed = RssFeed(entries)
            rssfeed.expiration = datetime.utcnow() + timedelta(seconds=expire_time)

            g_c.put(url, rssfeed, timeout=EXPIRE_WEEK)

        else:
            etag = ''
            last_modified = datetime.utcnow() - timedelta(seconds=EXPIRE_YEARS)

            rssfeed = g_c.get(url)
            if rssfeed != None:
                etag = rssfeed.etag
                last_modified = rssfeed.last_modified

            res = feedparser.parse(url, etag=etag, modified=last_modified)

            #No content changed:
            if rssfeed and hasattr(res, 'status') and (res.status == 304 or res.status == 301):
                print("No new info parsing from: %s, etag: %s, last_modified: %s." %(url, etag, last_modified))

                rssfeed.expiration = datetime.utcnow() + timedelta(seconds=expire_time)
                g_c.put(url, rssfeed, timeout=EXPIRE_WEEK)
                if EXPIRE_FILE:
                    g_c.put(url + ":EXPIRES", rssfeed.expiration, timeout=EXPIRE_WEEK)
                g_c.delete(url + "FETCHPID")
                return

            entries = prefilter_news(url, res)

            entries = filtersimilarTitles(url, entries)

            entries = list(itertools.islice(entries, MAX_ITEMS))

            if len(entries) <= 2 and rss_info.logo_url != "Custom.png":
                print("Failed to fetch %s, retry in 30 minutes." %(url))
                expire_time = 60 * 30

            rssfeed = RssFeed(entries)
            rssfeed.expiration = datetime.utcnow() + timedelta(seconds=expire_time)
            if hasattr(res, 'etag'):
                rssfeed.etag = res.etag

            if hasattr(res, 'modified'):
                rssfeed.last_modified = datetime.fromtimestamp(time.mktime(res.modified_parsed))
            elif res.feed.get('updated_parsed', None) is not None:
                rssfeed.last_modified = datetime.fromtimestamp(time.mktime(res.feed.updated_parsed))

        g_c.put(url, rssfeed, timeout=EXPIRE_WEEK)
        if EXPIRE_FILE:
            g_c.put(url + ":EXPIRES", rssfeed.expiration, timeout=EXPIRE_WEEK)

        if len(entries) > 2:
            g_c.delete(rss_info.site_url)

        g_c.delete(url + "FETCHPID")
        end = timer()
        print("Parsing from: %s, etag: %s, last-modified %s, in %f." %(url, rssfeed.etag, rssfeed.last_modified, end - start))

    else:
        print("Waiting for someone else to parse remote site %s" %(url))

        # Someone else is fetching, so wait
        while g_c.has(url + "FETCHPID"):
            time.sleep(0.1)

        print("Done waiting for someone else to parse remote site %s" %(url))

def wait_and_set_fetch_mode():
    #If any other process or thread is fetching feeds, then we should just wait a bit.
    #This prevents a thundering herd of threads.
    while g_c.has("FETCHMODE"):
        print("Waiting on another process to finish fetching.")
        time.sleep(0.2)
    print("Done waiting.")
    g_c.put("FETCHMODE", "FETCHMODE", timeout=10)


def fetch_urls_parallel(urls):
    wait_and_set_fetch_mode()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(load_url_worker, url): url for url in urls}

        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            future.result()

    g_c.delete("FETCHMODE")

def refresh_thread():
    for url in ALL_URLS.keys():
        rss_info = ALL_URLS[url]

        if g_c.has_feed_expired(url) and rss_info.logo_url != "Custom.png":
            wait_and_set_fetch_mode()
            load_url_worker(url)
            g_c.delete("FETCHMODE")
            time.sleep(0.2) #Give time for other processes to run

def fetch_urls_thread():
    t = threading.Thread(target=refresh_thread, args=())
    t.setDaemon(True) #It's okay to kill this thread when the process is trying to exit.
    t.start()

g_c = None
g_standard_order_s = str(site_urls)

#The main page
@g_app.route('/')
def index():

    global g_c
    #page_start = timer()

    if g_c is None:
        socket.setdefaulttimeout(7)
        g_c = FSCache()

    dark_mode = request.cookies.get('DarkMode') or request.args.get('DarkMode', False)
    no_underlines = request.cookies.get("NoUnderlines") or request.args.get('NoUnderlines', False)

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

    # if request.MOBILE:
    #     suffix = ":MOBILE"
    #     single_column = True

    if dark_mode:
        suffix = suffix + ":DARK"
    if no_underlines:
        suffix = suffix + ":NOUND"

    full_page = g_c.get(page_order_s + suffix)
    if full_page is not None:
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
            rss_info = RssInfo("Custom.png", "Custom site", url + "HTML", EXPIRE_HOUR * 3)
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
        if template is None:

            #The only reasons we don't have a template now is because:
            # 1. It's startup, or a custom feed.
            # 2. The feed was expired and refetched, and the template deleted after.

            # In either case, the RSS feed should be good for at least an hour so this is
            # pretty guaranteed to work and not crash.
            entries = g_c.get(url).entries

            template = render_template('sitebox.html', entries=entries, logo=URL_IMAGES + rss_info.logo_url,
                                       alt_tag=rss_info.logo_alt, link=rss_info.site_url)

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

    above_html = str(open(ABOVE_HTML_FILE).read())

    if not single_column:
        above_html = above_html.replace("<hr/>", "")

    page = render_template('page.html', columns=result, text_color=text_color,
                           logo_url=LOGO_URL, back_color=back_color, title=WEB_TITLE,
                           description=WEB_DESCRIPTION, favicon=FAVICON,
                           welcome_html=Markup(WELCOME_HTML), a_text_decoration=text_decoration,
                           above_html=Markup(above_html))

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

class ROStringField(StringField):
    def __call__(self, *args, **kwargs):
        kwargs.setdefault('readonly', True)
        return super(ROStringField, self).__call__(*args, **kwargs)

class UrlForm(Form):
    pri = IntegerField('Priority')
    url = ROStringField('RSS URL')

class CustomRSSForm(Form):
    pri = IntegerField('Priority')
    url = StringField('RSS URL', [validators.Length(min=10, max=120)])

class ConfigForm(Form):
    delete_cookie = BooleanField(label="Delete cookies")
    dark_mode = BooleanField(label="Dark mode")
    no_underlines = BooleanField(label="No underlines")
    urls = FieldList(FormField(UrlForm))
    url_custom = FieldList(FormField(CustomRSSForm))

@g_app.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'GET':
        form = ConfigForm()

        dark_mode = request.cookies.get('DarkMode')
        if dark_mode:
            form.dark_mode.data = True

        no_underlines = request.cookies.get('NoUnderlines')
        if no_underlines is not None:
            form.no_underlines.data = True

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

        if form.no_underlines.data:
            resp.set_cookie("NoUnderlines", "1", max_age=EXPIRE_YEARS)
        else:
            resp.delete_cookie("NoUnderlines")

        return resp
