from datetime import datetime, timedelta

class RssFeed:
    def __init__(self, entries):
        self.entries = entries
        self.expiration = datetime.utcnow() + timedelta(seconds=86400)
        self.etag = ''
        self.last_modified = datetime.utcnow() - timedelta(seconds=86400 * 365 * 2)

class RssInfo:
    def __init__(self, logo_url, logo_alt, site_url, expire_time):
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url
        self.expire_time = expire_time
