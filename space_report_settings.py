from models import RssInfo, SiteConfig
from app_config import REDDIT_FETCH_CONFIG
import shared

CONFIG: SiteConfig = SiteConfig(
	ALL_URLS={
		"https://www.nasa.gov/rss/dyn/breaking_news.rss": RssInfo("nasa.svg", "NASA News", "https://www.nasa.gov"),
		"http://www.esa.int/rssfeed/Our_Activities/Space_News": RssInfo("esa.svg", "ESA News", "https://www.esa.int"),
		"https://spacenews.com/feed/": RssInfo("spacenews.png", "SpaceNews.com", "https://spacenews.com"),
		"https://universetoday.com/feed/": RssInfo("universetoday.webp", "Universe Today", "https://universetoday.com"),
		"https://www.planetary.org/rss/articles": RssInfo("planetary.png", "The Planetary Society", "https://planetary.org"),
		"https://www.astronomy.com/feed/": RssInfo("astronomy.webp", "Astronomy Magazine", "https://www.astronomy.com"),
		"https://skyandtelescope.org/astronomy-news/rss/": RssInfo("sky-and-telescope.svg", "Sky & Telescope", "https://skyandtelescope.org"),
		"https://www.newscientist.com/subject/space/feed/": RssInfo("newscientist.png", "New Scientist", "https://www.newscientist.com"),
		"https://www.sciencedaily.com/rss/space_time.xml": RssInfo("sciencedaily.png", "Science Daily", "https://www.sciencedaily.com"),
		"https://phys.org/rss-feed/space-news/": RssInfo("phys.png", "Phys.org", "https://phys.org"),
		"https://space.com/feeds/all": RssInfo("space.webp", "Space.com", "https://space.com"),
        "https://www.spaceelevatorblog.com/?feed=rss2": RssInfo("spaceelevatorblog.jpg","Space Elevator Blog", "https://www.spaceelevatorblog.com"),
	},
	USER_AGENT="Space Report -- https://news.spaceelevatorwiki.com",
	SITE_URLS=[
		"https://space.com/feeds/all",
		"https://www.nasa.gov/rss/dyn/breaking_news.rss",
		"https://phys.org/rss-feed/space-news/",
		"http://www.esa.int/rssfeed/Our_Activities/Space_News",
		"https://spacenews.com/feed/",
		"https://www.astronomy.com/feed/",
		"https://universetoday.com/feed/",
		"https://www.newscientist.com/subject/space/feed/",
		"https://www.sciencedaily.com/rss/space_time.xml",
		"https://skyandtelescope.org/astronomy-news/rss/",
		"https://www.planetary.org/rss/articles",
		"https://www.spaceelevatorblog.com/?feed=rss2",
	],
	URL_IMAGES="https://news.spaceelevatorwiki.com/static/images/",
	FAVICON="SpaceReport.ico",
	LOGO_URL="SpaceReport.webp",
	WEB_DESCRIPTION="Space exploration news: Cosmic updates in milliseconds",
	WEB_TITLE="Space Report",
	REPORT_PROMPT="Latest top news in the space industry regarding space exploration, including space elevators",
    PATH="/srv/http/spacereport",
    SCHEDULE=[0, 8, 12, 16, 20],
    CUSTOM_FETCH_CONFIG={
        "reddit.com": REDDIT_FETCH_CONFIG,
    }
)
