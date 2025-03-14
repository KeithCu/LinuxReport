import diskcache
from enum import Enum
import zoneinfo
import datetime

from FeedHistory import FeedHistory

TZ = zoneinfo.ZoneInfo("US/Eastern")

class RssFeed:
    def __init__(self, entries, top_articles=None):
        self.entries = entries
        self.top_articles = top_articles if top_articles else []
        self.__post_init__()

    def __post_init__(self):
        if not hasattr(self, 'top_articles'):
            object.__setattr__(self, 'top_articles', [])

    def __setstate__(self, state):
        object.__setattr__(self, '__dict__', state)
        self.__post_init__()


class RssInfo:
    def __init__(self, logo_url, logo_alt, site_url):
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url

PATH = '/run/linuxreport'

class Mode(Enum):
    LINUX_REPORT = 1
    COVID_REPORT = 2
    TECHNO_REPORT = 3
    AI_REPORT = 4
    PYTHON_REPORT = 5
    TRUMP_REPORT = 6
    SPACE_REPORT = 7

EXPIRE_MINUTES = 60 * 5
EXPIRE_HOUR = 3600
EXPIRE_DAY = 3600 * 12
EXPIRE_WEEK = 86400 * 7
EXPIRE_YEARS = 86400 * 365 * 2

MODE = Mode.LINUX_REPORT

history = FeedHistory(data_file = f"{PATH}/feed_history{str(MODE)}.pickle")

class DiskCacheWrapper:
    def __init__(self, cache_dir):
        self.cache = diskcache.Cache(cache_dir)

    def has(self, key):
        return key in self.cache

    def get(self, key):
        return self.cache.get(key)

    def put(self, key, value, timeout=None):
        self.cache.set(key, value, expire=timeout)

    def delete(self, key):
        self.cache.delete(key)

    def has_feed_expired(self, url):
        last_fetch = self.get(url + ":last_fetch")
        if last_fetch is None:
            return True
        return history.has_expired(url, last_fetch)

g_c = DiskCacheWrapper(PATH)


def format_last_updated(last_fetch, timezone):
    """Format the last fetch time as 'X minutes ago' or 'X hours ago'.
    """
    if not last_fetch:
        return "Unknown"
    
    now = datetime.datetime.now(timezone)
    delta = now - last_fetch
    total_minutes = delta.total_seconds() / 60.0
    
    if total_minutes < 60:
        rounded_minutes = round(total_minutes / 5.0) * 5
        return f"{int(rounded_minutes)} minutes ago"
    else:
        rounded_hours = round(total_minutes / 60.0)
        if rounded_hours == 1:
            return "1 hour ago"
        return f"{int(rounded_hours)} hours ago"