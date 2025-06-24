/**
 * shared-utils.js
 * 
 * Shared utilities module for the LinuxReport application. Contains all
 * utility functions and classes used across multiple JavaScript modules.
 * This file should be loaded after shared-config.js but before other modules.
 * 
 * @author LinuxReport Team
 * @version 2.0.0
 */

// =============================================================================
// SHARED UTILITY FUNCTIONS
// =============================================================================

(function() {
  'use strict';
  
  // Only define utilities if they don't already exist
  if (typeof window.debounce === 'undefined') {
    /**
     * Debounce utility function.
     * Limits the rate at which a function can fire.
     * 
     * @param {Function} func - The function to debounce
     * @param {number} wait - The debounce delay in milliseconds
     * @returns {Function} The debounced function
     */
    window.debounce = function(func, wait) {
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
  }

  if (typeof window.throttle === 'undefined') {
    /**
     * Throttle utility function.
     * Ensures a function is called at most once in a specified time period.
     * 
     * @param {Function} func - The function to throttle
     * @param {number} limit - The throttle limit in milliseconds
     * @returns {Function} The throttled function
     */
    window.throttle = function(func, limit) {
      let inThrottle;
      return function executedFunction(...args) {
        if (!inThrottle) {
          func(...args);
          inThrottle = true;
          setTimeout(() => inThrottle = false, limit);
        }
      };
    };
  }

  // =============================================================================
  // SHARED UTILITY CLASSES
  // =============================================================================

  if (typeof window.CookieManager === 'undefined') {
    /**
     * Cookie management utility class.
     * Provides methods for getting and setting cookies with proper encoding/decoding.
     */
    window.CookieManager = class CookieManager {
      /**
       * Get a cookie value by name.
       * 
       * @param {string} name - The name of the cookie
       * @returns {string|null} The cookie value or null if not found
       */
      static get(name) {
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
      }
      
      /**
       * Set a cookie with the given name, value, and options.
       * 
       * @param {string} name - The name of the cookie
       * @param {string} value - The value to store
       * @param {Object} options - Cookie options (path, expires, etc.)
       */
      static set(name, value, options = {}) {
        const config = window.LINUXREPORT_CONFIG;
        const defaultOptions = {
          path: '/',
          'max-age': config.COOKIE_MAX_AGE,
          'SameSite': config.COOKIE_SAME_SITE,
          ...options
        };
        
        let cookieString = `${name}=${encodeURIComponent(value)}`;
        
        Object.entries(defaultOptions).forEach(([key, value]) => {
          cookieString += `; ${key}`;
          if (value !== true) {
            cookieString += `=${value}`;
          }
        });
        
        document.cookie = cookieString;
      }
    };
  }

  if (typeof window.CacheManager === 'undefined') {
    /**
     * Cache management utility class.
     * Handles session storage operations for data caching.
     */
    window.CacheManager = class CacheManager {
      /**
       * Get cached data if it exists and is not expired.
       * 
       * @param {string} key - The cache key
       * @param {number} duration - Cache duration in milliseconds
       * @returns {Object|null} The cached data or null if not found/expired
       */
      static get(key, duration) {
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
      }
      
      /**
       * Cache data with current timestamp.
       * 
       * @param {string} key - The cache key
       * @param {Object} data - The data to cache
       */
      static set(key, data) {
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
  }

  if (typeof window.ScrollManager === 'undefined') {
    /**
     * Scroll position management utility class.
     * Handles saving and restoring scroll positions with timeout validation.
     */
    window.ScrollManager = class ScrollManager {
      /**
       * Save the current scroll position to localStorage.
       */
      static savePosition() {
        try {
          const scrollData = {
            position: window.scrollY,
            timestamp: Date.now()
          };
          localStorage.setItem('scrollPosition', JSON.stringify(scrollData));
        } catch (error) {
          console.error('Error saving scroll position:', error);
        }
      }
      
      /**
       * Restore scroll position from localStorage if within timeout period.
       */
      static restorePosition() {
        try {
          const saved = localStorage.getItem('scrollPosition');
          if (!saved) return;
          
          const data = JSON.parse(saved);
          const config = window.LINUXREPORT_CONFIG;
          
          if (Date.now() - data.timestamp > config.SCROLL_TIMEOUT) {
            localStorage.removeItem('scrollPosition');
            return;
          }
          
          requestAnimationFrame(() => {
            window.scrollTo({
              top: data.position,
              behavior: 'instant'
            });
            localStorage.removeItem('scrollPosition');
          });
        } catch (error) {
          console.error('Error restoring scroll position:', error);
          localStorage.removeItem('scrollPosition');
        }
      }
    };
  }
})();

// =============================================================================
// EXPORT FOR MODULE SYSTEMS (if needed)
// =============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    debounce: window.debounce,
    throttle: window.throttle,
    CookieManager: window.CookieManager,
    CacheManager: window.CacheManager,
    ScrollManager: window.ScrollManager
  };
} 