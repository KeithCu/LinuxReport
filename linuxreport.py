import random
import json
import itertools
# import html
import os
import time
import socket
import threading
from timeit import default_timer as timer
import concurrent.futures
import feedparser

from flask_mobility import Mobility
from flask import Flask, render_template, Markup, request
from flask_caching import Cache
from wtforms import Form, BooleanField, FormField, FieldList, StringField, IntegerField, \
                    validators

LINUX_REPORT = True
DEBUG = False

g_app = Flask(__name__)
Mobility(g_app)
application = g_app

EXPIRE_MINUTES = 60 * 5

if DEBUG or g_app.debug:
    EXPIRE_MINUTES = 1
    print("Warning, in debug mode")

EXPIRE_HOUR = 3600
EXPIRE_DAY = 3600 * 6
EXPIRE_DAYS = 86400 * 10
EXPIRE_YEARS = 86400 * 365 * 2

g_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = EXPIRE_DAYS

ALL_URLS = {

    "https://www.reddit.com/r/China_Flu/rising/.rss" :
    ["Coronavirus.jpg",
     "Reddit China Flu sub",
     "https://www.reddit.com/r/China_Flu/",
     EXPIRE_HOUR],

    "https://www.reddit.com/r/Coronavirus/rising/.rss" :
    ["redditlogosmall.png",
     "Reddit Corona virus sub",
     "https://www.reddit.com/r/Coronavirus/",
     EXPIRE_HOUR],

    "http://lxer.com/module/newswire/headlines.rss" :
    ["lxer.png",
     "Lxer news",
     "http://lxer.com/",
     EXPIRE_HOUR],

    "http://www.reddit.com/r/linux/rising/.rss" :
    ["redditlogosmall.png",
     "Reddit Linux sub",
     "https://www.reddit.com/r/linux",
     EXPIRE_HOUR * 2],

    "http://rss.slashdot.org/Slashdot/slashdotMain" :
    ["slashdotlogo.png",
     "Slashdot",
     "https://slashdot.org/",
     EXPIRE_HOUR * 2],

    "http://lwn.net/headlines/newrss" :
    ["barepenguin-70.png",
     "LWN.net news",
     "https://lwn.net/",
     EXPIRE_DAY],

    "http://news.ycombinator.com/rss" :
    ["hackernews.jpg",
     "Ycombinator news",
     "http://news.ycombinator.com/",
     EXPIRE_HOUR * 2],

    "http://www.osnews.com/feed/" :
    ["osnews-logo.png",
     "OS News.com",
     "http://www.osnews.com/",
     EXPIRE_HOUR * 4],

    "http://www.geekwire.com/feed/" :
    ["GeekWire.png",
     "GeekWire",
     "http://www.geekwire.com/",
     EXPIRE_HOUR * 3], #Slow and slow-changing, so fetch less

    "http://feeds.feedburner.com/linuxtoday/linux" :
    ["linuxtd_logo.png",
     "Linux Today",
     "http://www.linuxtoday.com/",
     EXPIRE_HOUR * 3],

    "http://planet.debian.org/rss20.xml" :
    ["Debian-OpenLogo.svg",
     "Planet Debian",
     "http://planet.debian.org/",
     EXPIRE_HOUR * 3],

    "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984" :
    ["Google-News.png",
     "Google Coronavirus news",
     "https://news.google.com/search?q=coronavirus",
     EXPIRE_HOUR],

    "http://www.independent.co.uk/topic/coronavirus/rss" :
    ["Independent-Corona.png",
     "Independent UK news",
     "https://www.independent.co.uk/topic/coronavirus",
     EXPIRE_HOUR * 3],

    "https://gnews.org/feed/" :
    ["gnews.png",
     "Guo Media news",
     "https://gnews.org/",
     EXPIRE_HOUR * 3],

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
     EXPIRE_HOUR * 3],

}

