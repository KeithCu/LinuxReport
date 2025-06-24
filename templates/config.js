/**
 * config.js
 * 
 * Configuration page module for the LinuxReport application. Handles theme and font
 * settings, drag-and-drop URL reordering, admin mode functionality, and archive
 * headline management. Provides a professional and responsive configuration interface.
 * 
 * @author LinuxReport Team
 * @version 2.0.0
 */

// =============================================================================
// CONSTANTS AND CONFIGURATION
// =============================================================================

const CONFIG = {
  // Default values
  DEFAULT_THEME: 'silver',
  DEFAULT_FONT: 'sans-serif',
  
  // Drag and drop settings
  DRAG_OPACITY: '0.9',
  DRAG_OPACITY_NORMAL: '1',
  
  // Priority calculation
  PRIORITY_MULTIPLIER: 10,
  
  // API endpoints
  DELETE_HEADLINE_ENDPOINT: '/api/delete_headline'
};

// =============================================================================
// UTILITY CLASSES
// =============================================================================

/**
 * Cookie management utility class.
 * Provides methods for getting and setting cookies with proper encoding/decoding.
 */
class CookieManager {
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
    const defaultOptions = {
      path: '/',
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
}

// =============================================================================
// SETTINGS MANAGEMENT
// =============================================================================

/**
 * Settings management class.
 * Handles theme, font, and other configuration settings.
 */
class SettingsManager {
  /**
   * Initialize all settings from cookies and update UI elements.
   */
  static init() {
    SettingsManager.initTheme();
    SettingsManager.initFont();
    SettingsManager.initUnderlines();
    SettingsManager.initAdminMode();
  }
  
  /**
   * Initialize theme setting.
   */
  static initTheme() {
    const currentTheme = CookieManager.get('Theme') || CONFIG.DEFAULT_THEME;
    const themeSelect = document.querySelector('.config-container #theme-select');
    if (themeSelect) {
      themeSelect.value = currentTheme;
    }
  }
  
  /**
   * Initialize font setting.
   */
  static initFont() {
    const currentFont = CookieManager.get('FontFamily') || CONFIG.DEFAULT_FONT;
    const fontSelect = document.querySelector('.config-container #font-select');
    if (fontSelect) {
      fontSelect.value = currentFont;
    }
  }
  
  /**
   * Initialize underlines setting.
   */
  static initUnderlines() {
    const noUnderlines = CookieManager.get('NoUnderlines');
    const noUnderlinesCheckbox = document.querySelector('.config-container input[name="no_underlines"]');
    if (noUnderlinesCheckbox) {
      noUnderlinesCheckbox.checked = (!noUnderlines || noUnderlines === '1');
    }
  }
  
  /**
   * Initialize admin mode functionality.
   */
  static initAdminMode() {
    const adminModeCheckbox = document.querySelector('.config-container input[name="admin_mode"]');
    const adminPasswordField = document.querySelector('.admin-password-field');
    
    if (adminModeCheckbox && adminPasswordField) {
      // Set initial visibility
      adminPasswordField.style.display = adminModeCheckbox.checked ? 'block' : 'none';
      
      // Toggle visibility when checkbox changes
      adminModeCheckbox.addEventListener('change', function() {
        adminPasswordField.style.display = this.checked ? 'block' : 'none';
      });
    }
  }
}

// =============================================================================
// DRAG AND DROP MANAGEMENT
// =============================================================================

/**
 * Drag and drop manager for URL entries.
 * Handles reordering of URL entries with visual feedback and priority updates.
 */
class DragDropManager {
  constructor() {
    this.draggedItem = null;
    this.dragHandlers = new Map();
    this.init();
  }
  
  /**
   * Initialize drag and drop functionality.
   */
  init() {
    this.setupDragHandlers();
    this.setupCleanup();
  }
  
  /**
   * Get all current URL entries.
   * 
   * @returns {NodeList} All URL entry elements
   */
  getCurrentEntries() {
    return document.querySelectorAll('.url-entry');
  }
  
  /**
   * Set up drag handlers for all URL entries.
   */
  setupDragHandlers() {
    const urlEntries = this.getCurrentEntries();
    
    // Remove existing handlers to prevent duplicates
    this.cleanupExistingHandlers(urlEntries);
    
    // Clear handler map
    this.dragHandlers.clear();
    
    // Setup new handlers
    urlEntries.forEach(entry => {
      const handlers = this.createDragHandlers(entry);
      this.dragHandlers.set(entry, handlers);
      this.attachEventListeners(entry, handlers);
    });
  }
  
