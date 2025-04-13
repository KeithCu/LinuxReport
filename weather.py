
import requests
from flask import jsonify
from datetime import datetime
import shared
from shared import g_c # Assuming g_c is the cache instance

WEATHER_API_KEY = "YOUR_WEATHER_API_KEY"  # Replace with your actual API key
WEATHER_CACHE_TIMEOUT = 3600 * 12  # 12 hours in seconds
FAKE_API = True  # Fake Weather API calls

# Add default coordinates for weather (e.g., San Francisco)
DEFAULT_WEATHER_LAT = "37.7749"
DEFAULT_WEATHER_LON = "-122.4194"

def get_weather_data(lat, lon):
    """Fetches weather data for given coordinates, using cache or API."""
    if not lat or not lon:
        return {"error": "Missing latitude or longitude"}, 400

    cache_key = f"weather:{lat}:{lon}"

    # Check cache
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
        g_c.put(cache_key, fake_data, timeout=WEATHER_CACHE_TIMEOUT)
        return fake_data, 200

    # Fetch from real API
    try:
        # Using OpenWeatherMap API example
        url = f"https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&exclude=current,minutely,hourly,alerts&units=metric&appid={WEATHER_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status() # Raise an exception for bad status codes
        weather_data = response.json()

        # Process and simplify the data
        processed_data = {
            "daily": []
        }

        for day in weather_data.get("daily", [])[:5]:  # 5 days forecast
            processed_data["daily"].append({
                "dt": day.get("dt"),
                "temp_min": day.get("temp", {}).get("min"),
                "temp_max": day.get("temp", {}).get("max"),
                "precipitation": day.get("pop", 0) * 100,  # Convert to percentage
                "weather": day.get("weather", [{}])[0].get("main"),
                "weather_icon": day.get("weather", [{}])[0].get("icon")
            })

        # Cache the processed weather data
        g_c.put(cache_key, processed_data, timeout=WEATHER_CACHE_TIMEOUT)
        return processed_data, 200

    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return {"error": "Failed to fetch weather data from API"}, 500
    except Exception as e:
        print(f"Error processing weather data: {e}")
        return {"error": "Failed to process weather data"}, 500

def get_weather_html():
    """Returns HTML for displaying the 5-day weather forecast, using cached or fake data."""
    # Use default coordinates for the HTML display component
    weather_data, status_code = get_weather_data(DEFAULT_WEATHER_LAT, DEFAULT_WEATHER_LON)

    if status_code == 200 and weather_data and "daily" in weather_data and len(weather_data["daily"]) > 0:
        forecast_html = '<div id="weather-forecast" class="weather-forecast">'
        for day in weather_data["daily"]:
            try:
                d = datetime.fromtimestamp(day["dt"])
                day_name = "Today" if d.date() == datetime.now().date() else d.strftime("%a")
                temp_max = round(day.get("temp_max", 0)) # Add default value
                temp_min = round(day.get("temp_min", 0)) # Add default value
                precipitation = round(day.get("precipitation", 0)) # Add default value
                weather_icon = day.get("weather_icon", "01d") # Default icon
                weather_desc = day.get("weather", "N/A") # Default description

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
                # Optionally add placeholder HTML for the broken day
                forecast_html += '<div class="weather-day error">Error loading day</div>'

        forecast_html += '</div>'
        return f'''
        <div id="weather-container" class="weather-container">
            <h3>5-Day Weather</h3>
            {forecast_html}
        </div>
        '''
    else:
        # Fallback: client-side JS can attempt to fetch real data via geolocation or show error.
        return """
        <div id="weather-container" class="weather-container">
            <h3>5-Day Weather</h3>
            <div id="weather-loading">Loading weather data...</div>
            <div id="weather-error" style="display: none; color: red;">Could not load weather data.</div>
            <div id="weather-forecast" style="display: none;"></div>
            <script>
              // Optional: Add JS here to try fetching via /api/weather if geolocation is available
              // Or simply rely on the server-side attempt and show error if it failed.
              document.addEventListener('DOMContentLoaded', function() {
                  // Example: If server failed, show error message
                  const weatherContainer = document.getElementById('weather-container');
                  if (!weatherContainer.querySelector('.weather-forecast')) {
                      document.getElementById('weather-loading').style.display = 'none';
                      document.getElementById('weather-error').style.display = 'block';
                  }
              });
            </script>
        </div>
        """
