from dataclasses import dataclass
from models import RssInfo, SiteConfig
from app_config import FetchConfig

@dataclass(frozen=True)
class BandcampFetchConfig(FetchConfig):
    """
    Bandcamp-specific fetch configuration.
    
    Inherits from FetchConfig with Bandcamp-specific settings.
    """
    needs_selenium = True
    needs_tor = False
    post_container = ".music-grid-item"
    title_selector = ".title"
    link_selector = "a"
    link_attr = "href"
    filter_pattern = None
    use_random_user_agent = False
    published_selector = ".date"

CONFIG = SiteConfig(
    ALL_URLS = {
        "http://detroiteq.com/feed": RssInfo("deq.webp", "Detroit Electronic Quarterly", "http://detroiteq.com/"),
        "https://www.google.com/alerts/feeds/12151242449143161443/18325972585468687530": RssInfo("Google-NewsTechno.webp", "Google Detroit Techno news", "https://news.google.com/search?q=detroit techno"),
        "https://rocksteadydisco.bandcamp.com/fakefeed": RssInfo("RockSteadyDisco.webp", "RockSteady Disco", "https://rocksteadydisco.bandcamp.com"),
        "https://transmatdetroit.bandcamp.com/fakefeed": RssInfo("Transmat.webp", "Transmat", "https://transmatdetroit.bandcamp.com"),
        "https://pitsdetroit.bandcamp.com/fakefeed": RssInfo("pits.webp", "Place In Time And Space", "https://pitsdetroit.bandcamp.com/"),
        "https://planetecommunications.bandcamp.com/fakefeed": RssInfo("planete.webp", "Planet-E Communications", "https://planetecommunications.bandcamp.com"),
        "https://womenonwax.com/feed/": RssInfo("womenonwax.webp", "Women On Wax", "https://womenonwax.com"),
    },
    USER_AGENT = "The Detroit Techno Report -- http://news.thedetroitilove.com/",
    SITE_URLS = [
        "http://detroiteq.com/feed",
        "https://www.google.com/alerts/feeds/12151242449143161443/18325972585468687530",
        "https://rocksteadydisco.bandcamp.com/fakefeed",
        "https://womenonwax.com/feed/",
        "https://transmatdetroit.bandcamp.com/fakefeed",
        "https://planetecommunications.bandcamp.com/fakefeed",
        "https://pitsdetroit.bandcamp.com/fakefeed",
    ],
    URL_IMAGES = "http://news.thedetroitilove.com/static/images/",
    FAVICON = "technoreport.ico",
    LOGO_URL = "TechnoReport.webp",
    WEB_DESCRIPTION = "Detroit Techno, Arts and Events News",
    WEB_TITLE = "The Detroit Report | Latest Detroit Techno News",
    REPORT_PROMPT = "Detroit techno fans, DJs, producers, and labels interested in significant Detroit techno news, releases, and events.",
    PATH = "/srv/http/flask",
    SCHEDULE = [0],
    DEFAULT_THEME="paper",
    CUSTOM_FETCH_CONFIG={
        "bandcamp.com": BandcampFetchConfig(),
    }
)
