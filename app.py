import sys
import random
import json
import itertools
# import html
import os
import time
from datetime import datetime, timedelta
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

sys.path.insert(0,'/srv/http/flask/')
from feedfilter import prefilter_news
from shared import RssFeed

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
EXPIRE_WEEK = 86400 * 7
EXPIRE_YEARS = 86400 * 365 * 2

g_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = EXPIRE_WEEK

class RssInfo:
    def __init__(self, logo_url, logo_alt, site_url, expire_time):
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url
        self.expire_time = expire_time

#Mechanism to throw away old cookies.
URLS_COOKIE_VERSION = "1"

ALL_URLS = {

    "https://www.reddit.com/r/Coronavirus/rising/.rss" :
     RssInfo("redditlogosmall.png",
     "Reddit Corona virus sub",
     "https://www.reddit.com/r/Coronavirus/",
     EXPIRE_HOUR),

    "https://www.reddit.com/r/China_Flu/rising/.rss" :
     RssInfo("Coronavirus.jpg",
     "Reddit China Flu sub",
     "https://www.reddit.com/r/China_Flu/",
     EXPIRE_HOUR),

    "http://lxer.com/module/newswire/headlines.rss" :
     RssInfo("lxer.png",
     "Lxer news",
     "http://lxer.com/",
     EXPIRE_HOUR),

    "https://www.reddit.com/r/linux/rising/.rss" :
     RssInfo("redditlogosmall.png",
     "Reddit Linux sub",
     "https://www.reddit.com/r/linux",
     EXPIRE_HOUR * 2),

    "http://rss.slashdot.org/Slashdot/slashdotMain" :
     RssInfo("slashdotlogo.png",
     "Slashdot",
     "https://slashdot.org/",
     EXPIRE_HOUR * 2),

    "https://lwn.net/headlines/newrss" :
     RssInfo("barepenguin-70.png",
     "LWN.net news",
     "https://lwn.net/",
     EXPIRE_DAY),

    "https://news.ycombinator.com/rss" :
     RssInfo("hackernews.jpg",
     "Ycombinator news",
     "http://news.ycombinator.com/",
     EXPIRE_HOUR * 2),

    "https://www.osnews.com/feed/" :
     RssInfo("osnews-logo.png",
     "OS News.com",
     "http://www.osnews.com/",
     EXPIRE_HOUR * 4),

    "https://www.geekwire.com/feed/" :
     RssInfo("GeekWire.png",
     "GeekWire",
     "http://www.geekwire.com/",
     EXPIRE_HOUR * 3), #Slow and slow-changing, so fetch less

    "http://feeds.feedburner.com/linuxtoday/linux" :
     RssInfo("linuxtd_logo.png",
     "Linux Today",
     "http://www.linuxtoday.com/",
     EXPIRE_HOUR * 3),

    "https://planet.debian.org/rss20.xml" :
     RssInfo("Debian-OpenLogo.svg",
     "Planet Debian",
     "http://planet.debian.org/",
     EXPIRE_HOUR * 3),

    "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984" :
     RssInfo("Google-News.png",
     "Google Coronavirus news",
     "https://news.google.com/search?q=coronavirus",
     EXPIRE_HOUR),

    "http://www.independent.co.uk/topic/coronavirus/rss" :
     RssInfo("Independent-Corona.png",
     "Independent UK news",
     "https://www.independent.co.uk/topic/coronavirus",
     EXPIRE_HOUR * 3),

    "https://gnews.org/feed/" :
    RssInfo("gnews.png",
     "Guo Media news",
     "https://gnews.org/",
     EXPIRE_HOUR * 3),

    "https://tools.cdc.gov/api/v2/resources/media/403372.rss" :
     RssInfo("CDC-Logo.png",
     "Centers for Disease Control",
     "https://www.cdc.gov/coronavirus/2019-nCoV/index.html",
     EXPIRE_DAY),

    "https://www.youtube.com/feeds/videos.xml?channel_id=UCD2-QVBQi48RRQTD4Jhxu8w" :
     RssInfo("PeakProsperity.png",
     "Chris Martenson Peak Prosperity",
     "https://www.youtube.com/user/ChrisMartensondotcom/videos",
     EXPIRE_DAY),

    "https://www.youtube.com/feeds/videos.xml?channel_id=UCF9IOB2TExg3QIBupFtBDxg" :
     RssInfo("JohnCampbell.png",
     "Dr. John Campbell",
     "https://www.youtube.com/user/Campbellteaching/videos",
     EXPIRE_DAY),

    "https://coronavirus-central.castos.com/feed" :
     RssInfo("CoronaCastos2.png",
     "Coronavirus Central Daily Podcast",
     "http://coronaviruscentral.net",
     EXPIRE_HOUR * 3),

    "https://pandemic.warroom.org/feed/" :
     RssInfo("WarRoom.png",
     "War Room: Pandemic",
     "https://pandemic.warroom.org/",
     EXPIRE_HOUR * 3),

}

