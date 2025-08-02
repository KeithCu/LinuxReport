"""
weather.py

Weather data fetching and caching module for the Flask application.
Provides functions to fetch weather data from OpenWeather API, cache results,
and render weather forecasts as HTML. Includes GeoIP location detection and
rate limiting for API calls.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
import sys
import math
import time
import json
import argparse
from collections import defaultdict
from datetime import date as date_obj
from datetime import datetime, timedelta
from bisect import bisect_left

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import geoip2.database
import requests
from flask import jsonify, request
from flask_restful import Resource, reqparse

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from shared import (
    limiter, dynamic_rate_limit, g_cs, get_lock, USER_AGENT, 
    TZ, g_cm, PATH, EXPIRE_HOUR, MODE_MAP, MODE, 
    API, DISABLE_IP_GEOLOCATION, DISABLE_CLIENT_GEOLOCATION
)
from request_utils import is_web_bot
from app_config import DEBUG, get_weather_api_key

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# Weather bucket configuration for caching
WEATHER_BUCKET_SIZE_MILES = 10  # Default bucket diameter in miles (good balance for weather data)
_WEATHER_BUCKET_SIZE_DEG = WEATHER_BUCKET_SIZE_MILES / 69.0  # Convert miles to degrees (~1° ≈ 69 miles)

# Cache timeout configuration
if DEBUG:
    WEATHER_CACHE_TIMEOUT = 300
else:
    WEATHER_CACHE_TIMEOUT = 3600 * 4  # 4 hours

# Default coordinates for weather (Detroit, MI)
DEFAULT_WEATHER_LAT = 42.3314
DEFAULT_WEATHER_LON = -83.0458

# Rate limiting configuration
RL_KEY = "weather_api_call_timestamps_v2"
RATE_LIMIT_WINDOW = 10  # seconds
RATE_LIMIT_COUNT = 10   # calls per window

# Cache entry prefix
CACHE_ENTRY_PREFIX = 'weather:cache_entry:'

# =============================================================================
# GEOIP CONFIGURATION
# =============================================================================

def _get_geoip_db_path():
    """
    Get the path to the GeoIP database file.
    
    Returns:
        str: Path to the GeoIP database file
    """
    # Database stored in /srv/http/LinuxReport2/GeoLite2-City.mmdb
    srv_path = os.path.join('/srv/http/LinuxReport2', 'GeoLite2-City.mmdb')
    if os.path.exists(srv_path):
        return srv_path
    return os.path.join(os.path.dirname(__file__), 'GeoLite2-City.mmdb')

GEOIP_DB_PATH = _get_geoip_db_path()

# Global reader for GeoIP database to avoid reopening the file
_geoip_reader = None

# =============================================================================
# WEATHER API CONFIGURATION
# =============================================================================

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")



# =============================================================================
# GEOLOCATION CACHING
# =============================================================================

def save_geolocation_cache(ip, lat, lon, source='ip'):
    """
    Save geolocation data to shared cache.
    
    Args:
        ip (str): IP address
        lat (float): Latitude coordinate
        lon (float): Longitude coordinate
        source (str): Source of location data ('ip', 'browser', etc.)
    """
    cache_key = f"geolocation:{ip}"
    cache_data = {
        'lat': lat,
        'lon': lon,
        'source': source,
        'timestamp': datetime.now(TZ).timestamp()
    }
    # Cache for 30 days (location doesn't change often)
    g_cs.put(cache_key, cache_data, timeout=30 * 24 * 3600)

def get_cached_geolocation(ip):
    """
    Get cached geolocation data for an IP address.
    
    Args:
        ip (str): IP address
        
    Returns:
        tuple: (lat, lon) coordinates or (None, None) if not cached
    """
    cache_key = f"geolocation:{ip}"
    cached_data = g_cs.get(cache_key)
    
    if cached_data:
        return cached_data.get('lat'), cached_data.get('lon')
    
    return None, None





# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _bucket_coord(val, bucket_size_deg=_WEATHER_BUCKET_SIZE_DEG):
    """
    Buckets a coordinate into intervals of bucket_size_deg degrees.
    
    Args:
        val (float): Coordinate value to bucket
        bucket_size_deg (float): Size of each bucket in degrees
        
    Returns:
        float: Bucketed coordinate value
    """
    return math.floor(float(val) / bucket_size_deg) * bucket_size_deg

def _bucket_key(lat, lon):
    """
    Generates a cache key based on bucketed lat/lon coordinates.
    
    Args:
        lat (float): Latitude coordinate
        lon (float): Longitude coordinate
        
    Returns:
        str: Cache key for the bucketed coordinates
    """
    lat_b = _bucket_coord(lat)
    lon_b = _bucket_coord(lon)
    return f"{lat_b:.6f},{lon_b:.6f}"

def get_location_from_ip(ip):
    """
    Get geolocation coordinates from an IP address using MaxMind GeoIP database.
    
    Args:
        ip (str): IP address to geolocate
        
    Returns:
        tuple: (latitude, longitude) coordinates, or default coordinates if lookup fails
    """
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

def rate_limit_check():
    """
    Enforces RATE_LIMIT_COUNT calls per RATE_LIMIT_WINDOW seconds.
    
    This function implements a sliding window rate limiter for weather API calls.
    If the rate limit is exceeded, it sleeps until the oldest request expires.
    """
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



# =============================================================================
# CACHE MANAGEMENT
# =============================================================================

def save_weather_cache_entry(lat, lon, data):
    """
    Saves a weather data entry to the cache with timestamp and date, using bucketed key.
    
    Args:
        lat (float): Latitude coordinate
        lon (float): Longitude coordinate
        data (dict): Weather data to cache
    """
    key = _bucket_key(lat, lon)
    now = datetime.now(TZ).timestamp()
    today_str = date_obj.today().isoformat()
    
    # Calculate remaining cache time based on fetch_time if available
    fetch_time = data.get('fetch_time', now)
    time_since_fetch = now - fetch_time
    
    # Adjust timeout based on data age (remaining = total - elapsed)
    remaining_timeout = max(WEATHER_CACHE_TIMEOUT - time_since_fetch, 300)  # Minimum 5 minutes
    
    entry = {
        'lat': str(lat), 
        'lon': str(lon), 
        'data': data, 
        'timestamp': now, 
        'date': today_str
    }
    g_cs.put(CACHE_ENTRY_PREFIX + key, entry, timeout=remaining_timeout)

def get_bucketed_weather_cache(lat, lon):
    """
    Returns cached weather data for the bucketed (lat, lon) if present and same day.
    
    Args:
        lat (float): Latitude coordinate
        lon (float): Longitude coordinate
        
    Returns:
        dict or None: Cached weather data or None if not available
    """
    key = _bucket_key(lat, lon)
    entry = g_cs.get(CACHE_ENTRY_PREFIX + key)
    today_str = date_obj.today().isoformat()
    now = datetime.now(TZ).timestamp()
    
    if entry and entry.get('date') == today_str and now - entry.get('timestamp', 0) < WEATHER_CACHE_TIMEOUT:
        #print(f"[DEBUG] Cache HIT for key {key}, city: {entry.get('data', {}).get('city_name', 'unknown')}")
        return entry['data']
    #print(f"[DEBUG] Cache MISS for key {key}, lat={lat}, lon={lon}")
    return None

# Temperature conversion functions removed - now handled client-side

# =============================================================================
# WEATHER DATA PROCESSING
# =============================================================================

def _process_openweather_response(weather_data, fetch_time):
    """
    Process the OpenWeather API response into the standard format.
    
    Args:
        weather_data (dict): Raw response from OpenWeather API
        fetch_time (float): Timestamp when the data was fetched
        
    Returns:
        tuple: (processed_data, city_name) - Processed weather data and city name
    """
    # Determine city name for logging
    city_name = weather_data.get("city", {}).get("name", "Unknown location")
    #print(f"[DEBUG] Raw city name from API: {repr(city_name)}")
    
    # Fix Unicode encoding issue - the city name might be coming as bytes or with encoding issues
    if isinstance(city_name, str):
        try:
            # If it looks like it has escaped bytes, try to decode it
            if '\\x' in repr(city_name):
                # Convert the string representation back to bytes and decode
                city_name = city_name.encode('latin-1').decode('utf-8')
            else:
                # Ensure it's properly decoded
                city_name = city_name.encode('utf-8').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            # If all else fails, use the original
            pass
    
    #print(f"[DEBUG] Processed city name: {repr(city_name)}")
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

def _log_weather_result(processed_data, city_name, service_name, api_time):
    """
    Log the weather API result.
    
    Args:
        processed_data (dict): Processed weather data
        city_name (str): Name of the city
        service_name (str): Name of the weather service used
        api_time (float): Time taken for API call
    """
    try:
        today_entry = processed_data["daily"][0]
        # Get the temp (always in Fahrenheit)
        current_temp = round(today_entry.get("temp_max", today_entry.get("temp_min", 0)))
        
        # Ensure proper Unicode handling for city name
        try:
            # Try to decode if it's bytes, otherwise use as-is
            if isinstance(city_name, bytes):
                city_name = city_name.decode('utf-8')
            elif isinstance(city_name, str):
                # Ensure it's properly encoded
                city_name = city_name.encode('utf-8').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            # Fallback to safe string representation
            city_name = repr(city_name)
        
        print(f"Weather API result ({service_name}): city: {city_name}, temp: {current_temp}°F, API time: {api_time:.2f}s")
    except (IndexError, KeyError, TypeError):
        # Indicate error or missing data
        print(f"Weather API result ({service_name}): city: {city_name}, temp: N/A, API time: {api_time:.2f}s")

# =============================================================================
# API FETCHING
# =============================================================================

def _fetch_from_openweather_api(lat, lon, fetch_time):
    """
    Fetch weather data from OpenWeather API.
    
    Args:
        lat (float): Latitude coordinate
        lon (float): Longitude coordinate
        fetch_time (float): Timestamp when the fetch was initiated
        
    Returns:
        tuple: (processed_data, city_name, api_time, service_name, error_data, error_code)
    """
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
    
    # Ensure proper encoding for JSON parsing
    response.encoding = 'utf-8'
    weather_data = response.json()
    # print(f"[DEBUG] Full API response: {json.dumps(weather_data, indent=2)}")
    
    # Process the OpenWeather response
    processed_data, city_name = _process_openweather_response(weather_data, fetch_time)
    # print(f"[DEBUG] OpenWeather API response - city: {city_name}, status: {response.status_code}")
    
    return processed_data, city_name, api_time, service_name, None, None

def get_weather_data(lat=None, lon=None, ip=None):
    """
    Fetches weather data for given coordinates or IP address, using cache or API.
    
    This function first checks the cache for existing weather data. If not found,
    it fetches fresh data from the OpenWeather API and caches the result.
    All temperatures are returned in Fahrenheit for client-side conversion.
    
    Args:
        lat (float, optional): Latitude coordinate
        lon (float, optional): Longitude coordinate
        ip (str, optional): IP address for geolocation (only used if DISABLE_IP_GEOLOCATION is False)
        
    Returns:
        tuple: (data, status_code) where data includes 'fetch_time' when the data was fetched from the API
    """
    # If coordinates are provided, use them directly and cache them (unless client geolocation is disabled)
    if lat is not None and lon is not None:
        try:
            lat = float(lat)
            lon = float(lon)
            # Only cache the provided coordinates if client geolocation is enabled
            if ip and not DISABLE_CLIENT_GEOLOCATION:
                save_geolocation_cache(ip, lat, lon, 'client')
        except (ValueError, TypeError):
            lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON
    else:
        # No coordinates provided - handle based on IP availability and settings
        if ip:
            #print(f"[DEBUG] get_weather_data: IP provided: {ip}, DISABLE_CLIENT_GEOLOCATION={DISABLE_CLIENT_GEOLOCATION}, DISABLE_IP_GEOLOCATION={DISABLE_IP_GEOLOCATION}")
            if DISABLE_CLIENT_GEOLOCATION:
                # Skip cache when client geolocation disabled
                if DISABLE_IP_GEOLOCATION:
                    lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON
                    # print(f"[DEBUG] get_weather_data: Using Detroit coordinates (IP geolocation disabled)")
                else:
                    lat, lon = get_location_from_ip(ip)
                    # print(f"[DEBUG] get_weather_data: Using IP-based location: {lat}, {lon}")
            else:
                # Try cache first, then fallback
                lat, lon = get_cached_geolocation(ip)
                if lat is None or lon is None:
                    lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON if DISABLE_IP_GEOLOCATION else get_location_from_ip(ip)
                    if not DISABLE_CLIENT_GEOLOCATION:
                        save_geolocation_cache(ip, lat, lon, 'ip')
            
            # Common fallback for both paths
            if not lat or not lon:
                lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON
        else:
            # No IP available, use Detroit coordinates
            lat, lon = DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON

    # Convert coordinates to float if they're strings
    try:
        lat = float(lat)
        lon = float(lon)
    except (ValueError, TypeError):
        lat = DEFAULT_WEATHER_LAT
        lon = DEFAULT_WEATHER_LON

    # Check cache first
    bucketed_weather = get_bucketed_weather_cache(lat, lon)
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
            bucketed_weather = get_bucketed_weather_cache(lat, lon)
            if bucketed_weather:
                return bucketed_weather, 200
            
            result = _fetch_from_openweather_api(lat, lon, fetch_time)
            processed_data, city_name, api_time, service_name, error_data, error_code = result
            
            # If we got an error from the fetch function, return it
            if error_data and error_code:
                return error_data, error_code
        
        # Save to cache
        save_weather_cache_entry(lat, lon, processed_data)
        
        # Log the result
        _log_weather_result(processed_data, city_name, service_name, api_time)
        
        return processed_data, 200
        
    except requests.exceptions.RequestException as e:
        print(f"Weather API error: Failed to fetch weather data from OpenWeather API: {e}")
        error_data = {"error": "Failed to fetch weather data from OpenWeather API", "fetch_time": fetch_time}
        return error_data, 500
    except (ValueError, KeyError, TypeError) as e:
        print(f"Weather API error: Failed to process weather data from OpenWeather API: {e}")
        error_data = {"error": "Failed to process weather data from OpenWeather API", "fetch_time": fetch_time}
        return error_data, 500

# =============================================================================
# HTML GENERATION
# =============================================================================


def get_default_weather_html():
    """
    Returns the default HTML for the weather container (loading state).
    
    Returns:
        str: HTML string for default weather container
    """
    return '''
    <div id="weather-container" class="weather-container" style="display: none;">
        <h3>5-Day Weather</h3>
        <div id="weather-loading">Finding location...</div>
        <div id="weather-error" style="display: none; color: red;">Could not load weather data.</div>
        <div id="weather-forecast" style="display: none;"></div>
    </div>
    '''

# =============================================================================
# TESTING AND DEBUGGING
# =============================================================================

def test_weather_api_with_ips():
    """
    Test get_location_from_ip and get_weather_data for a list of IP addresses.
    
    This function is used for debugging and testing the weather API functionality
    with specific IP addresses.
    """
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

# =============================================================================
# FLASK ROUTES INITIALIZATION
# =============================================================================

def init_weather_routes(app):
    """
    Initialize weather API routes for the Flask application.
    
    Args:
        app (Flask): Flask application instance
    """
    # Create request parser for weather API
    weather_parser = reqparse.RequestParser()
    weather_parser.add_argument(
        'lat', 
        type=float, 
        location='args', 
        help='Latitude must be a valid number'
    )
    weather_parser.add_argument(
        'lon', 
        type=float, 
        location='args', 
        help='Longitude must be a valid number'
    )

    class WeatherResource(Resource):
        """
        Weather API Resource
        
        Provides weather data for a given location in Fahrenheit.
        Temperature conversion to Celsius is handled client-side.
        
        ---
        parameters:
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
            """Handle GET requests for weather data."""
            args = weather_parser.parse_args()
            ip = request.remote_addr
            
            # Check if request is from a web bot
            user_agent = request.headers.get('User-Agent', '')
            is_bot = is_web_bot(user_agent)
            
            # For web bots or requests from news.thedetroitilove.com, use default (Detroit) coordinates
            referrer = request.headers.get('Referer', '')
            if is_bot or 'news.thedetroitilove.com' in referrer:
                lat = DEFAULT_WEATHER_LAT
                lon = DEFAULT_WEATHER_LON
                ip = None  # Don't use IP for geolocation
                print(f"[DEBUG] Using Detroit coordinates for bot/referrer: lat={lat}, lon={lon}")
            else:
                # Get coordinates from request parameters
                lat = args['lat']
                lon = args['lon']
                
                # If client geolocation is disabled, ignore any provided coordinates
                if DISABLE_CLIENT_GEOLOCATION:
                    lat = None
                    lon = None
                
                # If no coordinates provided (geolocation failed or disabled), handle IP usage based on setting
                if lat is None and lon is None:
                    #print(f"[DEBUG] No coordinates provided, DISABLE_IP_GEOLOCATION={DISABLE_IP_GEOLOCATION}")
                    if DISABLE_IP_GEOLOCATION:
                        # Use Detroit coordinates when IP geolocation is disabled
                        lat = DEFAULT_WEATHER_LAT
                        lon = DEFAULT_WEATHER_LON
                        ip = None  # Don't use IP for geolocation
                        print(f"[DEBUG] Using Detroit coordinates (IP geolocation disabled): lat={lat}, lon={lon}")
                        
                        # Log warning if both client and IP geolocation are disabled
                        if DISABLE_CLIENT_GEOLOCATION:
                            print(f"[WARNING] Both client geolocation and IP geolocation are disabled - using Detroit fallback")
                    else:
                        # Use IP-based location when enabled
                        # ip is already set to request.remote_addr
                        #print(f"[DEBUG] Using IP-based location: ip={ip}")
                        pass
                else:
                    # Coordinates provided (geolocation successful), don't use IP
                    ip = None
                    print(f"[DEBUG] Using provided coordinates: lat={lat}, lon={lon}")
            
            weather_data, status_code = get_weather_data(lat=lat, lon=lon, ip=ip)
            
            # Log the result for debugging
            # if weather_data and 'city_name' in weather_data:
            #     print(f"[DEBUG] Weather API result: city={weather_data['city_name']}, status={status_code}")
            
            # Flask-RESTful handles JSON serialization automatically
            # Just return the data and status code
            return weather_data, status_code
        
        def dispatch_request(self, *args, **kwargs):
            """
            Override to add cache headers to all responses.
            
            Args:
                *args: Variable length argument list
                **kwargs: Arbitrary keyword arguments
                
            Returns:
                Response: Flask response with cache headers added
            """
            response = super().dispatch_request(*args, **kwargs)
            
            # Add cache control headers for 4 hours (14400 seconds)
            if hasattr(response, 'headers'):
                response.headers['Cache-Control'] = 'public, max-age=14400'
                response.headers['Expires'] = (datetime.utcnow() + timedelta(hours=4)).strftime('%a, %d %b %Y %H:%M:%S GMT')
            
            return response

    # Register the resource with Flask-RESTful
    API.add_resource(WeatherResource, '/api/weather')

