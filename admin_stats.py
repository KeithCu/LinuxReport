import time
import datetime
import numpy as np
from shared import FLASK_DASHBOARD, g_cm, EXPIRE_DAY, g_c, EXPIRE_YEARS

def update_performance_stats(render_time, current_time):
    """
    Update performance statistics for admin monitoring.
    
    This function is called on EVERY request (high frequency),
    so it must be fast and use memory cache for speed.
    
    Args:
        render_time: Time taken to render the page in seconds
        current_time: Current timestamp from the caller (no internal time calls)
    """
    # Skip if Flask-MonitoringDashboard is enabled (it handles this automatically)
    if FLASK_DASHBOARD:
        return
        
    stats_key = "admin_performance_stats"
    # Configuration
    BUFFER_SIZE = 100
    
    stats_data = g_cm.get(stats_key)
    
    # Initialize if not exists
    if not stats_data or not isinstance(stats_data.get("times"), list):
        stats_data = {
            "times": [0.0] * BUFFER_SIZE,
            "count": 0,
            "hourly_requests": {},
            "first_request_time": current_time,
            "last_cleanup_hour": None,
            "index": 0  # Write pointer for circular buffer
        }
    
    # Update hourly request count
    current_hour = int(current_time / 3600)
    if current_hour not in stats_data["hourly_requests"]:
        stats_data["hourly_requests"][current_hour] = 0
    stats_data["hourly_requests"][current_hour] += 1
    
    # Hourly cleanup (once per hour)
    if stats_data.get("last_cleanup_hour") != current_hour:
        old_hour = current_hour - 24
        stats_data["hourly_requests"] = {h: c for h, c in stats_data["hourly_requests"].items() if h > old_hour}
        stats_data["last_cleanup_hour"] = current_hour
    
    stats_data["count"] += 1
    
    # Update circular buffer
    if stats_data["count"] > 1:  # Skip cold start
        idx = stats_data.get("index", 0)
        stats_data["times"][idx] = render_time
        stats_data["index"] = (idx + 1) % BUFFER_SIZE
    
    g_cm.set(stats_key, stats_data, ttl=EXPIRE_DAY)

