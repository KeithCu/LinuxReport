from shared import RssInfo

CONFIG = {
    "ALL_URLS": {
        "https://revolver.news/fakefeed": RssInfo("revolvernews.png", "Revolver News", "https://revolver.news"),
        "https://justthenews.com/rss.xml": RssInfo("justthenewslogo.svg", "Just The News", "https://justthenews.com"),
        "https://citizenfreepress.com/feed/": RssInfo("citizenfreepress.webp", "Citizen Free Press", "https://citizenfreepress.com"),
        "https://patriots.win/fakefeed": RssInfo("patriotswin.webp", "Patriots.win", "https://patriots.win"),
        "https://thefederalist.com/feed/": RssInfo("federalist.webp", "The Federalist", "https://thefederalist.com"),
        "http://bonginoreport.com/index.rss": RssInfo("bonginoreport.png", "Bongino Report", "https://bonginoreport.com"),
        "https://freebeacon.com/feed/": RssInfo("freebeacon.png", "Free Beacon", "https://freebeacon.com"),
        "https://feeds.feedburner.com/breitbart": RssInfo("breitbart.webp", "Breitbart", "https://breitbart.com"),
        "https://nypost.com/politics/feed/": RssInfo("nypost.webp", "New York Post Politics Section", "https://nypost.com/politics/"),
        "https://www.washingtonexaminer.com/feed/": RssInfo("washingtonexaminer.webp", "Washington Examiner", "https://washingtonexaminer.com"),
        "https://conservativereview.com/feeds/feed.rss": RssInfo("conservativereview.webp", "Conservative Review", "https://conservativereview.com"),
        "https://townhall.com/feed/": RssInfo("logo-townhall.svg", "Townhall", "https://townhall.com"),
    },
    "USER_AGENT": "Trump Report -- https://trumpreport.info",
    "site_urls": [
        "https://feeds.feedburner.com/breitbart",
        "https://patriots.win/fakefeed",
        "https://revolver.news/fakefeed",
        "https://nypost.com/politics/feed/",
        "https://justthenews.com/rss.xml",
        "https://thefederalist.com/feed/",
        "https://freebeacon.com/feed/",
        "https://townhall.com/feed/",
        "https://citizenfreepress.com/feed/",
        "http://bonginoreport.com/index.rss",
        "https://www.washingtonexaminer.com/feed/",
        "https://conservativereview.com/feeds/feed.rss",
    ],
    "domain": "https://trumpreport.info",
    "URL_IMAGES": "https://trumpreport.info/static/images/",
    "FAVICON": "https://trumpreport.info/static/images/TrumpReport.webp",
    "LOGO_URL": "https://trumpreport.info/static/images/TrumpReport.webp",
    "WEB_DESCRIPTION": "Trump Report",
    "WEB_TITLE": "TrumpReport",
    "ABOVE_HTML_FILE": "/srv/http/trumpreport/trumpreportabove.html",
    "WELCOME_HTML": ('<font size="4">(Displays instantly, refreshes hourly -- See also <b><a target="_blank" href = '
                     '"https://linuxreport.net/">LinuxReport</a></b> or <b><a target="_blank" href = '
                     '"https://aireport.keithcu.com">AI Report</a></b>) - Fork me on <a target="_blank"'
                     'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
                     'href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a><br/><b>Note:</b> You can turn off underlines and courier in the Config dialog. Enjoy! -<a target="_blank" href = "https://keithcu.com/wordpress/?page_id=407/">Keith</a>. </font>')
}
