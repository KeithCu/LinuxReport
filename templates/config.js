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

  // Drag and drop handling with cleanup
  const urlEntries = document.querySelectorAll('.url-entry');
  let draggedItem = null;
  const dragHandlers = new Map();

  urlEntries.forEach(entry => {
    const handlers = {
      dragStart: function(e) {
        draggedItem = this;
        // Add dragging class for visual feedback
        this.classList.add('dragging');
        setTimeout(() => this.style.display = 'none', 0);
      },
      dragEnd: function(e) {
        this.classList.remove('dragging');
        setTimeout(() => {
          this.style.display = 'block';
          draggedItem = null;
        }, 0);
      },
      dragOver: function(e) {
        e.preventDefault();
        requestAnimationFrame(() => {
          if (!this.classList.contains('drag-over')) {
            this.classList.add('drag-over');
          }
        });
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
          const allEntries = Array.from(urlEntries);
          const draggedIndex = allEntries.indexOf(draggedItem);
          const targetIndex = allEntries.indexOf(this);
          
          // Use requestAnimationFrame for smooth visual updates
          requestAnimationFrame(() => {
            if (draggedIndex < targetIndex) {
              this.parentNode.insertBefore(draggedItem, this.nextSibling);
            } else {
              this.parentNode.insertBefore(draggedItem, this);
            }
            
            // Update priorities
            const updatedEntries = document.querySelectorAll('.url-entry');
            updatedEntries.forEach((ent, idx) => {
              const priorityInput = ent.querySelector('input[type="number"]');
              if (priorityInput) {
                priorityInput.value = (idx + 1) * 10;
              }
            });
          });
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

  // Cleanup on page unload
  window.addEventListener('unload', () => {
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