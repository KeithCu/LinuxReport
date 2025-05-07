// Weather widget toggle and data fetching

// Global flag to enable/disable weather widget toggle. Set to false to always show widget and hide toggle UI.
const weatherWidgetToggleEnabled = true;

// --- Weather Widget Toggle ---
const weatherDefaultCollapsed = false; // <<< SET TO true FOR COLLAPSED BY DEFAULT, false FOR OPEN BY DEFAULT >>>

document.addEventListener('DOMContentLoaded', function() {
  const weatherContainer = document.getElementById('weather-widget-container');
  const weatherContent = document.getElementById('weather-content');
  const weatherToggleBtn = document.getElementById('weather-toggle-btn');

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

  weatherToggleBtn.addEventListener('click', function(event) {
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
  });
});

// Weather data fetch and render

function loadWeather() {
  const weatherContainer = document.getElementById('weather-container');
  if (!weatherContainer) return;
  const widgetWrapper = document.getElementById('weather-widget-container');
  if ((widgetWrapper && widgetWrapper.classList.contains('collapsed')) ||
      getComputedStyle(weatherContainer).display === 'none') return;
  fetchWeatherData();
}

function fetchWeatherData() {
  const now = new Date();
  const year = now.getFullYear();
  const month = (now.getMonth() + 1).toString().padStart(2, '0');
  const day = now.getDate().toString().padStart(2, '0');
  const hour = now.getHours().toString().padStart(2, '0');
  const cacheBuster = `${year}${month}${day}${hour}`;
  const userLocale = new Intl.Locale(navigator.language || 'en-US');
  const prefersFahrenheit = ['US', 'BS', 'BZ', 'KY', 'PW'].includes(userLocale.region);
  const useMetric = !prefersFahrenheit;
  fetch(`/api/weather?units=${useMetric ? 'metric' : 'imperial'}&_=${cacheBuster}`)
    .then(response => {
      if (!response.ok) throw new Error('Network response was not ok');
      return response.json();
    })
    .then(data => {
      renderWeatherData(data, useMetric);
    })
    .catch(error => {
      if (document.getElementById('weather-loading')) document.getElementById('weather-loading').style.display = "none";
      if (document.getElementById('weather-error')) document.getElementById('weather-error').style.display = "block";
    });
}

function renderWeatherData(data, useMetric) {
  const weatherForecast = document.getElementById('weather-forecast');
  const weatherLoading = document.getElementById('weather-loading');
  const weatherError = document.getElementById('weather-error');
  if (!weatherForecast || !weatherLoading || !weatherError) return;
  if (!data.daily || data.daily.length === 0) {
    weatherLoading.style.display = "none";
    weatherError.style.display = "block";
    weatherError.textContent = "No weather data available.";
    return;
  }
  weatherForecast.innerHTML = '';
  weatherForecast.className = 'weather-forecast';
  const today = new Date();
  const todayYear = today.getFullYear();
  const todayMonth = today.getMonth();
  const todayDate = today.getDate();
  data.daily.forEach((day, i) => {
    const dayElement = document.createElement('div');
    dayElement.className = 'weather-day';
    const date = new Date(day.dt * 1000);
    const userLocale = navigator.language || 'en-US';
    let dayName;
    if (
      date.getFullYear() === todayYear &&
      date.getMonth() === todayMonth &&
      date.getDate() === todayDate
    ) {
      dayName = userLocale.startsWith('en') ? 'Today' : date.toLocaleDateString(userLocale, { weekday: 'long' });
    } else {
      dayName = date.toLocaleDateString(userLocale, { weekday: 'short' });
    }
    dayElement.innerHTML = `
        <div class="weather-day-name">${dayName}</div>
        <img class="weather-icon" src="https://openweathermap.org/img/wn/${day.weather_icon}.png" alt="${day.weather}">
        <div class="weather-temp">
          <span class="temp-max">${Math.round(day.temp_max)}°${useMetric ? 'C' : 'F'}</span> /
          <span class="temp-min">${Math.round(day.temp_min)}°${useMetric ? 'C' : 'F'}</span>
        </div>
        <div class="weather-precip">${Math.round(day.precipitation)}% precip</div>
      `;
    weatherForecast.appendChild(dayElement);
  });
  weatherLoading.style.display = "none";
  weatherForecast.style.display = "flex";
}

// Initialize weather fetch
setTimeout(loadWeather, 100);

const weatherToggleBtn = document.getElementById('weather-toggle-btn');
if (weatherToggleBtn) {
  weatherToggleBtn.addEventListener('click', function() {
    setTimeout(loadWeather, 100);
  });
}