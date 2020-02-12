import feedparser
import random
import json
import itertools
from random import shuffle
from bs4 import BeautifulSoup
import urllib3
import shutil
# import html
import os
import time
import socket
from timeit import default_timer as timer
import concurrent.futures

from flask_mobility import Mobility
from flask import Flask, render_template, Markup, request
from flask_caching import Cache
from wtforms import Form, BooleanField, FormField, FieldList, StringField, IntegerField, validators, SelectField

http = urllib3.PoolManager()

g_app = Flask(__name__)
Mobility(g_app)
application = g_app

EXPIRE_MINUTES = 60 * 5

if g_app.debug == True:
    EXPIRE_MINUTES = 1
    print ("Warning, in debug mode")

EXPIRE_HOURS = 3600
EXPIRE_DAY = 3600 * 6
EXPIRE_DAYS = 86400 * 10
EXPIRE_YEARS = 60 * 60 * 24 * 365 * 2

g_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = EXPIRE_DAYS

URL_IMAGES = "http://linuxreport.net/static/images/"

site_urls = {
              "https://www.reddit.com/r/Coronavirus/rising/.rss" :
             [URL_IMAGES + "Coronavirus.jpg",
              "https://www.reddit.com/r/Coronavirus/",
              EXPIRE_HOURS],

             "http://lxer.com/module/newswire/headlines.rss" :
             [URL_IMAGES + "lxer.png",
              "http://lxer.com/",
              EXPIRE_HOURS],
    
              "http://www.reddit.com/r/linux/.rss" : 
             [URL_IMAGES + "redditlogosmall.png",
              "https://www.reddit.com/r/linux",
              EXPIRE_HOURS],

              "http://rss.slashdot.org/Slashdot/slashdotMain" : 
             [URL_IMAGES + "slashdotlogo.png",
              "https://slashdot.org/",
              EXPIRE_HOURS],

              "http://lwn.net/headlines/newrss" :
             [URL_IMAGES + "barepenguin-70.png",
              "https://lwn.net/",
              EXPIRE_DAY],

              "http://news.ycombinator.com/rss" :
             [URL_IMAGES + "hackernews.jpg",
              "http://news.ycombinator.com/",
              EXPIRE_HOURS],

              "http://www.osnews.com/feed/" :
             [URL_IMAGES + "osnews-logo.png",
              "http://www.osnews.com/",
              EXPIRE_HOURS],

              "http://www.geekwire.com/feed/" :
             [URL_IMAGES + "GeekWire.png",
              "http://www.geekwire.com/",
              EXPIRE_HOURS],

               "http://feeds.feedburner.com/linuxtoday/linux" :
             [URL_IMAGES + "linuxtd_logo.png",
              "http://www.linuxtoday.com/",
              EXPIRE_HOURS],

               "http://planet.debian.org/rss20.xml" :
             [URL_IMAGES + "Debian-OpenLogo.svg",
              "http://planet.debian.org/",
              EXPIRE_HOURS],

               "http://www.independent.co.uk/topic/coronavirus/rss" :
             [URL_IMAGES + "Independent-Corona.png",
              "https://www.independent.co.uk/topic/coronavirus",
              EXPIRE_HOURS],

               "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984" :
             [URL_IMAGES + "Google-News.png",
              "https://news.google.com/search?q=coronavirus",
              EXPIRE_HOURS],

            }

 
class HelloCache(object):
    def __init__(self):
        global g_app
        self._cache = Cache(g_app, config={'CACHE_TYPE': 'filesystem', 'CACHE_DIR' : '/tmp/linuxreport/', 'CACHE_DEFAULT_TIMEOUT' : EXPIRE_DAY })

    def Put(self, url, template, timeout = None):
        self._cache.set(url, template, timeout)
        
    def Get(self, url):
        template = self._cache.get(url)
        return template

    def Del(self, url):
        self._cache.delete(url)

