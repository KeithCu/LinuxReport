"""
visitor_map.py

Records visitor IPs with GeoIP lookups and exposes a public /map page
showing visits (with/without bots) on a Leaflet map. Data is stored in g_c
and pruned to the last 48 hours.
"""

import time

from flask import request, render_template

from shared import g_c, EXPIRE_YEARS, FAVICON, LOGO_URL, WEB_TITLE
from request_utils import is_web_bot
from weather import get_location_from_ip, DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON

VISITOR_MAP_CACHE_KEY = "visitor_map_visits"
VISIT_WINDOW_SEC = 48 * 3600  # 48 hours


def _is_fallback_coords(lat, lon):
    """Exclude Detroit fallback so we don't cluster fake visits on the map."""
    return (lat == DEFAULT_WEATHER_LAT and lon == DEFAULT_WEATHER_LON)


def record_visit(ip, user_agent):
    """
    Geolocate the IP, determine bot status, append visit to g_c, and prune
    entries older than 48 hours.
    """
    try:
        lat, lon = get_location_from_ip(ip)
    except Exception:
        return
    if _is_fallback_coords(lat, lon):
        return
    is_bot = is_web_bot(user_agent or "")
    visits = g_c.get(VISITOR_MAP_CACHE_KEY) or []
    cutoff = time.time() - VISIT_WINDOW_SEC
    visits = [v for v in visits if v.get("timestamp", 0) > cutoff]
    visits.append({
        "lat": lat,
        "lon": lon,
        "is_bot": is_bot,
        "timestamp": time.time(),
        "country": None,
    })
    g_c.put(VISITOR_MAP_CACHE_KEY, visits, timeout=EXPIRE_YEARS)


def _get_visits_last_48h():
    """Return list of visit dicts from g_c, filtered to last 48 hours."""
    visits = g_c.get(VISITOR_MAP_CACHE_KEY) or []
    cutoff = time.time() - VISIT_WINDOW_SEC
    return [v for v in visits if v.get("timestamp", 0) > cutoff]


def init_visitor_map_routes(flask_app):
    """Register /map route and after_request hook to record visits."""

    @flask_app.after_request
    def _record_visit_after_request(response):
        path = request.path or ""
        if path.startswith("/static/") or path.rstrip("/") == "/map":
            return response
        ip = request.remote_addr
        if not ip:
            return response
        try:
            record_visit(ip, request.headers.get("User-Agent", ""))
        except Exception:
            pass
        return response

    @flask_app.route("/map")
    def map_page():
        visits = _get_visits_last_48h()
        return render_template(
            "visitor_map.html",
            visits=visits,
            favicon=FAVICON,
            title=WEB_TITLE,
            logo_url=LOGO_URL,
        )
