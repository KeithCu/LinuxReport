"""
visitor_map.py

Records visitor IPs with GeoIP lookups and exposes a public /map page
showing visits (with/without bots) on a Leaflet map. Data is stored in g_c
and pruned to the last 48 hours.

Also provides a caching tile proxy (/tiles/) that fetches OpenStreetMap tiles
on first request, caches them on disk, and serves cached copies thereafter.
"""

import io
import os
import time
import threading
import urllib.request

from flask import request, render_template, send_file, abort, make_response

from shared import g_c, g_logger, EXPIRE_YEARS, FAVICON, LOGO_URL, WEB_TITLE, USER_AGENT
from request_utils import is_web_bot
from weather import get_location_from_ip, DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON

VISITOR_MAP_CACHE_KEY = "visitor_map_visits"
VISIT_WINDOW_SEC = 48 * 3600  # 48 hours

# ── Tile caching proxy configuration ──────────────────────────────────────
TILE_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tile_cache")
TILE_CACHE_TTL = 7 * 86400  # 7 days
TILE_SUBDOMAINS = ["a", "b", "c"]

# Per-tile locks for request deduplication: only one upstream fetch per tile
_tile_locks = {}
_tile_locks_lock = threading.Lock()

# A minimal 1x1 gray PNG (67 bytes) returned when upstream fetch fails
_GRAY_TILE = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
    b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
    b'\x00\x00\x0cIDATx\x9cc\xb8\xb0\xb0\x00\x00\x00\xc2'
    b'\x00\x01\x1a\x13\x8c\xa0\x00\x00\x00\x00IEND\xaeB`\x82'
)


def _get_tile_lock(key):
    """Return a per-tile lock, creating one if needed."""
    with _tile_locks_lock:
        if key not in _tile_locks:
            _tile_locks[key] = threading.Lock()
        return _tile_locks[key]


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
    """Register /map route, tile proxy, and after_request hook to record visits."""

    @flask_app.after_request
    def _record_visit_after_request(response):
        path = request.path or ""
        if (path.startswith("/static/") or path.startswith("/tiles/")
                or path.rstrip("/") == "/map"):
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

    @flask_app.route("/tiles/<int:z>/<int:x>/<int:y>.png")
    def tile_proxy(z, x, y):
        """
        Caching tile proxy for OpenStreetMap tiles.
        Serves from disk cache when fresh, fetches upstream on cache miss.
        Concurrent requests for the same tile are deduplicated via per-tile locks.
        """
        cache_path = os.path.join(TILE_CACHE_DIR, str(z), str(x), f"{y}.png")
        tile_key = f"{z}/{x}/{y}"
        lock = _get_tile_lock(tile_key)

        with lock:
            # Serve from cache if the file exists and is fresh
            if os.path.exists(cache_path):
                age = time.time() - os.path.getmtime(cache_path)
                if age < TILE_CACHE_TTL:
                    g_logger.debug("Tile cache hit: %s (age %.0fs)", tile_key, age)
                    resp = make_response(send_file(cache_path, mimetype="image/png"))
                    resp.headers["Cache-Control"] = "public, max-age=86400"
                    return resp

            # Cache miss — fetch from OSM
            g_logger.info("Tile cache miss, fetching upstream: %s", tile_key)
            subdomain = TILE_SUBDOMAINS[(x + y) % len(TILE_SUBDOMAINS)]
            url = f"https://{subdomain}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=10) as resp_upstream:
                    data = resp_upstream.read()
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "wb") as f:
                    f.write(data)
                g_logger.info("Tile cached: %s (%d bytes)", tile_key, len(data))
                resp = make_response(send_file(cache_path, mimetype="image/png"))
                resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp
            except Exception as exc:
                g_logger.warning("Tile fetch failed for %s: %s", tile_key, exc)
                # Return a gray tile so the map degrades gracefully
                resp = make_response(send_file(
                    io.BytesIO(_GRAY_TILE), mimetype="image/png"))
                resp.headers["Cache-Control"] = "no-cache"
                return resp
