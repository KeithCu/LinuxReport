import numpy as np
import re
from datetime import datetime
from pathlib import Path

# Structured array definition for multi-metric storage
METRIC_DTYPE = np.dtype([
    ('timestamp', 'datetime64[ms]'),
    ('type', 'U16'),      # 'weather', 'feed', 'dedup'
    ('latency', 'f4'),    # seconds
    ('value', 'i4'),      # count (e.g., articles)
    ('source', 'U64')     # city name or URL
])

from shared import g_c, g_logger

class LogEngine:
    def __init__(self, log_path, metrics_path=None):
        self.log_path = Path(log_path)
        # If metrics_path is not absolute, make it relative to the log file's directory
        if metrics_path:
            self.metrics_path = Path(metrics_path)
        else:
            self.metrics_path = self.log_path.parent / "metrics.npy"
            
        self.data = self._load_persisted()

    def _load_persisted(self):
        """Loads historical metrics from the binary .npy store."""
        if self.metrics_path.exists():
            try:
                return np.load(self.metrics_path)
            except Exception as e:
                g_logger.error(f"Error loading {self.metrics_path}: {e}")
        return np.array([], dtype=METRIC_DTYPE)

    def _save_persisted(self):
        """Saves current metrics to the binary .npy store."""
        np.save(self.metrics_path, self.data)

    def _age_data(self, days=30):
        """Purges records older than N days using vectorized Boolean masking."""
        if len(self.data) == 0: return
        cutoff = np.datetime64('now') - np.timedelta64(days, 'D')
        self.data = self.data[self.data['timestamp'] > cutoff]

    def sync(self):
        """
        Incrementally syncs the log file by tracking the first line and byte offset.
        Handles rotation and extension gracefully.
        """
        if not self.log_path.exists(): 
            g_logger.error(f"CRITICAL: Performance log file not found at {self.log_path.absolute()}")
            return self.data

        # 1. Check for Rotation using the first line's timestamp
        last_offset = g_c.get("log_sync_offset") or 0
        last_first_ts = g_c.get("log_sync_first_ts")
        
        with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            current_first_ts = first_line[:23] if first_line else None
            
            # Simple rotation detection: if the first line changed, start from 0
            if current_first_ts != last_first_ts:
                last_offset = 0
                g_logger.info("Log rotation detected (First line TS mismatch). Resetting offset.")
            
            # 2. Seek and read new chunk
            f.seek(last_offset)
            new_lines = f.readlines()
            new_offset = f.tell()

        if not new_lines:
            self._age_data()
            self._save_persisted()
            return self.data

        # 3. Parse new chunk
        new_data = self.parse_from_lines(new_lines)
        
        # 4. Merge and Age
        if len(self.data) > 0:
            self.data = np.concatenate([self.data, new_data])
            # Sort by timestamp to ensure analytics work correctly
            self.data.sort(order='timestamp')
        else:
            self.data = new_data
            
        self._age_data()
        self._save_persisted()
        
        # Update state
        g_c.put("log_sync_offset", new_offset)
        g_c.put("log_sync_first_ts", current_first_ts)
        
        return self.data

    def parse_from_lines(self, lines):
        """Vectorized parsing logic (previously parse_vectorized)"""
        if not lines: return np.array([], dtype=METRIC_DTYPE)
        lines = np.array(lines)

        # Identify Metric Types
        is_weather = np.char.find(lines, "Weather API result") != -1
        is_feed = np.char.find(lines, "Parsing from:") != -1
        is_dedup = np.char.find(lines, "Deduplication: Filtered") != -1
        
        valid_mask = is_weather | is_feed | is_dedup
        valid_lines = lines[valid_mask]
        if len(valid_lines) == 0:
            return np.array([], dtype=METRIC_DTYPE)

        # Extract Timestamps
        ts_strings = np.array([line[:23] for line in valid_lines], dtype='U23')
        ts_strings = np.char.replace(ts_strings, ',', '.')
        is_date = np.char.startswith(ts_strings, '2')
        
        results = np.zeros(np.sum(is_date), dtype=METRIC_DTYPE)
        final_lines = valid_lines[is_date]
        results['timestamp'] = ts_strings[is_date].astype('datetime64[ms]')
        
        # Re-derive masks
        is_weather = np.char.find(final_lines, "Weather API result") != -1
        is_feed = np.char.find(final_lines, "Parsing from:") != -1
        is_dedup = np.char.find(final_lines, "Deduplication: Filtered") != -1

        # Weather Parsing
        weather_indices = np.where(is_weather)[0]
        if len(weather_indices) > 0:
            w_lines = final_lines[is_weather]
            results['type'][weather_indices] = 'weather'
            parts = np.char.partition(w_lines, "API time: ")[:, 2]
            results['latency'][weather_indices] = np.char.partition(parts, "s")[:, 0].astype('f4')
            results['source'][weather_indices] = np.char.partition(np.char.partition(w_lines, "city: ")[:, 2], ",")[:, 0]

        # Feed Parsing
        feed_indices = np.where(is_feed)[0]
        for idx in feed_indices:
            results['type'][idx] = 'feed'
            m = re.search(r"in ([\d]+(?:\.[\d]+)?)", final_lines[idx])
            if m: results['latency'][idx] = float(m.group(1))
            m = re.search(r"New articles: (\d+)", final_lines[idx])
            if m: results['value'][idx] = int(m.group(1))
            m = re.search(r"Parsing from: ([^,]+)", final_lines[idx])
            if m: results['source'][idx] = m.group(1).strip()

        # Dedup Parsing
        dedup_indices = np.where(is_dedup)[0]
        for idx in dedup_indices:
            results['type'][idx] = 'dedup'
            m = re.search(r"Filtered (\d+) duplicate", final_lines[idx])
            if m: results['value'][idx] = int(m.group(1))

        return results

    def parse_vectorized(self):
        """Wrapper for backward compatibility"""
        with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
            return self.parse_from_lines(f.readlines())

if __name__ == "__main__":
    from shared import g_logger
    engine = LogEngine("linuxreport.log")
    data = engine.sync()
    print(f"Total metrics in store: {len(data)}")
    print(data[:3])
