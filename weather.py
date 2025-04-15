"""
weather.py

Provides functions to fetch and cache weather data, including a fake API mode for testing. Includes HTML rendering for weather forecasts.
"""

# Standard library imports
from datetime import datetime, date as date_obj
from collections import OrderedDict, defaultdict
import time
import os

# Third-party imports
import requests
import geoip2.database

# Local imports
from shared import SPATH, DiskCacheWrapper, DEBUG

# --- Configurable cache bucketing ---
WEATHER_BUCKET_PRECISION = 1  # Decimal places for lat/lon rounding (lower = larger area per bucket)
WEATHER_CACHE_MAX_ENTRIES = 500

g_c = DiskCacheWrapper(SPATH)

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
if DEBUG:
    WEATHER_CACHE_TIMEOUT = 30
else:
    WEATHER_CACHE_TIMEOUT = 3600 * 4  # 4 hours in seconds

FAKE_API = False  # Fake Weather API calls

# Add default coordinates for weather (Detroit, MI)
DEFAULT_WEATHER_LAT = "42.3297"
DEFAULT_WEATHER_LON = "83.0425"

RL_KEY = "weather_api_call_timestamps"

# --- Bucketing helpers ---
def _round_coord(val, precision=WEATHER_BUCKET_PRECISION):
    return round(float(val), int(precision))

def _bucket_key(lat, lon, precision=WEATHER_BUCKET_PRECISION):
    return f"{_round_coord(lat, precision):.{precision}f},{_round_coord(lon, precision):.{precision}f}"

# --- GeoIP ---
def _get_geoip_db_path():
    srv_path = os.path.join('/srv/http/LinuxReport2', 'GeoLite2-City.mmdb')
    if os.path.exists(srv_path):
        return srv_path
    return os.path.join(os.path.dirname(__file__), 'GeoLite2-City.mmdb')

GEOIP_DB_PATH = _get_geoip_db_path()

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
    """Enforces 60 calls/minute and 1 second between calls."""
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

# --- Weather cache helpers (bucketed) ---
CACHE_ENTRY_PREFIX = 'weather:cache_entry:'
CACHE_KEYS_KEY = 'weather:cache_entry_keys'

def get_weather_cache_entries():
    """Returns an OrderedDict of bucket_key -> entry, sorted by most recent timestamp."""
    keys = g_c.get(CACHE_KEYS_KEY) or []
    now = time.time()
    entries = {}
    for key in keys:
        entry = g_c.get(CACHE_ENTRY_PREFIX + key)
        if entry and now - entry.get('timestamp', 0) < WEATHER_CACHE_TIMEOUT:
            entries[key] = entry
    # Sort by most recent timestamp
    sorted_items = sorted(entries.items(), key=lambda item: item[1].get('timestamp', 0), reverse=True)
    od = OrderedDict(sorted_items)
    # Prune if too many
    while len(od) > WEATHER_CACHE_MAX_ENTRIES:
        oldest_key, _ = od.popitem(last=False)
        g_c.delete(CACHE_ENTRY_PREFIX + oldest_key)
        keys.remove(oldest_key)
    g_c.put(CACHE_KEYS_KEY, list(od.keys()), timeout=WEATHER_CACHE_TIMEOUT)
    return od

def save_weather_cache_entry(lat, lon, data):
    """Saves a weather data entry to the cache with timestamp and date, using bucketed key."""
    key = _bucket_key(lat, lon)
    now = time.time()
    today_str = date_obj.today().isoformat()
    entry = {'lat': str(lat), 'lon': str(lon), 'data': data, 'timestamp': now, 'date': today_str}
    g_c.put(CACHE_ENTRY_PREFIX + key, entry, timeout=WEATHER_CACHE_TIMEOUT)
    keys = g_c.get(CACHE_KEYS_KEY) or []
    if key in keys:
        keys.remove(key)
    keys.append(key)
    # Prune if too many
    while len(keys) > WEATHER_CACHE_MAX_ENTRIES:
        oldest_key = keys.pop(0)
        g_c.delete(CACHE_ENTRY_PREFIX + oldest_key)
    g_c.put(CACHE_KEYS_KEY, keys, timeout=WEATHER_CACHE_TIMEOUT)

def get_bucketed_weather_cache(lat, lon):
    """Returns cached weather data for the bucketed (lat, lon) if present and same day."""
    key = _bucket_key(lat, lon)
    entry = g_c.get(CACHE_ENTRY_PREFIX + key)
    today_str = date_obj.today().isoformat()
    now = time.time()
    if entry and entry.get('date') == today_str and now - entry.get('timestamp', 0) < WEATHER_CACHE_TIMEOUT:
        return entry['data']
    return None

# ---
def get_weather_data(lat=None, lon=None, ip=None):
    """Fetches weather data for given coordinates or IP address, using cache or API."""
    # If IP is provided, use it to get lat/lon
    if ip and (not lat or not lon):
        lat, lon = get_location_from_ip(ip)
        if not lat or not lon:
            # fallback to default
            lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON
    if not lat or not lon:
        lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON

    # Bucketed cache lookup
    bucketed_weather = get_bucketed_weather_cache(lat, lon)
    if (bucketed_weather):
        return bucketed_weather, 200

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
        print(f"Fetching weather from API for lat={lat}, lon={lon}") # Log API request
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=imperial&appid={WEATHER_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        weather_data = response.json()

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

            # Determine if today or future day
            is_today = datetime.strptime(date, "%Y-%m-%d").date() == datetime.now().date()

            # Prefer earliest icon for today, noon icon for future days
            if is_today:
                preferred_entry = entries[0]
            else:
                preferred_entry = next((e for e in entries if "12:00:00" in e.get("dt_txt", "")), entries[0])

            weather_main = preferred_entry["weather"][0]["main"] if preferred_entry.get("weather") and len(preferred_entry["weather"]) > 0 else "N/A"
            weather_icon = preferred_entry["weather"][0]["icon"] if preferred_entry.get("weather") and len(preferred_entry["weather"]) > 0 else "01d"

            processed_data["daily"].append({
                "dt": int(datetime.strptime(date, "%Y-%m-%d").timestamp()),
                "temp_min": min(temp_mins) if temp_mins else None,
                "temp_max": max(temp_maxs) if temp_maxs else None,
                "precipitation": round(max(pops) * 100) if pops else 0,  # Max pop for the day as percent
                "rain": round(rain_total, 2),
                "weather": weather_main,
                "weather_icon": weather_icon
            })

        save_weather_cache_entry(lat, lon, processed_data)
        return processed_data, 200

    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return {"error": "Failed to fetch weather data from API"}, 500
    except Exception as e:
        print(f"Error processing weather data: {e}")
        return {"error": "Failed to process weather data"}, 500

# --- HTML rendering 
def get_weather_html(ip):
    """Returns HTML for displaying the 5-day weather forecast, using cached or fake data if available. If not, returns fallback HTML for client-side JS to fetch weather."""
    weather_data, status_code = get_weather_data(ip=ip)

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
        return get_default_weather_html()

def get_default_weather_html():
    """Returns the default HTML for the weather container (loading state)."""
    return '''
    <div id="weather-container" class="weather-container">
        <h3>5-Day Weather</h3>
        <div id="weather-loading">Loading weather data...</div>
        <div id="weather-error" style="display: none; color: red;">Could not load weather data.</div>
        <div id="weather-forecast" style="display: none;"></div>
    </div>
    '''
