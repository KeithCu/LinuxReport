from datetime import datetime, timedelta, timezone
import pickle
import json
from pathlib import Path
import threading
import time
from typing import Dict, List, Optional
import zoneinfo

TZ = zoneinfo.ZoneInfo("US/Eastern")

class RssFeed:
    def __init__(self, entries, last_fetch):
        self.entries = entries
        self.last_fetch = last_fetch

class RssInfo:
    def __init__(self, logo_url, logo_alt, site_url):
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url

EXPIRE_MINUTES = 60 * 5
EXPIRE_HOUR = 3600
EXPIRE_DAY = 3600 * 12
EXPIRE_WEEK = 86400 * 7
EXPIRE_YEARS = 86400 * 365 * 2


# Assume these are defined in shared.py
from shared import RssFeed, RssInfo, EXPIRE_HOUR, EXPIRE_DAY

# Constants
MIN_INTERVAL = timedelta(minutes=1)
MAX_INTERVAL = timedelta(hours=24)
BUCKET_SIZE_HOURS = 4                 # 6 buckets per day
HISTORY_WINDOW = 5                    # Track last 5 fetches
SMOOTHING_FACTOR = 0.7                # Weight for exponential smoothing (0-1)

class FeedHistory:
    """Manages historical fetch data and refresh intervals."""
    def __init__(self, data_file: str = "feed_history.pickle"):
        self.data_file = Path(data_file)
        self.lock = threading.RLock()
        self.data: Dict[str, dict] = self._load_data()
    
    def _load_data(self):
        """Load history from pickle file or initialize empty."""
        if self.data_file.exists():
            with open(self.data_file, "rb") as f:
                return pickle.load(f)
        return {"last_updated": None, "feeds": []}

    def _save_data(self):
        """Save history to pickle file."""
        with open(self.data_file, "wb") as f:
            pickle.dump(self.data, f)

    def _get_bucket(self, dt: datetime) -> str:
        """Map datetime to a bucket key (e.g., 'weekday-12' for 12-16h)."""
        is_weekday = dt.weekday() < 5
        bucket = dt.hour // BUCKET_SIZE_HOURS
        return f"{'weekday' if is_weekday else 'weekend'}-{bucket}"

    def update_fetch(self, url: str, new_articles: int, fetch_time: datetime):
        """Record fetch outcome and update history."""
        with self.lock:
            feed_data = self.data.setdefault(url, {
                "buckets": {},  # Frequency per time bucket
                "recent": [],   # Last HISTORY_WINDOW fetches: (time, new_articles)
                "interval": EXPIRE_HOUR.total_seconds()  # Default in seconds
            })

            # Update recent fetches
            fetch_entry = (fetch_time, new_articles)
            feed_data["recent"] = (feed_data["recent"][-HISTORY_WINDOW + 1:] + [fetch_entry])[-HISTORY_WINDOW:]

            # Update bucket frequency
            bucket = self._get_bucket(fetch_time)
            old_freq = feed_data["buckets"].get(bucket, 0)
            new_freq = 1 if new_articles > 0 else 0
            feed_data["buckets"][bucket] = (SMOOTHING_FACTOR * new_freq + 
                                           (1 - SMOOTHING_FACTOR) * old_freq)

            # Adjust interval based on recent success and bucket
            self._adjust_interval(url)
            self._save_data()

    def _adjust_interval(self, url: str):
        """Dynamically adjust refresh interval."""
        feed_data = self.data.get(url, {})
        recent = feed_data.get("recent", [])
        bucket = self._get_bucket(datetime.now(timezone.utc))
        freq = feed_data.get("buckets", {}).get(bucket, 0.5)  # Default to neutral

        # Success rate from recent fetches
        success_rate = sum(1 for _, n in recent if n > 0) / max(len(recent), 1)

        # Base interval: inversely proportional to frequency and success
        combined_score = (freq + success_rate) / 2  # 0 to 1
        interval_hours = MAX_INTERVAL.total_seconds() * (1 - combined_score) + \
                        MIN_INTERVAL.total_seconds() * combined_score
        interval = max(MIN_INTERVAL.total_seconds(), 
                      min(MAX_INTERVAL.total_seconds(), interval_hours))
        
        feed_data["interval"] = interval

    def get_interval(self, url: str) -> timedelta:
        """Get the current refresh interval for a URL."""
        return timedelta(seconds=self.data.get(url, {}).get("interval", EXPIRE_HOUR))

    def has_expired(self, url: str, last_fetch: datetime) -> bool:
        """Check if the feed should be refreshed."""
        interval = self.get_interval(url)
        return datetime.now(timezone.utc) > last_fetch + interval