SITE_URLS_LR = [
    "https://www.reddit.com/r/China_Flu/rising/.rss",
    "http://lxer.com/module/newswire/headlines.rss",
    "https://www.reddit.com/r/linux/rising/.rss",
    "http://rss.slashdot.org/Slashdot/slashdotMain",
    "https://lwn.net/headlines/newrss",
    "https://news.ycombinator.com/rss",
    "https://www.osnews.com/feed/",
    "https://www.geekwire.com/feed/",
    "http://feeds.feedburner.com/linuxtoday/linux",
    "https://planet.debian.org/rss20.xml",
    "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984",
]

SITE_URLS_CR = [
    "https://www.reddit.com/r/Coronavirus/rising/.rss",
    "https://www.reddit.com/r/China_Flu/rising/.rss",
    "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984",
    "http://www.independent.co.uk/topic/coronavirus/rss",
    "https://pandemic.warroom.org/feed/",
    "https://gnews.org/feed/",
    "https://tools.cdc.gov/api/v2/resources/media/403372.rss",
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCD2-QVBQi48RRQTD4Jhxu8w",
    "https://coronavirus-central.castos.com/feed",
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCF9IOB2TExg3QIBupFtBDxg",
]

if LINUX_REPORT:
    feedparser.USER_AGENT = "Linux Report -- http://linuxreport.net/"
    site_urls = SITE_URLS_LR
    URL_IMAGES = "http://linuxreport.net/static/images/"
    FAVICON = "http://linuxreport.net/static/images/linuxreport192.ico"
    LOGO_URL = "http://linuxreport.net/static/images/LinuxReport2.png"
    WEB_TITLE = "Linux Report"
    WEB_DESCRIPTION = "Linux News"
    ABOVE_HTML = (''
    #'<a target="_blank" href = "https://keithcu.com/wordpress/?page_id=407">'
    #'<code><font size="6"><b>Software Wars Free Download</b></font></code></a>'
    )
    WELCOME_HTML = ('<font size="4">(Refreshes hourly -- See also <b><a target="_blank" href = '
    '"http://covidreport.net/">CovidReport</a></b>) - Fork me on <a target="_blank"'
    'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
    'href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a></font>')
