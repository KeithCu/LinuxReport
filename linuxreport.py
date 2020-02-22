import random
import json
import itertools

# import html
import os
import time
import socket
from timeit import default_timer as timer
import concurrent.futures

import urllib3
import feedparser

from flask_mobility import Mobility
from flask import Flask, render_template, Markup, request
from flask_caching import Cache
from wtforms import Form, BooleanField, FormField, FieldList, StringField, IntegerField, \
                    validators

LINUX_REPORT = True
DEBUG = False

HTTP = urllib3.PoolManager()

g_app = Flask(__name__)
Mobility(g_app)
application = g_app

EXPIRE_MINUTES = 60 * 5

if DEBUG or g_app.debug:
    EXPIRE_MINUTES = 1
    print("Warning, in debug mode")

EXPIRE_HOURS = 3600
EXPIRE_DAY = 3600 * 6
EXPIRE_DAYS = 86400 * 10
EXPIRE_YEARS = 60 * 60 * 24 * 365 * 2

g_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = EXPIRE_DAYS

SITE_URLS_LR = {

    "https://www.reddit.com/r/China_Flu/rising/.rss" :
    ["Coronavirus.jpg",
     "Reddit Corona virus sub",
     "https://www.reddit.com/r/China_Flu/",
     EXPIRE_HOURS],

    "http://lxer.com/module/newswire/headlines.rss" :
    ["lxer.png",
     "Lxer news",
     "http://lxer.com/",
     EXPIRE_HOURS],

    "http://www.reddit.com/r/linux/rising/.rss" :
    ["redditlogosmall.png",
     "Reddit Linux sub",
     "https://www.reddit.com/r/linux",
     EXPIRE_HOURS * 2],

    "http://rss.slashdot.org/Slashdot/slashdotMain" :
    ["slashdotlogo.png",
     "Slashdot",
     "https://slashdot.org/",
     EXPIRE_HOURS],

    "http://lwn.net/headlines/newrss" :
    ["barepenguin-70.png",
     "LWN.net news",
     "https://lwn.net/",
     EXPIRE_DAY],

    "http://news.ycombinator.com/rss" :
    ["hackernews.jpg",
     "Ycombinator news",
     "http://news.ycombinator.com/",
     EXPIRE_HOURS],

    "http://www.osnews.com/feed/" :
    ["osnews-logo.png",
     "OS News.com",
     "http://www.osnews.com/",
     EXPIRE_HOURS * 2],

    "http://www.geekwire.com/feed/" :
    ["GeekWire.png",
     "GeekWire",
     "http://www.geekwire.com/",
     EXPIRE_HOURS * 3], #Slow and slow-changing, so fetch less

    "http://feeds.feedburner.com/linuxtoday/linux" :
    ["linuxtd_logo.png",
     "Linux Today",
     "http://www.linuxtoday.com/",
     EXPIRE_HOURS * 2],

    "http://planet.debian.org/rss20.xml" :
    ["Debian-OpenLogo.svg",
     "Planet Debian",
     "http://planet.debian.org/",
     EXPIRE_HOURS * 2],

    "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984" :
    ["Google-News.png",
     "Google Coronavirus news",
     "https://news.google.com/search?q=coronavirus",
     EXPIRE_HOURS],
}

SITE_URLS_CR = {
    "https://www.reddit.com/r/Coronavirus/rising/.rss" :
    ["redditlogosmall.png",
     "Reddit Corona virus sub",
     "https://www.reddit.com/r/Coronavirus/",
     EXPIRE_HOURS],

    "https://www.reddit.com/r/China_Flu/rising/.rss" :
    ["Coronavirus.jpg",
     "Reddit China Flu sub",
     "https://www.reddit.com/r/China_Flu/",
     EXPIRE_HOURS],

    "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984" :
    ["Google-News.png",
     "Google News",
     "https://news.google.com/search?q=coronavirus",
     EXPIRE_HOURS],

    "http://www.independent.co.uk/topic/coronavirus/rss" :
    ["Independent-Corona.png",
     "Independent UK news",
     "https://www.independent.co.uk/topic/coronavirus",
     EXPIRE_HOURS * 4],

    "https://gnews.org/feed/" :
    ["gnews.png",
     "Guo Media news",
     "https://gnews.org/",
     EXPIRE_HOURS * 4],

    "https://tools.cdc.gov/api/v2/resources/media/403372.rss" :
    ["CDC-Logo.png",
     "Centers for Disease Control",
     "https://www.cdc.gov/coronavirus/2019-nCoV/index.html",
     EXPIRE_DAY],

    "https://www.youtube.com/feeds/videos.xml?channel_id=UCD2-QVBQi48RRQTD4Jhxu8w" :
    ["PeakProsperity.png",
     "Chris Martenson Peak Prosperity",
     "https://www.youtube.com/user/ChrisMartensondotcom/videos",
     EXPIRE_DAY],

    "https://www.youtube.com/feeds/videos.xml?channel_id=UCF9IOB2TExg3QIBupFtBDxg" :
    ["JohnCampbell.png",
     "Dr. John Campbell",
     "https://www.youtube.com/user/Campbellteaching/videos",
     EXPIRE_DAY],

    "https://corona.castos.com/feed" :
    ["CoronaCastos2.png",
     "Coronavirus Central Daily Podcast",
     "http://coronaviruscentral.net",
     EXPIRE_DAY],

}

