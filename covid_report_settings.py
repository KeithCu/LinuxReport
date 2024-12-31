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

    "https://pandemic.warroom.org/feed/" :
    RssInfo("WarRoom.png",
    "War Room: Pandemic",
    "https://pandemic.warroom.org/",
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
}

feedparser.USER_AGENT = "Covid-19 Report -- http://covidreport.net/"
site_urls = [
    "https://www.reddit.com/r/Coronavirus/rising/.rss",
    "https://www.reddit.com/r/China_Flu/rising/.rss",
    "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984",
    "http://www.independent.co.uk/topic/coronavirus/rss",
    "https://pandemic.warroom.org/feed/",
    "https://gnews.org/feed/",
    "https://tools.cdc.gov/api/v2/resources/media/403372.rss",
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCD2-QVBQi48RRQTD4Jhxu8w",
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCF9IOB2TExg3QIBupFtBDxg",
]

URL_IMAGES = "http://covidreport.keithcu.com/static/images/"
FAVICON = "http://covidreport.keithcu.com//static/images/covidreport192.ico"
LOGO_URL = "http://covidreport.keithcu.com/static/images/CovidReport.png"
WEB_DESCRIPTION = "COVID-19 and SARS-COV-2 news"
WEB_TITLE = "COVID-19 Report"

ABOVE_HTML = ''
WELCOME_HTML = ('<font size="4">(Refreshes hourly) - Fork me on '
'<a target="_blank" href = "https://github.com/KeithCu/LinuxReport">GitHub</a> or'
' <a target="_blank" href = "https://gitlab.com/keithcu/linuxreport">GitLab.</a><br/></font>')