#First try to grab image from cache
# image_name = g_c.Get(rssurl + ":" + "IMAGE")
# if image_name is None:
#     image_name = GrabImage(feedinfo)
#     if image_name is not None:
#         g_c.Put(rssurl + ":" + "IMAGE", image_name, timeout = EXPIRE_DAYS)
#         print (image_name)

def GrabImageTest(feedinfo):

    #Search for first image in first article of feed:
    feed = feedinfo[0]
    url = feed.link

    #url = "http://keithcu.com/wordpress/?p=3847"

    http_response = g_c.Get(url)

    #Try to grab the mobile page since it is easier to find the correct first image
    if http_response is None:
        headers_mobile = { 'User-Agent' : 'Mozilla/5.0 (iPhone; CPU iPhone OS 9_1 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13B137 Safari/601.1'}
        http_response = http.request("Get", url, headers=headers_mobile).data
        g_c.Put(url, http_response, timeout = EXPIRE_DAYS)

    soup = BeautifulSoup(http_response, features = "lxml")
    img = None
    for img in soup.findAll('img'):
        if 'gravatar' in img.attrs['src'] or 'themes' in img.attrs['src'] or 'qsstats' in img.attrs['src']:
            continue
        else:
            print (img)
            break

    #Can't find an image, so give up
    if img is None:
        return None

    img_url = img.attrs['src']

    names = img_url.split("/")
    print (names[-1])

    try:
        response = http.request("Get", img_url)
        filename = "/srv/http/images/" + names[-1]
        f = open(filename, "wb+")
        shutil.copyfileobj(response, f)
    except:
        return None

    return "http://keithcu.com/images/" + names[-1]


g_c = None
g_standard_order = list(site_urls.keys())
g_standard_order_s = str(g_standard_order)

def load_url_worker(url):
    site_info = site_urls.get(url, None)

    if site_info is None:
        site_info = [URL_IMAGES + "Custom.png", url + "HTML", EXPIRE_HOURS]
        site_urls[url] = site_info

    logo_url, site_url, expire_time = site_info

    #This FETCHPID logic is to prevent race conditions of
    #multiple Python processes fetching an expired RSS feed.
    feedpid = g_c.Get(url + "FETCHPID")
    if feedpid is None:
        g_c.Put(url + "FETCHPID", os.getpid())
        feedpid = g_c.Get(url + "FETCHPID") #Check to make sure it's us

    if feedpid == os.getpid():
        start = timer()
        res = feedparser.parse(url)
        feedinfo = list(itertools.islice(res['entries'], 8))
        g_c.Put(url, feedinfo, timeout = expire_time)
        g_c.Del(url + "FETCHPID")
        end = timer()
        print ("Parsing from remote site %s in %f." %(url, end - start))
    else:
        print ("Waiting for someone else to parse remote site %s" %(url))

        # Someone else is fetching, so wait
        while feedpid is not None:
            time.sleep(0.1)
            feedpid = g_c.Get(url + "FETCHPID")

        print ("Done waiting for someone else to parse remote site %s" %(url))

def FetchUrlsParallel(urls):

    with concurrent.futures.ThreadPoolExecutor(max_workers = 10) as executor:
        future_to_url = {executor.submit(load_url_worker, url): url for url in urls}

        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            future.result()

