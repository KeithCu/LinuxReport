from models import RssInfo, SiteConfig
CONFIG: SiteConfig = SiteConfig(
    ALL_URLS = {
        "http://detroiteq.com/feed": RssInfo("deq.png", "Detroit Electronic Quarterly", "http://detroiteq.com/"),
        "https://www.google.com/alerts/feeds/12151242449143161443/18325972585468687530": RssInfo("Google-NewsTechno.png", "Google Detroit Techno news", "https://news.google.com/search?q=detroit techno"),
        "https://rocksteadydisco.bandcamp.com/fakefeed": RssInfo("RockSteadyDisco.png", "RockSteady Disco", "https://rocksteadydisco.bandcamp.com"),
        "https://transmatdetroit.bandcamp.com/fakefeed": RssInfo("Transmat.png", "Transmat", "https://transmatdetroit.bandcamp.com"),
        "https://pitsdetroit.bandcamp.com/fakefeed": RssInfo("pits.png", "Place In Time And Space", "https://pitsdetroit.bandcamp.com/"),
        "https://planetecommunications.bandcamp.com/fakefeed": RssInfo("planete.png", "Planet-E Communications", "https://planetecommunications.bandcamp.com"),
        "https://womenonwax.com/feed/": RssInfo("womenonwax.png", "Women On Wax", "https://womenonwax.com"),
    },
    USER_AGENT = "The Detroit Techno Report -- http://news.thedetroitilove.com/",
    site_urls = [
        "http://detroiteq.com/feed",
        "https://www.google.com/alerts/feeds/12151242449143161443/18325972585468687530",
        "https://rocksteadydisco.bandcamp.com/fakefeed",
        "https://womenonwax.com/feed/",
        "https://transmatdetroit.bandcamp.com/fakefeed",
        "https://planetecommunications.bandcamp.com/fakefeed",
        "https://pitsdetroit.bandcamp.com/fakefeed",
    ],
    URL_IMAGES = "http://news.thedetroitilove.com/static/images/",
    FAVICON = "http://news.thedetroitilove.com/static/images/technoreport.ico",
    LOGO_URL = "http://news.thedetroitilove.com/static/images/TechnoReport.png",
    WEB_DESCRIPTION = "Detroit Techno, Arts and Events News",
    WEB_TITLE = "The Detroit Techno Report",
    ABOVE_HTML_FILE = "/srv/http/flask/technoreportabove.html",

    CUSTOM_FETCH_CONFIG={
        "bandcamp.com": {
            "needs_selenium": True,
            "needs_tor": False,
            "post_container": ".music-grid-item",
            "title_selector": ".title",
            "link_selector": "a",
            "link_attr": "href",
            "published_selector": None,
            "filter_pattern": None
        },
    }
)
