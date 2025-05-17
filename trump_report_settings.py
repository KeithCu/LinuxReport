from models import RssInfo, SiteConfig, REDDIT_FETCH_CONFIG
import shared

CONFIG: SiteConfig = SiteConfig(
	ALL_URLS={
		"https://revolver.news/fakefeed": RssInfo("revolvernews.png", "Revolver News", "https://revolver.news"),
		"https://citizenfreepress.com/feed/": RssInfo("citizenfreepress.webp", "Citizen Free Press", "https://citizenfreepress.com"),
		"https://patriots.win/fakefeed": RssInfo("patriotswin.webp", "Patriots.win", "https://patriots.win"),
		"https://thefederalist.com/feed/": RssInfo("federalist.webp", "The Federalist", "https://thefederalist.com"),
		"http://bonginoreport.com/index.rss": RssInfo("bonginoreport.webp", "Bongino Report", "https://bonginoreport.com"),
		"https://freebeacon.com/feed/": RssInfo("freebeacon.webp", "Free Beacon", "https://freebeacon.com"),
		"https://feeds.feedburner.com/breitbart": RssInfo("breitbart.webp", "Breitbart", "https://breitbart.com"),
		"https://nypost.com/politics/feed/": RssInfo("nypost.webp", "New York Post Politics Section", "https://nypost.com/politics/"),
		"https://conservativereview.com/feeds/feed.rss": RssInfo("conservativereview.webp", "Conservative Review", "https://conservativereview.com"),
		"https://townhall.com/feed/": RssInfo("logo-townhall.svg", "Townhall", "https://townhall.com"),
		"https://api.dailycaller.com/?feed=full&key=abad8678eeda58de4efcc7e9a704d008": RssInfo("dailycaller.webp", "Daily Caller", "https://dailycaller.com"),

	},
	USER_AGENT="Trump Report -- https://trumpreport.info",
	SITE_URLS=[
		"https://feeds.feedburner.com/breitbart",
		"https://patriots.win/fakefeed",
		"https://revolver.news/fakefeed",
		"https://nypost.com/politics/feed/",
        "https://api.dailycaller.com/?feed=full&key=abad8678eeda58de4efcc7e9a704d008",
		"https://citizenfreepress.com/feed/",
		"https://thefederalist.com/feed/",
		"https://freebeacon.com/feed/",
		"https://townhall.com/feed/",
		"http://bonginoreport.com/index.rss",
		"https://conservativereview.com/feeds/feed.rss",
	],
	URL_IMAGES="https://trumpreport.info/static/images/",
	FAVICON="TrumpReport.webp",
	LOGO_URL="TrumpReport.webp",
	WEB_DESCRIPTION="Trump Report",
	WEB_TITLE="TrumpReport",
	REPORT_PROMPT="Trump's biggest fans of his 2nd term Presidency which started January 20, 2025.",
    PATH="/srv/http/trumpreport",
    SCHEDULE=[0, 4, 8, 10, 12, 14, 16, 20],
    CUSTOM_FETCH_CONFIG={
        "patriots.win": {
            "needs_selenium": True,
            "needs_tor": False,
            "post_container": ".post-item",
            "title_selector": ".title a",
            "link_selector": ".preview-parent",
            "link_attr": "href",
            "filter_pattern": ""
        },
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
        "revolver.news": {
            "needs_selenium": False,
            "needs_tor": False,
            "post_container": "article.item",
            "title_selector": "h2.title a",
            "link_selector": "h2.title a",
            "link_attr": "href",
            "filter_pattern": ""
        },
        "reddit.com": REDDIT_FETCH_CONFIG,
    }
)
