from shared import RssInfo

CONFIG = {
    "ALL_URLS": {
        "https://www.reddit.com/r/Coronavirus/rising/.rss": RssInfo("redditlogosmall.webp", "Reddit Corona virus sub", "https://www.reddit.com/r/Coronavirus/"),
        "https://www.reddit.com/r/COVID19/.rss": RssInfo("Coronavirus.jpg", "Reddit Covid-19 sub", "https://www.reddit.com/r/COVID19/"),
        "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984": RssInfo("Google-News.png", "Google Coronavirus news", "https://news.google.com/search?q=coronavirus"),
        "https://tools.cdc.gov/api/v2/resources/media/404952.rss": RssInfo("CDC-Logo.png", "Centers for Disease Control", "https://www.cdc.gov/coronavirus/2019-nCoV/index.html"),
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCD2-QVBQi48RRQTD4Jhxu8w": RssInfo("PeakProsperity.png", "Chris Martenson Peak Prosperity", "https://www.youtube.com/user/ChrisMartensondotcom/videos"),
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCF9IOB2TExg3QIBupFtBDxg": RssInfo("JohnCampbell.png", "Dr. John Campbell", "https://www.youtube.com/user/Campbellteaching/videos"),
    },
    "USER_AGENT": "Covid-19 Report -- https://covidreport.org/",
    "site_urls": [
        "https://www.reddit.com/r/Coronavirus/rising/.rss",
        "https://www.reddit.com/r/COVID19/.rss",
        "https://www.google.com/alerts/feeds/12151242449143161443/16985802477674969984",
        "https://tools.cdc.gov/api/v2/resources/media/404952.rss",
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCD2-QVBQi48RRQTD4Jhxu8w",
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCF9IOB2TExg3QIBupFtBDxg",
    ],
    "domain": "https://covidreport.org",
    "URL_IMAGES": "https://covidreport.org/static/images/",
    "FAVICON": "https://covidreport.org/static/images/covidreport192.ico",
    "LOGO_URL": "https://covidreport.org/static/images/covidreportfancy.webp",
    "WEB_DESCRIPTION": "COVID-19 and Infectious Disease News",
    "WEB_TITLE": "COVID-19 Report",
    "ABOVE_HTML_FILE": "/srv/http/CovidReport2/covidreportabove.html",
}
