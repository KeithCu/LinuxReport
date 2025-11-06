from typing import Dict, List

from models import RssInfo, SiteConfig
from app_config import RedditFetchConfig, FetchConfig

# No custom fetch config needed initially; add if sites require Selenium.

CONFIG: SiteConfig = SiteConfig(
    ALL_URLS={
        "https://www.therobotreport.com/feed/": RssInfo("therobotreport.webp", "The Robot Report", "https://www.therobotreport.com/"),
        "https://robohub.org/feed/": RssInfo("Robohub.webp", "Robohub", "https://robohub.org/"),
        "https://newatlas.com/robotics/index.rss": RssInfo("NewAtlas.svg", "New Atlas Robotics", "https://newatlas.com/robotics/"),
        "https://www.azorobotics.com/syndication.axd": RssInfo("AZoRobotics.webp", "AZoRobotics", "https://www.azorobotics.com/"),
        "https://www.unite.ai/fakefeed": RssInfo("UniteAI.svg", "Unite.AI Robotics", "https://www.unite.ai"),
        "https://arxiv.org/rss/cs.RO": RssInfo("arXiv.svg", "arXiv Robotics", "https://arxiv.org/list/cs.RO/recent"),
        "https://news.mit.edu/topic/mitrobotics-rss.xml": RssInfo("MIT.svg", "MIT News Robotics", "https://news.mit.edu/topic/robotics"),
        "https://spectrum.ieee.org/feeds/topic/robotics.rss": RssInfo("IEEESpectrum.svg", "IEEE Spectrum Robotics", "https://spectrum.ieee.org/topic/robotics/"),
        "https://techxplore.com/rss-feed/robotics-news/": RssInfo("TechXplore.svg", "TechXplore Robotics", "https://techxplore.com/robotics-news/"),
        "https://www.sciencedaily.com/rss/matter_energy/robotics.xml": RssInfo("ScienceDaily.webp", "ScienceDaily Robotics", "https://www.sciencedaily.com/news/matter_energy/robotics/"),
        "https://blogs.nvidia.com/blog/tag/robotics/feed/": RssInfo("NVIDIA.webp", "NVIDIA Robotics", "https://blogs.nvidia.com/blog/tag/robotics/"),
    },
    SITE_URLS=[
        "https://www.therobotreport.com/feed/",
        "https://www.azorobotics.com/syndication.axd",
        "https://techxplore.com/rss-feed/robotics-news/",
        "https://spectrum.ieee.org/feeds/topic/robotics.rss",
        "https://robohub.org/feed/",
        "https://www.sciencedaily.com/rss/matter_energy/robotics.xml",
        "https://www.unite.ai/fakefeed",
        "https://blogs.nvidia.com/blog/tag/robotics/feed/",
        "https://newatlas.com/robotics/index.rss",
        "https://news.mit.edu/topic/mitrobotics-rss.xml",
        "https://arxiv.org/rss/cs.RO",
    ],
    USER_AGENT="Robot Report -- https://robotreport.keithcu.com",
    URL_IMAGES="https://robotreport.keithcu.com/static/images/",
    FAVICON="robotreport192.ico",
    LOGO_URL="RobotReportFallharvesttheme.webp",
    WEB_DESCRIPTION="Latest robotics news: breakthroughs, trends, and tech for enthusiasts. Hourly updates, no fluff.",
    WEB_TITLE="Robot Report | Latest Robotics News",
    REPORT_PROMPT="Robotics and humanoid robotics news for both programmers / builders and less technical people curious about the biggest news in robotics / humanoids.",
    PATH="/srv/http/robotreport",
    SCHEDULE=[0, 8, 12, 16],
    CUSTOM_FETCH_CONFIG={
        # Site-specific Selenium config for Unite.AI main page
        # Updated to match actual site structure
        "unite.ai": FetchConfig(
            needs_selenium=True,
            needs_tor=False,
            post_container="li.mvp-blog-story-wrap",
            title_selector="h2",
            link_selector=".mvp-blog-story-text a[rel='bookmark']",
            link_attr="href",
            filter_pattern=None,
            use_random_user_agent=False,
            published_selector="span.mvp-cd-date",
        ),
    }
)