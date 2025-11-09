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

      // Debug settings
      DEBUG_MODE: false, // Set to true during development to enable debug logging
      LOG_LEVEL: 'ERROR', // Options: 'ERROR', 'WARN', 'INFO', 'DEBUG'

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
      
      // Client geolocation configuration
      // When True: Client geolocation is disabled, server uses IP-based location or defaults
      // When False: Client geolocation is enabled, server respects client-provided coordinates
      DISABLE_CLIENT_GEOLOCATION: true,

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
    utils: {
      ForceRefreshManager: {
        init() {
          if (!window.isAdmin) return; // Only initialize for admin users

          this.addRefreshButtons();
          this.bindEvents();
          this.log('ForceRefreshManager initialized');
        },

        addRefreshButtons() {
          // Find all feed boxes and add refresh buttons
          const feedBoxes = document.querySelectorAll('.box[id^="feed-"]');
          feedBoxes.forEach(box => {
            const feedId = box.id.replace('feed-', '');
            if (!box.querySelector('.force-refresh-btn')) {
              const button = document.createElement('button');
              button.className = 'force-refresh-btn';
              button.setAttribute('data-feed-id', feedId);
              button.setAttribute('title', 'Force refresh this feed');
              button.textContent = '🔄';
              button.style.cssText = `
                position: absolute;
                top: 5px;
                left: 5px;
                background: rgba(0, 0, 0, 0.3);
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 12px;
                cursor: pointer;
                opacity: 0.6;
                transition: opacity 0.2s;
                z-index: 10;
              `;
              button.addEventListener('mouseenter', () => button.style.opacity = '1');
              button.addEventListener('mouseleave', () => button.style.opacity = '0.6');
              
              // Make the box container relative positioned if it isn't already
              if (getComputedStyle(box).position === 'static') {
                box.style.position = 'relative';
              }
              
              box.appendChild(button);
            }
          });
        },

        bindEvents() {
          document.addEventListener('click', (event) => {
            if (event.target.classList.contains('force-refresh-btn')) {
              event.preventDefault();
              this.handleForceRefresh(event.target);
            }
          });
        },

        async handleForceRefresh(button) {
          const feedId = button.getAttribute('data-feed-id');
          if (!feedId) {
            this.error('No feed ID found for force refresh button');
            return;
          }

          // Show loading state
          const originalText = button.textContent;
          button.textContent = '⏳ Refreshing...';
          button.disabled = true;

          try {
            const response = await fetch('/api/force_refresh_feed', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.getCsrfToken()
              },
              body: JSON.stringify({ feed_url: feedId })
            });

            const result = await response.json();

            if (response.ok) {
              // Show success message
              button.textContent = '✅ Refreshed';
              this.log(`Successfully initiated refresh for feed: ${feedId}`);

              // Reset button after 2 seconds
              setTimeout(() => {
                button.textContent = originalText;
                button.disabled = false;
              }, 2000);
            } else {
              throw new Error(result.error || 'Unknown error occurred');
            }
          } catch (error) {
            this.error(`Failed to refresh feed ${feedId}:`, error);
            button.textContent = '❌ Error';

            // Reset button after 3 seconds on error
            setTimeout(() => {
              button.textContent = originalText;
              button.disabled = false;
            }, 3000);
          }
        },

        getCsrfToken() {
          // Get CSRF token from window variable set by Flask
          return window.csrf_token || '';
        },

        log(message) {
          if (app.config.DEBUG_MODE && app.config.LOG_LEVEL === 'DEBUG') {
            console.log(`[ForceRefreshManager] ${message}`);
          }
        },

        error(message, error) {
          console.error(`[ForceRefreshManager] ${message}`, error);
        }
      }
    },
    modules: {}
  };

  // =============================================================================
  // SHARED CONFIGURATION
  // =============================================================================

  app.config.WEATHER_BASE_URL = app.config.USE_LINUXREPORT_WEATHER ? 'https://linuxreport.net' : '';

  // Auto-set log level to DEBUG when Flask debug mode is enabled
  if (typeof window !== 'undefined' && window.flaskDebug) {
    app.config.LOG_LEVEL = 'DEBUG';
    app.config.DEBUG_MODE = true;
  }

  // =============================================================================
  // SHARED UTILITIES
  // =============================================================================

  // Professional logging utility
  app.utils.logger = {
    /**
     * Debug logging - shown when DEBUG_MODE is true or LOG_LEVEL is 'DEBUG'
     * @param {string} message - Log message
     * @param {...any} args - Additional arguments to log
     */
    debug: (message, ...args) => {
      if (app.config.DEBUG_MODE || app.config.LOG_LEVEL === 'DEBUG') {
        console.log(`[DEBUG] ${message}`, ...args);
      }
    },

    /**
     * Info logging - shown when DEBUG_MODE is true or LOG_LEVEL is 'INFO' or 'DEBUG'
     * @param {string} message - Log message
     * @param {...any} args - Additional arguments to log
     */
    info: (message, ...args) => {
      if (app.config.DEBUG_MODE || ['INFO', 'DEBUG'].includes(app.config.LOG_LEVEL)) {
        console.log(`[INFO] ${message}`, ...args);
      }
    },

    /**
     * Warning logging - shown when LOG_LEVEL is 'WARN', 'INFO', or 'DEBUG'
     * @param {string} message - Log message
     * @param {...any} args - Additional arguments to log
     */
    warn: (message, ...args) => {
      if (['WARN', 'INFO', 'DEBUG'].includes(app.config.LOG_LEVEL)) {
        console.warn(`[WARN] ${message}`, ...args);
      }
    },

    /**
     * Error logging - always shown regardless of LOG_LEVEL
     * @param {string} message - Log message
     * @param {...any} args - Additional arguments to log
     */
    error: (message, ...args) => {
      console.error(`[ERROR] ${message}`, ...args);
    }
  };

  app.utils.debounce = (func, wait) => {
    let timeout;
    return (...args) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => func(...args), wait);
    };
  };

  // Geolocation utilities
  app.utils.GeolocationManager = {
    /**
     * Get user's geolocation with fallback based on DISABLE_IP_GEOLOCATION setting
     * @returns {Promise<{lat: number, lon: number}>}
     */
    async getLocation() {
      return this._requestLocation();
    },

    /**
     * Request location from browser geolocation API
     * @returns {Promise<{lat: number, lon: number}>} - Returns coordinates or rejects on failure
     */
    _requestLocation() {
      return new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
          app.utils.logger.debug('Geolocation not supported');
          reject(new Error('Geolocation not supported'));
          return;
        }

        const options = {
          enableHighAccuracy: false, // Keep false for faster response
          timeout: 10000, // 10 seconds timeout
          maximumAge: 300000 // 5 minutes - data within last 5 minutes is good enough
        };

        app.utils.logger.debug('Requesting geolocation');
        navigator.geolocation.getCurrentPosition(
          (position) => {
            const { latitude, longitude } = position.coords;
            app.utils.logger.info(`Geolocation successful: ${latitude}, ${longitude}`);
            resolve({ lat: latitude, lon: longitude });
          },
          (error) => {
            app.utils.logger.warn('Geolocation failed:', error.message, 'Code:', error.code);
            reject(error);
          },
          options
        );
      });
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
    app.utils.logger.error(`Error in ${operation}:`, error);
  };

  // Cookie management
  app.utils.CookieManager = {
    get(name) {
      const cookies = document.cookie.split(';');
      const cookiesLength = cookies.length;
      
      for (let i = 0; i < cookiesLength; i++) {
        const trimmedCookie = cookies[i].trim();
        const separatorIndex = trimmedCookie.indexOf('=');
        if (separatorIndex === -1) continue;

        const cookieName = trimmedCookie.substring(0, separatorIndex);
        if (cookieName === name) {
          const cookieValue = trimmedCookie.substring(separatorIndex + 1);
          try {
            const value = decodeURIComponent(cookieValue);
            app.utils.logger.debug(`Cookie ${name}:`, value);
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

  // UI management (theme and font)
  app.utils.UIManager = {
    applySettings() {
      const theme = app.utils.CookieManager.get('Theme') || app.config.DEFAULT_THEME;
      const font = app.utils.CookieManager.get('FontFamily') || app.config.DEFAULT_FONT;
      const noUnderlines = app.utils.CookieManager.get('NoUnderlines');
      
      // Apply all settings at once
      document.body.setAttribute('data-theme', theme);
      document.body.setAttribute('data-font', font);
      
      if (!noUnderlines || noUnderlines === '1') {
        document.body.classList.add('no-underlines');
      }
      
      // Update select elements
      this.updateSelects(theme, font);
    },
    
    updateSelects(theme, font) {
      const themeSelect = document.getElementById('theme-select');
      const fontSelect = document.getElementById('font-select');
      
      if (themeSelect) themeSelect.value = theme;
      if (fontSelect) fontSelect.value = font;
    },
    
    setTheme(theme) {
      document.body.setAttribute('data-theme', theme);
      app.utils.CookieManager.set('Theme', theme);
      
      const themeSelect = document.getElementById('theme-select');
      if (themeSelect) themeSelect.value = theme;
    },
    
    setFont(font) {
      app.utils.ScrollManager.savePosition();
      document.body.setAttribute('data-font', font);
      app.utils.CookieManager.set('FontFamily', font);
      
      const fontSelect = document.getElementById('font-select');
      if (fontSelect) fontSelect.value = font;
      
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
      
      app.utils.logger.debug('Attempting to parse time:', utcTime, 'Type:', typeof utcTime);
      
      try {
        const date = new Date(utcTime);
        app.utils.logger.debug('Parsed date:', date, 'Valid:', !isNaN(date.getTime()));
        
        if (isNaN(date.getTime())) {
          app.utils.logger.warn('Invalid time format:', utcTime);
          return 'Invalid time';
        }
        
        // Check if the date is today
        const today = new Date();
        const isToday = date.toDateString() === today.toDateString();
        
        // Get user's locale for formatting
        const userLocale = navigator.language || 'en-US';
        
        // Format time according to user's locale preferences
        const timeString = date.toLocaleTimeString(userLocale, {
          hour: 'numeric',
          minute: '2-digit',
          hour12: userLocale.includes('en') || userLocale.includes('US') || userLocale.includes('CA')
        });
        
        // Get timezone abbreviation
        const timezoneAbbr = this.getTimezoneAbbreviation();
        
        let result = `${timeString} ${timezoneAbbr}`;
        
        // If not today, add the date in user's preferred format
        if (!isToday) {
          const dateString = date.toLocaleDateString(userLocale, {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
          });
          
          // Use appropriate connector based on locale
          let connector = ' at ';
          if (userLocale.startsWith('de')) {
            connector = ' um ';
          } else if (userLocale.startsWith('fr')) {
            connector = ' à ';
          } else if (userLocale.startsWith('es')) {
            connector = ' a las ';
          } else if (userLocale.startsWith('it')) {
            connector = ' alle ';
          } else if (userLocale.startsWith('pt')) {
            connector = ' às ';
          } else if (userLocale.startsWith('ru')) {
            connector = ' в ';
          } else if (userLocale.startsWith('ja')) {
            connector = ' ';
          } else if (userLocale.startsWith('zh')) {
            connector = ' ';
          } else if (userLocale.startsWith('ko')) {
            connector = ' ';
          }
          
          result = `${dateString}${connector}${result}`;
        }
        
        app.utils.logger.debug('Final result:', result);
        return result;
      } catch (error) {
        app.utils.logger.error('Error formatting time:', error, 'Input:', utcTime);
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
      // Cache the querySelectorAll result to avoid repeated DOM queries
      const timeElements = document.querySelectorAll('.last-updated-time');
      timeElements.forEach(element => {
        const utcTime = element.getAttribute('data-utc-time');
        app.utils.logger.debug('Processing time element:', element, 'UTC time:', utcTime);
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

  // GPU-accelerated animation utilities
  app.utils.AnimationManager = {
    /**
     * Apply GPU-accelerated transform with smooth transition
     * @param {Element} element - Element to animate
     * @param {string} transform - Transform string (e.g., 'translateX(100px)')
     * @param {number} duration - Animation duration in ms
     * @param {string} easing - Easing function
     */
    animateTransform(element, transform, duration = 300, easing = 'ease-out') {
      if (!element) return;
      
      // Force GPU acceleration
      element.style.willChange = 'transform';
      element.style.transition = `transform ${duration}ms ${easing}`;
      element.style.transform = transform;
      
      // Clean up after animation
      setTimeout(() => {
        element.style.willChange = '';
        element.style.transition = '';
      }, duration);
    },

    /**
     * Add GPU acceleration hints to an element
     * @param {Element} element - Element to optimize
     */
    enableGPUAcceleration(element) {
      if (!element) return;
      element.style.transform = element.style.transform || 'translateZ(0)';
      element.style.willChange = 'transform';
    },

    /**
     * Remove GPU acceleration hints from an element
     * @param {Element} element - Element to clean up
     */
    disableGPUAcceleration(element) {
      if (!element) return;
      element.style.willChange = '';
    },

    /**
     * Smooth fade transition with GPU acceleration
     * @param {Element} element - Element to fade
     * @param {number} targetOpacity - Target opacity (0-1)
     * @param {number} duration - Duration in ms
     */
    fadeTransition(element, targetOpacity, duration = 300) {
      if (!element) return;
      
      element.style.willChange = 'opacity';
      element.style.transition = `opacity ${duration}ms ease-out`;
      element.style.opacity = targetOpacity;
      
      setTimeout(() => {
        element.style.willChange = '';
        element.style.transition = '';
      }, duration);
    }
  };

  app.utils.DragDropManager = {
    init(options) {
      const { containerSelector, itemSelector, onDrop } = options;
      const container = document.querySelector(containerSelector);
      if (!container) return;

      let draggedItem = null;
      let draggedItemClone = null;

      container.addEventListener('dragstart', e => {
        if (e.target.matches(itemSelector)) {
          draggedItem = e.target;
          
          // Add GPU-accelerated dragging class for smooth animations
          draggedItem.classList.add('dragging', 'gpu-accelerated');
          
          // Create a visual clone for smoother drag feedback
          draggedItemClone = draggedItem.cloneNode(true);
          draggedItemClone.classList.add('drag-clone', 'gpu-accelerated');
          draggedItemClone.style.position = 'absolute';
          draggedItemClone.style.pointerEvents = 'none';
          draggedItemClone.style.zIndex = '1000';
          draggedItemClone.style.opacity = '0.8';
          draggedItemClone.style.transform = 'scale(1.02) rotate(2deg)';
          draggedItemClone.style.transition = 'transform 0.2s ease-out';
          
          // Make original item semi-transparent during drag
          draggedItem.style.opacity = '0.5';
          draggedItem.style.transform = 'scale(0.98)';
          draggedItem.style.transition = 'all 0.2s ease-out';
        }
      });

      container.addEventListener('dragend', e => {
        if (draggedItem) {
          // Remove GPU-accelerated classes and reset styles
          draggedItem.classList.remove('dragging', 'gpu-accelerated');
          draggedItem.classList.add('dragging-normal');
          
          // Animate back to normal state
          draggedItem.style.opacity = '';
          draggedItem.style.transform = '';
          draggedItem.style.transition = 'all 0.3s ease-out';
          
          // Remove clone if it exists
          if (draggedItemClone && draggedItemClone.parentNode) {
            draggedItemClone.remove();
          }
          
          // Clean up references
          draggedItem = null;
          draggedItemClone = null;
          
          // Clean up transition after animation
          setTimeout(() => {
            const items = container.querySelectorAll(itemSelector);
            items.forEach(item => {
              item.style.transition = '';
            });
          }, 300);
        }
      });

      container.addEventListener('dragover', e => {
        e.preventDefault();
        const afterElement = this.getDragAfterElement(container, e.clientY, itemSelector);
        if (draggedItem) {
          // Add smooth transition for reordering
          const items = container.querySelectorAll(`${itemSelector}:not(.dragging)`);
          items.forEach(item => {
            item.style.transition = 'transform 0.2s ease-out';
          });
          
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

  app.utils.StaleFeedManager = {
    init() {
      document.querySelectorAll('.box').forEach(box => {
        // If the backend marked this feed as having zero entries on the latest fetch
        // (e.g. JS/selenium selector or format broke), immediately apply stale-feed.
        // This uses the same visual cue as aged feeds and does not wait 2 days.
        const zeroLatest = box.getAttribute('data-zero-latest') === '1';
        if (zeroLatest) {
          box.classList.add('stale-feed');
        }

        // Existing age-based stale detection: if the newest visible entry is older
        // than 2 days, mark the feed as stale.
        const firstArticle = box.querySelector('.linkclass');
        if (firstArticle) {
          const timestamp = parseInt(firstArticle.dataset.index, 10);
          if (!isNaN(timestamp)) {
            const now = Date.now() / 1000;
            if ((now - timestamp) > 24 * 60 * 60 * 2) {
              box.classList.add('stale-feed');
            }
          }
        }
      });
    }
  };

  // =============================================================================
  // EXPOSE APP OBJECT
  // =============================================================================

  window.app = app;

  // =============================================================================
  // UTILITIES
  // =============================================================================

  // =============================================================================
  // INITIALIZE ON DOM CONTENT LOADED
  // =============================================================================

  document.addEventListener('DOMContentLoaded', () => {
    app.utils.UIManager.applySettings();
    app.utils.TimezoneManager.init();
    app.utils.StaleFeedManager.init();
    app.utils.ForceRefreshManager.init();
  });

})();