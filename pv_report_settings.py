from dataclasses import dataclass
from models import RssInfo, SiteConfig
from app_config import FetchConfig

@dataclass(frozen=True)
class SolarMagazineFetchConfig(FetchConfig):
    """
    Solar Magazine-specific fetch configuration.
    
    Inherits from FetchConfig with Solar Magazine-specific settings.
    """
    needs_selenium: bool = False
    needs_tor: bool = False
    post_container: str = "h3"
    title_selector: str = "a"
    link_selector: str = "a"
    link_attr: str = "href"
    filter_pattern: str = None
    use_random_user_agent: bool = False
    published_selector: str = ".date"

CONFIG = SiteConfig(
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
        "https://www.pv-tech.org/feed",
        "https://www.pv-magazine.com/feed/",
        "https://www.renewableenergyworld.com/feed",
        "https://www.altenergymag.com/rss/news/",
        "https://www.solarpowerworldonline.com/feed/",
        "https://solarmagazine.com/fakefeed",
        "https://ases.org/feed/",
    ],
    URL_IMAGES="https://pvreport.org/static/images/",
    FAVICON="pvreport.ico",
    LOGO_URL="PVReportChristmasfestivewintertheme.webp",
    WEB_DESCRIPTION="Solar and Renewable Energy News",
    WEB_TITLE="Photovoltaic Report",
    REPORT_PROMPT="Solar energy professionals and enthusiasts, primarily in the US. Focus on major solar and battery technology, policy, and market news. Avoid basic how-to guides, generic green content, and unrelated renewable topics.",
    PATH="/srv/http/pvreport",
    SCHEDULE=[7, 12, 17],
    DEFAULT_THEME="solarized",
    CUSTOM_FETCH_CONFIG={
        "solarmagazine.com": SolarMagazineFetchConfig(),
    },
)
