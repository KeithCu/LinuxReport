"""
weather.py

Provides functions to fetch and cache weather data, including a fake API mode for testing. Includes HTML rendering for weather forecasts.
"""

# Standard library imports
from datetime import datetime
import time
import math

# Third-party imports
import requests
import geoip2.database
import os

# Local imports
from shared import g_c, DEBUG

WEATHER_API_KEY = "FIXME"  # FIXME: Replace with your actual API key
if DEBUG:
    WEATHER_CACHE_TIMEOUT = 30
else:
    WEATHER_CACHE_TIMEOUT = 3600 * 12  # 12 hours in seconds

FAKE_API = False  # Fake Weather API calls

# Add default coordinates for weather (e.g., San Francisco)
DEFAULT_WEATHER_LAT = "37.7749"
DEFAULT_WEATHER_LON = "-122.4194"

# Configurable proximity threshold (in miles)
WEATHER_CACHE_DISTANCE_MILES = 30  # Can be overridden as needed

# Path to GeoLite2-City.mmdb (prefer /srv/http/LinuxReport2, fallback to script dir)
def _get_geoip_db_path():
    srv_path = os.path.join('/srv/http/LinuxReport2', 'GeoLite2-City.mmdb')
    if os.path.exists(srv_path):
        return srv_path
    return os.path.join(os.path.dirname(__file__), 'GeoLite2-City.mmdb')

GEOIP_DB_PATH = _get_geoip_db_path()

# Helper to get lat/lon from IP address
_geoip_reader = None
def get_location_from_ip(ip):
    global _geoip_reader
    if _geoip_reader is None:
        _geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
    try:
        response = _geoip_reader.city(ip)
        lat = response.location.latitude
        lon = response.location.longitude
        return lat, lon
    except Exception:
        return None, None

def rate_limit_check():
    """Enforces 60 calls/minute and 1 second between calls using g_c (DiskCacheWrapper)."""
    RL_KEY = "weather_api_call_timestamps"
    now = time.time()
    timestamps = g_c.get(RL_KEY) or []
    # Remove timestamps older than 60 seconds
    timestamps = [t for t in timestamps if now - t < 60]
    if timestamps:
        # Enforce at least 1 second between calls
        if now - timestamps[-1] < 1:
            time.sleep(1 - (now - timestamps[-1]))
    if len(timestamps) >= 60:
        wait_time = 60 - (now - timestamps[0])
        if wait_time > 0:
            time.sleep(wait_time)
        now = time.time()
        timestamps = [t for t in timestamps if now - t < 60]

    timestamps.append(time.time())
    g_c.put(RL_KEY, timestamps, timeout=70)

# Helper: Haversine formula to compute distance between two lat/lon points (in miles)
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8  # Earth radius in miles
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Helper: Get all cached weather entries (list of dicts with lat, lon, data, timestamp)
def get_weather_cache_entries():
    entries = g_c.get('weather:cache_entries')
    if not entries:
        entries = []
    # Remove expired entries
    now = time.time()
    entries = [e for e in entries if now - e.get('timestamp', 0) < WEATHER_CACHE_TIMEOUT]
    g_c.put('weather:cache_entries', entries, timeout=WEATHER_CACHE_TIMEOUT)
    return entries

# Helper: Save a new weather cache entry
def save_weather_cache_entry(lat, lon, data):
    entries = get_weather_cache_entries()
    now = time.time()
    entries.append({'lat': str(lat), 'lon': str(lon), 'data': data, 'timestamp': now})
    # Keep only recent entries (optional: limit size)
    if len(entries) > 100:
        entries = entries[-100:]
    g_c.put('weather:cache_entries', entries, timeout=WEATHER_CACHE_TIMEOUT)

# Helper: Find cached weather data within a distance threshold
def find_nearby_weather_cache(lat, lon, distance_miles=WEATHER_CACHE_DISTANCE_MILES):
    entries = get_weather_cache_entries()
    for entry in entries:
        d = haversine(lat, lon, entry['lat'], entry['lon'])
        if d <= distance_miles:
            return entry['data']
    return None