SITE_URLS_LR = [
    "https://www.reddit.com/r/China_Flu/rising/.rss",
    "http://lxer.com/module/newswire/headlines.rss",
    "http://www.reddit.com/r/linux/rising/.rss",
    "http://rss.slashdot.org/Slashdot/slashdotMain",
    "http://lwn.net/headlines/newrss",
    "http://news.ycombinator.com/rss",
    "http://www.osnews.com/feed/",
    "http://www.geekwire.com/feed/",
    "http://feeds.feedburner.com/linuxtoday/linux",
    "http://planet.debian.org/rss20.xml",
    "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984",
]

SITE_URLS_CR = [
    "https://www.reddit.com/r/Coronavirus/rising/.rss",
    "https://www.reddit.com/r/China_Flu/rising/.rss",
    "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984",
    "http://www.independent.co.uk/topic/coronavirus/rss",
    "https://gnews.org/feed/",
    "https://tools.cdc.gov/api/v2/resources/media/403372.rss",
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCD2-QVBQi48RRQTD4Jhxu8w",
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCF9IOB2TExg3QIBupFtBDxg",
    "https://corona.castos.com/feed",
]

if LINUX_REPORT:
    site_urls = SITE_URLS_LR
    URL_IMAGES = "http://linuxreport.net/static/images/"
    FAVICON = "http://linuxreport.net/static/images/linuxreport192.ico"
    LOGO_URL = "http://linuxreport.net/static/images/LinuxReport2.png"
    WEB_TITLE = "Linux Report"
    WEB_DESCRIPTION = "Linux News dashboard"
    ABOVE_HTML = ''
    WELCOME_HTML = ('(Refreshes hourly -- See also <b><a target="_blank" href = '
    '"http://covidreport.net/">CovidReport</a></b>) - Fork me on <a target="_blank"'
    'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
    'href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a>')
else:
    site_urls = SITE_URLS_CR
    URL_IMAGES = "http://covidreport.net/static/images/"
    FAVICON = "http://covidreport.net/static/images/covidreport192.ico"
    LOGO_URL = "http://covidreport.net/static/images/CovidReport.png"
    WEB_DESCRIPTION = "COVID-19 and SARS-COV-2 news dashboard"
    WEB_TITLE = "COVID-19 Report"
    ABOVE_HTML = (
    '<iframe width="385" height="216" src="https://www.youtube.com/embed/GuBB3GNGQIk" frameborder="0" allow="accelerometer; '
    'autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>')
    # '<video controls preload="metadata" src="http://covidreport.net/static/images/Humany.mp4" autostart="false"'
    # 'width="385" height = "216" </video><a href = "https://www.youtube.com/channel/UCx_JS-Fzrq-bXUYP0mk9Zag/videos">src</a>')

    WELCOME_HTML = ('(Refreshes hourly -- See also <b><a target="_blank" href = '
    '"http://linuxreport.net/">LinuxReport</a></b>) - Fork me on <a target="_blank"'
    'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a  target="_blank"'
    'href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a><br/><i><a target = "_blank" '
    'href = "http://chng.it/RqYm4mh4JL">Sign this Change.org petition to request CDC do widespread '
    'testing</a></i>.')

class FlaskCache():
    def __init__(self):
        self._cache = Cache(g_app, config={'CACHE_TYPE': 'filesystem',
        'CACHE_DIR' : '/tmp/linuxreport/', 'CACHE_DEFAULT_TIMEOUT' : EXPIRE_DAY,
        'CACHE_THRESHOLD' : 0})

    def put(self, url, template, timeout):
        self._cache.set(url, template, timeout)

    def has (self, url):
        return self._cache.cache.has(url)

    def get(self, url):
        return self._cache.get(url)

    def delete(self, url):
        self._cache.delete(url)

