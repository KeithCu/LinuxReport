"""
weather.py

Provides functions to fetch and cache weather data, including a fake API mode for testing. Includes HTML rendering for weather forecasts.
"""

import os
import time
from collections import defaultdict
# Standard library imports
from datetime import date as date_obj
from datetime import datetime
from bisect import bisect_left

import geoip2.database
# Third-party imports
import requests
from geoip2.errors import GeoIP2Error

# Local imports
from shared import DEBUG, SPATH, DiskCacheWrapper

# --- Configurable cache bucketing ---
WEATHER_BUCKET_PRECISION = 1  # Decimal places for lat/lon rounding (lower = larger area per bucket)

g_c = DiskCacheWrapper(SPATH)

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
if DEBUG:
    WEATHER_CACHE_TIMEOUT = 30
else:
    WEATHER_CACHE_TIMEOUT = 3600 * 4  # 4 hours

FAKE_API = False  # Fake Weather API calls

# Add default coordinates for weather (Detroit, MI)
DEFAULT_WEATHER_LAT = "42.3297"
DEFAULT_WEATHER_LON = "83.0425"

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
        except GeoIP2Error:
            return None, None


RL_KEY = "weather_api_call_timestamps_v2"
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_COUNT = 60   # calls per window

def rate_limit_check():
    """Enforces RATE_LIMIT_COUNT calls per RATE_LIMIT_WINDOW seconds."""
    now = time.time()
    timestamps = g_c.get(RL_KEY) or []

    valid_start_time = now - RATE_LIMIT_WINDOW
    start_index = bisect_left(timestamps, valid_start_time)

    timestamps_in_window = timestamps[start_index:]

    if len(timestamps_in_window) >= RATE_LIMIT_COUNT:
        # Calculate wait time based on the oldest timestamp in the current window
        # This ensures we wait until the oldest request expires from the window
        oldest_in_window = timestamps_in_window[0]
        wait_time = (oldest_in_window + RATE_LIMIT_WINDOW) - now
        if wait_time > 0:
            time.sleep(wait_time)
            now = time.time()

    timestamps_in_window.append(now)

    g_c.put(RL_KEY, timestamps_in_window, timeout=RATE_LIMIT_WINDOW + 1)

CACHE_ENTRY_PREFIX = 'weather:cache_entry:'

def save_weather_cache_entry(lat, lon, data):
    """Saves a weather data entry to the cache with timestamp and date, using bucketed key."""
    key = _bucket_key(lat, lon)
    now = time.time()
    today_str = date_obj.today().isoformat()
    entry = {'lat': str(lat), 'lon': str(lon), 'data': data, 'timestamp': now, 'date': today_str}
    g_c.put(CACHE_ENTRY_PREFIX + key, entry, timeout=WEATHER_CACHE_TIMEOUT)

def get_bucketed_weather_cache(lat, lon):
    """Returns cached weather data for the bucketed (lat, lon) if present and same day."""
    key = _bucket_key(lat, lon)
    entry = g_c.get(CACHE_ENTRY_PREFIX + key)
    today_str = date_obj.today().isoformat()
    now = time.time()
    if entry and entry.get('date') == today_str and now - entry.get('timestamp', 0) < WEATHER_CACHE_TIMEOUT:
        return entry['data']
    return None


