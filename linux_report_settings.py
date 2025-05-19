from models import RssInfo, SiteConfig, REDDIT_FETCH_CONFIG
import shared

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
        "http://lxer.com/module/newswire/headlines.rss",
        "https://www.reddit.com/r/linux/.rss",
        "http://rss.slashdot.org/Slashdot/slashdotMain",
        "https://lwn.net/headlines/newrss",
        "https://news.ycombinator.com/rss",
        "https://www.osnews.com/feed/",
        "https://breitbart.com/fakefeed",
        "https://www.geekwire.com/feed/",
        "http://feeds.feedburner.com/linuxtoday/linux",
        "https://planet.debian.org/rss20.xml",
    ],
    URL_IMAGES="https://linuxreport.net/static/images/",
    FAVICON="linuxreport192.ico",
    LOGO_URL="linuxreportfancy.webp",
    WEB_DESCRIPTION="Linux News",
    WEB_TITLE="Linux Report",
    REPORT_PROMPT="""Arch and Debian Linux programmers and experienced users.
    Prefer major news especially about important codebases. 
    Avoid simple tutorials, error explanations, troubleshooting guides, or cheat sheets.
    Nothing about Ubuntu or any other distro. Anything non-distro-specific is fine, but nothing about 
    the following products:
    tmux, redox, java, javascript, mysql (mariadb is ok).""",
    PATH="/srv/http/LinuxReport2",
    SCHEDULE=[0, 8, 12, 16, 20],  # Update schedule for Linux Report
    CUSTOM_FETCH_CONFIG={
        "reddit.com": REDDIT_FETCH_CONFIG,
        "breitbart.com": {
            "needs_selenium": False,
            "needs_tor": False,
            "post_container": "article",
            "title_selector": "h2 a",
            "link_selector": "h2 a",
            "link_attr": "href",
            "published_selector": ".header_byline time",
            "filter_pattern": "/tech/"
        },
    }
)