  /**
   * Clean up existing drag handlers for entries.
   * 
   * @param {NodeList} entries - The entries to clean up
   */
  cleanupExistingHandlers(entries) {
    entries.forEach(entry => {
      const oldHandlers = this.dragHandlers.get(entry);
      if (oldHandlers) {
        this.detachEventListeners(entry, oldHandlers);
      }
    });
  }
  
  /**
   * Create drag event handlers for an entry.
   * 
   * @param {HTMLElement} entry - The entry element
   * @returns {Object} The drag handlers object
   */
  createDragHandlers(entry) {
    return {
      dragStart: (e) => this.handleDragStart(e, entry),
      dragEnd: (e) => this.handleDragEnd(e, entry),
      dragOver: (e) => this.handleDragOver(e, entry),
      dragEnter: (e) => this.handleDragEnter(e, entry),
      dragLeave: (e) => this.handleDragLeave(e, entry),
      drop: (e) => this.handleDrop(e, entry)
    };
  }
  
  /**
   * Attach event listeners to an entry.
   * 
   * @param {HTMLElement} entry - The entry element
   * @param {Object} handlers - The drag handlers object
   */
  attachEventListeners(entry, handlers) {
    entry.addEventListener('dragstart', handlers.dragStart);
    entry.addEventListener('dragend', handlers.dragEnd);
    entry.addEventListener('dragover', handlers.dragOver);
    entry.addEventListener('dragenter', handlers.dragEnter);
    entry.addEventListener('dragleave', handlers.dragLeave);
    entry.addEventListener('drop', handlers.drop);
  }
  
  /**
   * Detach event listeners from an entry.
   * 
   * @param {HTMLElement} entry - The entry element
   * @param {Object} handlers - The drag handlers object
   */
  detachEventListeners(entry, handlers) {
    entry.removeEventListener('dragstart', handlers.dragStart);
    entry.removeEventListener('dragend', handlers.dragEnd);
    entry.removeEventListener('dragover', handlers.dragOver);
    entry.removeEventListener('dragenter', handlers.dragEnter);
    entry.removeEventListener('dragleave', handlers.dragLeave);
    entry.removeEventListener('drop', handlers.drop);
  }
  
  /**
   * Handle drag start event.
   * 
   * @param {DragEvent} e - The drag event
   * @param {HTMLElement} entry - The entry element
   */
  handleDragStart(e, entry) {
    entry.dataset.originalDisplay = entry.style.display || '';
    this.draggedItem = entry;
    entry.classList.add('dragging');
    entry.style.opacity = CONFIG.DRAG_OPACITY;
  }
  
  /**
   * Handle drag end event.
   * 
   * @param {DragEvent} e - The drag event
   * @param {HTMLElement} entry - The entry element
   */
  handleDragEnd(e, entry) {
    entry.classList.remove('dragging');
    entry.style.opacity = CONFIG.DRAG_OPACITY_NORMAL;
    this.draggedItem = null;
  }
  
  /**
   * Handle drag over event.
   * 
   * @param {DragEvent} e - The drag event
   * @param {HTMLElement} entry - The entry element
   */
  handleDragOver(e, entry) {
    e.preventDefault();
    if (!entry.classList.contains('drag-over')) {
      entry.classList.add('drag-over');
    }
  }
  
  /**
   * Handle drag enter event.
   * 
   * @param {DragEvent} e - The drag event
   * @param {HTMLElement} entry - The entry element
   */
  handleDragEnter(e, entry) {
    e.preventDefault();
  }
  
  /**
   * Handle drag leave event.
   * 
   * @param {DragEvent} e - The drag event
   * @param {HTMLElement} entry - The entry element
   */
  handleDragLeave(e, entry) {
    entry.classList.remove('drag-over');
  }
  
  /**
   * Handle drop event.
   * 
   * @param {DragEvent} e - The drag event
   * @param {HTMLElement} entry - The entry element
   */
  handleDrop(e, entry) {
    e.preventDefault();
    entry.classList.remove('drag-over');
    
    if (this.draggedItem && this.draggedItem !== entry) {
      this.reorderEntries(this.draggedItem, entry);
      this.updatePriorities();
    }
  }
  