def get_weather_data(lat=None, lon=None, ip=None):
    """Fetches weather data for given coordinates or IP address, using cache or API."""
    # If IP is provided, use it to get lat/lon
    if ip and (not lat or not lon):
        lat, lon = get_location_from_ip(ip)
        if not lat or not lon:
            lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON
    if not lat or not lon:
        lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON

    # Always use today's date for cache key
    bucketed_weather = get_bucketed_weather_cache(lat, lon)
    if bucketed_weather:
        return bucketed_weather, 200

    if FAKE_API:
        fake_data = {
            "daily": [
                {
                    "dt": int(datetime.now().replace(hour=12, minute=0, second=0, microsecond=0).timestamp()) + i * 86400,
                    "temp_min": 10 + i,
                    "temp_max": 20 + i,
                    "precipitation": 5 * i,
                    "weather": "Clear" if i % 2 == 0 else "Cloudy",
                    "weather_icon": "01d" if i % 2 == 0 else "02d"
                } for i in range(5)
            ]
        }
        return fake_data, 200

    try:
        rate_limit_check()
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=imperial&appid={WEATHER_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        weather_data = response.json()
        # Determine city name for logging
        city_name = weather_data.get("city", {}).get("name", "Unknown location")

        daily_data = defaultdict(list)
        for entry in weather_data.get("list", []):
            date_str = entry.get("dt_txt", "")[:10]
            daily_data[date_str].append(entry)

        processed_data = {"daily": []}
        today_date = datetime.now().date()
        days_added = 0
        for date, entries in sorted(daily_data.items()):
            entry_date = datetime.strptime(date, "%Y-%m-%d").date()
            if entry_date < today_date:
                continue
            if days_added >= 5:
                break
            temp_mins = [e["main"]["temp_min"] for e in entries if "main" in e and "temp_min" in e["main"]]
            temp_maxs = [e["main"]["temp_max"] for e in entries if "main" in e and "temp_max" in e["main"]]
            pops = [e.get("pop", 0) for e in entries]
            rain_total = sum(e.get("rain", {}).get("3h", 0) for e in entries if "rain" in e)

            # Use noon entry if possible, else first
            preferred_entry = next((e for e in entries if "12:00:00" in e.get("dt_txt", "")), entries[0])
            weather_main = preferred_entry["weather"][0]["main"] if preferred_entry.get("weather") and len(preferred_entry["weather"]) > 0 else "N/A"
            weather_icon = preferred_entry["weather"][0]["icon"] if preferred_entry.get("weather") and len(preferred_entry["weather"]) > 0 else "01d"

            processed_data["daily"].append({
                "dt": int(datetime.strptime(date, "%Y-%m-%d").replace(hour=12).timestamp()),
                "temp_min": min(temp_mins) if temp_mins else None,
                "temp_max": max(temp_maxs) if temp_maxs else None,
                "precipitation": round(max(pops) * 100) if pops else 0,
                "rain": round(rain_total, 2),
                "weather": weather_main,
                "weather_icon": weather_icon
            })
            days_added += 1

        save_weather_cache_entry(lat, lon, processed_data)
        # Single log: print city and current temperature
        try:
            today_entry = processed_data["daily"][0]
            current_temp = round(today_entry.get("temp_max", today_entry.get("temp_min", 0)))
        except (IndexError, KeyError, TypeError):
            current_temp = "N/A"
        print(f"Weather API result: city: {city_name}, temp: {current_temp}°F")
        return processed_data, 200

    except requests.exceptions.RequestException as e:
        print("Weather API error: Failed to fetch weather data from API")
        return {"error": "Failed to fetch weather data from API"}, 500
    except (ValueError, KeyError, TypeError) as e:
        # Always log error result
        print("Weather API error: Failed to process weather data")
        return {"error": "Failed to process weather data"}, 500



# Sample Python code for localizing 'Today' (commented out):
# import locale
# from datetime import date
# import babel.dates
#
# user_locale = 'fr_FR'  # Example: get from user settings
# today = date.today()
# today_label = babel.dates.format_timedelta(
#     today - today, locale=user_locale, granularity='day', add_direction=True
# )
# print(today_label)  # Should print 'aujourd'hui' in French

# HTML rendering unused because weather is rendered via JavaScript. 
# Separate page cache entries would be necessary for server-side rendering.
# Data is cached on client and server, so not a priority.
def get_weather_html(ip):
    weather_data, status_code = get_weather_data(ip=ip)
    if status_code == 200 and weather_data and "daily" in weather_data and len(weather_data["daily"]) > 0:
        forecast_html = '<div id="weather-forecast" class="weather-forecast">'
        for i, day in enumerate(weather_data["daily"]):
            try:
                d = datetime.fromtimestamp(day["dt"])
                day_name = "Today" if i == 0 else d.strftime("%a")
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
            except (KeyError, TypeError, ValueError) as e:
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

def test_weather_api_with_ips():
    """Test get_location_from_ip and get_weather_data for a list of IP addresses."""
    test_ips = [
        "100.19.21.35",
        "102.218.61.15",
    ]
    for ip in test_ips:
        lat, lon = get_location_from_ip(ip)
        print(f"IP: {ip} => lat: {lat}, lon: {lon}")
        data, status = get_weather_data(ip=ip)
        print(f"  Weather status: {status}, data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}\n")

if __name__ == "__main__":
    print("Running weather API tests with test IP addresses...")
    test_weather_api_with_ips()