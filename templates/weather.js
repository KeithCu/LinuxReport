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
            app.utils.logger.debug('[Weather] Creating WeatherWidget instance...');
            this.elements = this.getElements();
            app.utils.logger.debug('[Weather] Elements found:', this.elements.size);
            this.debouncedLoad = app.utils.debounce(() => this.load(), app.config.WEATHER_DEBOUNCE_DELAY);
            this.init();
        }

        getElements() {
            const elements = new Map();
            const ids = [
                'weather-widget-container', 'weather-content', 
                'weather-toggle-btn', 'weather-collapsed-label', 'weather-unit-toggle'
            ];
            ids.forEach(id => elements.set(id, document.getElementById(id)));
            
            // Use weather-content as the main container for hiding/showing
            elements.set('weather-container', document.getElementById('weather-content'));
            
            // Look for weather elements inside the weather-content-inner div
            const contentInner = document.querySelector('.weather-content-inner');
            if (contentInner) {
                elements.set('weather-forecast', contentInner.querySelector('#weather-forecast'));
                elements.set('weather-loading', contentInner.querySelector('#weather-loading'));
                elements.set('weather-error', contentInner.querySelector('#weather-error'));
                elements.set('header', contentInner.querySelector('h3'));
            }
            
            // Cache meta elements for location data
            elements.set('latMeta', document.querySelector('meta[name="weather-lat"]'));
            elements.set('lonMeta', document.querySelector('meta[name="weather-lon"]'));
            
            return elements;
        }

        init() {
            app.utils.logger.debug('[Weather] Initializing weather widget...');
            this.initToggle();
            this.initUnitToggle();
            app.utils.logger.debug('[Weather] Toggle initialized, calling debouncedLoad...');
            this.debouncedLoad();
            
            const toggleBtn = this.elements.get('weather-toggle-btn');
            if (toggleBtn) {
                toggleBtn.addEventListener('click', () => this.debouncedLoad());
            }

            // Apply collapsed state first, then make visible to prevent flash
            const container = this.elements.get('weather-container');
            const widgetWrapper = this.elements.get('weather-widget-container');
            if (container && widgetWrapper && app.config.WEATHER_WIDGET_TOGGLE_ENABLED) {
                const isCollapsed = (app.utils.CookieManager.get('weatherCollapsed') ?? String(app.config.WEATHER_DEFAULT_COLLAPSED)) === 'true';
                if (isCollapsed) {
                    widgetWrapper.classList.add('collapsed');
                    // Keep container hidden when collapsed
                    // TUTORIAL: Inline style for initial collapsed state
                    // This cannot be moved to CSS because:
                    // 1. The collapsed state is determined by JavaScript (cookie check)
                    // 2. CSS cannot read cookies or JavaScript variables
                    // 3. The initial state needs to be set before CSS classes are applied
                    // 4. This ensures the container is hidden immediately on page load
                    // Alternative: Could use CSS :not(.collapsed) selectors, but less reliable for initial state
                    container.style.display = 'none';
                } else {
                    // Show the container and start loading if not collapsed
                    // TUTORIAL: Inline styles for initial visible state
                    // These cannot be moved to CSS because:
                    // 1. The visibility state depends on JavaScript cookie check
                    // 2. CSS cannot conditionally apply styles based on JavaScript state
                    // 3. The container needs to be visible immediately for proper layout
                    // 4. This ensures smooth initial rendering without flash of hidden content
                    container.style.display = 'block';
                    container.style.visibility = 'visible';
                }
            }
            app.utils.logger.debug('[Weather] Initialization complete');
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
            if (content) content.style.display = 'block';
            if (toggleBtn) toggleBtn.style.display = 'none';
            if (collapsedLabel) collapsedLabel.style.display = 'none';
        }

        initUnitToggle() {
            const unitToggle = this.elements.get('weather-unit-toggle');
            if (!unitToggle) return;

            // Set initial state
            const currentUnits = this.getUnits();
            unitToggle.textContent = currentUnits === 'metric' ? '°F' : '°C';
            unitToggle.title = `Switch to ${currentUnits === 'metric' ? 'Fahrenheit' : 'Celsius'}`;

            // Add click handler
            unitToggle.addEventListener('click', () => {
                const currentUnits = this.getUnits();
                const newUnits = currentUnits === 'metric' ? 'imperial' : 'metric';
                
                // Save preference
                localStorage.setItem('weatherUnits', newUnits);
                
                // Update toggle button
                unitToggle.textContent = newUnits === 'metric' ? '°F' : '°C';
                unitToggle.title = `Switch to ${newUnits === 'metric' ? 'Fahrenheit' : 'Celsius'}`;
                
                // Re-render current weather data with new units
                const forecast = this.elements.get('weather-forecast');
                if (forecast && forecast.children.length > 0) {
                    // Re-render the current data
                    this.render(this.currentWeatherData).catch(error => {
                        app.utils.logger.error('[Weather] Error re-rendering after unit change:', error);
                    });
                }
            });
        }

        load() {
            app.utils.logger.debug('[Weather] load() called');
            const container = this.elements.get('weather-container');
            const widgetWrapper = this.elements.get('weather-widget-container');
            
            if (!container) {
                app.utils.logger.debug('[Weather] No container found, returning');
                return;
            }
            
            if (widgetWrapper && widgetWrapper.classList.contains('collapsed')) {
                app.utils.logger.debug('[Weather] Widget is collapsed, returning');
                return;
            }
            
            if (getComputedStyle(container).display === 'none') {
                app.utils.logger.debug('[Weather] Container is hidden, returning');
                return;
            }
            
            app.utils.logger.debug('[Weather] Calling fetch()...');
            this.fetch();
        }

        getUnits() {
            // Get user's preferred temperature units from localStorage or browser locale
            const savedUnits = localStorage.getItem('weatherUnits');
            if (savedUnits) {
                return savedUnits;
            }
            
            // Default to imperial (Fahrenheit) for US users, metric for others
            const locale = navigator.language || 'en-US';
            return locale.startsWith('en-US') ? 'imperial' : 'metric';
        }

        fahrenheitToCelsius(fahrenheit) {
            return Math.round((fahrenheit - 32) * 5/9);
        }

        celsiusToFahrenheit(celsius) {
            return Math.round((celsius * 9/5) + 32);
        }

        getCachedLocation() {
            // Check if we have location data from response headers
            const latHeader = this.elements.get('latMeta');
            const lonHeader = this.elements.get('lonMeta');
            
            if (latHeader && lonHeader) {
                const lat = parseFloat(latHeader.getAttribute('content'));
                const lon = parseFloat(lonHeader.getAttribute('content'));
                
                if (!isNaN(lat) && !isNaN(lon)) {
                    app.utils.logger.debug('[Weather] Found cached location in meta tags:', lat, lon);
                    return { lat, lon, source: 'cached' };
                }
            }
            
            app.utils.logger.debug('[Weather] No cached location found in meta tags');
            return null;
        }

        /**
         * Gets cached icon data from localStorage
         * @param {string} iconCode - Weather icon code (e.g., '01d')
         * @returns {string|null} Cached icon data URL or null if not found
         */
        getCachedIcon(iconCode) {
            try {
                const cacheKey = `weather_icon_${iconCode}`;
                return localStorage.getItem(cacheKey);
            } catch (error) {
                app.utils.logger.debug('[Weather] Error reading cached icon:', error);
                return null;
            }
        }

        /**
         * Caches icon data in localStorage
         * @param {string} iconCode - Weather icon code
         * @param {string} dataUrl - Base64 data URL of the icon
         */
        setCachedIcon(iconCode, dataUrl) {
            try {
                const cacheKey = `weather_icon_${iconCode}`;
                localStorage.setItem(cacheKey, dataUrl);
                app.utils.logger.debug('[Weather] Cached icon:', iconCode);
            } catch (error) {
                app.utils.logger.debug('[Weather] Error caching icon:', error);
            }
        }



        /**
         * Loads and caches a weather icon using persistent localStorage
         * @param {string} iconCode - Weather icon code
         * @returns {Promise<string>} Promise resolving to icon data URL or official URL
         */
        async loadAndCacheIcon(iconCode) {
            // Check persistent localStorage cache first
            const cached = this.getCachedIcon(iconCode);
            if (cached) {
                app.utils.logger.debug('[Weather] Using cached icon for:', iconCode);
                return cached;
            }

            // Load from network and cache persistently
            try {
                app.utils.logger.debug('[Weather] Fetching icon from network:', iconCode);
                const iconUrl = `https://openweathermap.org/img/wn/${iconCode}.png`;
                const response = await fetch(iconUrl);
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const blob = await response.blob();
                const dataUrl = await this.blobToDataUrl(blob);
                
                // Cache the icon persistently
                this.setCachedIcon(iconCode, dataUrl);
                app.utils.logger.debug('[Weather] Successfully cached icon:', iconCode);
                
                return dataUrl;
            } catch (error) {
                app.utils.logger.debug('[Weather] Failed to cache icon, using direct URL:', iconCode, error);
                // Return official URL as fallback
                return `https://openweathermap.org/img/wn/${iconCode}.png`;
            }
        }

        /**
         * Converts a blob to a data URL
         * @param {Blob} blob - The blob to convert
         * @returns {Promise<string>} Promise resolving to data URL
         */
        blobToDataUrl(blob) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
        }



        async fetch(retryCount = 0) {
            const maxRetries = 5; // Reduced retry limit
            
            const attemptFetch = async () => {
                try {
                    app.utils.logger.debug('[Weather] Starting fetch...');
                    const startTime = performance.now();
                    
                    // Determine location strategy
                    let location;
                    if (app.config.DISABLE_CLIENT_GEOLOCATION) {
                        app.utils.logger.debug('[Weather] Client geolocation disabled');
                        location = { lat: null, lon: null, source: 'client_disabled' };
                    } else {
                        // Try cached location first
                        location = this.getCachedLocation();
                        
                        if (!location) {
                            // No cached location, try browser geolocation
                            try {
                                app.utils.logger.debug('[Weather] Requesting browser geolocation...');
                                const coords = await app.utils.GeolocationManager.getLocation();
                                location = { 
                                    lat: coords.lat, 
                                    lon: coords.lon, 
                                    source: 'browser' 
                                };
                                app.utils.logger.debug('[Weather] Browser geolocation successful:', location);
                            } catch (geolocationError) {
                                app.utils.logger.debug('[Weather] Browser geolocation failed:', geolocationError.message);
                                if (geolocationError.code === 1) { // PERMISSION_DENIED
                                    location = { lat: null, lon: null, source: 'denied_permission' };
                                } else {
                                    location = { lat: null, lon: null, source: 'unavailable' };
                                }
                            }
                        }
                    }
                    
                    // Build URL with location parameters
                    const params = new URLSearchParams();
                    
                    // Add location parameters only if we have valid coordinates
                    if (location.lat !== null && location.lon !== null && 
                        location.source !== 'denied_permission' && 
                        location.source !== 'client_disabled') {
                        params.append('lat', location.lat);
                        params.append('lon', location.lon);
                        app.utils.logger.debug('[Weather] Sending coordinates to server:', location.lat, location.lon);
                    } else {
                        app.utils.logger.debug('[Weather] No coordinates to send, server will use fallback location');
                    }
                    
                    // Add cache busting parameter
                    const now = new Date();
                    const cacheBuster = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}${String(now.getHours()).padStart(2, '0')}`;
                    params.append('_cb', cacheBuster);
                    
                    const url = `${app.config.WEATHER_BASE_URL}/api/weather?${params.toString()}`;
                    app.utils.logger.debug('[Weather] Making request to:', url);
                    app.utils.logger.debug('[Weather] Time spent on geolocation:', performance.now() - startTime, 'ms');
                    
                    const response = await fetch(url);
                    app.utils.logger.debug('[Weather] Response received after:', performance.now() - startTime, 'ms');
                    
                    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                    const data = await response.json();
                    app.utils.logger.debug('[Weather] Data parsed after:', performance.now() - startTime, 'ms');
                    
                    await this.render(data);
                } catch (error) {
                    // If the weather request failed, retry with exponential backoff
                    if (retryCount < maxRetries) {
                        retryCount++;
                        const delay = Math.min(1000 * Math.pow(2, retryCount - 1), 5000); // Max 5 seconds
                        app.utils.logger.debug(`[Weather] Request failed, retrying in ${delay}ms (attempt ${retryCount}/${maxRetries})...`);
                        setTimeout(() => this.fetch(retryCount), delay);
                        return;
                    }
                    
                    app.utils.logger.error('[Weather] Max retries reached, showing error');
                    this.showError('Unable to load weather data. Please try again later.');
                }
            };
            
            await attemptFetch();
        }

        showError(message) {
            const error = this.elements.get('weather-error');
            const loading = this.elements.get('weather-loading');
            
            app.utils.logger.debug('[Weather] ShowError - error:', !!error, 'loading:', !!loading);
            
            this.showElement(error, message);
            this.hideElement(loading);
        }

        async render(data) {
            const forecast = this.elements.get('weather-forecast');
            const header = this.elements.get('header');
            const loading = this.elements.get('weather-loading');
            const container = this.elements.get('weather-container');
            
            app.utils.logger.debug('[Weather] Render - forecast:', !!forecast, 'header:', !!header, 'loading:', !!loading);
            app.utils.logger.debug('[Weather] Forecast element:', forecast);
            app.utils.logger.debug('[Weather] Forecast element ID:', forecast?.id);
            
            if (!forecast || !header) return;

            // Store current weather data for unit toggle re-rendering
            this.currentWeatherData = data;

            if (data.city_name) {
                header.textContent = `5-Day Weather (${data.city_name})`;
            }

            if (!data.daily?.length) {
                this.showError('No weather data available.');
                return;
            }

            // Create day HTML elements with cached icons
            const dayElements = await Promise.all(
                data.daily.map(day => this.createDayHTML(day))
            );
            
            forecast.innerHTML = dayElements.join('');
            this.hideElement(loading);
            this.showElement(forecast);
            
            // The weather container should already be visible if we're rendering data
            // Only ensure it's visible if it was hidden for some reason
            if (container && container.style.display === 'none') {
                container.style.display = 'block';
                container.style.visibility = 'visible';
            }
            
            // Apply horizontal layout using CSS class
            if (forecast) {
                forecast.classList.add('weather-forecast-horizontal');
                app.utils.logger.debug('[Weather] Applied CSS class for horizontal layout');
                app.utils.logger.debug('[Weather] Forecast element classes:', forecast.className);
                app.utils.logger.debug('[Weather] Forecast computed style:', getComputedStyle(forecast).display);
            }
        }

        async createDayHTML(day) {
            const useMetric = this.getUnits() === 'metric';
            const unit = useMetric ? 'C' : 'F';
            
            // Convert temperatures if needed (server always provides Fahrenheit)
            let tempMax = Math.round(day.temp_max);
            let tempMin = Math.round(day.temp_min);
            
            if (useMetric) {
                tempMax = this.fahrenheitToCelsius(tempMax);
                tempMin = this.fahrenheitToCelsius(tempMin);
            }
            
            // Load and cache the weather icon
            const iconSrc = await this.loadAndCacheIcon(day.weather_icon);
            
            return `
                <div class="weather-day">
                    <div class="weather-day-name">${this.getDayName(day)}</div>
                    <img class="weather-icon" src="${iconSrc}" alt="${day.weather}" loading="lazy">
                    <div class="weather-temp">
                        <span class="temp-max">${tempMax}°${unit}</span> /
                        <span class="temp-min">${tempMin}°${unit}</span>
                    </div>
                    <div class="weather-precip">${Math.round(day.precipitation)}% precip</div>
                </div>
            `;
        }

        getDayName(day) {
            const date = new Date(day.dt * 1000);
            const today = new Date();
            const isToday = date.toDateString() === today.toDateString();
            const userLocale = navigator.language || app.config.DEFAULT_LOCALE;
            
            return isToday ? 'Today' : 
                   date.toLocaleDateString(userLocale, { weekday: 'short' });
        }

        setCollapsed(isCollapsed, saveCookie = false) {
            const widgetWrapper = this.elements.get('weather-widget-container');
            const toggleBtn = this.elements.get('weather-toggle-btn');
            const container = this.elements.get('weather-container');
            
            if (widgetWrapper) {
                widgetWrapper.classList.toggle('collapsed', isCollapsed);
            }
            
            if (container) {
                // Hide/show the weather content based on collapsed state
                if (isCollapsed) {
                    container.style.display = 'none';
                } else {
                    container.style.display = 'block';
                    container.style.visibility = 'visible';
                }
            }
            
            if (toggleBtn) {
                toggleBtn.innerHTML = isCollapsed ? '&#9650;' : '&#9660;';
                // Set aria-expanded attribute for accessibility
                toggleBtn.setAttribute('aria-expanded', !isCollapsed);
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
            app.utils.logger.debug('[Weather] Initializing weather widget...');
            try {
                new WeatherWidget();
                app.utils.logger.debug('[Weather] Weather widget initialized successfully');
            } catch (error) {
                app.utils.logger.error('[Weather] Failed to initialize weather widget:', error);
            }
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        app.utils.logger.debug('[Weather] DOM loaded, initializing weather...');
        app.modules.weather.init();
    });

})(window.app);