# =============================================================================
# COMMAND LINE INTERFACE
# =============================================================================

def geoip_lookup(ip):
    """
    Perform IP geolocation lookup and return results.
    
    Args:
        ip (str): IP address to lookup
        
    Returns:
        dict: Geolocation results
    """
    print(f"Looking up IP: {ip}")
    
    # Check if IP is valid
    try:
        import ipaddress
        ip_obj = ipaddress.ip_address(ip)
        ip_type = "IPv6" if isinstance(ip_obj, ipaddress.IPv6Address) else "IPv4"
        print(f"IP type: {ip_type}")
    except ValueError:
        return {"error": f"Invalid IP address: {ip}"}
    
    # Perform fresh lookup directly from GeoIP database (bypass cache)
    print("Performing fresh lookup from GeoIP database...")
    
    # Test the GeoIP lookup with detailed error handling
    try:
        global _geoip_reader
        if _geoip_reader is None:
            _geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
        
        print(f"GeoIP database path: {GEOIP_DB_PATH}")
        print(f"Database exists: {os.path.exists(GEOIP_DB_PATH)}")
        
        response = _geoip_reader.city(ip)
        lat = response.location.latitude
        lon = response.location.longitude
        
        print(f"GeoIP lookup successful: {lat}, {lon}")
        print(f"City: {response.city.name if response.city else 'Unknown'}")
        print(f"Country: {response.country.name if response.country else 'Unknown'}")
        
    except Exception as e:
        print(f"GeoIP lookup failed with error: {type(e).__name__}: {e}")
        return {
            "ip": ip,
            "lat": DEFAULT_WEATHER_LAT,
            "lon": DEFAULT_WEATHER_LON,
            "source": "default",
            "error": f"GeoIP lookup failed: {type(e).__name__}: {e}"
        }
    
    if lat is None or lon is None:
        return {
            "ip": ip,
            "lat": DEFAULT_WEATHER_LAT,
            "lon": DEFAULT_WEATHER_LON,
            "source": "default",
            "error": "Lookup returned null coordinates"
        }
    
    # Create OpenStreetMap link
    osm_link = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=12"
    
    return {
        "ip": ip,
        "lat": lat,
        "lon": lon,
        "source": "geoip",
        "cached": False,
        "osm_link": osm_link
    }

