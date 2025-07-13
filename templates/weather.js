/**
 * weather.js
 * 
 * Weather widget module for the LinuxReport application, integrated with the global app object.
 * Handles weather data fetching, rendering, and widget toggle functionality.
 * 
 * @author LinuxReport Team
 * @version 3.1.0
 */

(function(app) {
    'use strict';

    class WeatherWidget {
        constructor() {
            this.elements = this.getElements();
            this.debouncedLoad = app.utils.debounce(() => this.load(), app.config.WEATHER_DEBOUNCE_DELAY);
            this.init();
        }

        getElements() {
            const elements = new Map();
            const ids = [
                'weather-container', 'weather-widget-container', 'weather-content', 
                'weather-toggle-btn', 'weather-collapsed-label', 'weather-forecast', 
                'weather-loading', 'weather-error'
            ];
            ids.forEach(id => elements.set(id, document.getElementById(id)));
            elements.set('header', document.querySelector('#weather-container h3'));
            return elements;
        }

        init() {
            this.initToggle();
            this.debouncedLoad();
            
            const toggleBtn = this.elements.get('weather-toggle-btn');
            if (toggleBtn) {
                toggleBtn.addEventListener('click', () => this.debouncedLoad());
            }
        }

        initToggle() {
            if (!app.config.WEATHER_WIDGET_TOGGLE_ENABLED) {
                this.disableToggle();
                return;
            }

            const widgetWrapper = this.elements.get('weather-widget-container');
            const toggleBtn = this.elements.get('weather-toggle-btn');
            if (!widgetWrapper || !toggleBtn) return;

            const isCollapsed = (app.utils.CookieManager.get('weatherCollapsed') ?? String(app.config.WEATHER_DEFAULT_COLLAPSED)) === 'true';
            this.setCollapsed(isCollapsed);

            toggleBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const isCurrentlyCollapsed = widgetWrapper.classList.toggle('collapsed');
                this.setCollapsed(isCurrentlyCollapsed, true);
            });
        }

        disableToggle() {
            const { widgetWrapper, content, toggleBtn, collapsedLabel } = this.elements;
            if (widgetWrapper) widgetWrapper.classList.remove('collapsed');
            if (content) content.style.display = '';
            if (toggleBtn) toggleBtn.style.display = 'none';
            if (collapsedLabel) collapsedLabel.style.display = 'none';
        }

        load() {
            const { container, widgetWrapper } = this.elements;
            if (!container || (widgetWrapper && widgetWrapper.classList.contains('collapsed')) || 
                getComputedStyle(container).display === 'none') return;
            
            this.fetch();
        }

        getUnits() {
            // Force imperial units for now while debugging
            return 'imperial';
        }

        async fetch() {
            const useMetric = this.getUnits() === 'metric';
            try {
                console.log('[Weather] Starting fetch...');
                const startTime = performance.now();
                
                // Get user's geolocation first
                console.log('[Weather] Getting location...');
                const location = await app.utils.GeolocationManager.getLocation();
                console.log('[Weather] Location obtained:', location);
                
                // Build URL with location parameters
                const params = new URLSearchParams({
                    units: useMetric ? 'metric' : 'imperial'
                });
                
                // Add location parameters if geolocation was successful
                if (location.lat !== null && location.lon !== null) {
                    params.append('lat', location.lat);
                    params.append('lon', location.lon);
                }
                // If geolocation failed, don't pass any coordinates - backend will handle fallback
                
                // Add cache busting parameter with current date and hour
                const now = new Date();
                const cacheBuster = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}${String(now.getHours()).padStart(2, '0')}`;
                params.append('_cb', cacheBuster);
                
                const url = `${app.config.WEATHER_BASE_URL}/api/weather?${params.toString()}`;
                console.log('[Weather] Making request to:', url);
                console.log('[Weather] Time before fetch:', performance.now() - startTime, 'ms');
                
                const response = await fetch(url);
                console.log('[Weather] Response received after:', performance.now() - startTime, 'ms');
                
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                console.log('[Weather] Data parsed after:', performance.now() - startTime, 'ms');
                this.render(data, useMetric);
            } catch (error) {
                this.showError('Unable to load weather data.');
                app.utils.handleError('Fetch Weather', error);
            }
        }

        showError(message) {
            this.showElement(this.elements.get('error'), message);
            this.hideElement(this.elements.get('loading'));
        }

        render(data, useMetric) {
            const forecast = this.elements.get('weather-forecast');
            const header = this.elements.get('header');
            if (!forecast || !header) return;

            if (data.city_name) {
                header.textContent = `5-Day Weather (${data.city_name})`;
            }

            if (!data.daily?.length) {
                this.showError('No weather data available.');
                return;
            }

            forecast.innerHTML = data.daily.map(day => this.createDayHTML(day, useMetric)).join('');
            this.hideElement(this.elements.get('loading'));
            this.showElement(forecast);
        }

        createDayHTML(day, useMetric) {
            const unit = 'F';
            return `
                <div class="weather-day">
                    <div class="weather-day-name">${this.getDayName(day)}</div>
                    <img class="weather-icon" src="https://openweathermap.org/img/wn/${day.weather_icon}.png" alt="${day.weather}" loading="lazy">
                    <div class="weather-temp">
                        <span class="temp-max">${Math.round(day.temp_max)}°${unit}</span> /
                        <span class="temp-min">${Math.round(day.temp_min)}°${unit}</span>
                    </div>
                    <div class="weather-precip">${Math.round(day.precipitation)}% precip</div>
                </div>
            `;
        }

        getDayName(day) {
            const date = new Date(day.dt * 1000);
            const today = new Date();
            return date.toDateString() === today.toDateString() ? 'Today' : 
                   date.toLocaleDateString(navigator.language || app.config.DEFAULT_LOCALE, { weekday: 'short' });
        }
    }

    app.modules.weather = {
        init() {
            new WeatherWidget();
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        app.modules.weather.init();
    });

})(window.app);