if LINUX_REPORT:
    site_urls = SITE_URLS_LR
    site_urls_alt = SITE_URLS_CR
    URL_IMAGES = "http://linuxreport.net/static/images/"
    FAVICON = "http://linuxreport.net/static/images/linuxreport192.ico"
    LOGO_URL = "http://linuxreport.net/static/images/LinuxReport2.png"
    WEB_TITLE = "Linux Report"
    WEB_DESCRIPTION = "Linux News dashboard"
    WELCOME_HTML = '(Refreshes automatically -- See also <b><a target="_blank" href = "http://covidreport.net/">CovidReport</a></b>) - Fork me on <a href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a>'

else:
    site_urls = SITE_URLS_CR
    site_urls_alt = SITE_URLS_LR
    URL_IMAGES = "http://covidreport.net/static/images/"
    FAVICON = "http://covidreport.net/static/images/covidreport192.ico"
    LOGO_URL = "http://covidreport.net/static/images/CovidReport.png"
    WEB_DESCRIPTION = "COVID-19 and SARS-COV-2 news dashboard"
    WEB_TITLE = "COVID-19 Report"
    WELCOME_HTML = '(Refreshes automatically -- See also <b><a target="_blank" href = "http://linuxreport.net/">LinuxReport</a></b>) - Fork me on <a href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a>'

class FlaskCache():
    def __init__(self):
        self._cache = Cache(g_app, config={'CACHE_TYPE': 'filesystem', 'CACHE_DIR' : '/tmp/linuxreport/', 'CACHE_DEFAULT_TIMEOUT' : EXPIRE_DAY})

    def put(self, url, template, timeout):
        self._cache.set(url, template, timeout)

    def get(self, url):
        template = self._cache.get(url)
        return template

    def delete(self, url):
        self._cache.delete(url)

def load_url_worker(url):
    site_info = site_urls[url]

    _logo_url, _logo_alt, site_url, expire_time = site_info

    #This FETCHPID logic is to prevent race conditions of
    #multiple Python processes fetching an expired RSS feed.
    feedpid = g_c.get(url + "FETCHPID")
    if feedpid is None:
        g_c.put(url + "FETCHPID", os.getpid(), timeout=10)
        feedpid = g_c.get(url + "FETCHPID") #Check to make sure it's us

    if feedpid == os.getpid():
        start = timer()
        res = feedparser.parse(url)
        feedinfo = list(itertools.islice(res['entries'], 8))
        g_c.put(url, feedinfo, timeout=expire_time)
        g_c.delete(url + "FETCHPID")
        end = timer()
        print("Parsing from remote site %s in %f." %(url, end - start))
    else:
        print("Waiting for someone else to parse remote site %s" %(url))

        # Someone else is fetching, so wait
        while feedpid is not None:
            time.sleep(0.1)
            feedpid = g_c.get(url + "FETCHPID")

        print("Done waiting for someone else to parse remote site %s" %(url))

def fetch_urls_parallel(urls):
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(load_url_worker, url): url for url in urls}

        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            future.result()

g_c = None
g_standard_order = list(site_urls.keys())
g_standard_order_s = str(g_standard_order)

g_first = True