def get_weather_data(lat=None, lon=None, ip=None, cache_distance_miles=WEATHER_CACHE_DISTANCE_MILES):
    """Fetches weather data for given coordinates or IP address, using cache or API."""
    # If IP is provided, use it to get lat/lon
    if ip and (not lat or not lon):
        lat, lon = get_location_from_ip(ip)
        if not lat or not lon:
            # fallback to default
            lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON
    if not lat or not lon:
        lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON

    cache_key = f"weather:{lat}:{lon}"

    # Proximity-based cache lookup
    nearby_weather = find_nearby_weather_cache(lat, lon, distance_miles=cache_distance_miles)
    if nearby_weather:
        return nearby_weather, 200

    # Check cache (legacy, exact match)
    cached_weather = g_c.get(cache_key)
    if cached_weather:
        return cached_weather, 200

    # Use fake data if enabled
    if FAKE_API:
        fake_data = {
            "daily": [
                {
                    "dt": int(datetime.now().timestamp()) + i * 86400,
                    "temp_min": 10 + i,
                    "temp_max": 20 + i,
                    "precipitation": 5 * i,
                    "weather": "Clear" if i % 2 == 0 else "Cloudy",
                    "weather_icon": "01d" if i % 2 == 0 else "02d"
                } for i in range(5)
            ]
        }
        return fake_data, 200

    # Fetch from real API
    try:
        rate_limit_check()  # Enforce rate limiting before API call
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=imperial&appid={WEATHER_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        weather_data = response.json()

        from collections import defaultdict
        daily_data = defaultdict(list)
        for entry in weather_data.get("list", []):
            date_str = entry.get("dt_txt", "")[:10]  # 'YYYY-MM-DD'
            daily_data[date_str].append(entry)

        processed_data = {"daily": []}
        for i, (date, entries) in enumerate(sorted(daily_data.items())[:5]):
            temp_mins = [e["main"]["temp_min"] for e in entries if "main" in e and "temp_min" in e["main"]]
            temp_maxs = [e["main"]["temp_max"] for e in entries if "main" in e and "temp_max" in e["main"]]
            pops = [e.get("pop", 0) for e in entries]
            rain_total = sum(e.get("rain", {}).get("3h", 0) for e in entries if "rain" in e)
            # Prefer weather at 12:00:00, else first
            midday = next((e for e in entries if "12:00:00" in e.get("dt_txt", "")), entries[0])
            weather_main = midday["weather"][0]["main"] if midday.get("weather") and len(midday["weather"]) > 0 else "N/A"
            weather_icon = midday["weather"][0]["icon"] if midday.get("weather") and len(midday["weather"]) > 0 else "01d"
            processed_data["daily"].append({
                "dt": int(datetime.strptime(date, "%Y-%m-%d").timestamp()),
                "temp_min": min(temp_mins) if temp_mins else None,
                "temp_max": max(temp_maxs) if temp_maxs else None,
                "precipitation": round(max(pops) * 100) if pops else 0,  # Max pop for the day as percent
                "rain": round(rain_total, 2),
                "weather": weather_main,
                "weather_icon": weather_icon
            })

        g_c.put(cache_key, processed_data, timeout=WEATHER_CACHE_TIMEOUT)
        save_weather_cache_entry(lat, lon, processed_data)
        return processed_data, 200

    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return {"error": "Failed to fetch weather data from API"}, 500
    except Exception as e:
        print(f"Error processing weather data: {e}")
        return {"error": "Failed to process weather data"}, 500

def get_weather_html():
    """Returns HTML for displaying the 5-day weather forecast, using cached or fake data if available. If not, returns fallback HTML for client-side JS to fetch weather."""
    weather_data, status_code = get_weather_data(DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON)

    if status_code == 200 and weather_data and "daily" in weather_data and len(weather_data["daily"]) > 0:
        forecast_html = '<div id="weather-forecast" class="weather-forecast">'
        for day in weather_data["daily"]:
            try:
                d = datetime.fromtimestamp(day["dt"])
                day_name = "Today" if d.date() == datetime.now().date() else d.strftime("%a")
                temp_max = round(day.get("temp_max", 0))
                temp_min = round(day.get("temp_min", 0))
                precipitation = round(day.get("precipitation", 0))
                weather_icon = day.get("weather_icon", "01d")
                weather_desc = day.get("weather", "N/A")

                forecast_html += f'''
                    <div class="weather-day">
                        <div class="weather-day-name">{day_name}</div>
                        <img class="weather-icon" src="https://openweathermap.org/img/wn/{weather_icon}.png" alt="{weather_desc}">
                        <div class="weather-temp">
                            <span class="temp-max">{temp_max}°</span> /
                            <span class="temp-min">{temp_min}°</span>
                        </div>
                        <div class="weather-precip">{precipitation}% precip</div>
                    </div>
                '''
            except Exception as e:
                print(f"Error processing weather day data: {e}")
                forecast_html += '<div class="weather-day error">Error loading day</div>'

        forecast_html += '</div>'
        return f'''
        <div id="weather-container" class="weather-container">
            <h3>5-Day Weather</h3>
            {forecast_html}
        </div>
        '''
    else:
        # Always render fallback HTML so JS can fetch and display weather later
        return """
        <div id="weather-container" class="weather-container">
            <h3>5-Day Weather</h3>
            <div id="weather-loading">Loading weather data...</div>
            <div id="weather-error" style="display: none; color: red;">Could not load weather data.</div>
            <div id="weather-forecast" style="display: none;"></div>
        </div>
        """
