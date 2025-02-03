from datetime import datetime, timedelta, timezone

class RssFeed:
    def __init__(self, entries):
        self.entries = entries
        self.expiration = datetime.now(timezone.utc) + timedelta(seconds=86400)
        self.etag = ''
        self.last_modified = datetime.now(timezone.utc) - timedelta(seconds=86400 * 365 * 2)

class RssInfo:
    def __init__(self, logo_url, logo_alt, site_url, expire_time):
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url
        self.expire_time = expire_time

EXPIRE_MINUTES = 60 * 5
EXPIRE_HOUR = 3600
EXPIRE_DAY = 3600 * 12
EXPIRE_WEEK = 86400 * 7
EXPIRE_YEARS = 86400 * 365 * 2
