/**
 * weather.js
 * 
 * Weather widget module for the LinuxReport application. Handles weather data fetching,
 * caching, rendering, and widget toggle functionality. Provides a responsive weather
 * display with automatic unit detection and error handling.
 * 
 * @author LinuxReport Team
 * @version 2.0.0
 */

// =============================================================================
// CONSTANTS AND CONFIGURATION
// =============================================================================

// Use shared configuration with fallback
const WEATHER_CONFIG = (function() {
  if (typeof window.LINUXREPORT_CONFIG !== 'undefined') {
    return window.LINUXREPORT_CONFIG;
  }
  
  // Fallback configuration if shared config is not available
  console.warn('Shared configuration not found, using fallback config');
  return {
    WEATHER_WIDGET_TOGGLE_ENABLED: true,
    WEATHER_DEFAULT_COLLAPSED: false,
    WEATHER_CACHE_DURATION: 30 * 60 * 1000,
    USE_LINUXREPORT_WEATHER: false,
    WEATHER_BASE_URL: '',
    WEATHER_DEBOUNCE_DELAY: 100,
    COOKIE_MAX_AGE: 31536000,
    COOKIE_SAME_SITE: 'Lax',
    IMPERIAL_REGIONS: ['US', 'BS', 'BZ', 'KY', 'PW'],
    DEFAULT_LOCALE: 'en-US'
  };
})();

// =============================================================================
// WEATHER WIDGET TOGGLE MANAGEMENT
// =============================================================================

/**
 * Weather widget toggle manager.
 * Handles the collapsible weather widget functionality.
 */
class WeatherToggleManager {
  constructor() {
    this.container = document.getElementById('weather-widget-container');
    this.content = document.getElementById('weather-content');
    this.toggleBtn = document.getElementById('weather-toggle-btn');
    this.collapsedLabel = document.getElementById('weather-collapsed-label');
    this.toggleHandler = null;
    
    this.init();
  }
  
  /**
   * Initialize the weather toggle functionality.
   */
  init() {
    if (!WEATHER_CONFIG.WEATHER_WIDGET_TOGGLE_ENABLED) {
      this.disableToggle();
      return;
    }
    
    if (!this.container || !this.content || !this.toggleBtn) {
      console.warn('Weather toggle elements not found.');
      return;
    }
    
    this.setInitialState();
    this.setupEventListeners();
    this.setupCleanup();
  }
  
  /**
   * Disable the toggle functionality and show widget permanently.
   */
  disableToggle() {
    if (this.container) this.container.classList.remove('collapsed');
    if (this.content) this.content.style.display = '';
    if (this.toggleBtn) this.toggleBtn.style.display = 'none';
    if (this.collapsedLabel) this.collapsedLabel.style.display = 'none';
  }
  
  /**
   * Set the initial collapsed state based on cookie or default.
   */
  setInitialState() {
    const cookieValue = CookieManager.get('weatherCollapsed');
    const isCollapsed = cookieValue !== null ? cookieValue === 'true' : WEATHER_CONFIG.WEATHER_DEFAULT_COLLAPSED;
    
    if (isCollapsed) {
      this.container.classList.add('collapsed');
      this.toggleBtn.innerHTML = '&#9650;';
    } else {
      this.container.classList.remove('collapsed');
      this.toggleBtn.innerHTML = '&#9660;';
    }
  }
  
  /**
   * Set up event listeners for the toggle button.
   */
  setupEventListeners() {
    this.toggleHandler = this.handleToggle.bind(this);
    this.toggleBtn.addEventListener('click', this.toggleHandler);
  }
  
  /**
   * Handle toggle button click events.
   * 
   * @param {Event} event - The click event
   */
  handleToggle(event) {
    console.log('Weather toggle button clicked!');
    event.stopPropagation();
    
    const isCurrentlyCollapsed = this.container.classList.toggle('collapsed');
    
    if (isCurrentlyCollapsed) {
      this.toggleBtn.innerHTML = '&#9650;';
      CookieManager.set('weatherCollapsed', 'true');
    } else {
      this.toggleBtn.innerHTML = '&#9660;';
      CookieManager.set('weatherCollapsed', 'false');
    }
  }
  
  /**
   * Set up cleanup on page unload.
   */
  setupCleanup() {
    window.addEventListener('unload', () => {
      if (this.toggleBtn && this.toggleHandler) {
        this.toggleBtn.removeEventListener('click', this.toggleHandler);
      }
    });
  }
}