def get_admin_stats_html():
    """Generate HTML for admin performance stats."""
    # Skip if Flask-MonitoringDashboard is enabled (it has its own dashboard)
    if FLASK_DASHBOARD:
        return None
        
    stats_key = "admin_performance_stats"
    stats = g_cm.get(stats_key)
    
    if not stats or not stats.get("times"):
        return None
    
    times_list = stats["times"]
    if stats["count"] < 3:
        return None
        
    # Vectorized analysis with NumPy
    # Filter out zero values (unused buffer) and handle effective size
    actual_data = np.array(times_list)
    idx = stats.get("index", 0)
    
    if stats["count"] < len(times_list):
        # Buffer not full yet, take only the entries we've written
        actual_data = actual_data[:stats["count"]]
    else:
        # Buffer is full, roll it so the oldest entry (at index) is at the start
        actual_data = np.roll(actual_data, -idx)
    
    # Filter out initial zeros if count is very low (e.g. first request)
    actual_data = actual_data[actual_data > 0]
    if len(actual_data) == 0:
        return None
    
    # Calculate stats
    min_time = np.min(actual_data)
    max_time = np.max(actual_data)
    avg_time = np.mean(actual_data)
    p50 = np.percentile(actual_data, 50)
    p95 = np.percentile(actual_data, 95)
    p99 = np.percentile(actual_data, 99)
    std_dev = np.std(actual_data)
    
    # System Jitter (coefficient of variation)
    jitter = (std_dev / avg_time * 100) if avg_time > 0 else 0
    
    count = stats.get("count", 0)
    
    # Calculate request counts
    current_time = time.time()
    current_hour = int(current_time / 3600)
    hourly_requests = stats.get("hourly_requests", {})
    requests_1h = hourly_requests.get(current_hour, 0)
    requests_24h = sum(hourly_requests.values())
    
    # Uptime
    first_request_time = stats.get("first_request_time", time.time())
    uptime_seconds = time.time() - first_request_time
    uptime_str = str(datetime.timedelta(seconds=int(uptime_seconds)))
    
    return f'''
    <div style="position: fixed; top: 10px; right: 10px; background: rgba(50,50,50,0.9); color: #eee; padding: 8px; 
                border-radius: 6px; font-size: 11px; z-index: 9999; font-family: 'JetBrains Mono', 'Courier New', monospace;
                border: 1px solid #444; box-shadow: 0 4px 12px rgba(0,0,0,0.3); line-height: 1.4;">
        <strong style="color: #4CAF50;">ADMIN CORE METRICS</strong>
        <a href="/admin/performance" style="float: right; color: #2196F3; text-decoration: none; border: 1px solid #2196F3; padding: 0 4px; border-radius: 3px; font-size: 10px;">DASHBOARD</a><br>
        <span style="color: #888;">UPTIME:</span> {uptime_str}<br>
        <span style="color: #888;">REQS (1H/24H):</span> {requests_1h} / {requests_24h}<br>
        <hr style="border: 0; border-top: 1px solid #444; margin: 4px 0;">
        <span style="color: #888;">LATENCY (N={len(actual_data)})</span><br>
        MIN/MAX: {min_time:.3f}s / {max_time:.3f}s<br>
        AVG: {avg_time:.3f}s | STD: {std_dev:.3f}s<br>
        <span style="color: #4CAF50;">P50:</span> {p50:.3f}s<br>
        <span style="color: #FFC107;">P95:</span> {p95:.3f}s<br>
        <span style="color: #FF5722;">P99:</span> {p99:.3f}s<br>
        <span style="color: #888;">JITTER:</span> {jitter:.1f}%
    </div>
    '''

def track_rate_limit_event(ip, endpoint, limit_type="exceeded"):
    """
    Track rate limit events for long-term monitoring and security analysis.
    
    This function is called ONLY when rate limits are exceeded (rare events),
    so it can be slower and use disk cache for persistence across restarts.
    
    Args:
        ip: IP address that hit the rate limit
        endpoint: Flask endpoint that was rate limited
        limit_type: Type of rate limit violation (default: "exceeded")
    """
    # Store events in disk cache for persistence across restarts
    rate_limit_events_key = "rate_limit_events"
    events = g_c.get(rate_limit_events_key) or []
    
    current_time = time.time()
    # Keep event data minimal - details can be found in Apache logs
    event = {
        "timestamp": current_time,
        "ip": ip,
        "endpoint": endpoint
    }
    
    # Add to events list (keep last 1000 events)
    events.append(event)
    if len(events) > 1000:
        events = events[-1000:]
    
    # Clean up old events (older than 30 days)
    cutoff_time = current_time - (30 * 24 * 3600)  # 30 days
    events = [e for e in events if e["timestamp"] > cutoff_time]
    
    # Store events in disk cache for persistence
    g_c.put(rate_limit_events_key, events, timeout=EXPIRE_YEARS)
    
    # Keep minimal stats in disk cache for long-term tracking
    rate_limit_stats_key = "rate_limit_stats"
    stats = g_c.get(rate_limit_stats_key) or {
        "by_ip": {},
        "by_endpoint": {}
    }
    
    # Track by IP and endpoint
    for key, data_dict in [("by_ip", ip), ("by_endpoint", endpoint)]:
        if data_dict not in stats[key]:
            stats[key][data_dict] = {"count": 0, "last_seen": current_time}
        stats[key][data_dict]["count"] += 1
        stats[key][data_dict]["last_seen"] = current_time
    
    g_c.put(rate_limit_stats_key, stats, timeout=EXPIRE_YEARS)  # Store in disk cache for persistence
