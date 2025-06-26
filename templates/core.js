/**
 * core.js
 * 
 * Core module for the LinuxReport application. Handles theme management, font settings,
 * scroll position restoration, auto-refresh functionality, pagination controls, and
 * infinite scroll view mode. Provides a professional and responsive user experience.
 * 
 * @author LinuxReport Team
 * @version 2.0.0
 */

// =============================================================================
// CONSTANTS AND CONFIGURATION
// =============================================================================

// Use shared configuration - fail fast if not available
if (typeof window.LINUXREPORT_CONFIG === 'undefined') {
  throw new Error('LINUXREPORT_CONFIG is not available. Make sure shared-config.js is loaded first.');
}

const CORE_CONFIG = window.LINUXREPORT_CONFIG;

// =============================================================================
// UTILITY CLASSES
// =============================================================================

/**
 * Scroll position management utility class.
 * Handles saving and restoring scroll positions with timeout validation.
 */
class ScrollManager {
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
      
      if (Date.now() - data.timestamp > CORE_CONFIG.SCROLL_TIMEOUT) {
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
}

// =============================================================================
// AUTO-REFRESH MANAGEMENT
// =============================================================================

/**
 * Auto-refresh manager with user activity tracking.
 * Automatically refreshes the page when the user has been inactive.
 */
class AutoRefreshManager {
  constructor() {
    this.interval = CORE_CONFIG.AUTO_REFRESH_INTERVAL;
    this.activityTimeout = CORE_CONFIG.ACTIVITY_TIMEOUT;
    this.lastActivity = Date.now();
    this.timer = null;
  }
  
  /**
   * Initialize the auto-refresh functionality.
   */
  init() {
    this.setupActivityTracking();
    this.start();
  }
  
  /**
   * Set up event listeners for user activity tracking.
   */
  setupActivityTracking() {
    const activityEvents = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
    
    activityEvents.forEach(event => {
      document.addEventListener(event, () => {
        this.lastActivity = Date.now();
      }, { passive: true });
    });
    
    // Handle online/offline status
    window.addEventListener('online', () => this.start());
    window.addEventListener('offline', () => this.stop());
  }
  
  /**
   * Start the auto-refresh timer.
   */
  start() {
    if (this.timer) this.stop();
    this.timer = setInterval(() => this.check(), this.interval);
  }
  
  /**
   * Stop the auto-refresh timer.
   */
  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
  
  /**
   * Check if a refresh should occur based on user activity and page state.
   */
  check() {
    // Only refresh if online
    if (!navigator.onLine) return;
    
    // Check if user has been inactive long enough
    const inactiveTime = Date.now() - this.lastActivity;
    if (inactiveTime < this.activityTimeout) return;
    
    // Check for unsaved changes or open dialogs
    const hasUnsavedChanges = document.querySelectorAll('form:invalid').length > 0;
    const hasOpenDialogs = document.querySelectorAll('dialog[open]').length > 0;
    
    if (!hasUnsavedChanges && !hasOpenDialogs) {
      self.location.reload();
    }
  }
}

// =============================================================================
// THEME AND FONT MANAGEMENT
// =============================================================================

/**
 * Theme and font management class.
 * Handles theme switching, font changes, and related UI updates.
 */
class ThemeManager {
  /**
   * Apply the current theme and font settings from cookies.
   */
  static applySettings() {
    // Apply theme
    const theme = CookieManager.get('Theme') || CORE_CONFIG.DEFAULT_THEME;
    document.body.classList.add(`theme-${theme}`);
    
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) themeSelect.value = theme;
    
    // Apply font
    const font = CookieManager.get('FontFamily') || CORE_CONFIG.DEFAULT_FONT;
    ThemeManager.applyFont(font);
    
    const fontSelect = document.getElementById('font-select');
    if (fontSelect) fontSelect.value = font;
    
    // Apply no-underlines setting
    const noUnderlines = CookieManager.get('NoUnderlines');
    if (!noUnderlines || noUnderlines === '1') {
      document.body.classList.add('no-underlines');
    }
  }
  
  /**
   * Apply a specific font to the document.
   * 
   * @param {string} font - The font family to apply
   */
  static applyFont(font) {
    document.body.classList.remove(...CORE_CONFIG.FONT_CLASSES);
    document.body.classList.add(`font-${font}`);
  }
  
  /**
   * Set a new theme and reload the page.
   * 
   * @param {string} theme - The theme to apply
   */
  static setTheme(theme) {
    ScrollManager.savePosition();
    CookieManager.set('Theme', theme);
    window.location.reload();
  }
  
  /**
   * Set a new font with smooth transition and scroll restoration.
   * 
   * @param {string} font - The font to apply
   */
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
}

// =============================================================================
// PAGINATION MANAGEMENT
// =============================================================================

