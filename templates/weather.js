// Weather widget toggle and data fetching

// Global flag to enable/disable weather widget toggle. Set to false to always show widget and hide toggle UI.
const weatherWidgetToggleEnabled = true;
const WEATHER_CACHE_DURATION = 30 * 60 * 1000; // 30 minutes in milliseconds

// --- Weather Widget Toggle ---
const weatherDefaultCollapsed = false; // <<< SET TO true FOR COLLAPSED BY DEFAULT, false FOR OPEN BY DEFAULT >>>

document.addEventListener('DOMContentLoaded', function() {
  const weatherContainer = document.getElementById('weather-widget-container');
  const weatherContent = document.getElementById('weather-content');
  const weatherToggleBtn = document.getElementById('weather-toggle-btn');
  let weatherToggleHandler = null;

  if (!weatherWidgetToggleEnabled) {
    if (weatherContainer) weatherContainer.classList.remove('collapsed');
    if (weatherContent) weatherContent.style.display = '';
    if (weatherToggleBtn) weatherToggleBtn.style.display = 'none';
    const label = document.getElementById('weather-collapsed-label');
    if (label) label.style.display = 'none';
    return;
  }

  if (!weatherContainer || !weatherContent || !weatherToggleBtn) {
    console.warn('Weather toggle elements not found.');
    return;
  }

  function setInitialWeatherState() {
    const cookieValue = document.cookie.split('; ').find(item => item.trim().startsWith('weatherCollapsed='));
    let isCollapsed;

    if (cookieValue) {
      isCollapsed = cookieValue.split('=')[1] === 'true';
    } else {
      isCollapsed = weatherDefaultCollapsed;
    }

    if (isCollapsed) {
      weatherContainer.classList.add('collapsed');
      weatherToggleBtn.innerHTML = '&#9650;';
    } else {
      weatherContainer.classList.remove('collapsed');
      weatherToggleBtn.innerHTML = '&#9660;';
    }
  }

  setInitialWeatherState();

  weatherToggleHandler = function(event) {
    console.log('Weather toggle button clicked!');
    event.stopPropagation();
    const isCurrentlyCollapsed = weatherContainer.classList.toggle('collapsed');
    if (isCurrentlyCollapsed) {
      weatherToggleBtn.innerHTML = '&#9650;';
      document.cookie = 'weatherCollapsed=true; path=/; max-age=31536000; SameSite=Lax';
    } else {
      weatherToggleBtn.innerHTML = '&#9660;';
      document.cookie = 'weatherCollapsed=false; path=/; max-age=31536000; SameSite=Lax';
    }
  };

  weatherToggleBtn.addEventListener('click', weatherToggleHandler);

  // Cleanup handler on page unload
  window.addEventListener('unload', () => {
    if (weatherToggleBtn && weatherToggleHandler) {
      weatherToggleBtn.removeEventListener('click', weatherToggleHandler);
    }
  });
});

// Weather data fetch and render with caching
function getCachedWeatherData() {
  try {
    const cached = sessionStorage.getItem('weatherData');
    if (cached) {
      const { data, timestamp } = JSON.parse(cached);
      if (Date.now() - timestamp < WEATHER_CACHE_DURATION) {
        return data;
      }
    }
  } catch (error) {
    console.error('Error reading cached weather data:', error);
  }
  return null;
}

function setCachedWeatherData(data) {
  try {
    sessionStorage.setItem('weatherData', JSON.stringify({
      data,
      timestamp: Date.now()
    }));
  } catch (error) {
    console.error('Error caching weather data:', error);
  }
}

function loadWeather() {
  const weatherContainer = document.getElementById('weather-container');
  if (!weatherContainer) return;
  
  const widgetWrapper = document.getElementById('weather-widget-container');
  if ((widgetWrapper && widgetWrapper.classList.contains('collapsed')) ||
      getComputedStyle(weatherContainer).display === 'none') return;

  const cachedData = getCachedWeatherData();
  if (cachedData) {
    renderWeatherData(cachedData, determineUnits());
    return;
  }

  fetchWeatherData();
}

function determineUnits() {
  const userLocale = new Intl.Locale(navigator.language || 'en-US');
  return ['US', 'BS', 'BZ', 'KY', 'PW'].includes(userLocale.region) ? 'imperial' : 'metric';
}

