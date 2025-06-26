/**
 * weather.js - Refactored
 * 
 * Weather widget module for the LinuxReport application, integrated with the global app object.
 * Handles weather data fetching, caching, rendering, and widget toggle functionality.
 * 
 * @author LinuxReport Team
 * @version 3.0.0
 */

(function(app) {
    'use strict';

    class WeatherToggleManager {
        constructor() {
            this.container = document.getElementById('weather-widget-container');
            this.content = document.getElementById('weather-content');
            this.toggleBtn = document.getElementById('weather-toggle-btn');
            this.collapsedLabel = document.getElementById('weather-collapsed-label');
            this.init();
        }

        init() {
            if (!app.config.WEATHER_WIDGET_TOGGLE_ENABLED) {
                this.disableToggle();
                return;
            }
            if (!this.container || !this.content || !this.toggleBtn) return;
            this.setInitialState();
            this.setupEventListeners();
        }

        disableToggle() {
            if (this.container) this.container.classList.remove('collapsed');
            if (this.content) this.content.style.display = '';
            if (this.toggleBtn) this.toggleBtn.style.display = 'none';
            if (this.collapsedLabel) this.collapsedLabel.style.display = 'none';
        }

        setInitialState() {
            const isCollapsed = app.utils.CookieManager.get('weatherCollapsed') === 'true' || app.config.WEATHER_DEFAULT_COLLAPSED;
            this.container.classList.toggle('collapsed', isCollapsed);
            this.toggleBtn.innerHTML = isCollapsed ? '&#9650;' : '&#9660;';
        }

        setupEventListeners() {
            this.toggleBtn.addEventListener('click', (e) => this.handleToggle(e));
        }

        handleToggle(event) {
            event.stopPropagation();
            const isCurrentlyCollapsed = this.container.classList.toggle('collapsed');
            this.toggleBtn.innerHTML = isCurrentlyCollapsed ? '&#9650;' : '&#9660;';
            app.utils.CookieManager.set('weatherCollapsed', isCurrentlyCollapsed ? 'true' : 'false');
        }
    }

    class WeatherDataManager {
        constructor() {
            this.container = document.getElementById('weather-container');
            this.widgetWrapper = document.getElementById('weather-widget-container');
            this.forecast = document.getElementById('weather-forecast');
            this.loading = document.getElementById('weather-loading');
            this.error = document.getElementById('weather-error');
            this.header = document.querySelector('#weather-container h3');
            this.debouncedLoad = app.utils.debounce(() => this.load(), app.config.WEATHER_DEBOUNCE_DELAY);
            this.init();
        }

        init() {
            this.debouncedLoad();
            const toggleBtn = document.getElementById('weather-toggle-btn');
            if (toggleBtn) {
                toggleBtn.addEventListener('click', () => this.debouncedLoad());
            }
        }

        load() {
            if (!this.container || (this.widgetWrapper && this.widgetWrapper.classList.contains('collapsed')) || getComputedStyle(this.container).display === 'none') return;
            const cachedData = app.utils.CacheManager.get('weatherData', app.config.WEATHER_CACHE_DURATION);
            if (cachedData) {
                this.render(cachedData, this.determineUnits());
                return;
            }
            this.fetch();
        }

        determineUnits() {
            const userLocale = new Intl.Locale(navigator.language || app.config.DEFAULT_LOCALE);
            return app.config.IMPERIAL_REGIONS.includes(userLocale.region) ? 'imperial' : 'metric';
        }

        async fetch() {
            const useMetric = this.determineUnits() === 'metric';
            try {
                const response = await fetch(`${app.config.WEATHER_BASE_URL}/api/weather?units=${useMetric ? 'metric' : 'imperial'}`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                app.utils.CacheManager.set('weatherData', data);
                this.render(data, useMetric);
            } catch (error) {
                this.showError('Unable to load weather data.');
            }
        }

        showError(message) {
            if (this.loading) this.loading.style.display = 'none';
            if (this.error) {
                this.error.style.display = 'block';
                this.error.textContent = message;
            }
        }

        render(data, useMetric) {
            if (!this.forecast || !this.loading || !this.error) return;
            if (this.header && data.city_name) this.header.textContent = `5-Day Weather (${data.city_name})`;
            if (!data.daily || data.daily.length === 0) {
                this.showError('No weather data available.');
                return;
            }
            const fragment = this.createWeatherFragment(data.daily, useMetric);
            this.forecast.innerHTML = '';
            this.forecast.appendChild(fragment);
            this.loading.style.display = 'none';
            this.forecast.style.display = 'flex';
        }

        createWeatherFragment(dailyData, useMetric) {
            const fragment = document.createDocumentFragment();
            dailyData.forEach(day => {
                fragment.appendChild(this.createDayElement(day, useMetric));
            });
            return fragment;
        }

        createDayElement(day, useMetric) {
            const dayElement = document.createElement('div');
            dayElement.className = 'weather-day';
            dayElement.innerHTML = `
                <div class="weather-day-name">${this.getDayName(day)}</div>
                <img class="weather-icon" src="https://openweathermap.org/img/wn/${day.weather_icon}.png" alt="${day.weather}" loading="lazy">
                <div class="weather-temp">
                    <span class="temp-max">${Math.round(day.temp_max)}°${useMetric ? 'C' : 'F'}</span> /
                    <span class="temp-min">${Math.round(day.temp_min)}°${useMetric ? 'C' : 'F'}</span>
                </div>
                <div class="weather-precip">${Math.round(day.precipitation)}% precip</div>
            `;
            return dayElement;
        }

        getDayName(day) {
            const date = new Date(day.dt * 1000);
            const today = new Date();
            if (date.toDateString() === today.toDateString()) return 'Today';
            return date.toLocaleDateString(navigator.language || app.config.DEFAULT_LOCALE, { weekday: 'short' });
        }
    }

    app.modules.weather = {
        init() {
            new WeatherToggleManager();
            new WeatherDataManager();
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        app.modules.weather.init();
    });

})(window.app);