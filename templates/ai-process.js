/**
 * ai-process.js
 *
 * Shared JavaScript for LLM process viewer popups.
 * Used by both the main page (generated HTML) and old headlines page.
 */

(function() {
  'use strict';

  /**
   * Initialize AI process popup functionality.
   * Works with both class naming conventions for backward compatibility:
   * - Base classes: .ai-process-link, .ai-process-popup, etc.
   * - Main page classes: .ai-process-link-main, .ai-process-popup-main, etc.
   */
  function initAiProcessPopups() {
    // Find all process links (both naming conventions)
    const links = document.querySelectorAll('.ai-process-link, .ai-process-link-main');
    const overlays = document.querySelectorAll('.ai-process-overlay, .ai-process-overlay-main');
    
    // Use shared overlay if available, otherwise find per-popup overlays
    const sharedOverlay = document.querySelector('.ai-process-overlay');
    
    // Handle link clicks
    links.forEach(link => {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        const targetId = this.dataset.target;
        if (!targetId) return;
        
        const popup = document.getElementById(targetId);
        if (!popup) return;
        
        // Determine overlay strategy
        let overlay;
        if (sharedOverlay) {
          // Use shared overlay (old headlines page)
          overlay = sharedOverlay;
        } else {
          // Find per-popup overlay (main page)
          // Try both naming conventions
          const overlayId = targetId.replace('popup-', 'overlay-').replace('popup-main-', 'overlay-main-');
          overlay = document.getElementById(overlayId);
        }
        
        if (popup && overlay) {
          popup.classList.add('active');
          overlay.classList.add('active');
        }
      });
    });
    
    // Handle close button clicks
    document.querySelectorAll('.ai-process-close, .ai-process-close-main').forEach(btn => {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        const targetId = this.dataset.target;
        if (!targetId) return;
        
        const popup = document.getElementById(targetId);
        if (popup) popup.classList.remove('active');
        
        // Close overlay
        if (sharedOverlay) {
          // Shared overlay (old headlines page)
          sharedOverlay.classList.remove('active');
        } else {
          // Per-popup overlay (main page)
          const overlayId = targetId.replace('popup-', 'overlay-').replace('popup-main-', 'overlay-main-');
          const overlay = document.getElementById(overlayId);
          if (overlay) overlay.classList.remove('active');
        }
      });
    });
    
    // Handle overlay clicks (close all popups)
    overlays.forEach(overlay => {
      overlay.addEventListener('click', function(e) {
        // Only close if clicking directly on overlay, not on popup
        if (e.target === overlay) {
          closeAllPopups();
        }
      });
    });
    
    /**
     * Close all AI process popups and overlays
     */
    function closeAllPopups() {
      document.querySelectorAll('.ai-process-popup, .ai-process-popup-main').forEach(p => {
        p.classList.remove('active');
      });
      document.querySelectorAll('.ai-process-overlay, .ai-process-overlay-main').forEach(o => {
        o.classList.remove('active');
      });
    }
    
    // Handle ESC key to close popups
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' || e.keyCode === 27) {
        // Check if any popup is currently active
        const activePopups = document.querySelectorAll('.ai-process-popup.active, .ai-process-popup-main.active');
        if (activePopups.length > 0) {
          e.preventDefault();
          closeAllPopups();
        }
      }
    });
    
    // Expose closeAllPopups for external use if needed
    window.closeAllAiProcessPopups = closeAllPopups;
  }
  
  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAiProcessPopups);
  } else {
    // DOM already loaded
    initAiProcessPopups();
  }
})();
