from datetime import datetime, timedelta

class rssfeed_info:
    def __init__(self, entries):
        self.entries = entries
        self.expiration = datetime.utcnow() + timedelta(seconds=86400)
