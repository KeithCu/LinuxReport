"""
weather.py

Provides functions to fetch and cache weather data, including a fake API mode for testing. Includes HTML rendering for weather forecasts.
"""

import os
import math
import time
from collections import defaultdict
from datetime import date as date_obj
from datetime import datetime, timedelta
from bisect import bisect_left
import json

import geoip2.database
# Third-party imports
import requests
from flask import jsonify, request
from flask_restful import Resource, reqparse, Api

from shared import limiter, dynamic_rate_limit
# Local imports
from shared import g_cs, get_lock, USER_AGENT, TZ, g_cm, PATH, EXPIRE_HOUR, MODE_MAP, MODE, WEB_BOT_USER_AGENTS
from models import DEBUG, get_weather_api_key

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
DEFAULT_WEATHER_LAT = 42.3314
DEFAULT_WEATHER_LON = -83.0458

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
    now = datetime.now(TZ).timestamp()
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
            now = datetime.now(TZ).timestamp()

    timestamps_in_window.append(now)

    g_cs.put(RL_KEY, timestamps_in_window, timeout=RATE_LIMIT_WINDOW + 1)

CACHE_ENTRY_PREFIX = 'weather:cache_entry:'

def save_weather_cache_entry(lat, lon, data):
    """Saves a weather data entry to the cache with timestamp and date, using bucketed key."""
    key = _bucket_key(lat, lon)
    now = datetime.now(TZ).timestamp()
    today_str = date_obj.today().isoformat()
    
    # Calculate remaining cache time based on fetch_time if available
    fetch_time = data.get('fetch_time', now)
    time_since_fetch = now - fetch_time
    
    # Adjust timeout based on data age (remaining = total - elapsed)
    remaining_timeout = max(WEATHER_CACHE_TIMEOUT - time_since_fetch, 300)  # Minimum 5 minutes
    
    entry = {'lat': str(lat), 'lon': str(lon), 'data': data, 'timestamp': now, 'date': today_str}
    g_cs.put(CACHE_ENTRY_PREFIX + key, entry, timeout=remaining_timeout)

def get_bucketed_weather_cache(lat, lon, units='imperial'):
    """Returns cached weather data for the bucketed (lat, lon) if present and same day."""
    key = _bucket_key(lat, lon)
    entry = g_cs.get(CACHE_ENTRY_PREFIX + key)
    today_str = date_obj.today().isoformat()
    now = datetime.now(TZ).timestamp()
    if entry and entry.get('date') == today_str and now - entry.get('timestamp', 0) < WEATHER_CACHE_TIMEOUT:
        # print(f"[DEBUG] Cache hit for key {key}, city: {entry.get('data', {}).get('city_name', 'unknown')}")
        data = entry['data']
        if units == 'metric':
            data = convert_weather_to_metric(data)
        return data
    # print(f"[DEBUG] Cache miss for key {key}")
    return None

def fahrenheit_to_celsius(f_temp):
    """Convert Fahrenheit temperature to Celsius, rounded to a whole number."""
    if f_temp is None:
        return None
    return round((f_temp - 32) * 5/9)

def convert_weather_to_metric(data):
    if 'daily' in data:
        for day in data['daily']:
            if 'temp_min' in day:
                day['temp_min'] = fahrenheit_to_celsius(day['temp_min'])
            if 'temp_max' in day:
                day['temp_max'] = fahrenheit_to_celsius(day['temp_max'])
    return data

def _process_openweather_response(weather_data, fetch_time):
    """Process the OpenWeather API response into the standard format."""
    # Determine city name for logging
    city_name = weather_data.get("city", {}).get("name", "Unknown location")
    # print(f"[DEBUG] Raw API response city data: {weather_data.get('city', {})}")

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

    # Add city information and fetch_time to processed data
    processed_data['city_name'] = city_name
    processed_data['fetch_time'] = fetch_time
    
    return processed_data, city_name

