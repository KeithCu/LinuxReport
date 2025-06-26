/**
 * core.js - Simplified
 * 
 * Core module for the LinuxReport application.
 * Handles auto-refresh, pagination, and view mode management.
 * 
 * @author LinuxReport Team
 * @version 2.1.0
 */

// Use shared configuration
if (typeof window.LINUXREPORT_CONFIG === 'undefined') {
  throw new Error('LINUXREPORT_CONFIG is not available. Make sure shared-config.js is loaded first.');
}

const CORE_CONFIG = window.LINUXREPORT_CONFIG;

// =============================================================================
// AUTO-REFRESH MANAGEMENT
// =============================================================================

class AutoRefreshManager {
  constructor() {
    this.interval = CORE_CONFIG.AUTO_REFRESH_INTERVAL;
    this.activityTimeout = CORE_CONFIG.ACTIVITY_TIMEOUT;
    this.lastActivity = Date.now();
    this.timer = null;
  }
  
  init() {
    this.setupActivityTracking();
    this.start();
  }
  
  setupActivityTracking() {
    const activityEvents = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
    
    activityEvents.forEach(event => {
      document.addEventListener(event, () => {
        this.lastActivity = Date.now();
      }, { passive: true });
    });
    
    window.addEventListener('online', () => this.start());
    window.addEventListener('offline', () => this.stop());
  }
  
  start() {
    if (this.timer) this.stop();
    this.timer = setInterval(() => this.check(), this.interval);
  }
  
  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
  
  check() {
    if (!navigator.onLine) return;
    
    const inactiveTime = Date.now() - this.lastActivity;
    if (inactiveTime < this.activityTimeout) return;
    
    const hasUnsavedChanges = document.querySelectorAll('form:invalid').length > 0;
    const hasOpenDialogs = document.querySelectorAll('dialog[open]').length > 0;
    
    if (!hasUnsavedChanges && !hasOpenDialogs) {
      self.location.reload();
    }
  }
}

// =============================================================================
// PAGINATION MANAGEMENT
// =============================================================================

class PaginationManager {
  static init() {
    document.querySelectorAll('.pagination-controls').forEach(feedControls => {
      new PaginationManager(feedControls);
    });
  }
  
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
  
  setupEventListeners() {
    if (this.prevBtn) {
      this.prevBtn.addEventListener('click', () => this.previousPage());
    }
    
    if (this.nextBtn) {
      this.nextBtn.addEventListener('click', () => this.nextPage());
    }
  }
  
  previousPage() {
    if (this.currentPage > 0) {
      this.currentPage--;
      this.update();
    }
  }
  
  nextPage() {
    if (this.currentPage < this.totalPages - 1) {
      this.currentPage++;
      this.update();
    }
  }
  
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

window.currentViewMode = 'column';

const autoRefreshManager = new AutoRefreshManager();
const infiniteScrollManager = typeof InfiniteScrollManager !== 'undefined'
  ? new InfiniteScrollManager()
  : null;

// =============================================================================
// PUBLIC API FUNCTIONS
// =============================================================================

function redirect() {
  ScrollManager.savePosition();
  window.location = "/config";
}

function setTheme(theme) {
  ThemeManager.setTheme(theme);
}

function setFont(font) {
  ThemeManager.setFont(font);
}

function toggleViewMode() {
  if (infiniteScrollManager) {
    infiniteScrollManager.toggleViewMode();
  }
}

// =============================================================================
// APPLICATION INITIALIZATION
// =============================================================================

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

// Initialize application when DOM is ready
document.addEventListener('DOMContentLoaded', initializeApplication);

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    AutoRefreshManager,
    PaginationManager,
    CORE_CONFIG
  };
}