@g_app.route('/')
def index():

    global g_c
    global g_app
    global g_standard_order
    global g_standard_order_s

    if g_c is None:
        socket.setdefaulttimeout(5)
        g_c = HelloCache()

    if request.cookies.get('DarkMode') is None:
        dark_mode = False
    else:
        dark_mode = True

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

    full_page = g_c.Get(page_order_s + suffix)
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
            site_info = [URL_IMAGES + "Custom.png", url + "HTML", EXPIRE_HOURS]
            site_urls[url] = site_info

        logo_url, site_url, expire_time = site_info

        #First check for the templatized content stored with site URL
        template = g_c.Get(site_url)

        #If we don't have the template, the feed has likely expired
        if template is None:
            needed_urls.append(url)
        else:
            result_1[url] = template

    # Asynchronously fetch all the needed URLs
    if len(needed_urls) > 0:
        start = timer()
        FetchUrlsParallel(needed_urls)
        end = timer()
        print ("Fetched all feeds in %f sec." % (end - start))

    #2. Now we've got all the data, go through again to build the page
    for url in page_order:
        site_info = site_urls[url]
        logo_url, site_url, expire_time = site_info

        #First check to see if we already have this result
        template = result_1.get(url, None)
        if template is None:

            #If not, feed should be in the RSS cache by now
            feedinfo = g_c.Get(url)

            jitter = random.randint(0, 60 * 15)
            template = render_template('sitebox.html', entries = feedinfo, logo = logo_url, link = site_url)
            g_c.Put(site_url, template, timeout = expire_time + jitter + 10)

        result[cur_col].append(template)

        if single_column == False:
            cur_col += 1
            cur_col %= 3

    result[0] = Markup(''.join(result[0]))

    if single_column == False:
        result[1] = Markup(''.join(result[1]))
        result[2] = Markup(''.join(result[2]))

    if dark_mode:
        back_color = '#1e1e1e'
        text_color = '#d4d4d4'
    else:
        back_color = '#f6f5f4'
        text_color = 'black'

    page = render_template('page.html', columns = result, text_color = text_color, back_color = back_color)

    # Only cache standard order
    if page_order_s == g_standard_order_s:
        g_c.Put(page_order_s + suffix, page, timeout = EXPIRE_MINUTES)
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
    delete_cookie = BooleanField(label = "Delete Cookie")
    dark_mode = BooleanField(label = "Dark Mode")
    urls = FieldList(FormField(UrlForm))
    url_custom = FieldList(FormField(CustomRSSForm))


@g_app.route('/config', methods=['GET', 'POST'])
def Config():
    if request.method == 'GET':
        form = ConfigForm()
        dark_mode = request.cookies.get('DarkMode')
        if dark_mode:
            form.dark_mode.data  = True

        page_order = request.cookies.get('RssUrls')
        if page_order is not None:
            page_order = json.loads(page_order)
        else:
            page_order = list(site_urls.keys())

        custom_count = 0
        for i, p_url in enumerate(page_order):
            site_info = site_urls.get(p_url, None)
            if site_info is not None and site_info[0] != URL_IMAGES + "Custom.png":
                urlf = UrlForm()
                urlf.pri = (i + 1) * 10
                urlf.url = p_url
                form.urls.append_entry(urlf)
            else:
                custom_count += 1
                rssf =  CustomRSSForm()
                rssf.url = p_url
                rssf.pri = (i + 1) * 10
                form.url_custom.append_entry(rssf)

        for i in range (custom_count, 5):
            rssf =  CustomRSSForm()
            rssf.url = "http://"
            rssf.pri = (i + 30) * 10
            form.url_custom.append_entry(rssf)

        page = render_template('config.html', form = form)
        return page
    else: #request == 'POST':
        form = ConfigForm(request.form)
        if form.delete_cookie.data:
            resp = g_app.make_response("<HTML><BODY>Deleted cookie.</BODY></HTML>")        
            resp.delete_cookie('RssUrls')
            resp.delete_cookie('DarkMode')
            return resp

        page_order = []

        urls = list(form.urls)

        url_custom = list(form.url_custom)
        for site in url_custom:
            if site.url.data != "http://":
                urls.append(site)

        urls.sort(key = lambda x: x.pri.data)

        for urlf in urls:
            if isinstance(urlf.form, UrlForm):
                page_order.append(urlf.url.data)
            elif isinstance(urlf.form, CustomRSSForm):
                page_order.append(urlf.url.data)
        
        #Pickle this stuff to a string to send as a cookie
        cookie_str = json.dumps(page_order)
        resp = g_app.make_response("<HTML><BODY>Saved cookie for later.</BODY></HTML>")        
        resp.set_cookie('RssUrls', cookie_str, max_age = EXPIRE_YEARS)
        if form.dark_mode.data:
            resp.set_cookie('DarkMode', "1", max_age = EXPIRE_YEARS)
        else:
            resp.delete_cookie('DarkMode')
        return resp
