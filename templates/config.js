// Config page: update dropdowns, drag-and-drop ordering

// Helper function for robust cookie handling
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    const cookieValue = parts.pop().split(';').shift();
    try {
      return decodeURIComponent(cookieValue);
    } catch (e) {
      console.error('Cookie decode error:', e);
      return null;
    }
  }
  return null;
}

document.addEventListener('DOMContentLoaded', function() {
  if (!document.querySelector('.config-container')) return;

  // Theme handling
  const currentTheme = getCookie('Theme') || 'silver';
  const themeSelectConfig = document.querySelector('.config-container #theme-select');
  if (themeSelectConfig) themeSelectConfig.value = currentTheme;

  // Font handling
  const currentFont = getCookie('FontFamily') || 'sans-serif';
  const fontSelectConfig = document.querySelector('.config-container #font-select');
  if (fontSelectConfig) fontSelectConfig.value = currentFont;

  // Underlines handling
  const noUnderlines = getCookie('NoUnderlines');
  const noUnderlinesConfig = document.querySelector('.config-container input[name="no_underlines"]');
  if (noUnderlinesConfig) noUnderlinesConfig.checked = (!noUnderlines || noUnderlines === '1');
  
  // Admin password field visibility
  const adminModeCheckbox = document.querySelector('.config-container input[name="admin_mode"]');
  const adminPasswordField = document.querySelector('.admin-password-field');
  
  // Set initial visibility
  if (adminModeCheckbox && adminPasswordField) {
    adminPasswordField.style.display = adminModeCheckbox.checked ? 'block' : 'none';
    
    // Toggle visibility when checkbox changes
    adminModeCheckbox.addEventListener('change', function() {
      adminPasswordField.style.display = this.checked ? 'block' : 'none';
    });
  }

  // Drag and drop handling with cleanup
  let draggedItem = null;
  const dragHandlers = new Map();

  // Get current entries - this will be dynamic
  function getCurrentEntries() {
    return document.querySelectorAll('.url-entry');
  }

  // Setup drag handlers for each entry
  function setupDragHandlers() {
    const urlEntries = getCurrentEntries();
    
    // First remove any existing handlers to prevent duplicates
    urlEntries.forEach(entry => {
      const oldHandlers = dragHandlers.get(entry);
      if (oldHandlers) {
        entry.removeEventListener('dragstart', oldHandlers.dragStart);
        entry.removeEventListener('dragend', oldHandlers.dragEnd);
        entry.removeEventListener('dragover', oldHandlers.dragOver);
        entry.removeEventListener('dragenter', oldHandlers.dragEnter);
        entry.removeEventListener('dragleave', oldHandlers.dragLeave);
        entry.removeEventListener('drop', oldHandlers.drop);
      }
    });
    
    // Clear map
    dragHandlers.clear();
    
    // Setup new handlers
    urlEntries.forEach(entry => {
      const handlers = {
        dragStart: function(e) {
          // Store original display style if we need to restore it
          this.dataset.originalDisplay = this.style.display || '';
          
          draggedItem = this;
          // Add dragging class for visual feedback
          this.classList.add('dragging');
          
          // Use opacity instead of display:none for more stable behavior
          this.style.opacity = '0.9';
        },
        dragEnd: function(e) {
          this.classList.remove('dragging');
          
          // Restore original appearance
          this.style.opacity = '1';
          
          // Reset the dragged item reference
          draggedItem = null;
        },
        dragOver: function(e) {
          e.preventDefault();
          if (!this.classList.contains('drag-over')) {
            this.classList.add('drag-over');
          }
        },
        dragEnter: function(e) {
          e.preventDefault();
        },
        dragLeave: function(e) {
          this.classList.remove('drag-over');
        },
        drop: function(e) {
          e.preventDefault();
          this.classList.remove('drag-over');
          
          if (this !== draggedItem) {
            // Get current state of DOM
            const allEntries = Array.from(getCurrentEntries());
            const draggedIndex = allEntries.indexOf(draggedItem);
            const targetIndex = allEntries.indexOf(this);
            
            // Update DOM
            if (draggedIndex < targetIndex) {
              this.parentNode.insertBefore(draggedItem, this.nextSibling);
            } else {
              this.parentNode.insertBefore(draggedItem, this);
            }
            
            // Update priorities
            updatePriorities();
          }
        }
      };

      // Store handlers for cleanup
      dragHandlers.set(entry, handlers);

      // Add event listeners
      entry.addEventListener('dragstart', handlers.dragStart);
      entry.addEventListener('dragend', handlers.dragEnd);
      entry.addEventListener('dragover', handlers.dragOver);
      entry.addEventListener('dragenter', handlers.dragEnter);
      entry.addEventListener('dragleave', handlers.dragLeave);
      entry.addEventListener('drop', handlers.drop);
    });
  }
  
  // Function to update priorities based on current order
  function updatePriorities() {
    const updatedEntries = getCurrentEntries();
    updatedEntries.forEach((entry, idx) => {
      const priorityInput = entry.querySelector('input[type="number"]');
      if (priorityInput) {
        priorityInput.value = (idx + 1) * 10;
      }
    });
  }
  
  // Initial setup
  setupDragHandlers();
  
  // Cleanup on page unload
  window.addEventListener('unload', () => {
    const urlEntries = getCurrentEntries();
    urlEntries.forEach(entry => {
      const handlers = dragHandlers.get(entry);
      if (handlers) {
        entry.removeEventListener('dragstart', handlers.dragStart);
        entry.removeEventListener('dragend', handlers.dragEnd);
        entry.removeEventListener('dragover', handlers.dragOver);
        entry.removeEventListener('dragenter', handlers.dragEnter);
        entry.removeEventListener('dragleave', handlers.dragLeave);
        entry.removeEventListener('drop', handlers.drop);
      }
    });
  });
});

// Archive headlines admin delete button with improved error handling
(function() {
  const archiveContainer = document.querySelector('.headline-archive-container');
  if (!archiveContainer) return;

  const isAdmin = typeof window.isAdmin !== 'undefined'
    ? window.isAdmin
    : getCookie('isAdmin') === '1';

  if (isAdmin) {
    const deleteHandler = async function(e) {
      if (e.target.classList.contains('delete-headline-btn')) {
        const entry = e.target.closest('.headline-entry');
        if (!entry) return;

        const url = entry.getAttribute('data-url');
        const timestamp = entry.getAttribute('data-timestamp');
        
        if (!url || !timestamp) {
          console.error('Missing required data attributes for deletion');
          return;
        }

        if (confirm('Delete this headline?')) {
          try {
            const response = await fetch('/api/delete_headline', {
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
      }
    };

    archiveContainer.addEventListener('click', deleteHandler);
    
    // Cleanup
    window.addEventListener('unload', () => {
      archiveContainer.removeEventListener('click', deleteHandler);
    });
  }
})();