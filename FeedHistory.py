"""
FeedHistory.py

Feed history management system for tracking RSS feed fetch patterns and optimizing
refresh intervals. Provides intelligent scheduling based on historical fetch data,
success rates, and time-based patterns.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import json
import pickle
import threading
import zoneinfo
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional

# =============================================================================
# CONFIGURATION CLASSES
# =============================================================================

class FeedConfig:
    """
    Configuration settings for feed history management.
    
    Centralizes all configuration parameters for the feed history system,
    including timezone settings, intervals, and algorithm parameters.
    """
    
    # Timezone configuration
    TZ = zoneinfo.ZoneInfo("US/Eastern")
    
    # Time-based settings
    EXPIRE_HOUR = 3600
    MIN_INTERVAL = timedelta(minutes=60)
    MAX_INTERVAL = timedelta(hours=12)
    BUCKET_SIZE_HOURS = 2                 # 12 buckets per day
    
    # History tracking settings
    HISTORY_WINDOW = 5                    # Track last 5 fetches
    SMOOTHING_FACTOR = 0.7                # Weight for exponential smoothing (0-1)

# =============================================================================
# MAIN FEED HISTORY CLASS
# =============================================================================

class FeedHistory:
    """
    Manages feed fetch history and provides intelligent refresh interval calculation.
    
    This class tracks RSS feed fetch patterns, success rates, and time-based
    activity to optimize refresh intervals. It uses exponential smoothing and
    bucket-based analysis to determine optimal fetch timing.
    
    Attributes:
        data_file (Path): Path to the JSON data file storing feed history
        lock (threading.RLock): Thread-safe lock for data access
        data (Dict[str, dict]): In-memory feed history data
    """
    
    def __init__(self, data_file: str):
        """
        Initialize the FeedHistory instance.
        
        Args:
            data_file (str): Path to the data file for storing feed history
        """
        self.data_file = Path(data_file)
        # Ensure the data file has a .json extension
        if not self.data_file.suffix == '.json':
            self.data_file = self.data_file.with_suffix('.json')
        
        self.lock = threading.RLock()
        self.data: Dict[str, dict] = self._load_data()

    # =============================================================================
    # DATA LOADING AND VALIDATION METHODS
    # =============================================================================

    def _load_data(self) -> Dict[str, dict]:
        """
        Load history from JSON file or pickle file, converting pickle to JSON if necessary.
        
        Attempts to load data from JSON format first, then falls back to pickle
        format if JSON is not available. Automatically converts pickle data to
        JSON format for future use.
        
        Returns:
            Dict[str, dict]: Loaded feed history data or empty dict if no valid data found
        """
        print(f"[FeedHistory] Loading data from file: {self.data_file}")
        
        # Try loading JSON first
        if self.data_file.exists():
            data = self._load_json()
            if data is not None:
                return data
        
        # Try loading pickle as fallback
        pickle_file = self.data_file.with_suffix('.pickle')
        if pickle_file.exists():
            data = self._load_pickle(pickle_file)
            if data is not None:
                # Convert pickle data to JSON for future use
                self.data = data
                self._save_data()
                return data
        
        print("[FeedHistory] No valid data file found, returning empty dictionary")
        return {}

    def _load_json(self) -> Optional[Dict[str, dict]]:
        """
        Attempt to load and validate JSON data.
        
        Loads JSON data and performs validation to ensure data integrity.
        Converts serialized datetime strings and list representations back to
        their original Python objects.
        
        Returns:
            Optional[Dict[str, dict]]: Validated feed data or None if loading fails
        """
        try:
            with open(self.data_file, "r") as f:
                loaded = json.load(f)
            
            if not self._validate_data(loaded):
                return None
            
            # Convert string dates back to datetime objects and lists back to sets
            for feed_url, feed_data in loaded.items():
                feed_data["recent"] = [(datetime.fromisoformat(dt), n) for dt, n in feed_data.get("recent", [])]
                feed_data["weekday_buckets"] = set(feed_data.get("weekday_buckets", []))
                feed_data["weekend_buckets"] = set(feed_data.get("weekend_buckets", []))
            
            return loaded
            
        except (json.JSONDecodeError, Exception) as e:
            print(f"[FeedHistory] Failed to load JSON: {str(e)}")
            return None

    def _load_pickle(self, pickle_file: Path) -> Optional[Dict[str, dict]]:
        """
        Attempt to load and validate pickle data.
        
        Loads pickle data and performs validation to ensure data integrity.
        Used as a fallback when JSON data is not available.
        
        Args:
            pickle_file (Path): Path to the pickle file to load
            
        Returns:
            Optional[Dict[str, dict]]: Validated feed data or None if loading fails
        """
        try:
            with open(pickle_file, "rb") as f:
                loaded = pickle.load(f)
            
            if not self._validate_data(loaded):
                return None
            
            return loaded
            
        except Exception as e:
            print(f"[FeedHistory] Failed to load pickle: {str(e)}")
            return None

    def _validate_data(self, data: Dict) -> bool:
        """
        Validate the structure of loaded data.
        
        Performs basic validation to ensure the loaded data has the expected
        structure and can be safely used by the FeedHistory class.
        
        Args:
            data (Dict): Data to validate
            
        Returns:
            bool: True if data is valid, False otherwise
        """
        if not isinstance(data, dict):
            print("[FeedHistory] ERROR: Data is not a dictionary")
            return False
        
        if not data:
            return True  # Empty dict is valid
        
        # Validate first feed's data structure
        first_key = next(iter(data.keys()))
        first_value = data[first_key]
        
        if not (isinstance(first_value, dict) and "weekday_buckets" in first_value):
            print("[FeedHistory] ERROR: Invalid feed data structure")
            return False
        
        return True

    # =============================================================================
    # DATA PERSISTENCE METHODS
    # =============================================================================

    def _save_data(self) -> None:
        """
        Save history to JSON file, converting datetime objects to strings and sets to lists.
        
        Serializes the in-memory feed history data to JSON format, converting
        Python objects that are not JSON-serializable to appropriate formats.
        """
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

    def reset_history(self, url: str) -> None:
        """
        Reset the history for a given URL.
        
        Args:
            url (str): The RSS feed URL to reset
        """
        with self.lock:
            if url in self.data:
                del self.data[url]
                self._save_data()

    # =============================================================================
    # FEED UPDATE AND TRACKING METHODS
    # =============================================================================

    def update_fetch(self, url: str, new_articles: int) -> None:
        """
        Update the fetch history for a given URL.
        
        Records a new fetch attempt for the specified URL, updating recent fetch
        history, bucket frequency analysis, and time-based coverage tracking.
        
        Args:
            url (str): The RSS feed URL that was fetched
            new_articles (int): Number of new articles found in the fetch
        """
        fetch_time = datetime.now(FeedConfig.TZ)
        with self.lock:
            feed_data = self.data.setdefault(url, {
                "buckets": {},           # Frequency per time bucket
                "recent": [],            # Last HISTORY_WINDOW fetches: (time, new_articles)
                "weekday_buckets": set(), # Track fetched weekday bucket numbers
                "weekend_buckets": set(), # Track fetched weekend bucket numbers
            })

            # Update recent fetches
            fetch_entry = (fetch_time, new_articles)
            feed_data["recent"] = (feed_data["recent"][-FeedConfig.HISTORY_WINDOW + 1:] + [fetch_entry])[-FeedConfig.HISTORY_WINDOW:]

            # Update bucket frequency
            bucket = self._get_bucket(fetch_time)
            old_freq = feed_data["buckets"].get(bucket, 0)
            new_freq = 1 if new_articles > 0 else 0
            feed_data["buckets"][bucket] = (FeedConfig.SMOOTHING_FACTOR * new_freq +
                                           (1 - FeedConfig.SMOOTHING_FACTOR) * old_freq)

            # Update bucket coverage
            is_weekday = fetch_time.weekday() < 5
            bucket_num = fetch_time.hour // FeedConfig.BUCKET_SIZE_HOURS
            if is_weekday:
                feed_data["weekday_buckets"].add(bucket_num)
            else:
                feed_data["weekend_buckets"].add(bucket_num)

            self._save_data()

    # =============================================================================
    # UTILITY AND ANALYSIS METHODS
    # =============================================================================

    def _get_bucket(self, dt: datetime) -> str:
        """
        Map datetime to a bucket key for time-based analysis.
        
        Creates a bucket identifier based on whether the time is on a weekday
        or weekend and the hour range. Used for frequency analysis.
        
        Args:
            dt (datetime): Datetime to map to a bucket
            
        Returns:
            str: Bucket key (e.g., 'weekday-0' for 00:00-02:00 on weekdays)
        """
        is_weekday = dt.weekday() < 5
        bucket = dt.hour // FeedConfig.BUCKET_SIZE_HOURS
        return f"{'weekday' if is_weekday else 'weekend'}-{bucket}"

    def get_interval(self, url: str) -> timedelta:
        """
        Get the current refresh interval for a URL based on historical data.
        
        Calculates an optimal refresh interval using a combination of:
        - Recent fetch success rate
        - Current time bucket frequency
        - Exponential smoothing for stability
        
        Args:
            url (str): The RSS feed URL to calculate interval for
            
        Returns:
            timedelta: Recommended refresh interval between MIN_INTERVAL and MAX_INTERVAL
        """
        feed_data = self.data.get(url, {})

        current_bucket = self._get_bucket(datetime.now(FeedConfig.TZ))
        recent = feed_data.get("recent", [])

        if not recent:
            # If recent is empty, assume a neutral success rate
            success_rate = 0.5
        else:
            success_rate = sum(1 for _, n in recent if n > 0) / len(recent)

        current_freq = feed_data.get("buckets", {}).get(current_bucket, 0.5)  # Default to neutral
        combined_score = (current_freq + success_rate) / 2  # 0 to 1

        interval_seconds = (FeedConfig.MIN_INTERVAL.total_seconds() * combined_score +
                        FeedConfig.MAX_INTERVAL.total_seconds() * (1 - combined_score))

        interval = max(FeedConfig.MIN_INTERVAL.total_seconds(),
                    min(FeedConfig.MAX_INTERVAL.total_seconds(), interval_seconds))

        return timedelta(seconds=interval)

    def has_expired(self, url: str, last_fetch: datetime) -> bool:
        """
        Check if the feed should be refreshed based on current interval and last fetch time.
        
        Determines whether enough time has passed since the last fetch to warrant
        a new fetch attempt, respecting the calculated optimal interval.
        
        Args:
            url (str): The RSS feed URL to check
            last_fetch (datetime): Timestamp of the last fetch attempt
            
        Returns:
            bool: True if the feed should be refreshed, False otherwise
        """
        interval = self.get_interval(url)
        # Clamp the interval to the current MAX_INTERVAL
        clamped_interval = min(interval, FeedConfig.MAX_INTERVAL)
        return datetime.now(FeedConfig.TZ) > last_fetch + clamped_interval
