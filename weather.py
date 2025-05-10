"""
weather.py

Provides functions to fetch and cache weather data, including a fake API mode for testing. Includes HTML rendering for weather forecasts.
Supports fetching from LinuxReport.net API as an alternative to OpenWeather API.
"""

import os
import math
import time
from collections import defaultdict
# Standard library imports
from datetime import date as date_obj
from datetime import datetime, timezone
from bisect import bisect_left

import geoip2.database
# Third-party imports
import requests

# Local imports
from shared import g_cs, get_lock, USER_AGENT, TZ

# Global flag to control whether to use LinuxReport.net API instead of OpenWeather
# This allows to share data between servers and for better rate-limit support
# Since all servers are in the same datacenter, it will be very fast.
USE_LINUXREPORT_API = False  # Set to True to use LinuxReport.net API, False to use OpenWeather

# LinuxReport.net API endpoint
LINUXREPORT_WEATHER_API = "https://linuxreport.net/api/weather"
from models import DEBUG

# --- Arbitrary bucket resolution (miles-based) ---
WEATHER_BUCKET_SIZE_MILES = 10  # default bucket diameter in miles (good balance for weather data)
_WEATHER_BUCKET_SIZE_DEG = WEATHER_BUCKET_SIZE_MILES / 69.0  # convert miles to degrees (~1° ≈ 69 miles)

def _bucket_coord(val, bucket_size_deg=_WEATHER_BUCKET_SIZE_DEG):
    """Buckets a coordinate into intervals of bucket_size_deg degrees."""
    return math.floor(float(val) / bucket_size_deg) * bucket_size_deg

def _bucket_key(lat, lon):
    """Generates a cache key based on bucketed lat/lon coordinates."""
    lat_b = _bucket_coord(lat)
    lon_b = _bucket_coord(lon)
    return f"{lat_b:.6f},{lon_b:.6f}"

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
if DEBUG:
    WEATHER_CACHE_TIMEOUT = 300
else:
    WEATHER_CACHE_TIMEOUT = 3600 * 4  # 4 hours

# Add default coordinates for weather (Detroit, MI)
DEFAULT_WEATHER_LAT = "42.3297"
DEFAULT_WEATHER_LON = "83.0425"

# --- GeoIP ---
def _get_geoip_db_path():
    #Database stored in /srv/http/LinuxReport2/GeoLite2-City.mmdb
    srv_path = os.path.join('/srv/http/LinuxReport2', 'GeoLite2-City.mmdb')
    if os.path.exists(srv_path):
        return srv_path
    return os.path.join(os.path.dirname(__file__), 'GeoLite2-City.mmdb')

GEOIP_DB_PATH = _get_geoip_db_path()

# Global reader for GeoIP database to avoid reopening the file
_geoip_reader = None

def get_location_from_ip(ip):
    """Get geolocation coordinates from an IP address using MaxMind GeoIP database."""
    global _geoip_reader
    if _geoip_reader is None:
        _geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)

    try:
        response = _geoip_reader.city(ip)
        lat = response.location.latitude
        lon = response.location.longitude
        return lat, lon
    except:
        return DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON


RL_KEY = "weather_api_call_timestamps_v2"
RATE_LIMIT_WINDOW = 10  # seconds
RATE_LIMIT_COUNT = 10   # calls per window

def rate_limit_check():
    """Enforces RATE_LIMIT_COUNT calls per RATE_LIMIT_WINDOW seconds."""
    now = datetime.now(timezone.utc).timestamp()
    timestamps = g_cs.get(RL_KEY) or []

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
            print(f"Weather API rate limit exceeded. Sleeping for {wait_time:.2f} seconds. Consider increasing WEATHER_BUCKET_SIZE_MILES.")
            now = datetime.now(timezone.utc).timestamp()

    timestamps_in_window.append(now)

    g_cs.put(RL_KEY, timestamps_in_window, timeout=RATE_LIMIT_WINDOW + 1)

CACHE_ENTRY_PREFIX = 'weather:cache_entry:'

def save_weather_cache_entry(lat, lon, data):
    """Saves a weather data entry to the cache with timestamp and date, using bucketed key."""
    key = _bucket_key(lat, lon)
    now = datetime.now(timezone.utc).timestamp()
    today_str = date_obj.today().isoformat()
    entry = {'lat': str(lat), 'lon': str(lon), 'data': data, 'timestamp': now, 'date': today_str}
    g_cs.put(CACHE_ENTRY_PREFIX + key, entry, timeout=WEATHER_CACHE_TIMEOUT)

def get_bucketed_weather_cache(lat, lon):
    """Returns cached weather data for the bucketed (lat, lon) if present and same day."""
    key = _bucket_key(lat, lon)
    entry = g_cs.get(CACHE_ENTRY_PREFIX + key)
    today_str = date_obj.today().isoformat()
    now = datetime.now(timezone.utc).timestamp()
    if entry and entry.get('date') == today_str and now - entry.get('timestamp', 0) < WEATHER_CACHE_TIMEOUT:
        return entry['data']
    return None

def fahrenheit_to_celsius(f_temp):
    """Convert Fahrenheit temperature to Celsius, rounded to a whole number."""
    if f_temp is None:
        return None
    return round((f_temp - 32) * 5/9)

