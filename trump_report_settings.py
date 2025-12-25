from dataclasses import dataclass
from models import RssInfo, SiteConfig
from app_config import RedditFetchConfig, FetchConfig

@dataclass(frozen=True)
class PatriotsWinFetchConfig(FetchConfig):
    """
    Patriots.win-specific fetch configuration.
    
    Inherits from FetchConfig with Patriots.win-specific settings.
    """
    needs_selenium: bool = True
    needs_tor: bool = False
    post_container: str = "a[href^='/p/']"  # Post links start with /p/
    title_selector: str = "a[href^='/p/']"  # Title is the text content of post links
    link_selector: str = "a[href^='/p/']"   # Post links
    link_attr: str = "href"
    filter_pattern: str = None
    use_random_user_agent: bool = False
    published_selector: str = "span:contains('ago')"  # Time elements contain "ago"


@dataclass(frozen=True)
class RevolverNewsFetchConfig(FetchConfig):
    """
    Revolver.news-specific fetch configuration.
    
    Inherits from FetchConfig with Revolver.news-specific settings.
    """
    needs_selenium: bool = False
    needs_tor: bool = False
    post_container: str = "article.item"
    title_selector: str = "h2.title a"
    link_selector: str = "h2.title a"
    link_attr: str = "href"
    filter_pattern: str = None
    use_random_user_agent: bool = False
    published_selector: str = ".meta time"
import datetime

CONFIG = SiteConfig(
	ALL_URLS={
		"https://revolver.news/fakefeed": RssInfo("revolvernews.png", "Revolver News", "https://revolver.news"),
		"https://citizenfreepress.com/feed/": RssInfo("citizenfreepress.webp", "Citizen Free Press", "https://citizenfreepress.com"),
		"https://patriots.win/fakefeed": RssInfo("patriotswin.webp", "Patriots.win", "https://patriots.win"),
		"https://thefederalist.com/feed/": RssInfo("federalist.webp", "The Federalist", "https://thefederalist.com"),
#		"https://bonginoreport.com/index.rss": RssInfo("bonginoreport.webp", "Bongino Report", "https://bonginoreport.com"),
		"https://freebeacon.com/feed/": RssInfo("freebeacon.webp", "Free Beacon", "https://freebeacon.com"),
		"https://feeds.feedburner.com/breitbart": RssInfo("breitbart.webp", "Breitbart", "https://breitbart.com"),
		"https://nypost.com/politics/feed/": RssInfo("nypost.webp", "New York Post Politics Section", "https://nypost.com/politics/"),
		"https://conservativereview.com/feeds/feed.rss": RssInfo("conservativereview.webp", "Conservative Review", "https://conservativereview.com"),
		"https://townhall.com/feed/": RssInfo("logo-townhall.svg", "Townhall", "https://townhall.com"),
		"https://api.dailycaller.com/?feed=full&key=abad8678eeda58de4efcc7e9a704d008": RssInfo("dailycaller.webp", "Daily Caller", "https://dailycaller.com"),

	},
	USER_AGENT="Trump Report -- https://trumpreport.info",
	SITE_URLS=[
		"https://patriots.win/fakefeed",
		"https://citizenfreepress.com/feed/",
		"https://townhall.com/feed/",
		"https://conservativereview.com/feeds/feed.rss",
		"https://nypost.com/politics/feed/",
		"https://api.dailycaller.com/?feed=full&key=abad8678eeda58de4efcc7e9a704d008",
		"https://feeds.feedburner.com/breitbart",
		"https://revolver.news/fakefeed",
		"https://thefederalist.com/feed/",
		"https://freebeacon.com/feed/",
	#	"https://bonginoreport.com/index.rss",
	],
	URL_IMAGES="https://trumpreport.info/static/images/",
	FAVICON="TrumpReportChristmasfestivewintertheme.webp",
	LOGO_URL="TrumpReportChristmasfestivewintertheme.webp",
	WEB_DESCRIPTION="Fast Trump 2025 news for MAGA: tariffs, immigration, deregulation. Hourly conservative headlines.",
	WEB_TITLE="Trump Report | Conservative News",
	REPORT_PROMPT=f'''Trump's biggest supporters of his second term Presidency, which began on January 20, 2025, as of today: {datetime.date.today().strftime('%B %d, %Y')}
VP: J.D. Vance
Cabinet: Marco Rubio (State), Pete Hegseth (Defense), Scott Bessent (Treasury), Pam Bondi (AG), Doug Burgum (Interior), Lori Chavez-DeRemer (Labor), Sean Duffy (Transpo),
Robert F. Kennedy Jr. (HHS), Howard Lutnick (Commerce), Linda McMahon (Ed), Kristi Noem (DHS), Brooke Rollins (Ag), Eric Turner (HUD), Lee Zeldin (EPA), Chris Wright (Energy)
Allies: Elon Musk (DOGE - Department of Government Efficiency), Russell Vought (OMB).
''',
    PATH="/srv/http/trumpreport",
    SCHEDULE=[0, 4, 8, 10, 12, 14, 16, 18, 20, 22],
    DEFAULT_THEME="silver",
    CUSTOM_FETCH_CONFIG={
        "patriots.win": PatriotsWinFetchConfig(),
        "revolver.news": RevolverNewsFetchConfig(),
        "reddit.com": RedditFetchConfig(),
    }
)
