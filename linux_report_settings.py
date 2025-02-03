from shared import RssInfo, EXPIRE_HOUR, EXPIRE_DAY

ALL_URLS = {

    "http://lxer.com/module/newswire/headlines.rss" :
    RssInfo("lxer.webp",
    "Lxer news",
    "http://lxer.com/",
    EXPIRE_HOUR),

    "https://www.reddit.com/r/linux/.rss" :
    RssInfo("redditlogosmall.webp",
    "Reddit Linux sub",
    "https://www.reddit.com/r/linux",
    EXPIRE_HOUR * 4),

    "http://rss.slashdot.org/Slashdot/slashdotMain" :
    RssInfo("slashdotlogo.webp",
    "Slashdot",
    "https://slashdot.org/",
    EXPIRE_HOUR * 2),

    "https://lwn.net/headlines/newrss" :
    RssInfo("barepenguin-70.webp",
    "LWN.net news",
    "https://lwn.net/",
    EXPIRE_DAY),

    "https://news.ycombinator.com/rss" :
    RssInfo("hackernews.webp",
    "Ycombinator news",
    "http://news.ycombinator.com/",
    EXPIRE_HOUR * 2),

    "https://www.osnews.com/feed/" :
    RssInfo("osnews-logo.webp",
    "OS News.com",
    "http://www.osnews.com/",
    EXPIRE_HOUR * 4),

    "https://www.geekwire.com/feed/" :
    RssInfo("GeekWire.png",
    "GeekWire",
    "http://www.geekwire.com/",
    EXPIRE_HOUR * 8), #Slow and slow-changing, so fetch less

    "http://feeds.feedburner.com/linuxtoday/linux" :
    RssInfo("linuxtd_logo.png",
    "Linux Today",
    "http://www.linuxtoday.com/",
    EXPIRE_DAY),

    "https://planet.debian.org/rss20.xml" :
    RssInfo("Debian-OpenLogo.svg",
    "Planet Debian",
    "http://planet.debian.org/",
    EXPIRE_HOUR * 4),
}

USER_AGENT = "Linux Report -- https://linuxreport.net/"
site_urls = [
    "http://lxer.com/module/newswire/headlines.rss",
    "https://www.reddit.com/r/linux/.rss",
    "http://rss.slashdot.org/Slashdot/slashdotMain",
    "https://lwn.net/headlines/newrss",
    "https://news.ycombinator.com/rss",
    "https://www.osnews.com/feed/",
    "https://www.geekwire.com/feed/",
    "http://feeds.feedburner.com/linuxtoday/linux",
    "https://planet.debian.org/rss20.xml",
]

URL_IMAGES = "https://linuxreport.net/static/images/"
FAVICON = "https://linuxreport.net/static/images/linuxreport192.ico"
LOGO_URL = "https://linuxreport.net/static/images/LinuxReport2.webp"
WEB_TITLE = "Linux Report"
WEB_DESCRIPTION = "Linux News"
ABOVE_HTML_FILE = 'linuxreportabove.html'
WELCOME_HTML = ('<font size="4">(Refreshes hourly -- See also <b><a target="_blank" href = '
'"https://covidreport.org/">CovidReport</a></b> or <b><a target="_blank" href = '
'"https://aireport.keithcu.com/">AI Report</a></b> ) - Fork me on <a target="_blank"'
'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
'href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a></font>')