def get_weather_data(lat=None, lon=None, ip=None, units='imperial'):
    """Fetches weather data for given coordinates or IP address, using cache or API.
    Returns a tuple of (data, status_code, fetch_time) where fetch_time is the UTC timestamp
    when the data was fetched from the API."""
    # If IP is provided, use it to get lat/lon
    if ip and (not lat or not lon):
        lat, lon = get_location_from_ip(ip)
        if not lat or not lon:
            lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON
    if not lat or not lon:
        lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON

    bucket_key = _bucket_key(lat, lon)
    lock_key = f"weather_fetch:{bucket_key}"

    # Check cache first (outside the lock for a quick check)
    bucketed_weather = get_bucketed_weather_cache(lat, lon)
    if bucketed_weather:
        # Convert to metric if requested
        if units == 'metric':
            for day in bucketed_weather['daily']:
                day['temp_min'] = fahrenheit_to_celsius(day['temp_min'])
                day['temp_max'] = fahrenheit_to_celsius(day['temp_max'])
        return bucketed_weather, 200, datetime.now(timezone.utc).timestamp()

    # Acquire lock specific to this location bucket
    # The 'with' statement handles waiting and acquisition via __enter__
    with get_lock(lock_key):  # We don't need to assign the lock to a variable

        # Re-check cache *inside* the lock to prevent race condition
        bucketed_weather = get_bucketed_weather_cache(lat, lon)
        if bucketed_weather:
            # Convert to metric if requested
            if units == 'metric':
                for day in bucketed_weather['daily']:
                    day['temp_min'] = fahrenheit_to_celsius(day['temp_min'])
                    day['temp_max'] = fahrenheit_to_celsius(day['temp_max'])
            return bucketed_weather, 200, datetime.now(timezone.utc).timestamp()

        # Cache miss and lock acquired, proceed with API call
        try:
            # Decide whether to use LinuxReport API or OpenWeather
            if USE_LINUXREPORT_API:
                # Use LinuxReport.net API - already processes the data in the correct format
                service_name = "LinuxReport.net"
                url = f"{LINUXREPORT_WEATHER_API}?lat={lat}&lon={lon}&units=imperial"
                start_time = datetime.now(timezone.utc).timestamp()
                response = requests.get(url, timeout=10, headers={'User-Agent': USER_AGENT})
                api_time = datetime.now(timezone.utc).timestamp() - start_time
                response.raise_for_status()
                processed_data = response.json()
                
                # Get fetch time from API response, ensuring it's UTC
                fetch_time = processed_data.get('fetch_time', datetime.now(timezone.utc).timestamp())
                
                # Extract city name from the API response if available
                city_name = processed_data.get("city_name", "Unknown Location")
                
            else:
                # Original OpenWeather API implementation
                service_name = "OpenWeather"
                fetch_time = datetime.now(timezone.utc).timestamp()  # Record the fetch time in UTC
                # Check for valid API key before proceeding
                if not WEATHER_API_KEY or len(WEATHER_API_KEY) < 10:
                    print("Weather API error: WEATHER_API_KEY is missing or too short.")
                    return {"error": "Weather API key is not configured"}, 500, fetch_time
                
                rate_limit_check()
                # Always fetch in imperial (Fahrenheit) for consistent caching
                url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=imperial&appid={WEATHER_API_KEY}"
                start_time = datetime.now(timezone.utc).timestamp()
                response = requests.get(url, timeout=10)
                api_time = datetime.now(timezone.utc).timestamp() - start_time
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

            # Add city information to processed data
            processed_data['city_name'] = city_name
            
            # Save to cache regardless of which API was used
            save_weather_cache_entry(lat, lon, processed_data)

            # Convert to metric if requested *before* logging
            if units == 'metric':
                for day in processed_data['daily']:
                    day['temp_min'] = fahrenheit_to_celsius(day['temp_min'])
                    day['temp_max'] = fahrenheit_to_celsius(day['temp_max'])

            try:
                today_entry = processed_data["daily"][0]
                # Get the temp (already potentially converted)
                current_temp = round(today_entry.get("temp_max", today_entry.get("temp_min", 0)))
                log_unit = 'C' if units == 'metric' else 'F'
                print(f"Weather API result ({service_name}): city: {city_name}, temp: {current_temp}{log_unit}, API time: {api_time:.2f}s")
            except (IndexError, KeyError, TypeError):
                 # Indicate error or missing data
                print(f"Weather API result ({service_name}): city: {city_name}, temp: N/A, API time: {api_time:.2f}s")

            return processed_data, 200, fetch_time

        except requests.exceptions.RequestException as e:
            print(f"Weather API error: Failed to fetch weather data from API: {e}")
            return {"error": "Failed to fetch weather data from API"}, 500, fetch_time
        except (ValueError, KeyError, TypeError) as e:
            # Always log error result
            print(f"Weather API error: Failed to process weather data: {e}")
            return {"error": "Failed to process weather data"}, 500, fetch_time
        # Lock is automatically released by the 'with' statement



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
    weather_data, status_code, fetch_time = get_weather_data(ip=ip)
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
        data, status, fetch_time = get_weather_data(ip=ip)
        print(f"  Weather status: {status}, data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}, fetch time: {fetch_time:.2f}s")

if __name__ == "__main__":
    print("Running weather API tests with test IP addresses...")
    test_weather_api_with_ips()