async function fetchWeatherData() {
  const now = new Date();
  const cacheBuster = `${now.getFullYear()}${(now.getMonth() + 1).toString().padStart(2, '0')}${now.getDate().toString().padStart(2, '0')}${now.getHours().toString().padStart(2, '0')}`;
  const useMetric = determineUnits() === 'metric';

  try {
    const response = await fetch(`/api/weather?units=${useMetric ? 'metric' : 'imperial'}&_=${cacheBuster}`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    const data = await response.json();
    setCachedWeatherData(data);
    renderWeatherData(data, useMetric);
  } catch (error) {
    console.error('Weather fetch error:', error);
    const weatherLoading = document.getElementById('weather-loading');
    const weatherError = document.getElementById('weather-error');
    if (weatherLoading) weatherLoading.style.display = "none";
    if (weatherError) {
      weatherError.style.display = "block";
      weatherError.textContent = "Unable to load weather data. Please try again later.";
    }
  }
}

function renderWeatherData(data, useMetric) {
  const weatherForecast = document.getElementById('weather-forecast');
  const weatherLoading = document.getElementById('weather-loading');
  const weatherError = document.getElementById('weather-error');
  
  if (!weatherForecast || !weatherLoading || !weatherError) {
    console.error('Weather elements not found');
    return;
  }

  // Add this line to update the header with city name
  const weatherHeader = document.querySelector('#weather-container h3');
  if (weatherHeader && data.city_name) {
    weatherHeader.textContent = `5-Day Weather (${data.city_name})`;
  }

  if (!data.daily || data.daily.length === 0) {
    weatherLoading.style.display = "none";
    weatherError.style.display = "block";
    weatherError.textContent = "No weather data available.";
    return;
  }

  // Create document fragment for better performance
  const fragment = document.createDocumentFragment();
  const today = new Date();
  const todayYear = today.getFullYear();
  const todayMonth = today.getMonth();
  const todayDate = today.getDate();
  const userLocale = navigator.language || 'en-US';

  data.daily.forEach((day, i) => {
    const dayElement = document.createElement('div');
    dayElement.className = 'weather-day';

    const date = new Date(day.dt * 1000);
    let dayName;
    
    if (date.getFullYear() === todayYear &&
        date.getMonth() === todayMonth &&
        date.getDate() === todayDate) {
      dayName = userLocale.startsWith('en') ? 'Today' : date.toLocaleDateString(userLocale, { weekday: 'long' });
    } else {
      dayName = date.toLocaleDateString(userLocale, { weekday: 'short' });
    }

    const dayNameDiv = document.createElement('div');
    dayNameDiv.className = 'weather-day-name';
    dayNameDiv.textContent = dayName;
    dayElement.appendChild(dayNameDiv);

    const img = document.createElement('img');
    img.className = 'weather-icon';
    img.src = `https://openweathermap.org/img/wn/${day.weather_icon}.png`;
    img.alt = day.weather;
    img.loading = 'lazy';
    img.onerror = function() {
      this.onerror = null;
      this.src = '/static/weather-fallback.png'; // Make sure to create this fallback icon
    };
    dayElement.appendChild(img);

    const tempDiv = document.createElement('div');
    tempDiv.className = 'weather-temp';
    tempDiv.innerHTML = `
      <span class="temp-max">${Math.round(day.temp_max)}°${useMetric ? 'C' : 'F'}</span> /
      <span class="temp-min">${Math.round(day.temp_min)}°${useMetric ? 'C' : 'F'}</span>
    `;
    dayElement.appendChild(tempDiv);

    const precipDiv = document.createElement('div');
    precipDiv.className = 'weather-precip';
    precipDiv.textContent = `${Math.round(day.precipitation)}% precip`;
    dayElement.appendChild(precipDiv);

    fragment.appendChild(dayElement);
  });

  weatherForecast.innerHTML = '';
  weatherForecast.appendChild(fragment);
  weatherLoading.style.display = "none";
  weatherForecast.style.display = "flex";
}

// Initialize weather fetch with debouncing
let weatherLoadTimeout = null;
function debouncedLoadWeather() {
  if (weatherLoadTimeout) {
    clearTimeout(weatherLoadTimeout);
  }
  weatherLoadTimeout = setTimeout(loadWeather, 100);
}

// Initialize weather fetch
debouncedLoadWeather();

const weatherToggleBtn = document.getElementById('weather-toggle-btn');
if (weatherToggleBtn) {
  weatherToggleBtn.addEventListener('click', debouncedLoadWeather);
  
  // Cleanup
  window.addEventListener('unload', () => {
    if (weatherToggleBtn) {
      weatherToggleBtn.removeEventListener('click', debouncedLoadWeather);
    }
  });
}