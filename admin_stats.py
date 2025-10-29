import time
import datetime
from shared import FLASK_DASHBOARD, g_cm, EXPIRE_DAY, g_c, EXPIRE_YEARS, ALL_URLS, SITE_URLS, MODE, TZ
from typing import Dict, List, Optional

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
    stats = g_cm.get(stats_key) or {
        "times": [],
        "count": 0,
        "hourly_requests": {},  # Track requests per hour
        "first_request_time": current_time,
        "last_cleanup_hour": None  # Track when we last cleaned up
    }
    
    # Use hour since epoch for consistent tracking
    current_hour = int(current_time / 3600)
    
    # Initialize hourly request count if not exists
    if current_hour not in stats["hourly_requests"]:
        stats["hourly_requests"][current_hour] = 0
    
    # Update hourly request count
    stats["hourly_requests"][current_hour] += 1
    
    # Only clean up old hourly data when we've moved to a new hour
    # This reduces cleanup from every request to once per hour
    last_cleanup_hour = stats.get("last_cleanup_hour")
    if last_cleanup_hour != current_hour:
        old_hour = current_hour - 24
        hourly_requests = stats["hourly_requests"]
        
        # Only clean up if we have old data to remove
        if hourly_requests:
            # Find keys to remove (more efficient than dict comprehension)
            keys_to_remove = []
            for hour in hourly_requests:
                if hour <= old_hour:
                    keys_to_remove.append(hour)
            
            # Remove old entries in-place (faster than creating new dict)
            for key in keys_to_remove:
                del hourly_requests[key]
        
        stats["last_cleanup_hour"] = current_hour
    
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
    <div style="position: fixed; top: 10px; right: 10px; background: #ccc; color: #333; padding: 5px; 
                border-radius: 5px; font-size: 10px; z-index: 9999; 
                border: 1px solid #999; box-shadow: 0 2px 4px rgba(0,0,0,0.1); line-height: 1.2;">
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

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _format_age(seconds: float) -> str:
    """Format age in seconds to human-readable string."""
    if seconds is None:
        return "Never"
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h"
    else:
        return f"{int(seconds / 86400)}d"

# =============================================================================
# FEED HEALTH TRACKING
# =============================================================================

def get_feed_health_stats() -> Dict:
    """
    Get feed health statistics including last fetch times and status.
    
    Returns:
        dict: Dictionary containing feed health information
    """
    feed_stats = []
    all_fetches = g_c.get('all_last_fetches') or {}
    current_time = time.time()
    
    # Thresholds for feed status
    FRESH_THRESHOLD = 3600  # 1 hour
    STALE_THRESHOLD = 86400  # 24 hours
    
    for url in SITE_URLS:
        rss_info = ALL_URLS.get(url)
        if not rss_info:
            continue
        
        last_fetch = all_fetches.get(url)
        feed_data = g_c.get(url)
        
        # Determine feed status
        if last_fetch is None:
            status = "never_fetched"
            age_seconds = None
        else:
            # Convert datetime to timestamp if needed
            if isinstance(last_fetch, datetime.datetime):
                age_seconds = (datetime.datetime.now(TZ) - last_fetch).total_seconds()
            elif isinstance(last_fetch, (int, float)):
                age_seconds = current_time - last_fetch
            else:
                age_seconds = None
            
            if age_seconds is not None:
                if age_seconds < FRESH_THRESHOLD:
                    status = "healthy"
                elif age_seconds < STALE_THRESHOLD:
                    status = "stale"
                else:
                    status = "error"
            else:
                status = "never_fetched"
        
        # Count entries
        entry_count = 0
        if feed_data and hasattr(feed_data, 'entries'):
            entry_count = len(feed_data.entries)
        
        feed_stats.append({
            'url': url,
            'site_url': rss_info.site_url,
            'logo_alt': rss_info.logo_alt,
            'last_fetch': last_fetch.isoformat() if isinstance(last_fetch, datetime.datetime) else (last_fetch if last_fetch else None),
            'age_seconds': age_seconds,
            'age_formatted': _format_age(age_seconds) if age_seconds is not None else "Never",
            'status': status,
            'entry_count': entry_count
        })
    
    return {
        'feeds': feed_stats,
        'total_feeds': len(feed_stats),
        'healthy_count': sum(1 for f in feed_stats if f['status'] == 'healthy'),
        'stale_count': sum(1 for f in feed_stats if f['status'] == 'stale'),
        'error_count': sum(1 for f in feed_stats if f['status'] == 'error'),
        'never_fetched_count': sum(1 for f in feed_stats if f['status'] == 'never_fetched')
    }

