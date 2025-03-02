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
    def __init__(self, entries):
        self.entries = entries

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

# Constants
INITIAL_INTERVAL = timedelta(hours=2)  # Query every 2 hours
MIN_INTERVAL = timedelta(minutes=60)
MAX_INTERVAL = timedelta(hours=24)
BUCKET_SIZE_HOURS = 2                 # 12 buckets per day
HISTORY_WINDOW = 5                    # Track last 5 fetches
SMOOTHING_FACTOR = 0.7                # Weight for exponential smoothing (0-1)

class FeedHistory:
    def __init__(self, data_file: str):
        self.data_file = Path(data_file)
        self.lock = threading.RLock()
        self.data: Dict[str, dict] = self._load_data()
    
    def _load_data(self):
        """Load history from pickle file or initialize empty if it fails or is invalid."""
        if self.data_file.exists():
            try:
                with open(self.data_file, "rb") as f:
                    loaded = pickle.load(f)
                # Ensure loaded is a dictionary
                if not isinstance(loaded, dict):
                    return {}
                # If not empty, validate one feed's data has "weekday_buckets"
                if loaded:
                    first_value = next(iter(loaded.values()))  # Get first feed's data
                    if not (isinstance(first_value, dict) and "weekday_buckets" in first_value):
                        return {}
                return loaded
            except Exception:
                # Loading failed (e.g., file corruption or unpickling error)
                return {}
        return {}
    
    def _save_data(self):
        """Save history to pickle file."""
        with open(self.data_file, "wb") as f:
            pickle.dump(self.data, f)

    def update_fetch(self, url: str, new_articles: int):
        fetch_time = datetime.now(TZ)
        with self.lock:
            feed_data = self.data.setdefault(url, {
                "buckets": {},           # Frequency per time bucket
                "recent": [],            # Last HISTORY_WINDOW fetches: (time, new_articles)
                "interval": EXPIRE_HOUR, # Default in seconds
                "weekday_buckets": set(), # Track fetched weekday bucket numbers
                "weekend_buckets": set(), # Track fetched weekend bucket numbers
                "in_initial_phase": True  # Track initial phase
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

            # Update bucket coverage
            is_weekday = fetch_time.weekday() < 5
            bucket_num = fetch_time.hour // BUCKET_SIZE_HOURS
            if is_weekday:
                feed_data["weekday_buckets"].add(bucket_num)
            else:
                feed_data["weekend_buckets"].add(bucket_num)

            # Exit initial phase if sufficient data collected
            if feed_data["in_initial_phase"]:
                weekday_complete = len(feed_data["weekday_buckets"]) == 12
                weekend_started = len(feed_data["weekend_buckets"]) > 0
                now = datetime.now(TZ)
                is_saturday = now.weekday() == 5  # Saturday
                after_saturday_6pm = is_saturday and now.hour >= 18

                # Exit initial phase after Monday (weekday complete) and some weekend data,
                # but re-enter on Saturday morning until 6 PM
                if weekday_complete and weekend_started and not (is_saturday and now.hour < 18):
                    feed_data["in_initial_phase"] = False
                # Ensure we stay in initial phase on Saturday until 6 PM if weekend buckets incomplete
                elif is_saturday and len(feed_data["weekend_buckets"]) < 12:
                    feed_data["in_initial_phase"] = True

            # Adjust interval based on recent success and bucket
            self._adjust_interval(url)
            self._save_data()

    def _get_bucket(self, dt: datetime) -> str:
        """Map datetime to a bucket key (e.g., 'weekday-0' for 00:00-02:00)."""
        is_weekday = dt.weekday() < 5
        bucket = dt.hour // BUCKET_SIZE_HOURS
        return f"{'weekday' if is_weekday else 'weekend'}-{bucket}"

    def _adjust_interval(self, url: str):
        """Dynamically adjust refresh interval."""
        feed_data = self.data.get(url, {})
        recent = feed_data.get("recent", [])
        bucket = self._get_bucket(datetime.now(TZ))
        freq = feed_data.get("buckets", {}).get(bucket, 0.5)  # Default to neutral

        # Success rate from recent fetches
        success_rate = sum(1 for _, n in recent if n > 0) / max(len(recent), 1)

        # Base interval: inversely proportional to frequency and success
        combined_score = (freq + success_rate) / 2  # 0 to 1
        interval_seconds = (MAX_INTERVAL.total_seconds() * (1 - combined_score) + 
                           MIN_INTERVAL.total_seconds() * combined_score)
        interval = max(MIN_INTERVAL.total_seconds(), 
                      min(MAX_INTERVAL.total_seconds(), interval_seconds))
        
        feed_data["interval"] = interval

    def get_interval(self, url: str) -> timedelta:
        """Get the current refresh interval for a URL."""
        feed_data = self.data.get(url, {})
        if feed_data.get("in_initial_phase", True):
            return INITIAL_INTERVAL
        return timedelta(seconds=feed_data.get("interval", EXPIRE_HOUR))

    def has_expired(self, url: str, last_fetch: datetime) -> bool:
        """Check if the feed should be refreshed, respecting the current interval."""
        interval = self.get_interval(url)
        return datetime.now(TZ) > last_fetch + interval