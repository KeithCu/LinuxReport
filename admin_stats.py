import time
import datetime
from shared import FLASK_DASHBOARD, g_cm, EXPIRE_DAY, g_c, EXPIRE_YEARS

def update_performance_stats(render_time, current_time):
    """
    Update performance statistics for admin monitoring.
    
    This function is called on EVERY request (high frequency),
    so it must be fast and use memory cache for speed.
    
    Args:
        render_time: Time taken to render the page in seconds
        current_time: Current time (required)
    """
    # Skip if Flask-MonitoringDashboard is enabled (it handles this automatically)
    if FLASK_DASHBOARD:
        return
        
    stats_key = "admin_performance_stats"
    stats = g_cm.get(stats_key) or {
        "times": [],
        "count": 0,
        "hourly_requests": {},  # Track requests per hour
        "first_request_time": current_time
    }
    
    # Use hour since epoch for consistent tracking
    current_hour = int(current_time / 3600)
    
    # Initialize hourly request count if not exists
    if current_hour not in stats["hourly_requests"]:
        stats["hourly_requests"][current_hour] = 0
    
    # Update hourly request count
    stats["hourly_requests"][current_hour] += 1
    
    # Clean up old hourly data (keep last 24 hours)
    old_hour = current_hour - 24
    stats["hourly_requests"] = {h: count for h, count in stats["hourly_requests"].items() if h > old_hour}
    
    stats["count"] += 1
    
    # Skip the first request (cold start)
    if stats["count"] > 1:
        stats["times"].append(render_time)
        
        # Keep only last 100 measurements
        if len(stats["times"]) > 100:
            stats["times"] = stats["times"][-100:]
    
    # Store back
    g_cm.set(stats_key, stats, ttl=EXPIRE_DAY)

def get_admin_stats_html():
    """Generate HTML for admin performance stats."""
    # Skip if Flask-MonitoringDashboard is enabled (it has its own dashboard)
    if FLASK_DASHBOARD:
        return None
        
    stats_key = "admin_performance_stats"
    stats = g_cm.get(stats_key)
    
    if not stats or not stats.get("times"):
        return None
    
    times = stats["times"]
    if len(times) < 3:
        return None
    
    # Calculate statistics
    sorted_times = sorted(times)
    min_time = min(sorted_times)
    max_time = max(sorted_times)
    avg_time = sum(times) / len(times)
    count = stats.get("count", len(times))
    
    # Calculate request counts for different time windows
    current_time = time.time()
    current_hour = int(current_time / 3600)
    
    # Get request counts for different time windows
    hourly_requests = stats.get("hourly_requests", {})
    requests_1h = sum(count for hour, count in hourly_requests.items() if hour == current_hour)
    requests_6h = sum(count for hour, count in hourly_requests.items() if hour >= current_hour - 5)  # Include current hour + 5 previous
    requests_12h = sum(count for hour, count in hourly_requests.items() if hour >= current_hour - 11)  # Include current hour + 11 previous    
    # Calculate uptime
    first_request_time = stats.get("first_request_time", time.time())
    uptime_seconds = time.time() - first_request_time
    uptime_str = str(datetime.timedelta(seconds=int(uptime_seconds)))
    
    return f'''
    <div style="position: fixed; top: 10px; right: 10px; background: #ccc; color: #333; padding: 10px; 
                border-radius: 5px; font-family: monospace; font-size: 12px; z-index: 9999; 
                border: 1px solid #999; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <strong>Admin Stats (Page Render)</strong><br>
        Uptime: {uptime_str}<br>
        Total Requests: {count}<br>
        Requests (1h): {requests_1h}<br>
        Requests (6h): {requests_6h}<br>
        Requests (12h): {requests_12h}<br>
        Min: {min_time:.3f}s<br>
        Max: {max_time:.3f}s<br>
        Avg: {avg_time:.3f}s<br>
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
