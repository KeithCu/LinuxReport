from datetime import datetime, timedelta

class RssFeed:
    def __init__(self, entries):
        self.entries = entries
        self.expiration = datetime.utcnow() + timedelta(seconds=86400)
        self.etag = ''
        self.last_modified = datetime.utcnow() - timedelta(seconds=86400 * 365 * 2)
