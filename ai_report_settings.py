from shared import RssInfo, EXPIRE_HOUR, EXPIRE_DAY

ALL_URLS = {
    "https://www.reddit.com/r/LocalLlama/.rss" :
    RssInfo("LocalLlama.png",
    "Machine Learning sub",
    "https://www.reddit.com/r/LocalLlama/"),

    "https://venturebeat.com/category/ai/feed/" :
    RssInfo("VentureBeat_logo.png",
    "VentureBeat AI",
    "https://venturebeat.com/category/ai/"),

    "https://www.theregister.com/software/ai_ml/headlines.atom" :
    RssInfo("RegisterLogo.png",
    "The Register AI News",
    "https://www.theregister.com/software/ai_ml/"),

    "https://hnrss.org/newest?tags=ai" :
    RssInfo("hackernews.webp",
    "YCombinator",
    "https://news.ycombinator.com/"),

    "https://www.reddit.com/r/Python/.rss" :
    RssInfo("redditlogosmall.webp",
    "Reddit Python",
    "https://www.reddit.com/r/Python/"),

    "https://planetpython.org/rss20.xml" :
    RssInfo("Python-logo-notext.svg",
    "Planet Python",
    "https://planetpython.org/"),

    "https://www.reddit.com/r/Grok/.rss" :
    RssInfo("Grok.gif",
    "Reddit Grok",
    "https://www.reddit.com/r/Grok/"),

}

USER_AGENT = "AI Report -- https://aireport.keithcu.com"
site_urls = [
    "https://www.reddit.com/r/LocalLlama/.rss",
    "https://www.reddit.com/r/Grok/.rss",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.theregister.com/software/ai_ml/headlines.atom",
    "https://hnrss.org/newest?tags=ai",
    "https://www.reddit.com/r/Python/.rss",
    "https://planetpython.org/rss20.xml",
]

DOMAIN = "https://aireport.keithcu.com"
URL_IMAGES = DOMAIN + "/static/images/"
FAVICON = URL_IMAGES + "covidreport192.ico"
LOGO_URL = URL_IMAGES + "aireportfancy.webp"
WEB_DESCRIPTION = "AI News"
WEB_TITLE = "AI Report"

ABOVE_HTML_FILE = 'covidreportabove.html'

WELCOME_HTML = ('<font size="4">(Refreshes hourly -- See also <b><a target="_blank" href = '
'"https://linuxreport.net/">LinuxReport</a></b>) - Fork me on <a target="_blank"'
'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
'href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a></font>')