def test_openweather_api(lat, lon):
    """
    Test OpenWeather API directly with given coordinates.
    
    Args:
        lat (float): Latitude
        lon (float): Longitude
    """
    print(f"Testing OpenWeather API with coordinates: {lat}, {lon}")
    
    try:
        # Use the same function that the weather API uses
        weather_data, status_code = get_weather_data(lat=lat, lon=lon, ip=None)
        
        if status_code == 200:
            city_name = weather_data.get('city_name', 'Unknown')
            print(f"✅ OpenWeather API successful!")
            print(f"City: {city_name}")
            print(f"Status: {status_code}")
            print(f"Data keys: {list(weather_data.keys())}")
            
            # Show first daily forecast
            if 'daily' in weather_data and weather_data['daily']:
                first_day = weather_data['daily'][0]
                print(f"First day forecast: {first_day.get('weather', 'Unknown')} - {first_day.get('temp_max', 'N/A')}°F")
        else:
            print(f"❌ OpenWeather API failed with status: {status_code}")
            print(f"Error: {weather_data}")
            
    except Exception as e:
        print(f"❌ OpenWeather API test failed with error: {type(e).__name__}: {e}")

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description='Weather and IP geolocation utilities')
    parser.add_argument('command', choices=['geoip', 'test', 'openweather'], help='Command to run')
    parser.add_argument('ip', nargs='?', help='IP address for geoip command')
    parser.add_argument('--lat', type=float, help='Latitude for openweather command')
    parser.add_argument('--lon', type=float, help='Longitude for openweather command')
    
    args = parser.parse_args()
    
    if args.command == 'geoip':
        if not args.ip:
            print("Error: IP address required for geoip command")
            print("Usage: python weather.py geoip <IP_ADDRESS>")
            sys.exit(1)
        
        result = geoip_lookup(args.ip)
        print(json.dumps(result, indent=2))
        
    elif args.command == 'openweather':
        if args.lat is None or args.lon is None:
            print("Error: Both --lat and --lon required for openweather command")
            print("Usage: python weather.py openweather --lat <LATITUDE> --lon <LONGITUDE>")
            sys.exit(1)
        
        test_openweather_api(args.lat, args.lon)
        
    elif args.command == 'test':
        print("Running weather API tests with test IP addresses...")
        test_weather_api_with_ips()

# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    main()