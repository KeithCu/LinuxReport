import time
import datetime
from shared import FLASK_DASHBOARD, g_cm, EXPIRE_DAY

def update_performance_stats(render_time):
    """
    Update performance statistics for admin monitoring.
    
    This function is called on EVERY request (high frequency),
    so it must be fast and use memory cache for speed.
    
    Args:
        render_time: Time taken to render the page in seconds
    """
    # Skip if Flask-MonitoringDashboard is enabled (it handles this automatically)
    if FLASK_DASHBOARD:
        return
        
    stats_key = "admin_performance_stats"
    stats = g_cm.get(stats_key) or {
        "times": [],
        "count": 0,
        "hourly_requests": {},  # Track requests per hour
        "first_request_time": time.time()
    }
    
    current_time = time.time()
    current_hour = int(current_time / 3600)  # Get current hour timestamp
    
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
    requests_6h = sum(count for hour, count in hourly_requests.items() if hour >= current_hour - 6)
    requests_12h = sum(count for hour, count in hourly_requests.items() if hour >= current_hour - 12)
    
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
        Avg: {avg_time:.3f}s
    </div>
    '''
