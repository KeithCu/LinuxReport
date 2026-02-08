"""
visitor_map.py

Records visitor IPs with GeoIP lookups and exposes a public /map page
showing visits (with/without bots) on a Leaflet map. Data is stored in g_c
and pruned to the last 48 hours.

Visits are buffered in memory (deduped by IP) and flushed to g_c every few
seconds by a daemon thread — one SQLite read + one write per flush cycle.
record_visit() itself is near-zero cost (dict lookup + insert).

Also provides a caching tile proxy (/tiles/) that fetches OpenStreetMap tiles
on first request, caches them on disk, and serves cached copies thereafter.
"""

import io
import os
import time
import threading
import urllib.request
from functools import lru_cache

from flask import request, render_template, send_file, abort, make_response

from shared import g_c, g_logger, limiter, EXPIRE_YEARS, FAVICON, LOGO_URL, WEB_TITLE, USER_AGENT
from weather import get_location_from_ip, DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON

VISITOR_MAP_CACHE_KEY = "visitor_map_visits_v2"
VISIT_WINDOW_SEC = 48 * 3600  # 48 hours

# ── Visit buffering ────────────────────────────────────────────────────────
# Visits accumulate in an in-memory dict keyed by IP (natural dedup) and are
# flushed to g_c every _FLUSH_INTERVAL seconds.  GeoIP resolution happens in
# the flusher thread, not on the request path.  record_visit() is near-free.
_pending_visits = {}                  # ip → (is_bot, timestamp)
_pending_lock = threading.Lock()
_FLUSH_INTERVAL = 60                  # seconds between flushes
_PRUNE_INTERVAL = 300                 # prune stale entries every 5 minutes
_last_prune = 0.0


@lru_cache(maxsize=4096)
def _cached_geoip(ip):
    """GeoIP lookup with per-process LRU cache — avoids redundant MMDB reads."""
    try:
        return get_location_from_ip(ip)
    except Exception:
        return None

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


def record_visit(ip, is_bot):
    """
    Buffer a visit in memory — just a dict lookup + insert (~100ns).
    GeoIP resolution is deferred to the flusher thread.
    """
    with _pending_lock:
        if ip not in _pending_visits:
            _pending_visits[ip] = (is_bot, time.time())


def _flush_visits():
    """Daemon thread: GeoIP-resolve buffered IPs and merge into g_c — one read + one write per cycle."""
    global _last_prune
    while True:
        time.sleep(_FLUSH_INTERVAL)
        with _pending_lock:
            if not _pending_visits:
                continue
            batch = dict(_pending_visits)   # ip → (is_bot, timestamp)
            _pending_visits.clear()
        try:
            # Resolve GeoIP in this thread, not on the request path
            resolved = []
            for ip, (is_bot, ts) in batch.items():
                coords = _cached_geoip(ip)
                if coords is not None and not _is_fallback_coords(*coords):
                    resolved.append((coords[0], coords[1], is_bot, ts))
            if not resolved:
                continue
            visits = g_c.get(VISITOR_MAP_CACHE_KEY) or []
            now = time.time()
            # Periodic prune — not every flush, just every _PRUNE_INTERVAL
            if now - _last_prune > _PRUNE_INTERVAL:
                cutoff = now - VISIT_WINDOW_SEC
                visits = [v for v in visits if v[3] > cutoff]
                _last_prune = now
            visits.extend(resolved)
            g_c.put(VISITOR_MAP_CACHE_KEY, visits, timeout=EXPIRE_YEARS)
        except Exception:
            g_logger.exception("Failed to flush visitor map visits")


threading.Thread(target=_flush_visits, daemon=True, name="visitor-map-flusher").start()


def _get_visits_last_48h():
    """Return visit dicts from g_c + unflushed buffer, filtered to last 48h."""
    visits = g_c.get(VISITOR_MAP_CACHE_KEY) or []
    with _pending_lock:
        pending = dict(_pending_visits)    # ip → (is_bot, timestamp)
    cutoff = time.time() - VISIT_WINDOW_SEC
    result = [{"lat": v[0], "lon": v[1], "is_bot": v[2]} for v in visits if v[3] > cutoff]
    # Resolve any unflushed visits for the map view
    for ip, (is_bot, ts) in pending.items():
        if ts > cutoff:
            coords = _cached_geoip(ip)
            if coords is not None and not _is_fallback_coords(*coords):
                result.append({"lat": coords[0], "lon": coords[1], "is_bot": is_bot})
    return result


def init_visitor_map_routes(flask_app):
    """Register /map route and tile proxy. Visits are recorded by calling record_visit() from routes."""

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
    @limiter.exempt
    def tile_proxy(z, x, y):
        """
        Caching tile proxy for OpenStreetMap tiles.
        Serves from disk cache when fresh, fetches upstream on cache miss.
        Concurrent requests for the same tile are deduplicated via per-tile locks.
        """
        # Reject out-of-range coordinates (e.g. negative x from Leaflet edge panning)
        max_tile = (1 << z) - 1  # 2^z - 1
        if x < 0 or y < 0 or x > max_tile or y > max_tile:
            resp = make_response(send_file(
                io.BytesIO(_GRAY_TILE), mimetype="image/png"))
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp

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
