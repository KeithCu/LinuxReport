from shared import RssInfo, EXPIRE_HOUR, EXPIRE_DAY

ALL_URLS = {
    "https://revolver.news/feed" :
    RssInfo("revolvernews.png",
    "Revolver News",
    "https://revolver.news/",
    EXPIRE_DAY),

    "https://justthenews.com/rss.xml" :
    RssInfo("justthenewslogo.svg",
    "Just The News",
    "https://justthenews.com/",
    EXPIRE_DAY),

    "https://citizenfreepress.com/feed/" :
    RssInfo("citizenfreepress.webp",
    "Citizen Free Press",
    "https://citizenfreepress.com",
    EXPIRE_DAY),

    "https://patriots.win/fakefeed" : #No RSS feed, custom parser will handle
    RssInfo("patriotswin.webp",
    "Patriots.win",
    "https://patriots.win",
    EXPIRE_HOUR * 6),

    "https://thefederalist.com/feed/" :
    RssInfo("federalist.webp",
    "The Federalist",
    "https://thefederalist.com/",
    EXPIRE_DAY),

    "http://bonginoreport.com/index.rss" :
    RssInfo("bonginoreport.png",
    "Bongino Report",
    "https://bonginoreport.com",
    EXPIRE_DAY),

    "https://freebeacon.com/feed/" :
    RssInfo("freebeacon.png",
    "Free Beacon",
    "https://freebeacon.com",
    EXPIRE_HOUR * 4),

    "https://feeds.feedburner.com/breitbart" :
    RssInfo("breitbart.webp",
    "Breitbart",
    "https://breitbart.com",
    EXPIRE_HOUR * 4),

    "https://nypost.com/feed/" :
    RssInfo("nypost.webp",
    "New York Post",
    "https://nypost.com",
    EXPIRE_HOUR * 4),

    "https://www.washingtonexaminer.com/feed/" :
    RssInfo("washingtonexaminer.webp",
    "Washington Examiner",
    "https://washingtonexaminer.com",
    EXPIRE_HOUR * 6),


    "https://conservativereview.com/feeds/feed.rss" :
    RssInfo("conservativereview.webp",
    "Conservative Review",
    "https://conservativereview.com",
    EXPIRE_DAY),

}

USER_AGENT = "AI Report -- https://trumpreport.info"

#This specifies the order of the sites in the report, derived from ALL_URLS keys.
site_urls = [
    "https://feeds.feedburner.com/breitbart",
    "https://patriots.win/fakefeed",
    "https://revolver.news/feed",
    "https://justthenews.com/rss.xml",
    "https://thefederalist.com/feed/",
    "https://freebeacon.com/feed/",
    "https://citizenfreepress.com/feed/",
    "http://bonginoreport.com/index.rss",
    "https://nypost.com/feed/",
    "https://www.washingtonexaminer.com/feed/",
    "https://conservativereview.com/feeds/feed.rss",
]

domain = "http://trumpreport.info"


URL_IMAGES = domain + "/static/images/"
FAVICON = domain + "/static/images/TrumpReport.webp"
LOGO_URL = domain + "/static/images/TrumpReport.webp"
WEB_DESCRIPTION = "Trump Report"
WEB_TITLE = "TrumpReport"

ABOVE_HTML_FILE = 'trumpreportabove.html'

WELCOME_HTML = ('<font size="4">(Refreshes hourly -- See also <b><a target="_blank" href = '
'"https://linuxreport.net/">LinuxReport</a></b> or <b><a target="_blank" href = '
'"https://aireport.keithcu.com">AI Report</a></b>) - Fork me on <a target="_blank"'
'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
'href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a></font>')
