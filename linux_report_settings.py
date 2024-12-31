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
    EXPIRE_DAY * 8),

    "https://www.reddit.com/r/linux/rising/.rss" :
    RssInfo("redditlogosmall.png",
    "Reddit Linux sub",
    "https://www.reddit.com/r/linux",
    EXPIRE_DAY * 8),

    "http://rss.slashdot.org/Slashdot/slashdotMain" :
    RssInfo("slashdotlogo.png",
    "Slashdot",
    "https://slashdot.org/",
    EXPIRE_DAY * 8),

    "https://lwn.net/headlines/newrss" :
    RssInfo("barepenguin-70.png",
    "LWN.net news",
    "https://lwn.net/",
    EXPIRE_DAY * 8),

    "https://news.ycombinator.com/rss" :
    RssInfo("hackernews.jpg",
    "Ycombinator news",
    "http://news.ycombinator.com/",
    EXPIRE_DAY * 8),

    "https://www.osnews.com/feed/" :
    RssInfo("osnews-logo.png",
    "OS News.com",
    "http://www.osnews.com/",
    EXPIRE_DAY * 8),

    "https://www.geekwire.com/feed/" :
    RssInfo("GeekWire.png",
    "GeekWire",
    "http://www.geekwire.com/",
    EXPIRE_DAY * 8), #Slow and slow-changing, so fetch less

    "http://feeds.feedburner.com/linuxtoday/linux" :
    RssInfo("linuxtd_logo.png",
    "Linux Today",
    "http://www.linuxtoday.com/",
    EXPIRE_DAY * 8),

    "https://planet.debian.org/rss20.xml" :
    RssInfo("Debian-OpenLogo.svg",
    "Planet Debian",
    "http://planet.debian.org/",
    EXPIRE_DAY * 8),

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

    "https://pandemic.warroom.org/feed/" :
    RssInfo("WarRoom.png",
    "War Room: Pandemic",
    "https://pandemic.warroom.org/",
    EXPIRE_HOUR * 3),
}

feedparser.USER_AGENT = "Linux Report -- http://linuxreport.net/"
site_urls = [
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

URL_IMAGES = "http://linuxreport.net/static/images/"
FAVICON = "http://linuxreport.net/static/images/linuxreport192.ico"
LOGO_URL = "http://linuxreport.net/static/images/LinuxReport2.png"
WEB_TITLE = "Linux Report"
WEB_DESCRIPTION = "Linux News"
ABOVE_HTML = ''
WELCOME_HTML = ('<font size="4">(Refreshes hourly -- See also <b><a target="_blank" href = '
'"http://covidreport.keithcu.com/">CovidReport</a></b>) - Fork me on <a target="_blank"'
'href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or <a target="_blank"'
'href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a></font>')