/**
 * Pagination manager for feed content.
 * Handles pagination controls and item visibility.
 */
class PaginationManager {
  /**
   * Initialize pagination for all feed containers.
   */
  static init() {
    document.querySelectorAll('.pagination-controls').forEach(feedControls => {
      new PaginationManager(feedControls);
    });
  }
  
  /**
   * Create a new pagination manager instance.
   * 
   * @param {HTMLElement} feedControls - The pagination controls container
   */
  constructor(feedControls) {
    this.feedControls = feedControls;
    this.feedId = feedControls.dataset.feedId;
    this.feedContainer = document.getElementById(this.feedId);
    
    if (!this.feedContainer) return;
    
    this.items = Array.from(this.feedContainer.querySelectorAll('.linkclass'));
    this.prevBtn = feedControls.querySelector('.prev-btn');
    this.nextBtn = feedControls.querySelector('.next-btn');
    this.currentPage = 0;
    this.totalPages = Math.ceil(this.items.length / CORE_CONFIG.ITEMS_PER_PAGE);
    
    this.setupEventListeners();
    this.update();
  }
  
  /**
   * Set up event listeners for pagination buttons.
   */
  setupEventListeners() {
    if (this.prevBtn) {
      this.prevBtn.addEventListener('click', () => this.previousPage());
    }
    
    if (this.nextBtn) {
      this.nextBtn.addEventListener('click', () => this.nextPage());
    }
  }
  
  /**
   * Go to the previous page.
   */
  previousPage() {
    if (this.currentPage > 0) {
      this.currentPage--;
      this.update();
    }
  }
  
  /**
   * Go to the next page.
   */
  nextPage() {
    if (this.currentPage < this.totalPages - 1) {
      this.currentPage++;
      this.update();
    }
  }
  
  /**
   * Update the display based on current page.
   */
  update() {
    requestAnimationFrame(() => {
      const startIdx = this.currentPage * CORE_CONFIG.ITEMS_PER_PAGE;
      const endIdx = startIdx + CORE_CONFIG.ITEMS_PER_PAGE;
      
      this.items.forEach((item, i) => {
        if (window.currentViewMode === 'column') {
          item.style.display = (i >= startIdx && i < endIdx) ? 'block' : 'none';
        } else {
          item.style.display = 'block';
        }
      });
      
      if (this.prevBtn) this.prevBtn.disabled = this.currentPage === 0;
      if (this.nextBtn) this.nextBtn.disabled = this.currentPage >= this.totalPages - 1;
    });
  }
}

// =============================================================================
// GLOBAL STATE MANAGEMENT
// =============================================================================

// Global view mode state
window.currentViewMode = 'column';

// Global instances
const autoRefreshManager = new AutoRefreshManager();
const infiniteScrollManager = typeof InfiniteScrollManager !== 'undefined'
  ? new InfiniteScrollManager()
  : null;

// =============================================================================
// PUBLIC API FUNCTIONS
// =============================================================================

/**
 * Redirect to the configuration page.
 */
function redirect() {
  ScrollManager.savePosition();
  window.location = "/config";
}

/**
 * Set a new theme.
 * 
 * @param {string} theme - The theme to apply
 */
function setTheme(theme) {
  ThemeManager.setTheme(theme);
}

/**
 * Set a new font.
 * 
 * @param {string} font - The font to apply
 */
function setFont(font) {
  ThemeManager.setFont(font);
}

/**
 * Toggle between column and infinite scroll view modes.
 */
function toggleViewMode() {
  infiniteScrollManager.toggleViewMode();
}

// =============================================================================
// APPLICATION INITIALIZATION
// =============================================================================

/**
 * Initialize the core application functionality.
 */
function initializeApplication() {
  // Apply theme and font settings
  ThemeManager.applySettings();
  
  // Restore scroll position
  ScrollManager.restorePosition();
  
  // Initialize pagination
  PaginationManager.init();
  
  // Initialize auto-refresh
  autoRefreshManager.init();
  
  // Set up view mode toggle
  const viewModeToggle = document.getElementById('view-mode-toggle');
  if (viewModeToggle) {
    viewModeToggle.addEventListener('click', toggleViewMode);
    
    // Debug mode indicator
    if (document.body.classList.contains('desktop-view')) {
      viewModeToggle.style.border = '2px solid #ff0000';
      viewModeToggle.title = 'Debug Mode: Infinite Scroll';
    }
  }
}

// =============================================================================
// EVENT LISTENERS
// =============================================================================

// Initialize application when DOM is ready
document.addEventListener('DOMContentLoaded', initializeApplication);

// =============================================================================
// EXPORT FOR MODULE SYSTEMS (if needed)
// =============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    AutoRefreshManager,
    ThemeManager,
    PaginationManager,
    CORE_CONFIG
  };
}