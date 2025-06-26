/**
 * shared-config.js
 * 
 * Shared configuration module for the LinuxReport application. Contains all
 * configuration constants and settings used across multiple JavaScript modules.
 * This file should be loaded first before other modules.
 * 
 * @author LinuxReport Team
 * @version 2.0.0
 */

// =============================================================================
// SHARED CONFIGURATION
// =============================================================================

/**
 * Global configuration object containing all application settings.
 * This object is shared across all JavaScript modules to prevent conflicts.
 * 
 * If this configuration is not available, the application should fail fast
 * rather than using fallback values.
 */
(function() {
  'use strict';
  
  // Create the global configuration object - this is the single source of truth
  window.LINUXREPORT_CONFIG = {
    // =============================================================================
    // CORE MODULE SETTINGS
    // =============================================================================
    
    // Auto-refresh settings
    AUTO_REFRESH_INTERVAL: 3601 * 1000, // 1 hour + 1 second
    ACTIVITY_TIMEOUT: 5 * 60 * 1000, // 5 minutes
    
    // Pagination settings
    ITEMS_PER_PAGE: 8,
    INFINITE_ITEMS_PER_PAGE: 20,
    
    // Scroll restoration settings
    SCROLL_TIMEOUT: 10000, // 10 seconds
    
    // Font families
    FONT_CLASSES: [
      'font-system', 'font-monospace', 'font-inter', 'font-roboto',
      'font-open-sans', 'font-source-sans', 'font-noto-sans',
      'font-lato', 'font-raleway', 'font-sans-serif'
    ],
    
    // Default values
    DEFAULT_THEME: 'silver',
    DEFAULT_FONT: 'sans-serif',
    
    // =============================================================================
    // WEATHER MODULE SETTINGS
    // =============================================================================
    
    // Widget toggle settings
    WEATHER_WIDGET_TOGGLE_ENABLED: true,
    WEATHER_DEFAULT_COLLAPSED: false, // Set to true for collapsed by default
    
    // Caching settings
    WEATHER_CACHE_DURATION: 30 * 60 * 1000, // 30 minutes in milliseconds
    
    // API settings
    USE_LINUXREPORT_WEATHER: false,
    WEATHER_BASE_URL: '', // Set dynamically based on USE_LINUXREPORT_WEATHER
    
    // Debounce settings
    WEATHER_DEBOUNCE_DELAY: 100,
    
    // Cookie settings
    COOKIE_MAX_AGE: 31536000, // 1 year
    COOKIE_SAME_SITE: 'Lax',
    
    // Imperial units regions
    IMPERIAL_REGIONS: ['US', 'BS', 'BZ', 'KY', 'PW'],
    
    // Default locale
    DEFAULT_LOCALE: 'en-US',
    
    // =============================================================================
    // CHAT MODULE SETTINGS
    // =============================================================================
    
    // Communication settings
    CHAT_USE_SSE: false, // Set to true to enable SSE, false for polling
    CHAT_POLLING_INTERVAL: 15000, // 15 seconds
    
    // Retry settings
    CHAT_MAX_RETRIES: 5,
    CHAT_BASE_RETRY_DELAY: 1000,
    CHAT_MAX_RETRY_DELAY: 30000,
    
    // Performance settings
    CHAT_FETCH_DEBOUNCE_DELAY: 1000,
    CHAT_RENDER_DEBOUNCE_DELAY: 100,
    CHAT_DRAG_THROTTLE_DELAY: 16, // ~60fps
    
    // File upload settings
    CHAT_MAX_FILE_SIZE: 5 * 1024 * 1024, // 5MB
    CHAT_ALLOWED_FILE_TYPES: ['image/png', 'image/jpeg', 'image/gif', 'image/webp'],
    
    // UI settings
    CHAT_RESIZE_DEBOUNCE_DELAY: 250,
    
    // =============================================================================
    // CONFIG MODULE SETTINGS
    // =============================================================================
    
    // Drag and drop settings
    DRAG_OPACITY: '0.9',
    DRAG_OPACITY_NORMAL: '1',
    
    // Priority calculation
    PRIORITY_MULTIPLIER: 10,
    
    // API endpoints
    DELETE_HEADLINE_ENDPOINT: '/api/delete_headline'
  };

  // Initialize weather base URL
  window.LINUXREPORT_CONFIG.WEATHER_BASE_URL = window.LINUXREPORT_CONFIG.USE_LINUXREPORT_WEATHER ? 'https://linuxreport.net' : '';
  
  // Configuration validation - ensure all required keys exist
  const requiredKeys = [
    'AUTO_REFRESH_INTERVAL', 'ACTIVITY_TIMEOUT', 'ITEMS_PER_PAGE', 'INFINITE_ITEMS_PER_PAGE',
    'SCROLL_TIMEOUT', 'FONT_CLASSES', 'DEFAULT_THEME', 'DEFAULT_FONT',
    'WEATHER_WIDGET_TOGGLE_ENABLED', 'WEATHER_DEFAULT_COLLAPSED', 'WEATHER_CACHE_DURATION',
    'USE_LINUXREPORT_WEATHER', 'WEATHER_BASE_URL', 'WEATHER_DEBOUNCE_DELAY',
    'COOKIE_MAX_AGE', 'COOKIE_SAME_SITE', 'IMPERIAL_REGIONS', 'DEFAULT_LOCALE',
    'CHAT_USE_SSE', 'CHAT_POLLING_INTERVAL', 'CHAT_MAX_RETRIES', 'CHAT_BASE_RETRY_DELAY',
    'CHAT_MAX_RETRY_DELAY', 'CHAT_FETCH_DEBOUNCE_DELAY', 'CHAT_RENDER_DEBOUNCE_DELAY',
    'CHAT_DRAG_THROTTLE_DELAY', 'CHAT_MAX_FILE_SIZE', 'CHAT_ALLOWED_FILE_TYPES',
    'CHAT_RESIZE_DEBOUNCE_DELAY', 'DRAG_OPACITY', 'DRAG_OPACITY_NORMAL',
    'PRIORITY_MULTIPLIER', 'DELETE_HEADLINE_ENDPOINT'
  ];
  
  const missingKeys = requiredKeys.filter(key => !(key in window.LINUXREPORT_CONFIG));
  if (missingKeys.length > 0) {
    throw new Error(`Missing required configuration keys: ${missingKeys.join(', ')}`);
  }
  
})();

// =============================================================================
// EXPORT FOR MODULE SYSTEMS (if needed)
// =============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    LINUXREPORT_CONFIG: window.LINUXREPORT_CONFIG
  };
} 