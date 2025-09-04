from models import RssInfo, SiteConfig
from app_config import RedditFetchConfig, FetchConfig

class BreitbartTechFetchConfig(FetchConfig):
    """
    Breitbart tech-specific fetch configuration.
    
    Inherits from FetchConfig with Breitbart tech-specific settings.
    """
    def __new__(cls):
        return super().__new__(
            cls,
            needs_selenium=False,
            needs_tor=False,
            post_container="article",
            title_selector="h2 a",
            link_selector="h2 a",
            link_attr="href",
            filter_pattern="/tech/",  # Only tech articles
            use_random_user_agent=False,
            published_selector=".header_byline time"
        )

CONFIG: SiteConfig = SiteConfig(
    ALL_URLS={
        "http://lxer.com/module/newswire/headlines.rss": RssInfo("lxer.webp", "Lxer news", "http://lxer.com/"),
        "https://www.reddit.com/r/linux/.rss": RssInfo("redditlogosmall.webp", "Reddit Linux sub", "https://www.reddit.com/r/linux"),
        "http://rss.slashdot.org/Slashdot/slashdotMain": RssInfo("slashdotlogo.webp", "Slashdot", "https://slashdot.org/"),
        "https://lwn.net/headlines/newrss": RssInfo("barepenguin-70.webp", "LWN.net news", "https://lwn.net/"),
        "https://news.ycombinator.com/rss": RssInfo("hackernews.webp", "Ycombinator news", "http://news.ycombinator.com/"),
        "https://www.osnews.com/feed/": RssInfo("osnews-logo.webp", "OS News.com", "http://www.osnews.com/"),
        "https://www.geekwire.com/feed/": RssInfo("GeekWire.png", "GeekWire", "http://www.geekwire.com/"),
        "http://feeds.feedburner.com/linuxtoday/linux": RssInfo("linuxtd_logo.webp", "Linux Today", "http://www.linuxtoday.com/"),
        "https://planet.debian.org/rss20.xml": RssInfo("Debian-OpenLogo.svg", "Planet Debian", "http://planet.debian.org/"),
        "https://breitbart.com/fakefeed": RssInfo("breitbart.webp", "Breitbart Tech feed", "https://breitbart.com/tech/"),
    },
    USER_AGENT="Linux Report -- https://linuxreport.net/",
    SITE_URLS=[
        "https://news.ycombinator.com/rss",
        "http://rss.slashdot.org/Slashdot/slashdotMain",
        "https://www.reddit.com/r/linux/.rss",
        "http://lxer.com/module/newswire/headlines.rss",
        "https://lwn.net/headlines/newrss",
        "https://www.geekwire.com/feed/",
        "http://feeds.feedburner.com/linuxtoday/linux",
        "https://planet.debian.org/rss20.xml",
        "https://breitbart.com/fakefeed",
        "https://www.osnews.com/feed/",
    ],
    URL_IMAGES="https://linuxreport.net/static/images/",
    FAVICON="linuxreport192.ico",
    LOGO_URL="linuxreportfancy.webp",   
    WEB_DESCRIPTION="Top Linux news: updates, distros, and open-source tech. Hourly briefs for geeks, no fluff.",
    WEB_TITLE="Linux Report | Latest Linux News",
    REPORT_PROMPT="""Arch and Debian Linux programmers and experienced users.
    Prefer major news especially about important codebases. 
    Avoid simple tutorials, error explanations, troubleshooting guides, or cheat sheets.
    Nothing about Ubuntu or any other distro. Anything non-distro-specific is fine, but nothing about 
    the following products:
    tmux, redox, java, Rust, PHP, javascript, mysql (but mariadb is fine) .""",
    PATH="/srv/http/LinuxReport2",
    SCHEDULE=[0, 8, 12, 16, 20],  # Update schedule for Linux Report
    CUSTOM_FETCH_CONFIG={
        "reddit.com": RedditFetchConfig(),
        "breitbart.com": BreitbartTechFetchConfig()
    }
)
