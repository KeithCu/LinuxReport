/**
 * app.js
 *
 * Main application module for LinuxReport. Consolidates shared configuration,
 * utilities, and core application logic into a single global 'app' object.
 * This improves modularity and reduces global namespace pollution.
 *
 * @author LinuxReport Team
 * @version 3.1.0
 */

(function() {
  'use strict';

  // =============================================================================
  // INITIALIZE GLOBAL APP OBJECT
  // =============================================================================

  const app = {
    config: {
      // Core settings
      AUTO_REFRESH_INTERVAL: 3601 * 1000,
      ACTIVITY_TIMEOUT: 5 * 60 * 1000,
      ITEMS_PER_PAGE: 8,
      INFINITE_ITEMS_PER_PAGE: 20,
      SCROLL_TIMEOUT: 10000,
      DEFAULT_THEME: 'silver',
      DEFAULT_FONT: 'sans-serif',
      FONT_CLASSES: [
        'font-system', 'font-monospace', 'font-inter', 'font-roboto',
        'font-open-sans', 'font-source-sans', 'font-noto-sans',
        'font-lato', 'font-raleway', 'font-sans-serif'
      ],

      // Weather settings
      WEATHER_WIDGET_TOGGLE_ENABLED: true,
      WEATHER_DEFAULT_COLLAPSED: false,
      USE_LINUXREPORT_WEATHER: true,
      WEATHER_BASE_URL: '',
      WEATHER_DEBOUNCE_DELAY: 100,
      COOKIE_MAX_AGE: 31536000,
      COOKIE_SAME_SITE: 'Lax',
      IMPERIAL_REGIONS: ['US', 'BS', 'BZ', 'KY', 'PW'],
      DEFAULT_LOCALE: 'en-US',

      // Chat settings
      CHAT_USE_SSE: false,
      CHAT_POLLING_INTERVAL: 15000,
      CHAT_MAX_RETRIES: 5,
      CHAT_BASE_RETRY_DELAY: 1000,
      CHAT_MAX_RETRY_DELAY: 30000,
      CHAT_FETCH_DEBOUNCE_DELAY: 1000,
      CHAT_RENDER_DEBOUNCE_DELAY: 100,
      CHAT_DRAG_THROTTLE_DELAY: 16,
      CHAT_MAX_FILE_SIZE: 5 * 1024 * 1024,
      CHAT_ALLOWED_FILE_TYPES: ['image/png', 'image/jpeg', 'image/gif', 'image/webp'],
      CHAT_RESIZE_DEBOUNCE_DELAY: 250,

      // Config page settings
      DRAG_OPACITY: '0.9',
      DRAG_OPACITY_NORMAL: '1',
      PRIORITY_MULTIPLIER: 10,
      DELETE_HEADLINE_ENDPOINT: '/api/delete_headline'
    },
    utils: {},
    modules: {}
  };

  // =============================================================================
  // SHARED CONFIGURATION
  // =============================================================================

  app.config.WEATHER_BASE_URL = app.config.USE_LINUXREPORT_WEATHER ? 'https://linuxreport.net' : '';

  // =============================================================================
  // SHARED UTILITIES
  // =============================================================================

  app.utils.debounce = (func, wait) => {
    let timeout;
    return (...args) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => func(...args), wait);
    };
  };

  // Geolocation utilities
  app.utils.GeolocationManager = {
    // Global variable to store location data
    locationData: null,
    locationPromise: null,

    /**
     * Get user's geolocation with fallback based on DISABLE_IP_GEOLOCATION setting
     * @returns {Promise<{lat: number, lon: number}>}
     */
    async getLocation() {
      // Always request fresh location from browser - no caching
      return this._requestLocation();
    },

    /**
     * Request location from browser geolocation API
     * @returns {Promise<{lat: number, lon: null}>} - Returns null for lon when geolocation fails
     */
            _requestLocation() {
            return new Promise((resolve, reject) => {
                        if (!navigator.geolocation) {
            // console.log('Geolocation not supported, using IP-based location');
            resolve({ lat: null, lon: null });
            return;
        }

                const options = {
                    enableHighAccuracy: false, // Keep false for faster response
                    timeout: 15000, // Increased timeout to 15 seconds
                    maximumAge: 3600000 // 1 hour - data within last hour is good enough
                };

                // console.log('Requesting geolocation with options:', options);
                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        const { latitude, longitude } = position.coords;
                        console.log(`Geolocation successful: ${latitude}, ${longitude}`);
                        resolve({ lat: latitude, lon: longitude });
                    },
                    (error) => {
                        console.log('Geolocation failed:', error.message, 'Code:', error.code);
                        // Reject with the error so the caller can check the error code
                        reject(error);
                    },
                    options
                );
            });
        },

    /**
     * Clear cached location data (kept for compatibility, but no longer needed)
     */
    clearLocation() {
      // No longer caching, so this is a no-op
    }
  };

  app.utils.throttle = (func, limit) => {
    let inThrottle;
    return (...args) => {
      if (!inThrottle) {
        func(...args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  };

  // Error handler
  app.utils.handleError = (operation, error) => {
    console.error(`Error in ${operation}:`, error);
  };

  // Cookie management
  app.utils.CookieManager = {
    get(name) {
      const cookies = document.cookie.split(';');
      for (let cookie of cookies) {
        const trimmedCookie = cookie.trim();
        const separatorIndex = trimmedCookie.indexOf('=');
        if (separatorIndex === -1) continue;

        const cookieName = trimmedCookie.substring(0, separatorIndex);
        if (cookieName === name) {
          const cookieValue = trimmedCookie.substring(separatorIndex + 1);
          try {
            const value = decodeURIComponent(cookieValue);
            console.log(`Cookie ${name}:`, value); // Debug log
            return value;
          } catch (error) {
            app.utils.handleError('cookie decode', error);
            return null;
          }
        }
      }
      return null;
    },
    set(name, value, options = {}) {
      const opts = {
        path: '/',
        'max-age': app.config.COOKIE_MAX_AGE,
        'SameSite': app.config.COOKIE_SAME_SITE,
        ...options
      };
      const cookieString = `${name}=${encodeURIComponent(value)}` + 
        Object.entries(opts).map(([k, v]) => `; ${k}${v !== true ? `=${v}` : ''}`).join('');
      document.cookie = cookieString;
    }
  };

  // Scroll management
  app.utils.ScrollManager = {
    savePosition() {
      try {
        localStorage.setItem('scrollPosition', JSON.stringify({
          position: window.scrollY,
          timestamp: Date.now()
        }));
      } catch (error) {
        app.utils.handleError('saving scroll position', error);
      }
    },
    restorePosition() {
      try {
        const saved = localStorage.getItem('scrollPosition');
        if (!saved) return;
        
        const data = JSON.parse(saved);
        if (Date.now() - data.timestamp > app.config.SCROLL_TIMEOUT) {
          localStorage.removeItem('scrollPosition');
          return;
        }
        
        requestAnimationFrame(() => {
          window.scrollTo({ top: data.position, behavior: 'instant' });
          localStorage.removeItem('scrollPosition');
        });
      } catch (error) {
        app.utils.handleError('restoring scroll position', error);
        localStorage.removeItem('scrollPosition');
      }
    }
  };

  // Theme management
  app.utils.ThemeManager = {
    applySettings() {
        const theme = app.utils.CookieManager.get('Theme') || app.config.DEFAULT_THEME;
        document.body.setAttribute('data-theme', theme);
        const themeSelect = document.getElementById('theme-select');
      if (themeSelect) themeSelect.value = theme;

      const font = app.utils.CookieManager.get('FontFamily') || app.config.DEFAULT_FONT;
      this.applyFont(font);
      const fontSelect = document.getElementById('font-select');
      if (fontSelect) fontSelect.value = font;

      const noUnderlines = app.utils.CookieManager.get('NoUnderlines');
      if (!noUnderlines || noUnderlines === '1') {
        document.body.classList.add('no-underlines');
      }
    },
    applyFont(font) {
      document.body.setAttribute('data-font', font);
    },
    setTheme(theme) {
        app.utils.ScrollManager.savePosition();
        app.utils.CookieManager.set('Theme', theme);
        window.location.reload();
    },
    setFont(font) {
      app.utils.ScrollManager.savePosition();
      app.utils.CookieManager.set('FontFamily', font);
      this.applyFont(font);

      const fontSelect = document.getElementById('font-select');
      if (fontSelect) fontSelect.value = font;

      // The original implementation caused a jarring flicker to force a reflow.
      // We can simply restore the scroll position, which already uses requestAnimationFrame.
      app.utils.ScrollManager.restorePosition();
    }
  };

  app.utils.TimezoneManager = {
    /**
     * Convert UTC ISO timestamp to local timezone display format
     * @param {string} utcTime - UTC ISO timestamp string
     * @returns {string} Formatted time in local timezone with timezone name
     */
    formatLocalTime(utcTime) {
      if (!utcTime || utcTime === 'Unknown' || utcTime === '') {
        return 'Unknown';
      }
      
      console.log('Attempting to parse time:', utcTime, 'Type:', typeof utcTime);
      
      try {
        const date = new Date(utcTime);
        console.log('Parsed date:', date, 'Valid:', !isNaN(date.getTime()));
        
        if (isNaN(date.getTime())) {
          console.warn('Invalid time format:', utcTime);
          return 'Invalid time';
        }
        
        // Format as 12-hour time with AM/PM and timezone
        const timeString = date.toLocaleTimeString('en-US', {
          hour: 'numeric',
          minute: '2-digit',
          hour12: true
        });
        
        // Get timezone abbreviation
        const timezoneAbbr = this.getTimezoneAbbreviation();
        
        const result = `${timeString} ${timezoneAbbr}`;
        console.log('Final result:', result);
        return result;
      } catch (error) {
        console.error('Error formatting time:', error, 'Input:', utcTime);
        return 'Error';
      }
    },

    /**
     * Get timezone abbreviation
     * @returns {string} Timezone abbreviation
     */
    getTimezoneAbbreviation() {
      try {
        const date = new Date();
        const options = { timeZoneName: 'short' };
        const timeZoneString = date.toLocaleString('en-US', options);
        
        // Extract timezone abbreviation from the formatted string
        const match = timeZoneString.match(/\s([A-Z]{3,4})$/);
        return match ? match[1] : 'Local';
      } catch (error) {
        return 'Local';
      }
    },

    /**
     * Initialize timezone conversion for all last-updated elements
     */
    init() {
      document.querySelectorAll('.last-updated-time').forEach(element => {
        const utcTime = element.getAttribute('data-utc-time');
        console.log('Processing time element:', element, 'UTC time:', utcTime);
        if (utcTime) {
          element.textContent = this.formatLocalTime(utcTime);
        } else {
          element.textContent = 'Unknown';
        }
      });
    },

    /**
     * Convert timezone for a specific element (for dynamic content)
     * @param {Element} element - The element containing the time
     */
    convertElement(element) {
      const utcTime = element.getAttribute('data-utc-time');
      if (utcTime) {
        element.textContent = this.formatLocalTime(utcTime);
      }
    }
  };

  app.utils.DragDropManager = {
    init(options) {
      const { containerSelector, itemSelector, onDrop } = options;
      const container = document.querySelector(containerSelector);
      if (!container) return;

      let draggedItem = null;

      container.addEventListener('dragstart', e => {
        if (e.target.matches(itemSelector)) {
          draggedItem = e.target;
          draggedItem.style.opacity = app.config.DRAG_OPACITY;
        }
      });

      container.addEventListener('dragend', e => {
        if (draggedItem) {
          draggedItem.style.opacity = app.config.DRAG_OPACITY_NORMAL;
          draggedItem = null;
        }
      });

      container.addEventListener('dragover', e => {
        e.preventDefault();
        const afterElement = this.getDragAfterElement(container, e.clientY, itemSelector);
        if (draggedItem) {
          container.insertBefore(draggedItem, afterElement);
        }
      });

      container.addEventListener('drop', e => {
        e.preventDefault();
        if (onDrop) {
          onDrop();
        }
      });
    },

    getDragAfterElement(container, y, itemSelector) {
      const draggableElements = [...container.querySelectorAll(`${itemSelector}:not(.dragging)`)];
      let closestElement = null;
      let closestOffset = Number.NEGATIVE_INFINITY;

      for (const child of draggableElements) {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;

        if (offset < 0 && offset > closestOffset) {
          closestOffset = offset;
          closestElement = child;
        }
      }
      return closestElement;
    }
  };

  // =============================================================================
  // EXPOSE APP OBJECT
  // =============================================================================

  window.app = app;

})();
