from models import RssInfo, SiteConfig

CONFIG: SiteConfig = SiteConfig(
    ALL_URLS={
        "https://www.pv-tech.org/feed": RssInfo("pv-tech-logo.webp", "PV Tech", "https://www.pv-tech.org"),
        "https://www.solarpowerworldonline.com/feed/": RssInfo("solarpowerworld.svg", "Solar power World Online", "https://www.solarpowerworldonline.com"),
        "https://www.pv-magazine.com/feed/": RssInfo("pv-magazine-logo.png", "PV Magazine", "https://www.pv-magazine.com"),
       # "https://solartribune.com/fakefeed": RssInfo("solartribune.webp", "Solar Tribune", "https://solartribune.com"),
        "https://solarmagazine.com/fakefeed": RssInfo("solar-magazine-logo.webp", "Solar Magazine", "https://solarmagazine.com"),
        "https://cleantechnica.com/feed/": RssInfo("cleantechnica-logo.webp", "Clean Technica", "https://cleantechnica.com"),
        "https://www.renewableenergyworld.com/feed": RssInfo("renewableenergyworld-logo.svg", "Renewable Energy World", "https://www.renewableenergyworld.com"),
        "https://ases.org/feed/": RssInfo("ases-logo.svg", "American Solar Energy Society", "https://ases.org"),
        "https://www.altenergymag.com/rss/news/": RssInfo("altenergymag.webp", "Alternative Energy Magazine", "https://www.altenergymag.com"),
    },
    USER_AGENT="Solar Report -- https://pvreport.org",
    SITE_URLS=[
        "https://www.pv-magazine.com/feed/",
        "https://www.pv-tech.org/feed",
        "https://cleantechnica.com/feed/",
        "https://www.solarpowerworldonline.com/feed/",
        "https://www.altenergymag.com/rss/news/",
        "https://www.renewableenergyworld.com/feed",
        "https://solarmagazine.com/fakefeed",
        "https://ases.org/feed/",
    ],
    URL_IMAGES="https://pvreport.org/static/images/",
    FAVICON="pvreport.ico",
    LOGO_URL="pvreport.webp",
    WEB_DESCRIPTION="Solar and Renewable Energy News",
    WEB_TITLE="Photovoltaic Report",
    REPORT_PROMPT="Solar energy industry professionals and enthusiasts. Focus on major solar and battery technology, policy, and market news. Avoid basic installation guides, generic green energy content, or unrelated renewables.",
    PATH="/srv/http/pvreport",
    SCHEDULE=[1, 7, 13, 19],
    CUSTOM_FETCH_CONFIG={
        "solarmagazine.com": {
            "needs_selenium": False,
            "needs_tor": False,
            "post_container": "h3",
            "title_selector": "a",
            "link_selector": "a",
            "link_attr": "href",
            "published_selector": None,
            "filter_pattern": ""
        },
    },
)
