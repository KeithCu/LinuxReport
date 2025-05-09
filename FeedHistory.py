import json
import pickle
import threading
import zoneinfo
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

TZ = zoneinfo.ZoneInfo("US/Eastern")

# Constants

EXPIRE_HOUR = 3600
# INITIAL_INTERVAL = timedelta(hours=4)
MIN_INTERVAL = timedelta(minutes=60)
MAX_INTERVAL = timedelta(hours=12)
BUCKET_SIZE_HOURS = 2                 # 12 buckets per day
HISTORY_WINDOW = 5                    # Track last 5 fetches
SMOOTHING_FACTOR = 0.7                # Weight for exponential smoothing (0-1)

class FeedHistory:
    def __init__(self, data_file: str):
        self.data_file = Path(data_file)
        # Ensure the data file has a .json extension
        if not self.data_file.suffix == '.json':
            self.data_file = self.data_file.with_suffix('.json')
        self.lock = threading.RLock()
        self.data: Dict[str, dict] = self._load_data()

    def _load_data(self):
        """Load history from JSON file or pickle file, converting pickle to JSON if necessary."""
        print(f"[FeedHistory] Loading data from file: {self.data_file}")
        
        if self.data_file.exists():
            print(f"[FeedHistory] Data file exists: {self.data_file}")
            try:
                print(f"[FeedHistory] Attempting to load JSON from: {self.data_file}")
                with open(self.data_file, "r") as f:
                    loaded = json.load(f)
                
                print(f"[FeedHistory] Successfully loaded JSON data with {len(loaded)} feeds")
                
                # Convert string dates back to datetime objects and lists back to sets
                print(f"[FeedHistory] Converting date strings to datetime objects and lists to sets")
                for feed_url, feed_data in loaded.items():
                    feed_data["recent"] = [(datetime.fromisoformat(dt), n) for dt, n in feed_data.get("recent", [])]
                    feed_data["weekday_buckets"] = set(feed_data.get("weekday_buckets", []))
                    feed_data["weekend_buckets"] = set(feed_data.get("weekend_buckets", []))
                
                # Ensure loaded is a dictionary
                if not isinstance(loaded, dict):
                    print(f"[FeedHistory] ERROR: Loaded data is not a dictionary, returning empty dict")
                    return {}
                
                # If not empty, validate one feed's data has "weekday_buckets"
                if loaded:
                    first_key = next(iter(loaded.keys()))
                    first_value = loaded[first_key]
                    print(f"[FeedHistory] First feed in loaded data: {first_key}")
                    
                    if not (isinstance(first_value, dict) and "weekday_buckets" in first_value):
                        print(f"[FeedHistory] ERROR: Data validation failed, missing 'weekday_buckets' in feed data")
                        return {}
                    
                    # Print sample of data for one feed
                    print(f"[FeedHistory] Sample data for first feed: recent={first_value.get('recent', [])[:2]}, "
                          f"weekday_buckets={list(first_value.get('weekday_buckets', []))[:3]}")
                
                print(f"[FeedHistory] Successfully processed JSON data")
                return loaded
            
            except json.JSONDecodeError:
                # JSON loading failed, try loading from pickle
                print(f"[FeedHistory] JSON loading failed, attempting to load from pickle instead")
                try:
                    pickle_file = self.data_file.with_suffix('.pickle')
                    print(f"[FeedHistory] Attempting to load pickle from: {pickle_file}")
                    
                    with open(pickle_file, "rb") as f:
                        loaded = pickle.load(f)
                    
                    print(f"[FeedHistory] Successfully loaded pickle data with {len(loaded)} feeds")
                    
                    # Ensure loaded is a dictionary
                    if not isinstance(loaded, dict):
                        print(f"[FeedHistory] ERROR: Pickle data is not a dictionary, returning empty dict")
                        return {}
                    
                    # If not empty, validate one feed's data has "weekday_buckets"
                    if loaded:
                        first_key = next(iter(loaded.keys()))
                        first_value = loaded[first_key]
                        print(f"[FeedHistory] First feed in pickle data: {first_key}")
                        
                        if not (isinstance(first_value, dict) and "weekday_buckets" in first_value):
                            print(f"[FeedHistory] ERROR: Pickle data validation failed")
                            return {}
                    
                    # Save the loaded pickle data as JSON
                    print(f"[FeedHistory] Converting pickle data to JSON format")
                    self._save_data()
                    return loaded
                
                except Exception as e:
                    # Loading failed (e.g., file corruption or unpickling error)
                    print(f"[FeedHistory] ERROR: Failed to load pickle data: {str(e)}")
                    return {}
            
            except Exception as e:
                # Other exceptions
                print(f"[FeedHistory] ERROR: Unexpected exception during data loading: {str(e)}")
                return {}
        
        # JSON file doesn't exist, try loading from pickle file
        pickle_file = self.data_file.with_suffix('.pickle')
        print(f"[FeedHistory] JSON file does not exist, checking for pickle file: {pickle_file}")
        
        if pickle_file.exists():
            try:
                print(f"[FeedHistory] Attempting to load pickle from: {pickle_file}")
                
                with open(pickle_file, "rb") as f:
                    loaded = pickle.load(f)
                
                print(f"[FeedHistory] Successfully loaded pickle data with {len(loaded)} feeds")
                
                # Ensure loaded is a dictionary
                if not isinstance(loaded, dict):
                    print(f"[FeedHistory] ERROR: Pickle data is not a dictionary, returning empty dict")
                    return {}
                
                # If not empty, validate one feed's data has "weekday_buckets"
                if loaded:
                    first_key = next(iter(loaded.keys()))
                    first_value = loaded[first_key]
                    print(f"[FeedHistory] First feed in pickle data: {first_key}")
                    
                    if not (isinstance(first_value, dict) and "weekday_buckets" in first_value):
                        print(f"[FeedHistory] ERROR: Pickle data validation failed")
                        return {}
                
                # Save the loaded pickle data as JSON for future use
                print(f"[FeedHistory] Converting pickle data to JSON format")
                self.data = loaded
                self._save_data()
                return loaded
            
            except Exception as e:
                # Loading failed (e.g., file corruption or unpickling error)
                print(f"[FeedHistory] ERROR: Failed to load pickle data: {str(e)}")
                return {}
        
        print(f"[FeedHistory] Neither JSON nor pickle file exists, returning empty dictionary")
        return {}

    def _save_data(self):
        """Save history to JSON file, converting datetime objects to strings and sets to lists."""
        # Convert datetime objects to strings and sets to lists
        serializable_data = {
            url: {
                **feed_data,
                "recent": [(dt.isoformat(), n) for dt, n in feed_data.get("recent", [])],
                "weekday_buckets": list(feed_data.get("weekday_buckets", [])),
                "weekend_buckets": list(feed_data.get("weekend_buckets", []))
            }
            for url, feed_data in self.data.items()
        }
        with open(self.data_file, "w") as f:
            json.dump(serializable_data, f, indent=4, sort_keys=True)

    def update_fetch(self, url: str, new_articles: int):
        fetch_time = datetime.now(TZ)
        with self.lock:
            feed_data = self.data.setdefault(url, {
                "buckets": {},           # Frequency per time bucket
                "recent": [],            # Last HISTORY_WINDOW fetches: (time, new_articles)
                "weekday_buckets": set(), # Track fetched weekday bucket numbers
                "weekend_buckets": set(), # Track fetched weekend bucket numbers
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

            self._save_data()

    def _get_bucket(self, dt: datetime) -> str:
        """Map datetime to a bucket key (e.g., 'weekday-0' for 00:00-02:00)."""
        is_weekday = dt.weekday() < 5
        bucket = dt.hour // BUCKET_SIZE_HOURS
        return f"{'weekday' if is_weekday else 'weekend'}-{bucket}"

    def get_interval(self, url: str) -> timedelta:
        """Get the current refresh interval for a URL."""
        feed_data = self.data.get(url, {})

        current_bucket = self._get_bucket(datetime.now(TZ))
        recent = feed_data.get("recent", [])

        if not recent:
            # If recent is empty, assume a neutral success rate
            success_rate = 0.5
        else:
            success_rate = sum(1 for _, n in recent if n > 0) / len(recent)

        current_freq = feed_data.get("buckets", {}).get(current_bucket, 0.5)  # Default to neutral
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
