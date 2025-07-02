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
            return {
                container: document.getElementById('weather-container'),
                widgetWrapper: document.getElementById('weather-widget-container'),
                content: document.getElementById('weather-content'),
                toggleBtn: document.getElementById('weather-toggle-btn'),
                collapsedLabel: document.getElementById('weather-collapsed-label'),
                forecast: document.getElementById('weather-forecast'),
                loading: document.getElementById('weather-loading'),
                error: document.getElementById('weather-error'),
                header: document.querySelector('#weather-container h3')
            };
        }

        init() {
            this.initToggle();
            this.debouncedLoad();
            if (this.elements.toggleBtn) {
                this.elements.toggleBtn.addEventListener('click', () => this.debouncedLoad());
            }
        }

        initToggle() {
            if (!app.config.WEATHER_WIDGET_TOGGLE_ENABLED) {
                this.disableToggle();
                return;
            }
            if (!this.elements.widgetWrapper || !this.elements.content || !this.elements.toggleBtn) return;
            
            const isCollapsed = app.utils.CookieManager.get('weatherCollapsed') === 'true' || app.config.WEATHER_DEFAULT_COLLAPSED;
            this.elements.widgetWrapper.classList.toggle('collapsed', isCollapsed);
            this.elements.toggleBtn.innerHTML = isCollapsed ? '&#9650;' : '&#9660;';
            
            this.elements.toggleBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const isCurrentlyCollapsed = this.elements.widgetWrapper.classList.toggle('collapsed');
                this.elements.toggleBtn.innerHTML = isCurrentlyCollapsed ? '&#9650;' : '&#9660;';
                app.utils.CookieManager.set('weatherCollapsed', isCurrentlyCollapsed ? 'true' : 'false');
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
                // Add cache busting parameter with current date and hour
                const now = new Date();
                const cacheBuster = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}${String(now.getHours()).padStart(2, '0')}`;
                const response = await fetch(`${app.config.WEATHER_BASE_URL}/api/weather?units=${useMetric ? 'metric' : 'imperial'}&_cb=${cacheBuster}`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                this.render(data, useMetric);
            } catch (error) {
                this.showError('Unable to load weather data.');
                app.utils.handleError('Fetch Weather', error);
            }
        }

        showError(message) {
            const { loading, error } = this.elements;
            if (loading) loading.style.display = 'none';
            if (error) {
                error.style.display = 'block';
                error.textContent = message;
            }
        }

        render(data, useMetric) {
            const { forecast, loading, error, header } = this.elements;
            if (!forecast || !loading || !error) return;
            
            if (header && data.city_name) header.textContent = `5-Day Weather (${data.city_name})`;
            if (!data.daily?.length) {
                this.showError('No weather data available.');
                return;
            }
            
            forecast.innerHTML = data.daily.map(day => this.createDayHTML(day, useMetric)).join('');
            loading.style.display = 'none';
            forecast.style.display = 'flex';
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