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
            // console.log('[Weather] Creating WeatherWidget instance...');
            this.elements = this.getElements();
            // console.log('[Weather] Elements found:', this.elements.size);
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
            // console.log('[Weather] Initializing weather widget...');
            this.initToggle();
            // console.log('[Weather] Toggle initialized, calling debouncedLoad...');
            this.debouncedLoad();
            
            const toggleBtn = this.elements.get('weather-toggle-btn');
            if (toggleBtn) {
                toggleBtn.addEventListener('click', () => this.debouncedLoad());
            }
            // console.log('[Weather] Initialization complete');
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
            const widgetWrapper = this.elements.get('weather-widget-container');
            const content = this.elements.get('weather-content');
            const toggleBtn = this.elements.get('weather-toggle-btn');
            const collapsedLabel = this.elements.get('weather-collapsed-label');
            
            if (widgetWrapper) widgetWrapper.classList.remove('collapsed');
            if (content) content.style.display = '';
            if (toggleBtn) toggleBtn.style.display = 'none';
            if (collapsedLabel) collapsedLabel.style.display = 'none';
        }

        load() {
            // console.log('[Weather] load() called');
            const container = this.elements.get('weather-container');
            const widgetWrapper = this.elements.get('weather-widget-container');
            
            if (!container) {
                // console.log('[Weather] No container found, returning');
                return;
            }
            
            if (widgetWrapper && widgetWrapper.classList.contains('collapsed')) {
                // console.log('[Weather] Widget is collapsed, returning');
                return;
            }
            
            if (getComputedStyle(container).display === 'none') {
                // console.log('[Weather] Container is hidden, returning');
                return;
            }
            
            // console.log('[Weather] Calling fetch()...');
            this.fetch();
        }

        getUnits() {
            // Force imperial units for now while debugging
            return 'imperial';
        }

        async fetch() {
            const useMetric = this.getUnits() === 'metric';
            try {
                // console.log('[Weather] Starting fetch...');
                const startTime = performance.now();
                
                // Get user's geolocation first
                // console.log('[Weather] Getting location...');
                const location = await app.utils.GeolocationManager.getLocation();
                // console.log('[Weather] Location obtained:', location);
                
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
                // console.log('[Weather] Making request to:', url);
                // console.log('[Weather] Time spent on geolocation:', performance.now() - startTime, 'ms');
                
                const response = await fetch(url);
                // console.log('[Weather] Response received after:', performance.now() - startTime, 'ms');
                
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                // console.log('[Weather] Data parsed after:', performance.now() - startTime, 'ms');
                this.render(data, useMetric);
            } catch (error) {
                this.showError('Unable to load weather data.');
                app.utils.handleError('Fetch Weather', error);
            }
        }

        showError(message) {
            const error = this.elements.get('weather-error');
            const loading = this.elements.get('weather-loading');
            
            console.log('[Weather] ShowError - error:', !!error, 'loading:', !!loading);
            
            this.showElement(error, message);
            this.hideElement(loading);
        }

        render(data, useMetric) {
            const forecast = this.elements.get('weather-forecast');
            const header = this.elements.get('header');
            const loading = this.elements.get('weather-loading');
            
            console.log('[Weather] Render - forecast:', !!forecast, 'header:', !!header, 'loading:', !!loading);
            
            if (!forecast || !header) return;

            if (data.city_name) {
                header.textContent = `5-Day Weather (${data.city_name})`;
            }

            if (!data.daily?.length) {
                this.showError('No weather data available.');
                return;
            }

            forecast.innerHTML = data.daily.map(day => this.createDayHTML(day, useMetric)).join('');
            this.hideElement(loading);
            this.showElement(forecast);
            
            // Force horizontal layout with inline styles
            if (forecast) {
                forecast.style.display = 'flex';
                forecast.style.flexDirection = 'row';
                forecast.style.flexWrap = 'nowrap';
                forecast.style.width = 'max-content';
                console.log('[Weather] Applied inline styles for horizontal layout');
            }
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

        setCollapsed(isCollapsed, saveCookie = false) {
            const widgetWrapper = this.elements.get('weather-widget-container');
            const toggleBtn = this.elements.get('weather-toggle-btn');
            
            if (widgetWrapper) {
                widgetWrapper.classList.toggle('collapsed', isCollapsed);
            }
            
            if (toggleBtn) {
                toggleBtn.innerHTML = isCollapsed ? '&#9650;' : '&#9660;';
            }
            
            if (saveCookie) {
                app.utils.CookieManager.set('weatherCollapsed', isCollapsed ? 'true' : 'false');
            }
        }

        showElement(element, content = null) {
            if (element) {
                if (content !== null) {
                    element.textContent = content;
                }
                element.style.display = 'block';
            }
        }

        hideElement(element) {
            if (element) {
                element.style.display = 'none';
            }
        }
    }

    app.modules.weather = {
        init() {
            // console.log('[Weather] Initializing weather widget...');
            try {
                new WeatherWidget();
                // console.log('[Weather] Weather widget initialized successfully');
            } catch (error) {
                console.error('[Weather] Failed to initialize weather widget:', error);
            }
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        // console.log('[Weather] DOM loaded, initializing weather...');
        app.modules.weather.init();
    });

})(window.app);