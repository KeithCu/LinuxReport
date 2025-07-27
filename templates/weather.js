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
            
            // Cache meta elements for location data
            elements.set('latMeta', document.querySelector('meta[name="weather-lat"]'));
            elements.set('lonMeta', document.querySelector('meta[name="weather-lon"]'));
            
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
            if (content) content.style.display = 'block';
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

        getCachedLocation() {
            // Check if we have location data from response headers
            const latHeader = this.elements.get('latMeta');
            const lonHeader = this.elements.get('lonMeta');
            
            if (latHeader && lonHeader) {
                const lat = parseFloat(latHeader.getAttribute('content'));
                const lon = parseFloat(lonHeader.getAttribute('content'));
                
                if (!isNaN(lat) && !isNaN(lon)) {
                    console.log('[Weather] Found cached location in meta tags:', lat, lon);
                    return { lat, lon };
                }
            }
            
            console.log('[Weather] No cached location found in meta tags');
            return null;
        }

        async fetch(retryCount = 0) {
            const useMetric = this.getUnits() === 'metric';
            const maxRetries = 20; // Much higher retry limit
            
            const attemptFetch = async () => {
                try {
                    // console.log('[Weather] Starting fetch...');
                    const startTime = performance.now();
                    
                    // Check for cached location in response headers first
                    let location = this.getCachedLocation();
                    
                                         if (!location || location.lat === null || location.lon === null) {
                         // No cached location, get user's geolocation
                         console.log('[Weather] Getting location...');
                         let geolocationAttempts = 0;
                         const maxGeolocationAttempts = 60; // Allow up to 60 attempts (15 seconds with 250ms delays)
                         let userDeniedPermission = false;
                         
                         while (geolocationAttempts < maxGeolocationAttempts && !userDeniedPermission) {
                             try {
                                 location = await app.utils.GeolocationManager.getLocation();
                                 console.log('[Weather] Location obtained:', location);
                                 
                                 // If we got valid coordinates, break out of the retry loop
                                 if (location.lat !== null && location.lon !== null) {
                                     console.log('[Weather] Valid coordinates obtained, proceeding with weather request');
                                     break;
                                 } else {
                                     geolocationAttempts++;
                                     console.log(`[Weather] Geolocation returned null coordinates, retrying... (attempt ${geolocationAttempts}/${maxGeolocationAttempts})`);
                                     await new Promise(resolve => setTimeout(resolve, 250)); // 250ms delay
                                 }
                             } catch (geolocationError) {
                                 geolocationAttempts++;
                                 
                                 // Check if user explicitly denied permission
                                 if (geolocationError.code === 1) { // PERMISSION_DENIED
                                     console.log('[Weather] User denied geolocation permission, letting server use fallback');
                                     userDeniedPermission = true;
                                     // Don't send any coordinates - let the server use its own fallback logic
                                     location = { lat: null, lon: null, source: 'denied_permission' };
                                     break;
                                 } else if (geolocationError.code === 2) { // POSITION_UNAVAILABLE
                                     console.log(`[Weather] Position unavailable (attempt ${geolocationAttempts}/${maxGeolocationAttempts}):`, geolocationError.message);
                                     await new Promise(resolve => setTimeout(resolve, 250)); // 250ms delay
                                 } else if (geolocationError.code === 3) { // TIMEOUT
                                     console.log(`[Weather] Geolocation timeout (attempt ${geolocationAttempts}/${maxGeolocationAttempts}):`, geolocationError.message);
                                     await new Promise(resolve => setTimeout(resolve, 250)); // 250ms delay
                                 } else {
                                     console.log(`[Weather] Geolocation error (attempt ${geolocationAttempts}/${maxGeolocationAttempts}):`, geolocationError.message);
                                     await new Promise(resolve => setTimeout(resolve, 250)); // 250ms delay
                                 }
                             }
                         }
                         
                         // If we exhausted attempts without getting location, use default
                         if (geolocationAttempts >= maxGeolocationAttempts && !userDeniedPermission) {
                             console.log('[Weather] Geolocation timed out after max attempts, using default location (Detroit)');
                             location = { lat: 42.3314, lon: -83.0458, source: 'default' }; // Detroit coordinates
                         }
                     } else {
                        console.log('[Weather] Using cached location from headers:', location);
                    }
                    
                                         // Build URL with location parameters
                     const params = new URLSearchParams({
                         units: useMetric ? 'metric' : 'imperial'
                     });
                     
                     // Add location parameters only if we have valid coordinates and user didn't deny permission
                     if (location.lat !== null && location.lon !== null && location.source !== 'denied_permission') {
                         params.append('lat', location.lat);
                         params.append('lon', location.lon);
                         console.log('[Weather] Sending coordinates to server:', location.lat, location.lon);
                     } else {
                         console.log('[Weather] No coordinates to send, server will use fallback location');
                     }
                    
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
                    // If the weather request failed, keep retrying until we succeed
                    if (retryCount < maxRetries) {
                        retryCount++;
                        console.log(`[Weather] Request failed, retrying in 250ms (attempt ${retryCount}/${maxRetries})...`);
                        setTimeout(() => this.fetch(retryCount), 250); // Non-blocking retry
                        return;
                    }
                    
                    this.showError('Unable to load weather data.');
                    app.utils.handleError('Fetch Weather', error);
                }
            };
            
            return attemptFetch();
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
            const container = this.elements.get('weather-container');
            
            console.log('[Weather] Render - forecast:', !!forecast, 'header:', !!header, 'loading:', !!loading);
            console.log('[Weather] Forecast element:', forecast);
            console.log('[Weather] Forecast element ID:', forecast?.id);
            
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
            
            // The weather container should already be visible if we're rendering data
            // Only ensure it's visible if it was hidden for some reason
            if (container && container.style.display === 'none') {
                container.style.display = 'block';
                container.style.visibility = 'visible';
            }
            
            // Apply horizontal layout using CSS class
            if (forecast) {
                forecast.classList.add('weather-forecast-horizontal');
                console.log('[Weather] Applied CSS class for horizontal layout');
                console.log('[Weather] Forecast element classes:', forecast.className);
                console.log('[Weather] Forecast computed style:', getComputedStyle(forecast).display);
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