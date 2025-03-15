from shared import RssInfo, EXPIRE_DAY

CONFIG = {
    "ALL_URLS": {
        "http://detroiteq.com/feed": RssInfo("deq.png", "Detroit Electronic Quarterly", "http://detroiteq.com/"),
        "https://www.google.com/alerts/feeds/12151242449143161443/18325972585468687530": RssInfo("Google-News.png", "Google Detroit Techno news", "https://news.google.com/search?q=detroit techno"),
        "https://keithcu.com/BandcampTestRS/": RssInfo("RockSteadyDisco.png", "RockSteady Disco", "https://rocksteadydisco.bandcamp.com/music"),
        "https://keithcu.com/BandcampTest2/": RssInfo("Transmat.png", "Transmat", "https://transmatdetroit.bandcamp.com/music"),
        "https://placeintimeandspace.com/feed/": RssInfo("pits.png", "Place In Time And Space", "https://placeintimeandspace.com/"),
        "https://keithcu.com/PlanetETest": RssInfo("planete.png", "Planet-E Communications", "https://planetecommunications.bandcamp.com/music"),
        "https://keithcu.com/SampledDetroitTest": RssInfo("SampledDetroit.png", "Sampled Detroit", "https://sampleddetroit.bandcamp.com/music"),
        "https://keithcu.com/WomenOnWaxTest/": RssInfo("womenonwax.png", "Women On Wax", "https://womenonwax.com/"),
    },
    "USER_AGENT": "The Detroit Techno Report -- http://news.thedetroitilove.com/",
    "site_urls": [
        "http://detroiteq.com/feed",
        "https://www.google.com/alerts/feeds/12151242449143161443/18325972585468687530",
        "https://keithcu.com/BandcampTestRS/",
        "https://keithcu.com/BandcampTest2/",
        "https://placeintimeandspace.com/feed/",
        "https://keithcu.com/PlanetETest",
        "https://keithcu.com/SampledDetroitTest",
        "https://keithcu.com/WomenOnWaxTest/",
    ],
    "MAX_ITEMS": 11,
    "URL_IMAGES": "http://news.thedetroitilove.com/static/images/",
    "FAVICON": "http://news.thedetroitilove.com/static/images/technoreport.ico",
    "LOGO_URL": "http://news.thedetroitilove.com/static/images/TechnoReport.png",
    "WEB_DESCRIPTION": "Detroit Techno, Arts and Events News",
    "WEB_TITLE": "The Detroit Report",
    "ABOVE_HTML_FILE": "/srv/http/flask/detroitreportabove.html",
    "WELCOME_HTML": ('<font size="4">(Refreshes Daily)</font>')
}