else:
    feedparser.USER_AGENT = "Covid-19 Report -- http://covidreport.net/"
    site_urls = SITE_URLS_CR
    URL_IMAGES = "http://covidreport.net/static/images/"
    FAVICON = "http://covidreport.net/static/images/covidreport192.ico"
    LOGO_URL = "http://covidreport.net/static/images/CovidReport.png"
    WEB_DESCRIPTION = "COVID-19 and SARS-COV-2 news"
    WEB_TITLE = "COVID-19 Report"
    ABOVE_HTML = (''
         #'<a target="_blank" href = "https://github.com/KeithCu/LinuxReport">'
     #'<code><font size="6"><b>Help Me Update Headlines -- Just requires changing HTML in a text file...</b></font></code></a>'
        #'<a target = "_blank" href = "http://covidreport.net/static/covidactivities.html"><img width = "500" src = "http://covidreport.net/static/images/Exercise.jpg"/></a><br/>'
          #'<a target = "_blank" href = "https://archive.is/8SYhJ"><img width = "500" src = "http://covidreport.net/static/images/USSTeddyRoosevelt.jpg"/></a><br/>'
     #'<iframe width="385" height="216" src="https://www.youtube.com/embed/6EQXhViMBdg" frameborder="0" allow="accelerometer; '
     #'autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe><br/>'
    #'<a target="_blank" href = "https://keithcu.com/wordpress/?page_id=407">'
    # '<code><font size="6"><b>Software Wars Free Download</b></font></code></a>'
     #'<br/><hr/><a target="_blank" href = "https://journals.plos.org/plospathogens/article?id=10.1371/journal.ppat.1001176">'
     #'<code><font size="9"><b>And In-Vitro Studies Showing how it Enables Zinc to Stop Viral Replication</b></font></code></a>'

     '<a target="_blank" href = "https://youtu.be/3ywj-PZTt4g?t=355">'
     '<code><font size="9"><b>Quercetin, a Plant Pigment Supplement + Zinc Stop COVID-19</b></font></code></a>'
     '<br/><hr/><a target="_blank" href = "https://twitter.com/__ice9/status/1281013400752009216">'
     '<code><font size="9"><b>Quercetin Phytosome, Liposomal Quercetin, Isoquercetin, or EMIQ (Modified Isoquercetin) Needed for High Plasma Levels</b></font></code></a>'
     '<br/><hr/><a target="_blank" href = "https://www.youtube.com/watch?v=F-pwPIXCXX8">'
     '<code><font size="9"><b>1st Covid-19 Whistleblower - Li-Meng Yan from Hong Kong</b></font></code></a>'
    )

    # '<video controls preload="metadata" src="http://covidreport.net/static/images/Humany.mp4" autostart="false"'
    # 'width="385" height = "216" </video><a href = "https://www.youtube.com/channel/UCx_JS-Fzrq-bXUYP0mk9Zag/videos">src</a>')

    WELCOME_HTML = ('<font size="4">(Refreshes hourly -- See also <b><a target="_blank" '
    'href = "http://linuxreport.net/">LinuxReport</a></b>) - Fork me on '
    '<a target="_blank" href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or'
    ' <a target="_blank" href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a><br/></font>')
#    '<font size = "5"><i><a target = "_blank" href = "https://ncov2019.live/">ncov2019.live</a></i></font>')

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

# Alternate backend using memcached. It is 2x slower without the page cache, and 15% slower with,
# so don't bother for now.
class MEMCache():
    def __init__(self):
        self._cache = Cache(g_app, config={'CACHE_TYPE': 'memcached', })

    def normalize_url(url):
        if len(url) > 250:
            url = hash(url)
        return url

    def put(self, url, template, timeout):
        url = normalize_url(url)
        self._cache.set(url, template, timeout)

    def has(self, url):
        url = normalize_url(url)
        return self._cache.cache.has(url)

    def has(self, url):
        url = normalize_url(url)
        return self._cache.get(url) is not None

    def get(self, url):
        url = normalize_url(url)
        return self._cache.get(url)

    def delete(self, url):
        url = normalize_url(url)
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
            entry_set = set(entry.title.split())

            for entry_alt in feed_alt.entries:
                entry_alt_set = set(entry_alt.title.split())
                c = entry_set.intersection(entry_alt_set)
                dist = float(len(c)) / (len(entry_set) + len(entry_alt_set) - len(c))
#                dist = jellyfish.jaro_winkler(entry.title, entry_alt.title)
                if dist > 0.20:
                    print ("Similar title: 1: %s, 2: %s, diff: %s." %(entry.title, entry_alt.title, str(dist)))
                    try: #Entry could have been removed by another similar title
                        entries.remove(entry)
                    except:
                        pass
                    else:
                        print ("Deleted title.")

    return entries



def load_url_worker(url):
    rss_info = ALL_URLS[url]

    expire_time = rss_info.expire_time

    #This FETCHPID logic is to prevent race conditions of
    #multiple Python processes fetching an expired RSS feed.
    #This isn't as useful anymore given the FETCHMODE.
    if not g_c.has(url + "FETCHPID"):
        g_c.put(url + "FETCHPID", os.getpid(), timeout=10)
        feedpid = g_c.get(url + "FETCHPID") #Check to make sure it's us

    if feedpid == os.getpid():
        start = timer()

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

        entries = list(itertools.islice(entries, 8))

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
    #If any other process is fetching feeds, then we should just wait a bit.
    #This prevents a thundering herd of threads.
    if g_c.has("FETCHMODE"):
        print("Waiting on another process to finish fetching.")
        while g_c.has("FETCHMODE"):
            time.sleep(0.1)
        print("Done waiting.")

    g_c.put("FETCHMODE", "FETCHMODE", timeout=10)

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

    above_html = ABOVE_HTML
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
