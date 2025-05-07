// Config page: update dropdowns, drag-and-drop ordering

document.addEventListener('DOMContentLoaded', function() {
  if (!document.querySelector('.config-container')) return;

  var themeMatch = document.cookie.match(/(?:^|; )Theme=([^;]+)/);
  var currentTheme = themeMatch ? themeMatch[1] : 'silver';
  var themeSelectConfig = document.querySelector('.config-container #theme-select');
  if (themeSelectConfig) themeSelectConfig.value = currentTheme;

  var fontMatchCookie = document.cookie.match(/(?:^|; )FontFamily=([^;]+)/);
  var currentFont = fontMatchCookie ? fontMatchCookie[1] : 'sans-serif';
  var fontSelectConfig = document.querySelector('.config-container #font-select');
  if (fontSelectConfig) fontSelectConfig.value = currentFont;

  var nuMatch = document.cookie.match(/(?:^|; )NoUnderlines=([^;]+)/);
  var noUnderlinesConfig = document.querySelector('.config-container input[name="no_underlines"]');
  if (noUnderlinesConfig) noUnderlinesConfig.checked = (!nuMatch || nuMatch[1] === '1');

  const urlEntries = document.querySelectorAll('.url-entry');
  let draggedItem = null;
  urlEntries.forEach(entry => {
    entry.addEventListener('dragstart', function() {
      draggedItem = this;
      setTimeout(() => this.style.display = 'none', 0);
    });
    entry.addEventListener('dragend', function() {
      setTimeout(() => { this.style.display = 'block'; draggedItem = null; }, 0);
    });
    entry.addEventListener('dragover', function(e) { e.preventDefault(); });
    entry.addEventListener('dragenter', function(e) {
      e.preventDefault(); this.style.border = '2px dashed #000';
    });
    entry.addEventListener('dragleave', function() { this.style.border = ''; });
    entry.addEventListener('drop', function() {
      this.style.border = '';
      if (this !== draggedItem) {
        const allEntries = Array.from(urlEntries);
        const draggedIndex = allEntries.indexOf(draggedItem);
        const targetIndex = allEntries.indexOf(this);
        if (draggedIndex < targetIndex) {
          this.parentNode.insertBefore(draggedItem, this.nextSibling);
        } else {
          this.parentNode.insertBefore(draggedItem, this);
        }
        const updatedEntries = document.querySelectorAll('.url-entry');
        updatedEntries.forEach((ent, idx) => {
          const priorityInput = ent.querySelector('input[type="number"]');
          if (priorityInput) priorityInput.value = (idx + 1) * 10;
        });
      }
    });
  });
});

// Archive headlines admin delete button
(function() {
  const archiveContainer = document.querySelector('.headline-archive-container');
  if (!archiveContainer) return;
  const isAdmin = typeof window.isAdmin !== 'undefined'
    ? window.isAdmin
    : document.cookie.split('; ').some(item => item.trim().startsWith('isAdmin=1'));
  if (isAdmin) {
    archiveContainer.addEventListener('click', function(e) {
      if (e.target.classList.contains('delete-headline-btn')) {
        const entry = e.target.closest('.headline-entry');
        const url = entry.getAttribute('data-url');
        const timestamp = entry.getAttribute('data-timestamp');
        if (confirm('Delete this headline?')) {
          fetch('/api/delete_headline', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, timestamp })
          })
          .then(r => r.json())
          .then(resp => {
            if (resp.success) entry.remove();
            else alert('Delete failed: ' + (resp.error || 'Unknown error'));
          })
          .catch(() => alert('Delete failed.'));
        }
      }
    });
  }
})();