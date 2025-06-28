/**
 * app.js
 *
 * Main application module for LinuxReport. Consolidates shared configuration,
 * utilities, and core application logic into a single global 'app' object.
 * This improves modularity and reduces global namespace pollution.
 *
 * @author LinuxReport Team
 * @version 3.0.0
 */

(function() {
  'use strict';

  // =============================================================================
  // INITIALIZE GLOBAL APP OBJECT
  // =============================================================================

  const app = {
    config: {},
    utils: {},
    modules: {}
  };

  // =============================================================================
  // SHARED CONFIGURATION
  // =============================================================================

  app.config = {
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
    WEATHER_CACHE_DURATION: 30 * 60 * 1000,
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
  };

  app.config.WEATHER_BASE_URL = app.config.USE_LINUXREPORT_WEATHER ? 'https://linuxreport.net' : '';

  // =============================================================================
  // SHARED UTILITIES
  // =============================================================================

  app.utils.debounce = function(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  };

  app.utils.throttle = function(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
      if (!inThrottle) {
        func(...args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  };

  app.utils.CookieManager = {
    get(name) {
      const value = `; ${document.cookie}`;
      const parts = value.split(`; ${name}=`);
      if (parts.length === 2) {
        const cookieValue = parts.pop().split(';').shift();
        try {
          return decodeURIComponent(cookieValue);
        } catch (error) {
          console.error('Cookie decode error:', error);
          return null;
        }
      }
      return null;
    },
    set(name, value, options = {}) {
      const defaultOptions = {
        path: '/',
        'max-age': app.config.COOKIE_MAX_AGE,
        'SameSite': app.config.COOKIE_SAME_SITE,
        ...options
      };
      let cookieString = `${name}=${encodeURIComponent(value)}`;
      for (const [key, val] of Object.entries(defaultOptions)) {
        cookieString += `; ${key}`;
        if (val !== true) {
          cookieString += `=${val}`;
        }
      }
      document.cookie = cookieString;
    }
  };

  app.utils.CacheManager = {
    get(key, duration) {
      try {
        const cached = sessionStorage.getItem(key);
        if (cached) {
          const { data, timestamp } = JSON.parse(cached);
          if (Date.now() - timestamp < duration) {
            return data;
          }
        }
      } catch (error) {
        console.error(`Error reading cached data for key ${key}:`, error);
      }
      return null;
    },
    set(key, data) {
      try {
        sessionStorage.setItem(key, JSON.stringify({
          data,
          timestamp: Date.now()
        }));
      } catch (error) {
        console.error(`Error caching data for key ${key}:`, error);
      }
    }
  };

  app.utils.ScrollManager = {
    savePosition() {
      try {
        localStorage.setItem('scrollPosition', JSON.stringify({
          position: window.scrollY,
          timestamp: Date.now()
        }));
      } catch (error) {
        console.error('Error saving scroll position:', error);
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
        console.error('Error restoring scroll position:', error);
        localStorage.removeItem('scrollPosition');
      }
    }
  };

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
      requestAnimationFrame(() => {
        document.body.style.display = 'none';
        requestAnimationFrame(() => {
          document.body.style.display = '';
          app.utils.ScrollManager.restorePosition();
        });
      });
    }
  };

  // =============================================================================
  // EXPOSE APP OBJECT
  // =============================================================================

  window.app = app;

})();
