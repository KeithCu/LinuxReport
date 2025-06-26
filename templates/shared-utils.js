/**
 * shared-utils.js - Simplified
 * 
 * Shared utilities module for the LinuxReport application.
 * Consolidated utility functions and classes used across modules.
 * 
 * @author LinuxReport Team
 * @version 2.1.0
 */

(function() {
  'use strict';
  
  // =============================================================================
  // UTILITY FUNCTIONS
  // =============================================================================
  
  // Debounce utility function
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

  // Throttle utility function
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

  // =============================================================================
  // UTILITY CLASSES
  // =============================================================================

  // Cookie management utility class
  window.CookieManager = class CookieManager {
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

  // Cache management utility class
  window.CacheManager = class CacheManager {
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

  // Scroll position management utility class
  window.ScrollManager = class ScrollManager {
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

  // Theme and font management utility class
  window.ThemeManager = class ThemeManager {
    static applySettings() {
      const config = window.LINUXREPORT_CONFIG;
      
      // Apply theme
      const theme = CookieManager.get('Theme') || config.DEFAULT_THEME;
      document.body.classList.add(`theme-${theme}`);
      
      const themeSelect = document.getElementById('theme-select');
      if (themeSelect) themeSelect.value = theme;
      
      // Apply font
      const font = CookieManager.get('FontFamily') || config.DEFAULT_FONT;
      ThemeManager.applyFont(font);
      
      const fontSelect = document.getElementById('font-select');
      if (fontSelect) fontSelect.value = font;
      
      // Apply no-underlines setting
      const noUnderlines = CookieManager.get('NoUnderlines');
      if (!noUnderlines || noUnderlines === '1') {
        document.body.classList.add('no-underlines');
      }
    }
    
    static applyFont(font) {
      const config = window.LINUXREPORT_CONFIG;
      document.body.classList.remove(...config.FONT_CLASSES);
      document.body.classList.add(`font-${font}`);
    }
    
    static setTheme(theme) {
      ScrollManager.savePosition();
      CookieManager.set('Theme', theme);
      window.location.reload();
    }
    
    static setFont(font) {
      ScrollManager.savePosition();
      CookieManager.set('FontFamily', font);
      
      ThemeManager.applyFont(font);
      
      const fontSelect = document.getElementById('font-select');
      if (fontSelect) fontSelect.value = font;
      
      // Force reflow with minimal layout thrashing
      requestAnimationFrame(() => {
        document.body.style.display = 'none';
        requestAnimationFrame(() => {
          document.body.style.display = '';
          document.querySelectorAll('*').forEach(el => {
            el.style.fontFamily = 'inherit';
          });
          
          // Restore scroll position after font change
          setTimeout(() => {
            ScrollManager.restorePosition();
          }, 1000);
        });
      });
    }
  };

})();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    debounce: window.debounce,
    throttle: window.throttle,
    CookieManager: window.CookieManager,
    CacheManager: window.CacheManager,
    ScrollManager: window.ScrollManager,
    ThemeManager: window.ThemeManager
  };
} 