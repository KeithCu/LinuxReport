from models import RssInfo, SiteConfig
from app_config import FetchConfig

class SolarMagazineFetchConfig(FetchConfig):
    """
    Solar Magazine-specific fetch configuration.
    
    Inherits from FetchConfig with Solar Magazine-specific settings.
    """
    def __new__(cls):
        return super().__new__(
            cls,
            needs_selenium=False,
            needs_tor=False,
            post_container="h3",
            title_selector="a",
            link_selector="a",
            link_attr="href",
            filter_pattern="",
            use_random_user_agent=False,
            published_selector=".date"
        )

CONFIG: SiteConfig = SiteConfig(
    ALL_URLS={
        "https://www.pv-tech.org/feed": RssInfo("pv-tech-logo.webp", "PV Tech", "https://www.pv-tech.org"),
        "https://www.solarpowerworldonline.com/feed/": RssInfo("solarpowerworld.svg", "Solar power World Online", "https://www.solarpowerworldonline.com"),
        "https://www.pv-magazine.com/feed/": RssInfo("pv-magazine-logo.png", "PV Magazine", "https://www.pv-magazine.com"),
        "https://solarmagazine.com/fakefeed": RssInfo("solar-magazine-logo.webp", "Solar Magazine", "https://solarmagazine.com"),
        "https://cleantechnica.com/feed/": RssInfo("cleantechnica-logo.webp", "Clean Technica", "https://cleantechnica.com"),
        "https://www.renewableenergyworld.com/feed": RssInfo("renewableenergyworld-logo.svg", "Renewable Energy World", "https://www.renewableenergyworld.com"),
        "https://ases.org/feed/": RssInfo("ases-logo.svg", "American Solar Energy Society", "https://ases.org"),
        "https://www.altenergymag.com/rss/news/": RssInfo("altenergymag.webp", "Alternative Energy Magazine", "https://www.altenergymag.com"),
    },
    USER_AGENT="Solar Report -- https://pvreport.org",
    SITE_URLS=[
        "https://cleantechnica.com/feed/",
        "https://www.pv-magazine.com/feed/",
        "https://www.pv-tech.org/feed",
        "https://www.solarpowerworldonline.com/feed/",
        "https://www.altenergymag.com/rss/news/",
        "https://www.renewableenergyworld.com/feed",
        "https://ases.org/feed/",
        "https://solarmagazine.com/fakefeed",
    ],
    URL_IMAGES="https://pvreport.org/static/images/",
    FAVICON="pvreport.ico",
    LOGO_URL="pvreport.webp",
    WEB_DESCRIPTION="Solar and Renewable Energy News",
    WEB_TITLE="Photovoltaic Report",
    REPORT_PROMPT="Solar energy industry professionals and enthusiasts in the US. Focus on major solar and battery technology, policy, and market news. Avoid basic installation guides, generic green energy content, or unrelated renewables.",
    PATH="/srv/http/pvreport",
    SCHEDULE=[7, 12, 17],
    CUSTOM_FETCH_CONFIG={
        "solarmagazine.com": SolarMagazineFetchConfig(),
    },
)