def _log_weather_result(processed_data, city_name, service_name, api_time, units):
    """Log the weather API result."""
    try:
        today_entry = processed_data["daily"][0]
        # Get the temp (already potentially converted)
        current_temp = round(today_entry.get("temp_max", today_entry.get("temp_min", 0)))
        log_unit = 'C' if units == 'metric' else 'F'
        print(f"Weather API result ({service_name}): city: {city_name}, temp: {current_temp}{log_unit}, API time: {api_time:.2f}s")
    except (IndexError, KeyError, TypeError):
        # Indicate error or missing data
        print(f"Weather API result ({service_name}): city: {city_name}, temp: N/A, API time: {api_time:.2f}s")

def _fetch_from_openweather_api(lat, lon, fetch_time):
    """Fetch weather data from OpenWeather API."""
    service_name = "OpenWeather"
    
    # Check for valid API key before proceeding
    if not WEATHER_API_KEY or len(WEATHER_API_KEY) < 10:
        print("Weather API error: WEATHER_API_KEY is missing or too short.")
        error_data = {"error": "Weather API key is not configured", "fetch_time": fetch_time}
        return None, "Unknown", 0, service_name, error_data, 500
    
    rate_limit_check()
    # Always fetch in imperial (Fahrenheit) for consistent caching
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=imperial&appid={WEATHER_API_KEY}"
    # print(f"[DEBUG] OpenWeather API request URL: {url}")
    start_time = datetime.now(TZ).timestamp()
    response = requests.get(url, timeout=10)
    api_time = datetime.now(TZ).timestamp() - start_time
    response.raise_for_status()
    weather_data = response.json()
    # print(f"[DEBUG] Full API response: {json.dumps(weather_data, indent=2)}")
    
    # Process the OpenWeather response
    processed_data, city_name = _process_openweather_response(weather_data, fetch_time)
    # print(f"[DEBUG] OpenWeather API response - city: {city_name}, status: {response.status_code}")
    
    return processed_data, city_name, api_time, service_name, None, None

def get_weather_data(lat=None, lon=None, ip=None, units='imperial'):
    """Fetches weather data for given coordinates or IP address, using cache or API.
    Returns a tuple of (data, status_code) where data includes 'fetch_time'
    when the data was fetched from the API."""
    
    # If IP is provided, use it to get lat/lon
    if ip and (not lat or not lon):
        lat, lon = get_location_from_ip(ip)
        if not lat or not lon:
            lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON
    if not lat or not lon:
        lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON

    # Convert coordinates to float if they're strings
    try:
        lat = float(lat)
        lon = float(lon)
    except (ValueError, TypeError):
        lat = DEFAULT_WEATHER_LAT
        lon = DEFAULT_WEATHER_LON

    # Check cache first
    bucketed_weather = get_bucketed_weather_cache(lat, lon, units=units)
    if bucketed_weather:
        return bucketed_weather, 200

    # Record a preliminary fetch_time, to be overwritten by API if possible
    fetch_time = datetime.now(TZ).timestamp()
    error_data = None
    error_code = None
    
    try:
        bucket_key = _bucket_key(lat, lon)
        
        # Use OpenWeather API with locking
        lock_key = f"weather_fetch:{bucket_key}"
        with get_lock(lock_key):
            # Re-check cache inside the lock to prevent race condition
            bucketed_weather = get_bucketed_weather_cache(lat, lon, units=units)
            if bucketed_weather:
                return bucketed_weather, 200
            
            result = _fetch_from_openweather_api(lat, lon, fetch_time)
            processed_data, city_name, api_time, service_name, error_data, error_code = result
            
            # If we got an error from the fetch function, return it
            if error_data and error_code:
                return error_data, error_code
        
        # Save to cache
        save_weather_cache_entry(lat, lon, processed_data)
        
        # Convert to metric if requested
        if units == 'metric':
            processed_data = convert_weather_to_metric(processed_data)
        
        # Log the result
        _log_weather_result(processed_data, city_name, service_name, api_time, units)
        
        return processed_data, 200
        
    except requests.exceptions.RequestException as e:
        print(f"Weather API error: Failed to fetch weather data from OpenWeather API: {e}")
        error_data = {"error": "Failed to fetch weather data from OpenWeather API", "fetch_time": fetch_time}
        return error_data, 500
    except (ValueError, KeyError, TypeError) as e:
        print(f"Weather API error: Failed to process weather data from OpenWeather API: {e}")
        error_data = {"error": "Failed to process weather data from OpenWeather API", "fetch_time": fetch_time}
        return error_data, 500

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
        fetch_time_from_data = data.get('fetch_time', 'N/A')
        if isinstance(fetch_time_from_data, float):
            fetch_time_from_data = f"{fetch_time_from_data:.2f}s"
        print(f"  Weather status: {status}, data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}, fetch time: {fetch_time_from_data}")