#The main page
@g_app.route('/')
def index():

    global g_c
    global g_first

    if g_c is None:
        socket.setdefaulttimeout(5)
        g_c = FlaskCache()

    if request.cookies.get('DarkMode') is None:
        dark_mode = False
    else:
        dark_mode = True

    if request.cookies.get("NoUnderlines") is None:
        no_underlines = False
    else:
        no_underlines = True

    page_order = request.cookies.get('RssUrls')
    if page_order is not None:
        page_order = json.loads(page_order)

    if page_order is None:
        page_order = g_standard_order

    page_order_s = str(page_order)

    suffix = ""
    single_column = False

    if request.MOBILE:
        suffix = ":MOBILE"
        single_column = True

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
    # 1. Go through URLs and collect the template and the needed feeds.
    result_1 = {}
    needed_urls = []

    for url in page_order:
        site_info = site_urls.get(url, None)

        if site_info is None:
            #Check if site info is in other urls
            site_info = site_urls_alt.get(url, None)

            if site_info is None:
                site_info = ["Custom.png", "Custom site", url + "HTML", EXPIRE_HOURS * 3]

            site_urls[url] = site_info

        logo_url, _logo_alt, site_url, expire_time = site_info

        #First check for the templatized content stored with site URL
        template = g_c.get(site_url)

        #If we don't have the template, the feed has expired
        if template is None:
            needed_urls.append(url)
        else:
            result_1[url] = template

    # Asynchronously fetch all the needed URLs
    if len(needed_urls) > 0:
        start = timer()
        fetch_urls_parallel(needed_urls)
        end = timer()
        print("Fetched %d feeds in %f sec." % (len(needed_urls), end - start))

    #2. Now we've got all the data, go through again to build the page
    for url in page_order:
        site_info = site_urls[url]
        logo_url, logo_alt, site_url, expire_time = site_info

        #First check to see if we already have this result
        template = result_1.get(url, None)
        if template is None:

            #If not, feed should be in the RSS cache by now
            feedinfo = g_c.get(url)

            if DEBUG:
                expire_time = 10

            template = render_template('sitebox.html', entries=feedinfo, logo=URL_IMAGES + logo_url,
                                       alt_tag=logo_alt, link=site_url)

            offset = 0

            # Add 2.5 min offset so refreshes likely to expire together between page cache expirations.
            if g_first:
                offset = 150

            g_c.put(site_url, template, timeout=expire_time + offset)

        result[cur_col].append(template)

        if not single_column:
            cur_col += 1
            cur_col %= 3

    g_first = False

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

    page = render_template('page.html', columns=result, text_color=text_color,
                           logo_url=LOGO_URL, back_color=back_color, title=WEB_TITLE, 
                           description = WEB_DESCRIPTION, favicon=FAVICON,
                           welcome_html=Markup(WELCOME_HTML), a_text_decoration = text_decoration)

    # Only cache standard order
    if page_order_s == g_standard_order_s:
        g_c.put(page_order_s + suffix, page, timeout=EXPIRE_MINUTES)
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
            page_order = list(site_urls.keys())

        custom_count = 0
        for i, p_url in enumerate(page_order):
            site_info = site_urls.get(p_url, None)
            if site_info is not None and site_info[0] != "Custom.png":
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
            resp = g_app.make_response("<HTML><BODY>Deleted cookies.</BODY></HTML>")
            resp.delete_cookie('RssUrls')
            resp.delete_cookie('DarkMode')
            resp.delete_cookie('NoUnderlines')
            return resp

        page_order = []

        urls = list(form.urls)

        url_custom = list(form.url_custom)
        for site in url_custom:
            if len(site.url.data) > 10: #URLs greater than 10 chars
                urls.append(site)

        urls.sort(key=lambda x: x.pri.data)

        for urlf in urls:
            if isinstance(urlf.form, UrlForm):
                page_order.append(urlf.url.data)
            elif isinstance(urlf.form, CustomRSSForm):
                page_order.append(urlf.url.data)

        resp = g_app.make_response("<HTML><BODY>Saved cookies for later.</BODY></HTML>")

        if page_order != g_standard_order:
            #Pickle this stuff to a string to send as a cookie
            cookie_str = json.dumps(page_order)
            resp.set_cookie('RssUrls', cookie_str, max_age=EXPIRE_YEARS)
        else:
            resp.delete_cookie('RssUrls')

        if form.dark_mode.data:
            resp.set_cookie('DarkMode', "1", max_age=EXPIRE_YEARS)
        else:
            resp.delete_cookie('DarkMode')

        if form.no_underlines.data:
            resp.set_cookie("NoUnderlines", "1", max_age=EXPIRE_YEARS)
        else:
            resp.delete_cookie("NoUnderlines")

        return resp