def track_llm_model_usage(model_name: str, success: bool = True):
    """
    Track LLM model usage for analytics.
    
    Args:
        model_name: Name of the LLM model used
        success: Whether the model call was successful
    """
    stats_key = "llm_model_stats"
    stats = g_c.get(stats_key) or {}
    
    if model_name not in stats:
        stats[model_name] = {
            'total_uses': 0,
            'successful_uses': 0,
            'failed_uses': 0,
            'last_used': time.time()
        }
    
    stats[model_name]['total_uses'] += 1
    stats[model_name]['last_used'] = time.time()
    
    if success:
        stats[model_name]['successful_uses'] += 1
    else:
        stats[model_name]['failed_uses'] += 1
    
    g_c.put(stats_key, stats, timeout=EXPIRE_YEARS)

def get_llm_model_stats() -> Dict:
    """
    Get LLM model usage statistics.
    
    Returns:
        dict: Dictionary containing LLM model statistics
    """
    stats_key = "llm_model_stats"
    stats = g_c.get(stats_key) or {}
    
    # Calculate success rates
    model_stats = []
    for model_name, data in stats.items():
        success_rate = 0.0
        if data['total_uses'] > 0:
            success_rate = data['successful_uses'] / data['total_uses']
        
        model_stats.append({
            'model_name': model_name,
            'total_uses': data['total_uses'],
            'successful_uses': data['successful_uses'],
            'failed_uses': data['failed_uses'],
            'success_rate': success_rate,
            'last_used': data['last_used']
        })
    
    # Sort by total uses (descending)
    model_stats.sort(key=lambda x: x['total_uses'], reverse=True)
    
    return {
        'models': model_stats,
        'total_models': len(model_stats),
        'total_uses': sum(m['total_uses'] for m in model_stats)
    }

def get_comprehensive_admin_stats() -> Dict:
    """
    Get comprehensive admin statistics including performance, feed health, and LLM stats.
    
    Returns:
        dict: Dictionary containing all admin statistics
    """
    # Get performance stats
    perf_stats_key = "admin_performance_stats"
    perf_stats = g_cm.get(perf_stats_key) or {}
    
    # Get feed health
    feed_health = get_feed_health_stats()
    
    # Get LLM model stats
    llm_stats = get_llm_model_stats()
    
    # Get rate limit stats
    rate_limit_stats_key = "rate_limit_stats"
    rate_limit_stats = g_c.get(rate_limit_stats_key) or {
        "by_ip": {},
        "by_endpoint": {}
    }
    
    return {
        'performance': {
            'total_requests': perf_stats.get('count', 0),
            'avg_render_time': sum(perf_stats.get('times', [])) / len(perf_stats.get('times', [1])) if perf_stats.get('times') else 0,
            'min_render_time': min(perf_stats.get('times', [0])) if perf_stats.get('times') else 0,
            'max_render_time': max(perf_stats.get('times', [0])) if perf_stats.get('times') else 0,
            'uptime_seconds': time.time() - perf_stats.get('first_request_time', time.time())
        },
        'feed_health': feed_health,
        'llm_models': llm_stats,
        'rate_limits': {
            'unique_ips': len(rate_limit_stats.get('by_ip', {})),
            'unique_endpoints': len(rate_limit_stats.get('by_endpoint', {}))
        },
        'timestamp': datetime.datetime.now(TZ).isoformat()
    }
