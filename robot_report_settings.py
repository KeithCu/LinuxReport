from typing import Dict, List

from models import RssInfo, SiteConfig
from app_config import RedditFetchConfig, FetchConfig

# No custom fetch config needed initially; add if sites require Selenium.

CONFIG: SiteConfig = SiteConfig(
    ALL_URLS={
        "https://www.therobotreport.com/feed/": RssInfo("RobotReport.svg", "The Robot Report", "https://www.therobotreport.com/"),
        "https://robohub.org/feed/": RssInfo("Robohub.webp", "Robohub", "https://robohub.org/"),
        "https://newatlas.com/robotics/index.rss": RssInfo("NewAtlas.svg", "New Atlas Robotics", "https://newatlas.com/robotics/"),
        "https://www.azorobotics.com/syndication.axd": RssInfo("AZoRobotics.webp", "AZoRobotics", "https://www.azorobotics.com/"),
        "https://www.unite.ai/category/robotics/fakefeed": RssInfo("UniteAI.svg", "Unite.AI Robotics", "https://www.unite.ai/category/robotics/"),
        "https://arxiv.org/rss/cs.RO": RssInfo("arXiv.svg", "arXiv Robotics", "https://arxiv.org/list/cs.RO/recent"),
        "https://news.mit.edu/topic/mitrobotics-rss.xml": RssInfo("MIT.svg", "MIT News Robotics", "https://news.mit.edu/topic/robotics"),
        "https://spectrum.ieee.org/feeds/topic/robotics.rss": RssInfo("IEEESpectrum.svg", "IEEE Spectrum Robotics", "https://spectrum.ieee.org/topic/robotics/"),
        "https://techxplore.com/rss-feed/robotics-news/": RssInfo("TechXplore.svg", "TechXplore Robotics", "https://techxplore.com/robotics-news/"),
        "https://www.sciencedaily.com/rss/matter_energy/robotics.xml": RssInfo("ScienceDaily.webp", "ScienceDaily Robotics", "https://www.sciencedaily.com/news/matter_energy/robotics/"),
        "https://blogs.nvidia.com/blog/tag/robotics/feed/": RssInfo("NVIDIA.webp", "NVIDIA Robotics", "https://blogs.nvidia.com/blog/tag/robotics/"),
    },
    SITE_URLS=[
        "https://www.therobotreport.com/feed/",
        "https://robohub.org/feed/",
        "https://newatlas.com/robotics/index.rss",
        "https://www.azorobotics.com/syndication.axd",
        "https://www.unite.ai/category/robotics/fakefeed",
        "https://arxiv.org/rss/cs.RO",
        "https://news.mit.edu/topic/mitrobotics-rss.xml",
        "https://spectrum.ieee.org/feeds/topic/robotics.rss",
        "https://techxplore.com/rss-feed/robotics-news/",
        "https://www.sciencedaily.com/rss/matter_energy/robotics.xml",
        "https://blogs.nvidia.com/blog/tag/robotics/feed/",
    ],
    USER_AGENT="Robot Report -- https://robotreport.keithcu.com",
    URL_IMAGES="https://robotreport.keithcu.com/static/images/",
    FAVICON="robotreport192.ico",
    LOGO_URL="RobotReport.webp",
    WEB_DESCRIPTION="Latest robotics news: breakthroughs, trends, and tech for enthusiasts. Hourly updates, no fluff.",
    WEB_TITLE="Robot Report | Latest Robotics News",
    REPORT_PROMPT="Robotics and humanoid robotics news for both programmers / builders and less technical people curious about the biggest news in robotics / humanoids.",
    PATH="/srv/http/robotreport",
    SCHEDULE=[7, 11, 15, 19, 23],
    CUSTOM_FETCH_CONFIG={
        # Site-specific Selenium config for Unite.AI category page
        # Fallback heuristic: select anchors that look like permalinks (contain a year)
        # Special-case in seleniumfetch: when title_selector==post_container, use element text
        "unite.ai": FetchConfig(
            needs_selenium=True,
            needs_tor=False,
            post_container="a[href*='/20']",
            title_selector="a[href*='/20']",
            link_selector="a[href*='/20']",
            link_attr="href",
            filter_pattern="/20",
            use_random_user_agent=False,
            published_selector=None,
        ),
    }
)