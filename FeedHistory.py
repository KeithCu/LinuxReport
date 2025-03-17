from datetime import datetime, timedelta
import pickle
from pathlib import Path
import threading
from typing import Dict
import zoneinfo

TZ = zoneinfo.ZoneInfo("US/Eastern")

# Constants

EXPIRE_HOUR = 3600
INITIAL_INTERVAL = timedelta(hours=2)  # Query every 2 hours
MIN_INTERVAL = timedelta(minutes=60)
MAX_INTERVAL = timedelta(hours=12)
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

            # Determine initial phase status based on current day type and future bucket completeness
            now = datetime.now(TZ)
            is_weekday = now.weekday() < 5
            current_bucket = now.hour // BUCKET_SIZE_HOURS

            # Get the set of buckets for the current day type
            relevant_buckets = feed_data["weekday_buckets"] if is_weekday else feed_data["weekend_buckets"]

            # Check if any buckets ahead of the current time are missing
            future_buckets_missing = False
            for future_bucket in range(current_bucket + 1, 12):  # Check buckets ahead of current time
                if future_bucket not in relevant_buckets:
                    future_buckets_missing = True
                    break

            # Only stay in initial phase if missing buckets are in the future
            feed_data["in_initial_phase"] = future_buckets_missing

            self._save_data()

    def _get_bucket(self, dt: datetime) -> str:
        """Map datetime to a bucket key (e.g., 'weekday-0' for 00:00-02:00)."""
        is_weekday = dt.weekday() < 5
        bucket = dt.hour // BUCKET_SIZE_HOURS
        return f"{'weekday' if is_weekday else 'weekend'}-{bucket}"

    def get_interval(self, url: str) -> timedelta:
        """Get the current refresh interval for a URL."""
        feed_data = self.data.get(url, {})

        if feed_data.get("in_initial_phase", True):
            return INITIAL_INTERVAL

        current_bucket = self._get_bucket(datetime.now(TZ))
        recent = feed_data.get("recent", [])

        current_freq = feed_data.get("buckets", {}).get(current_bucket, 0.5)  # Default to neutral
        success_rate = sum(1 for _, n in recent if n > 0) / max(len(recent), 1)
        combined_score = (current_freq + success_rate) / 2  # 0 to 1

        interval_seconds = (MIN_INTERVAL.total_seconds() * combined_score +
                        MAX_INTERVAL.total_seconds() * (1 - combined_score))

        interval = max(MIN_INTERVAL.total_seconds(),
                    min(MAX_INTERVAL.total_seconds(), interval_seconds))

        return timedelta(seconds=interval)

    def has_expired(self, url: str, last_fetch: datetime) -> bool:
        """Check if the feed should be refreshed, respecting the current interval and MAX_INTERVAL."""
        interval = self.get_interval(url)
        # Clamp the interval to the current MAX_INTERVAL
        clamped_interval = min(interval, MAX_INTERVAL)
        return datetime.now(TZ) > last_fetch + clamped_interval