  /**
   * Reorder entries in the DOM.
   * 
   * @param {HTMLElement} draggedItem - The item being dragged
   * @param {HTMLElement} targetItem - The target item
   */
  reorderEntries(draggedItem, targetItem) {
    const allEntries = Array.from(this.getCurrentEntries());
    const draggedIndex = allEntries.indexOf(draggedItem);
    const targetIndex = allEntries.indexOf(targetItem);
    
    if (draggedIndex < targetIndex) {
      targetItem.parentNode.insertBefore(draggedItem, targetItem.nextSibling);
    } else {
      targetItem.parentNode.insertBefore(draggedItem, targetItem);
    }
  }
  
  /**
   * Update priorities based on current order.
   */
  updatePriorities() {
    const entries = this.getCurrentEntries();
    entries.forEach((entry, index) => {
      const priorityInput = entry.querySelector('input[type="number"]');
      if (priorityInput) {
        priorityInput.value = (index + 1) * CONFIG.PRIORITY_MULTIPLIER;
      }
    });
  }
  
  /**
   * Set up cleanup on page unload.
   */
  setupCleanup() {
    window.addEventListener('unload', () => {
      const entries = this.getCurrentEntries();
      entries.forEach(entry => {
        const handlers = this.dragHandlers.get(entry);
        if (handlers) {
          this.detachEventListeners(entry, handlers);
        }
      });
    });
  }
}

// =============================================================================
// ARCHIVE MANAGEMENT
// =============================================================================

/**
 * Archive management class for headline deletion.
 * Handles admin-only headline deletion with proper error handling.
 */
class ArchiveManager {
  constructor() {
    this.archiveContainer = document.querySelector('.headline-archive-container');
    this.isAdmin = typeof window.isAdmin !== 'undefined' ? window.isAdmin : false;
    
    if (this.archiveContainer && this.isAdmin) {
      this.init();
    }
  }
  
  /**
   * Initialize archive management functionality.
   */
  init() {
    this.setupDeleteHandler();
    this.setupCleanup();
  }
  
  /**
   * Set up the delete handler for headline entries.
   */
  setupDeleteHandler() {
    this.deleteHandler = this.handleDelete.bind(this);
    this.archiveContainer.addEventListener('click', this.deleteHandler);
  }
  
  /**
   * Handle delete button clicks.
   * 
   * @param {Event} e - The click event
   */
  async handleDelete(e) {
    if (!e.target.classList.contains('delete-headline-btn')) {
      return;
    }
    
    const entry = e.target.closest('.headline-entry');
    if (!entry) {
      return;
    }
    
    const url = entry.getAttribute('data-url');
    const timestamp = entry.getAttribute('data-timestamp');
    
    if (!url || !timestamp) {
      console.error('Missing required data attributes for deletion');
      return;
    }
    
    if (confirm('Delete this headline?')) {
      await this.performDelete(entry, url, timestamp);
    }
  }
  
  /**
   * Perform the actual delete operation.
   * 
   * @param {HTMLElement} entry - The entry element to delete
   * @param {string} url - The URL of the headline
   * @param {string} timestamp - The timestamp of the headline
   */
  async performDelete(entry, url, timestamp) {
    try {
      const response = await fetch(CONFIG.DELETE_HEADLINE_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, timestamp })
      });
      
      const data = await response.json();
      
      if (data.success) {
        entry.remove();
      } else {
        throw new Error(data.error || 'Unknown error');
      }
    } catch (error) {
      console.error('Delete operation failed:', error);
      alert(`Delete failed: ${error.message}`);
    }
  }
  
  /**
   * Set up cleanup on page unload.
   */
  setupCleanup() {
    window.addEventListener('unload', () => {
      if (this.deleteHandler) {
        this.archiveContainer.removeEventListener('click', this.deleteHandler);
      }
    });
  }
}

// =============================================================================
// GLOBAL INSTANCES
// =============================================================================

let dragDropManager = null;
let archiveManager = null;

// =============================================================================
// APPLICATION INITIALIZATION
// =============================================================================

/**
 * Initialize the configuration page functionality.
 */
function initializeConfigPage() {
  // Check if we're on the config page
  if (!document.querySelector('.config-container')) {
    return;
  }
  
  // Initialize settings
  SettingsManager.init();
  
  // Initialize drag and drop
  dragDropManager = new DragDropManager();
  
  // Initialize archive management
  archiveManager = new ArchiveManager();
}

// =============================================================================
// EVENT LISTENERS
// =============================================================================

// Initialize configuration page when DOM is ready
document.addEventListener('DOMContentLoaded', initializeConfigPage);

// =============================================================================
// EXPORT FOR MODULE SYSTEMS (if needed)
// =============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    CookieManager,
    SettingsManager,
    DragDropManager,
    ArchiveManager,
    CONFIG
  };
}