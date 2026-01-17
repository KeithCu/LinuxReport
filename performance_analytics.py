import numpy as np
from log_engine import LogEngine
import json
from datetime import datetime

class PerformanceAnalytics:
    def __init__(self, data):
        self.data = data

    def get_summary(self):
        """Standard statistical summary using NumPy's aggregation functions."""
        if len(self.data) == 0:
            return "No data available."

        summary = []
        for m_type in np.unique(self.data['type']):
            subset = self.data[self.data['type'] == m_type]
            latencies = subset['latency']
            
            p50 = np.percentile(latencies, 50)
            p99 = np.percentile(latencies, 99)
            std = np.std(latencies)
            
            summary.append(f"TYPE: {m_type:8} | N: {len(subset):4} | P50: {p50:.3f}s | P99: {p99:.3f}s | STD: {std:.3f}")
        
        return "\n".join(summary)

    def detect_outliers_zscore(self, threshold=3):
        """
        Uses Z-Score (standard deviations from mean) to detect performance anomalies.
        Vectorized O(1) implementation.
        """
        outliers = []
        for m_type in np.unique(self.data['type']):
            subset = self.data[self.data['type'] == m_type]
            if len(subset) < 2: continue
            
            latencies = subset['latency']
            z_scores = np.abs((latencies - np.mean(latencies)) / np.std(latencies))
            
            anomalies = subset[z_scores > threshold]
            for a in anomalies:
                outliers.append(f"OUTLIER: {m_type:8} | {a['timestamp']} | Latency: {a['latency']:.3f}s | Source: {a['source']}")
        
        return "\n".join(outliers)

    def get_echarts_data(self):
        """
        Processes NumPy data into a JSON-compatible format optimized for Apache ECharts.
        """
        if len(self.data) == 0:
            return {}

        # 1. Latency Trends (P50/P99)
        trends = {}
        for m_type in np.unique(self.data['type']):
            subset = self.data[self.data['type'] == m_type]
            # Group by 10 minute intervals for smoothing
            times = subset['timestamp'].astype('datetime64[m]').view('int64') // 10
            unique_bins, indices = np.unique(times, return_inverse=True)
            
            p50_vals = []
            p99_vals = []
            timestamps = []
            
            for i, bin_val in enumerate(unique_bins):
                bin_subset = subset['latency'][indices == i]
                p50_vals.append(float(np.percentile(bin_subset, 50)))
                p99_vals.append(float(np.percentile(bin_subset, 99)))
                timestamps.append((bin_val * 10).astype('datetime64[m]').astype(str))
                
            trends[m_type] = {
                "timestamps": timestamps,
                "p50": p50_vals,
                "p99": p99_vals
            }

        # 2. Hourly Density Heatmap
        # Data format: [[day_of_week, hour, count], ...]
        days = (self.data['timestamp'].astype('datetime64[D]').view('int64') - 4) % 7 # 0=Monday
        hours = self.data['timestamp'].astype('datetime64[h]').view('int64') % 24
        
        # Combine day and hour into a single coordinate
        coords = days * 24 + hours
        counts = np.bincount(coords, minlength=7*24)
        
        heatmap_data = []
        for d in range(7):
            for h in range(24):
                heatmap_data.append([h, d, int(counts[d * 24 + h])])

        # 3. Anomaly Calendar
        # Data format: [[date, count], ...]
        outliers_mask = np.zeros(len(self.data), dtype=bool)
        for m_type in np.unique(self.data['type']):
            subset_mask = self.data['type'] == m_type
            subset_latencies = self.data[subset_mask]['latency']
            if len(subset_latencies) > 2:
                z = np.abs((subset_latencies - np.mean(subset_latencies)) / np.std(subset_latencies))
                outliers_mask[subset_mask] = z > 3
        
        anomaly_dates = self.data[outliers_mask]['timestamp'].astype('datetime64[D]').astype(str)
        unique_dates, anomaly_counts = np.unique(anomaly_dates, return_counts=True)
        calendar_data = [[d, int(c)] for d, c in zip(unique_dates, anomaly_counts)]

        # 4. System Jitter (Rolling)
        weather_latencies = self.data[self.data['type'] == 'weather']['latency']
        jitter_data = []
        if len(weather_latencies) >= 5:
            from numpy.lib.stride_tricks import sliding_window_view
            windows = sliding_window_view(weather_latencies, window_shape=5)
            volatilities = np.std(windows, axis=1) / np.mean(windows, axis=1)
            ts = self.data[self.data['type'] == 'weather']['timestamp'][4:].astype(str)
            jitter_data = [[t, float(v)] for t, v in zip(ts, volatilities)]

        return {
            "trends": trends,
            "heatmap": heatmap_data,
            "calendar": calendar_data,
            "jitter": jitter_data
        }

    def rolling_volatility(self, window=5):
        """
        Calculates rolling standard deviation using a sliding window view.
        No iterative loops - pure vectorized memory projection.
        """
        weather_latencies = self.data[self.data['type'] == 'weather']['latency']
        if len(weather_latencies) < window:
            return "Insufficient data for rolling analysis."
            
        # Magic of stride_tricks: creates a (N, window) view of original memory
        from numpy.lib.stride_tricks import sliding_window_view
        windows = sliding_window_view(weather_latencies, window_shape=window)
        volatilities = np.std(windows, axis=1)
        
        return f"Average Weather Volatility (Rolling {window}): {np.mean(volatilities):.4f}"

if __name__ == "__main__":
    from shared import g_logger
    engine = LogEngine("linuxreport.log")
    data = engine.sync()
    
    analytics = PerformanceAnalytics(data)
    print("=== PERFORMANCE SUMMARY ===")
    print(analytics.get_summary())
    print("\n=== SYSTEM JITTER (ROLLING) ===")
    print(analytics.rolling_volatility())
    print("\n=== METRIC CORRELATIONS ===")
    print(analytics.correlate_metrics())
    print("\n=== ANOMALY DETECTION (Z-SCORE > 3) ===")
    print(analytics.detect_outliers_zscore())
    print("\n=== TEMPORAL TRAFFIC DENSITY ===")
    print(analytics.temporal_density_heatmap())