def init_weather_routes(app):
    # Create request parser for weather API
    weather_parser = reqparse.RequestParser()
    weather_parser.add_argument('units', type=str, default='imperial', choices=['imperial', 'metric'], 
                               location='args', help='Units must be either imperial or metric')
    weather_parser.add_argument('lat', type=float, location='args', help='Latitude must be a valid number')
    weather_parser.add_argument('lon', type=float, location='args', help='Longitude must be a valid number')

    class WeatherResource(Resource):
        """
        Weather API Resource
        
        Provides weather data for a given location.
        
        ---
        parameters:
          - name: units
            in: query
            type: string
            enum: [imperial, metric]
            default: imperial
            description: Temperature units (Fahrenheit or Celsius)
          - name: lat
            in: query
            type: number
            description: Latitude coordinate (optional, uses IP location if not provided)
          - name: lon
            in: query
            type: number
            description: Longitude coordinate (optional, uses IP location if not provided)
        responses:
          200:
            description: Weather data retrieved successfully
            schema:
              type: object
              properties:
                daily:
                  type: array
                  items:
                    type: object
                    properties:
                      dt:
                        type: integer
                        description: Unix timestamp for the day
                      temp_min:
                        type: number
                        description: Minimum temperature
                      temp_max:
                        type: number
                        description: Maximum temperature
                      precipitation:
                        type: integer
                        description: Precipitation probability (0-100)
                      weather:
                        type: string
                        description: Weather condition description
                      weather_icon:
                        type: string
                        description: Weather icon code
                city_name:
                  type: string
                  description: City name for the location
                fetch_time:
                  type: number
                  description: Unix timestamp when data was fetched
          400:
            description: Invalid parameters
          500:
            description: Server error or API service unavailable
        """
        @limiter.limit(dynamic_rate_limit)
        def get(self):
            args = weather_parser.parse_args()
            ip = request.remote_addr
            units = args['units']
            
            # Check if request is from a web bot
            user_agent = request.headers.get('User-Agent', '')
            is_web_bot = any(bot in user_agent for bot in WEB_BOT_USER_AGENTS)
            
            # For web bots or requests from news.thedetroitilove.com, use default (Detroit) coordinates
            referrer = request.headers.get('Referer', '')
            if is_web_bot or 'news.thedetroitilove.com' in referrer:
                lat = DEFAULT_WEATHER_LAT
                lon = DEFAULT_WEATHER_LON
            else:
                lat = args['lat']
                lon = args['lon']
            
            weather_data, status_code = get_weather_data(lat=lat, lon=lon, ip=ip, units=units)
            
            # Flask-RESTful handles JSON serialization automatically
            # Just return the data and status code
            return weather_data, status_code
        
        def dispatch_request(self, *args, **kwargs):
            """Override to add cache headers to all responses"""
            response = super().dispatch_request(*args, **kwargs)
            
            # Add cache control headers for 4 hours (14400 seconds)
            if hasattr(response, 'headers'):
                response.headers['Cache-Control'] = 'public, max-age=14400'
                response.headers['Expires'] = (datetime.utcnow() + timedelta(hours=4)).strftime('%a, %d %b %Y %H:%M:%S GMT')
            
            return response

    # Register the resource with Flask-RESTful
    api = Api(app)
    api.add_resource(WeatherResource, '/api/weather')

if __name__ == "__main__":
    print("Running weather API tests with test IP addresses...")
    test_weather_api_with_ips()