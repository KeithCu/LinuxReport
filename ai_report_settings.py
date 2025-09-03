from typing import Dict, List

from models import RssInfo, SiteConfig
from app_config import REDDIT_FETCH_CONFIG

CONFIG: SiteConfig = SiteConfig(
	ALL_URLS={
		"https://www.reddit.com/r/LocalLlama/.rss": RssInfo("LocalLlama.webp", "Machine Learning sub", "https://www.reddit.com/r/LocalLlama/"),
		"https://venturebeat.com/category/ai/fakefeed": RssInfo("VentureBeat_logo.webp", "VentureBeat AI", "https://venturebeat.com/category/ai/"),
		"https://www.theregister.com/software/ai_ml/headlines.atom": RssInfo("RegisterLogo.webp", "The Register AI News", "https://www.theregister.com/software/ai_ml/"),
        "https://news.smol.ai/rss.xml": RssInfo("smol.webp", "Smol.ai News", "https://news.smol.ai/"),
		"https://hnrss.org/newest?tags=ai": RssInfo("hackernews.webp", "YCombinator", "https://news.ycombinator.com/"),
		"https://www.reddit.com/r/Python/.rss": RssInfo("redditlogosmall.webp", "Reddit Python", "https://www.reddit.com/r/Python/"),
		"https://planetpython.org/rss20.xml": RssInfo("Python-logo-notext.svg", "Planet Python", "https://planetpython.org/"),
		"https://www.reddit.com/r/Grok/.rss": RssInfo("Grok.gif", "Reddit Grok", "https://www.reddit.com/r/Grok/"),
		"https://huggingface.co/blog/feed.xml": RssInfo("hf-logo.svg", "HuggingFace Blog", "https://huggingface.co/blog/"),
		"https://feed.infoq.com/ai-ml-data-eng/": RssInfo("infoq.png", "InfoQ AI", "https://www.infoq.com/ai-ml-data-eng/"),
		"https://futurism.com/categories/ai-artificial-intelligence/feed": RssInfo("futurism.svg", "Futurism", "https://futurism.com/categories/ai-artificial-intelligence"),
        "https://www.google.com/alerts/feeds/12151242449143161443/8656080270874628454": RssInfo("Google-News.webp", "Google AI news", "https://news.google.com/search?q=AI Large Language Models"),
	},
	USER_AGENT="AI Report -- https://aireport.keithcu.com",
	SITE_URLS=[
		"https://www.reddit.com/r/LocalLlama/.rss",
		"https://hnrss.org/newest?tags=ai",
        "https://www.google.com/alerts/feeds/12151242449143161443/8656080270874628454",
		"https://www.reddit.com/r/Grok/.rss",
		"https://huggingface.co/blog/feed.xml",
		"https://futurism.com/categories/ai-artificial-intelligence/feed",
        "https://news.smol.ai/rss.xml",
		"https://venturebeat.com/category/ai/fakefeed",
		"https://feed.infoq.com/ai-ml-data-eng/",
		"https://www.theregister.com/software/ai_ml/headlines.atom",
		"https://www.reddit.com/r/Python/.rss",
		"https://planetpython.org/rss20.xml",
	],
	URL_IMAGES="https://aireport.keithcu.com/static/images/",
	FAVICON="covidreport192.ico",
	LOGO_URL="aireportfancy2.webp",
	WEB_DESCRIPTION="Latest AI news: breakthroughs, trends, and tech for enthusiasts. Hourly updates, no fluff.",
	WEB_TITLE="AI Report | Latest AI News",
	REPORT_PROMPT="AI and robotics for both programmers / researchers and less technical people curious about the biggest news in AI / robots. Nothing about AI security.",
    PATH="/srv/http/aireport",
    SCHEDULE=[7, 11, 15, 19, 23],
    CUSTOM_FETCH_CONFIG={
        "reddit.com": REDDIT_FETCH_CONFIG,
        "venturebeat.com": {
            "needs_selenium": True,  # Use Selenium to avoid rate limiting
            "needs_tor": False,
            "post_container": "article",
            "title_selector": "h2 a",
            "link_selector": "h2 a",
            "link_attr": "href",
            "published_selector": "time",
            "filter_pattern": "",
            "use_random_user_agent": True  # Use random user agent to avoid detection
        }
    }
)