// =============================================================================
// WEATHER DATA MANAGEMENT
// =============================================================================

/**
 * Weather data manager.
 * Handles fetching, caching, and rendering of weather data.
 */
class WeatherDataManager {
  constructor() {
    this.container = document.getElementById('weather-container');
    this.widgetWrapper = document.getElementById('weather-widget-container');
    this.forecast = document.getElementById('weather-forecast');
    this.loading = document.getElementById('weather-loading');
    this.error = document.getElementById('weather-error');
    this.header = document.querySelector('#weather-container h3');
    
    this.loadTimeout = null;
    this.init();
  }
  
  /**
   * Initialize weather data management.
   */
  init() {
    this.debouncedLoad();
    
    // Set up toggle button event listener
    const toggleBtn = document.getElementById('weather-toggle-btn');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => this.debouncedLoad());
      
      // Cleanup
      window.addEventListener('unload', () => {
        toggleBtn.removeEventListener('click', () => this.debouncedLoad());
      });
    }
  }
  
  /**
   * Load weather data with debouncing.
   */
  debouncedLoad() {
    if (this.loadTimeout) {
      clearTimeout(this.loadTimeout);
    }
    this.loadTimeout = setTimeout(() => this.load(), WEATHER_CONFIG.WEATHER_DEBOUNCE_DELAY);
  }
  
  /**
   * Load weather data from cache or API.
   */
  load() {
    if (!this.container) return;
    
    // Check if widget is collapsed or hidden
    if ((this.widgetWrapper && this.widgetWrapper.classList.contains('collapsed')) ||
        getComputedStyle(this.container).display === 'none') {
      return;
    }
    
    // Try to load from cache first
    const cachedData = CacheManager.get('weatherData', WEATHER_CONFIG.WEATHER_CACHE_DURATION);
    if (cachedData) {
      this.render(cachedData, this.determineUnits());
      return;
    }
    
    // Fetch fresh data
    this.fetch();
  }
  
  /**
   * Determine units based on user locale.
   * 
   * @returns {string} 'imperial' or 'metric'
   */
  determineUnits() {
    const userLocale = new Intl.Locale(navigator.language || WEATHER_CONFIG.DEFAULT_LOCALE);
    return WEATHER_CONFIG.IMPERIAL_REGIONS.includes(userLocale.region) ? 'imperial' : 'metric';
  }
  
  /**
   * Fetch weather data from the API.
   */
  async fetch() {
    const now = new Date();
    const cacheBuster = `${now.getFullYear()}${(now.getMonth() + 1).toString().padStart(2, '0')}${now.getDate().toString().padStart(2, '0')}${now.getHours().toString().padStart(2, '0')}`;
    const useMetric = this.determineUnits() === 'metric';
    
    try {
      const response = await fetch(`${WEATHER_CONFIG.WEATHER_BASE_URL}/api/weather?units=${useMetric ? 'metric' : 'imperial'}&v=${cacheBuster}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      CacheManager.set('weatherData', data);
      this.render(data, useMetric);
    } catch (error) {
      console.error('Weather fetch error:', error);
      this.showError('Unable to load weather data. Please try again later.');
    }
  }
  
  /**
   * Show error message.
   * 
   * @param {string} message - The error message to display
   */
  showError(message) {
    if (this.loading) this.loading.style.display = 'none';
    if (this.error) {
      this.error.style.display = 'block';
      this.error.textContent = message;
    }
  }
  
  /**
   * Render weather data to the DOM.
   * 
   * @param {Object} data - The weather data
   * @param {boolean} useMetric - Whether to use metric units
   */
  render(data, useMetric) {
    if (!this.forecast || !this.loading || !this.error) {
      console.error('Weather elements not found');
      return;
    }
    
    // Update header with city name
    if (this.header && data.city_name) {
      this.header.textContent = `5-Day Weather (${data.city_name})`;
    }
    
    if (!data.daily || data.daily.length === 0) {
      this.showError('No weather data available.');
      return;
    }
    
    // Create document fragment for better performance
    const fragment = this.createWeatherFragment(data.daily, useMetric);
    
    this.forecast.innerHTML = '';
    this.forecast.appendChild(fragment);
    this.loading.style.display = 'none';
    this.forecast.style.display = 'flex';
  }
  
  /**
   * Create weather forecast fragment.
   * 
   * @param {Array} dailyData - Array of daily weather data
   * @param {boolean} useMetric - Whether to use metric units
   * @returns {DocumentFragment} The weather forecast fragment
   */
  createWeatherFragment(dailyData, useMetric) {
    const fragment = document.createDocumentFragment();
    const today = new Date();
    const todayYear = today.getFullYear();
    const todayMonth = today.getMonth();
    const todayDate = today.getDate();
    const userLocale = navigator.language || WEATHER_CONFIG.DEFAULT_LOCALE;
    
    dailyData.forEach((day, index) => {
      const dayElement = this.createDayElement(day, {
        todayYear,
        todayMonth,
        todayDate,
        userLocale,
        useMetric
      });
      fragment.appendChild(dayElement);
    });
    
    return fragment;
  }
  
  /**
   * Create a single day weather element.
   * 
   * @param {Object} day - The day's weather data
   * @param {Object} options - Rendering options
   * @returns {HTMLElement} The day element
   */
  createDayElement(day, options) {
    const { todayYear, todayMonth, todayDate, userLocale, useMetric } = options;
    
    const dayElement = document.createElement('div');
    dayElement.className = 'weather-day';
    
    // Day name
    const dayName = this.getDayName(day, { todayYear, todayMonth, todayDate, userLocale });
    const dayNameDiv = document.createElement('div');
    dayNameDiv.className = 'weather-day-name';
    dayNameDiv.textContent = dayName;
    dayElement.appendChild(dayNameDiv);
    
    // Weather icon
    const img = this.createWeatherIcon(day);
    dayElement.appendChild(img);
    
    // Temperature
    const tempDiv = document.createElement('div');
    tempDiv.className = 'weather-temp';
    tempDiv.innerHTML = `
      <span class="temp-max">${Math.round(day.temp_max)}°${useMetric ? 'C' : 'F'}</span> /
      <span class="temp-min">${Math.round(day.temp_min)}°${useMetric ? 'C' : 'F'}</span>
    `;
    dayElement.appendChild(tempDiv);
    
    // Precipitation
    const precipDiv = document.createElement('div');
    precipDiv.className = 'weather-precip';
    precipDiv.textContent = `${Math.round(day.precipitation)}% precip`;
    dayElement.appendChild(precipDiv);
    
    return dayElement;
  }
  
  /**
   * Get the display name for a day.
   * 
   * @param {Object} day - The day's weather data
   * @param {Object} options - Date comparison options
   * @returns {string} The day name
   */
  getDayName(day, options) {
    const { todayYear, todayMonth, todayDate, userLocale } = options;
    const date = new Date(day.dt * 1000);
    
    if (date.getFullYear() === todayYear &&
        date.getMonth() === todayMonth &&
        date.getDate() === todayDate) {
      return userLocale.startsWith('en') ? 'Today' : date.toLocaleDateString(userLocale, { weekday: 'long' });
    } else {
      return date.toLocaleDateString(userLocale, { weekday: 'short' });
    }
  }
  
  /**
   * Create weather icon element.
   * 
   * @param {Object} day - The day's weather data
   * @returns {HTMLImageElement} The weather icon element
   */
  createWeatherIcon(day) {
    const img = document.createElement('img');
    img.className = 'weather-icon';
    img.src = `https://openweathermap.org/img/wn/${day.weather_icon}.png`;
    img.alt = day.weather;
    img.loading = 'lazy';
    img.onerror = function() {
      this.onerror = null;
      this.src = '/static/weather-fallback.png';
    };
    return img;
  }
}

// =============================================================================
// GLOBAL INSTANCES
// =============================================================================

let weatherToggleManager = null;
let weatherDataManager = null;

// =============================================================================
// APPLICATION INITIALIZATION
// =============================================================================

/**
 * Initialize the weather functionality.
 */
function initializeWeather() {
  // Initialize weather toggle
  weatherToggleManager = new WeatherToggleManager();
  
  // Initialize weather data management
  weatherDataManager = new WeatherDataManager();
}

// =============================================================================
// EVENT LISTENERS
// =============================================================================

// Initialize weather when DOM is ready
document.addEventListener('DOMContentLoaded', initializeWeather);

// =============================================================================
// EXPORT FOR MODULE SYSTEMS (if needed)
// =============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    WeatherToggleManager,
    WeatherDataManager,
    WEATHER_CONFIG
  };
}