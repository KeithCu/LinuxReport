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
    iframe: null,
    iframeReady: false,
    pendingRequests: [],

    /**
     * Initialize the shared storage iframe
     */
    init() {
      // Create hidden iframe for cross-domain storage
      this.iframe = document.createElement('iframe');
      this.iframe.style.display = 'none';
      this.iframe.src = 'https://linuxreport.net/storage.html';
      
      // Wait for iframe to load
      this.iframe.onload = () => {
        this.iframeReady = true;
        console.log('Shared location storage iframe loaded');
        // Process any pending requests
        this.pendingRequests.forEach(resolve => resolve());
        this.pendingRequests = [];
      };
      
      document.body.appendChild(this.iframe);
    },

    /**
     * Get user's geolocation with cross-domain caching
     * @returns {Promise<{lat: number, lon: number}>}
     */
    async getLocation() {
      // Wait for iframe to be ready
      if (!this.iframeReady) {
        await new Promise(resolve => this.pendingRequests.push(resolve));
      }
      
      // Try to get from shared storage first
      const sharedLocation = await this.getFromSharedStorage();
      if (sharedLocation) {
        console.log('Using shared location from iframe');
        return sharedLocation;
      }
      
      // Fall back to local storage
      const cached = localStorage.getItem('weatherLocation');
      if (cached) {
        const data = JSON.parse(cached);
        const currentIP = await this.getCurrentIP();
        
        if (data.ip && currentIP && data.ip !== currentIP) {
          console.log('IP changed, invalidating cached location');
          localStorage.removeItem('weatherLocation');
        } else if (Date.now() - data.timestamp < 3600000) {
          console.log('Using local cached location');
          return { lat: data.lat, lon: data.lon };
        }
      }
      
      // Get fresh location
      const location = await this._requestLocation();
      if (location.lat !== null && location.lon !== null) {
        // Store in both places
        localStorage.setItem('weatherLocation', JSON.stringify({
          lat: location.lat,
          lon: location.lon,
          ip: await this.getCurrentIP(),
          timestamp: Date.now()
        }));
        
        // Also store in shared storage
        await this.storeInSharedStorage(location);
      }
      return location;
    },

    /**
     * Get location from shared storage via iframe
     * @returns {Promise<{lat: number, lon: number} | null>}
     */
    async getFromSharedStorage() {
      return new Promise((resolve) => {
        const messageHandler = (event) => {
          if (event.origin !== 'https://linuxreport.net') return;
          
          if (event.data.type === 'LOCATION_DATA') {
            window.removeEventListener('message', messageHandler);
            resolve(event.data.location);
          }
        };
        
        window.addEventListener('message', messageHandler);
        
        // Request location from iframe
        this.iframe.contentWindow.postMessage({
          type: 'GET_LOCATION'
        }, 'https://linuxreport.net');
        
        // Timeout after 2 seconds
        setTimeout(() => {
          window.removeEventListener('message', messageHandler);
          resolve(null);
        }, 2000);
      });
    },

    /**
     * Store location in shared storage via iframe
     * @param {Object} location - Location object with lat and lon
     * @returns {Promise<boolean>}
     */
    async storeInSharedStorage(location) {
      return new Promise(async (resolve) => {
        const messageHandler = (event) => {
          if (event.origin !== 'https://linuxreport.net') return;
          
          if (event.data.type === 'LOCATION_STORED') {
            window.removeEventListener('message', messageHandler);
            resolve(true);
          }
        };
        
        window.addEventListener('message', messageHandler);
        
        // Get current IP and store location in iframe
        const currentIP = await this.getCurrentIP();
        this.iframe.contentWindow.postMessage({
          type: 'STORE_LOCATION',
          data: {
            lat: location.lat,
            lon: location.lon,
            ip: currentIP
          }
        }, 'https://linuxreport.net');
        
        // Timeout after 2 seconds
        setTimeout(() => {
          window.removeEventListener('message', messageHandler);
          resolve(false);
        }, 2000);
      });
    },

    /**
     * Get current IP address for cache invalidation
     * @returns {Promise<string | null>}
     */
    async getCurrentIP() {
      try {
        // Get IP from server-injected variable (most efficient)
        if (window.CLIENT_IP && window.CLIENT_IP !== '' && this.isValidIP(window.CLIENT_IP)) {
          console.log(`IP detected via server injection: ${window.CLIENT_IP}`);
          return window.CLIENT_IP;
        }
        
        // Fallback: try to get from response headers (requires additional request)
        const response = await fetch(window.location.href, {
          method: 'HEAD',
          cache: 'no-cache'
        });
        
        if (response.ok) {
          const ip = response.headers.get('X-Client-IP');
          
          if (ip && this.isValidIP(ip)) {
            console.log(`IP detected via response headers: ${ip}`);
            return ip;
          } else {
            console.error('IP detection failed: X-Client-IP header missing or invalid');
          }
        } else {
          console.error('IP detection failed: HEAD request failed');
        }
        
        return null;
      } catch (error) {
        console.error('IP detection failed:', error.message);
        return null;
      }
    },

    /**
     * Validate IP address (IPv4 or IPv6)
     * @param {string} ip - IP address to validate
     * @returns {boolean}
     */
    isValidIP(ip) {
      // Validate IPv4
      const ipv4Regex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
      
      // Validate IPv6
      const ipv6Regex = /^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::1$|^::$|^(?:[0-9a-fA-F]{1,4}:){1,7}:$|^:(?::[0-9a-fA-F]{1,4}){1,7}$|^::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}$|^[0-9a-fA-F]{1,4}::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}$|^::(?:[0-9a-fA-F]{1,4}:){0,3}[0-9a-fA-F]{1,4}$|^[0-9a-fA-F]{1,4}::(?:[0-9a-fA-F]{1,4}:){0,3}[0-9a-fA-F]{1,4}$|^[0-9a-fA-F]{1,4}:[0-9a-fA-F]{1,4}:(?:[0-9a-fA-F]{1,4}:){0,2}[0-9a-fA-F]{1,4}$|^[0-9a-fA-F]{1,4}:[0-9a-fA-F]{1,4}:[0-9a-fA-F]{1,4}:(?:[0-9a-fA-F]{1,4}:)?[0-9a-fA-F]{1,4}$/;
      
      return ipv4Regex.test(ip) || ipv6Regex.test(ip);
    },

    /**
     * Request location from browser geolocation API
     * @returns {Promise<{lat: number, lon: null}>} - Returns null for lon when geolocation fails
     */
    _requestLocation() {
      return new Promise((resolve) => {
        if (!navigator.geolocation) {
          console.log('Geolocation not supported, using IP-based location');
          resolve({ lat: null, lon: null });
          return;
        }

        const options = {
          enableHighAccuracy: false, // Keep false for faster response
          timeout: 10000, // Reduced timeout to 10 seconds
          maximumAge: 3600000 // 1 hour - data within last hour is good enough
        };

        console.log('Requesting fresh geolocation with options:', options);
        navigator.geolocation.getCurrentPosition(
          (position) => {
            const { latitude, longitude } = position.coords;
            console.log(`Geolocation successful: ${latitude}, ${longitude}`);
            resolve({ lat: latitude, lon: longitude });
          },
          (error) => {
            console.log('Geolocation failed:', error.message, 'Code:', error.code);
            // Return null coordinates to indicate geolocation failure
            resolve({ lat: null, lon: null });
          },
          options
        );
      });
    },

    /**
     * Clear cached location data
     */
    clearLocation() {
      localStorage.removeItem('weatherLocation');
      // Also clear shared storage
      if (this.iframe && this.iframeReady) {
        this.iframe.contentWindow.postMessage({
          type: 'CLEAR_LOCATION'
        }, 'https://linuxreport.net');
      }
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

  // =============================================================================
  // INITIALIZATION
  // =============================================================================

  // Initialize shared location storage when DOM is ready
  document.addEventListener('DOMContentLoaded', () => {
    // Initialize the shared storage iframe
    app.utils.GeolocationManager.init();
    
    // Preload location in background
    app.utils.GeolocationManager.getLocation().catch(() => {
      // Silently fail - user will be prompted when weather loads
    });
  });

})();
