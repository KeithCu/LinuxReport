from typing import Dict, List

from models import RssInfo, SiteConfig
from app_config import RedditFetchConfig, FetchConfig

class VentureBeatFetchConfig(FetchConfig):
    """
    VentureBeat-specific fetch configuration.
    
    Inherits from FetchConfig with VentureBeat-specific settings.
    """
    def __new__(cls):
        return super().__new__(
            cls,
            needs_selenium=True,
            needs_tor=False,
            post_container="article",
            title_selector="h2 a",
            link_selector="h2 a",
            link_attr="href",
            filter_pattern="",
            use_random_user_agent=True,
            published_selector="time"
        )

CONFIG: SiteConfig = SiteConfig(
	ALL_URLS={
		"https://www.reddit.com/r/LocalLlama/rising/.rss": RssInfo("LocalLlama.webp", "Machine Learning sub", "https://www.reddit.com/r/LocalLlama/"),
#		"https://venturebeat.com/category/ai/fakefeed": RssInfo("VentureBeat_logo.webp", "VentureBeat AI", "https://venturebeat.com/category/ai/"),
		"https://www.theregister.com/software/ai_ml/headlines.atom": RssInfo("RegisterLogo.webp", "The Register AI News", "https://www.theregister.com/software/ai_ml/"),
        "https://news.smol.ai/rss.xml": RssInfo("smol.webp", "Smol.ai News", "https://news.smol.ai/"),
		"https://hnrss.org/newest?tags=ai": RssInfo("hackernews.webp", "YCombinator", "https://news.ycombinator.com/"),
		"https://www.reddit.com/r/Python/rising/.rss": RssInfo("redditlogosmall.webp", "Reddit Python", "https://www.reddit.com/r/Python/"),
		"https://planetpython.org/rss20.xml": RssInfo("Python-logo-notext.svg", "Planet Python", "https://planetpython.org/"),
		"https://www.reddit.com/r/Grok/rising/.rss": RssInfo("Grok.gif", "Reddit Grok", "https://www.reddit.com/r/Grok/"),
		"https://huggingface.co/blog/feed.xml": RssInfo("hf-logo.svg", "HuggingFace Blog", "https://huggingface.co/blog/"),
		"https://feed.infoq.com/ai-ml-data-eng/": RssInfo("infoq.png", "InfoQ AI", "https://www.infoq.com/ai-ml-data-eng/"),
		"https://futurism.com/categories/ai-artificial-intelligence/feed": RssInfo("futurism.svg", "Futurism", "https://futurism.com/categories/ai-artificial-intelligence"),
        "https://www.google.com/alerts/feeds/12151242449143161443/8656080270874628454": RssInfo("Google-News.webp", "Google AI news", "https://news.google.com/search?q=AI Large Language Models"),
	},
	USER_AGENT="AI Report -- https://aireport.keithcu.com",
	SITE_URLS=[
		"https://www.reddit.com/r/LocalLlama/rising/.rss",
		"https://hnrss.org/newest?tags=ai",
        "https://www.google.com/alerts/feeds/12151242449143161443/8656080270874628454",
		"https://www.reddit.com/r/Grok/rising/.rss",
		"https://huggingface.co/blog/feed.xml",
		"https://futurism.com/categories/ai-artificial-intelligence/feed",
        "https://news.smol.ai/rss.xml",
#		"https://venturebeat.com/category/ai/fakefeed",
		"https://feed.infoq.com/ai-ml-data-eng/",
		"https://www.theregister.com/software/ai_ml/headlines.atom",
		"https://www.reddit.com/r/Python/rising/.rss",
		"https://planetpython.org/rss20.xml",
	],
	URL_IMAGES="https://aireport.keithcu.com/static/images/",
	FAVICON="covidreport192.ico",
	LOGO_URL="AIReportSpooky.webp",
	WEB_DESCRIPTION="Latest AI news: breakthroughs, trends, and tech for enthusiasts. Hourly updates, no fluff.",
	WEB_TITLE="AI Report | Latest AI News",
	REPORT_PROMPT="AI and robotics for both programmers / researchers and less technical people curious about the biggest news in AI / robots. Nothing about AI security.",
    PATH="/srv/http/aireport",
    SCHEDULE=[7, 13, 19],
    CUSTOM_FETCH_CONFIG={
        "reddit.com": RedditFetchConfig(),
        "venturebeat.com": VentureBeatFetchConfig()
    }
)