def load_url_worker(url):
    site_info = ALL_URLS[url]

    logo_url, _logo_alt, site_url, expire_time = site_info

    #This FETCHPID logic is to prevent race conditions of
    #multiple Python processes fetching an expired RSS feed.
    #This isn't as useful anymore given the FETCHMODE.
    if g_c.has(url + "FETCHPID") == False:
        g_c.put(url + "FETCHPID", os.getpid(), timeout=10)
        feedpid = g_c.get(url + "FETCHPID") #Check to make sure it's us

    if feedpid == os.getpid():
        start = timer()
        res = feedparser.parse(url)
        feedinfo = list(itertools.islice(res['entries'], 8))

        if len(feedinfo) < 2 and logo_url != "Custom.png":
            print("Failed to fetch, retry in 15 minutes.")
            expire_time = 60 * 15

        g_c.put(url, feedinfo, timeout=expire_time)
        #Delete the template so that we refresh it next time
        g_c.delete(site_url)
        g_c.delete(url + "FETCHPID")
        end = timer()
        print("Parsing from remote site %s in %f." %(url, end - start))
    else:
        print("Waiting for someone else to parse remote site %s" %(url))

        # Someone else is fetching, so wait
        while g_c.has(url + "FETCHPID") == True:
            time.sleep(0.1)

        print("Done waiting for someone else to parse remote site %s" %(url))


def wait_and_set_fetch_mode():
    #If any other process is fetching feeds, then we should just wait a bit.
    #This prevents a thundering herd of threads.
    if g_c.has("FETCHMODE"):
        print ("Waiting on another process to finish fetching feeds.")
        while g_c.has("FETCHMODE"):
            time.sleep(0.1)
        print ("Done waiting.")

    g_c.put("FETCHMODE", "FETCHMODE", timeout = 20)

def fetch_urls_parallel(urls):
    wait_and_set_fetch_mode()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(load_url_worker, url): url for url in urls}

        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            future.result()

    g_c.delete("FETCHMODE")

def refresh_thread():
    for url in ALL_URLS.keys():
        wait_and_set_fetch_mode()

        if not g_c.has(url):
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
        page_order = site_urls

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
    # 1. Go through URLs and collect the needed feeds.
    needed_urls = []
    need_fetch = False

    for url in page_order:
        site_info = ALL_URLS.get(url, None)

        if site_info is None:
            site_info = ["Custom.png", "Custom site", url + "HTML", EXPIRE_HOUR * 3]
            ALL_URLS[url] = site_info

        logo_url, _logo_alt, site_url, expire_time = site_info

        has_rss = g_c.has(url)

        #Check for the templatized content stored with site URL
        if g_c.has(site_url) == False and has_rss == False: #If don't have template or RSS, have to fetch now
            needed_urls.append(url)
        else:
            #Check to see if the RSS feed is out of date, which means the template is old.
            if has_rss == False:
                need_fetch = True

    #Immediately fetch all needed feeds
    if len(needed_urls) > 0:
        start = timer()
        fetch_urls_parallel(needed_urls)
        end = timer()
        print("Fetched %d feeds in %f sec." % (len(needed_urls), end - start))

    #2. Now we've got all the data, go through again to build the page
    for url in page_order:
        site_info = ALL_URLS[url]
        logo_url, logo_alt, site_url, expire_time = site_info

        template = g_c.get(site_url)
        if template is None:

            #Feed should be in the RSS cache by now
            feedinfo = g_c.get(url)

            template = render_template('sitebox.html', entries=feedinfo, logo=URL_IMAGES + logo_url,
                                       alt_tag=logo_alt, link=site_url)

            g_c.put(site_url, template, timeout=EXPIRE_HOUR * 12)

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

    page = render_template('page.html', columns=result, text_color=text_color,
                           logo_url=LOGO_URL, back_color=back_color, title=WEB_TITLE, 
                           description = WEB_DESCRIPTION, favicon=FAVICON,
                           welcome_html=Markup(WELCOME_HTML), a_text_decoration = text_decoration,
                           above_html=Markup(ABOVE_HTML))

    # Only cache standard order
    if page_order_s == g_standard_order_s:

        expire = EXPIRE_MINUTES
        if need_fetch:
            expire = 30 #Page is already out of date, so cache page for only 30 seconds

        g_c.put(page_order_s + suffix, page, timeout=expire)

    # Spin up a thread to fetch all the expired feeds
    if need_fetch == True and g_c.has("FETCHMODE") is False:
        fetch_urls_thread()

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
            site_info = ALL_URLS.get(p_url, None)
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

        if page_order != site_urls:
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
