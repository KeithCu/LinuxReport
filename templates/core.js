// Core module: theme, font, scroll restore, auto-refresh, redirect, and pagination

// Cookie handling utilities
const Cookie = {
  get(name) {
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
  },
  
  set(name, value, options = {}) {
    options = {
      path: '/',
      ...options
    };
    
    let cookieString = `${name}=${encodeURIComponent(value)}`;
    
    Object.entries(options).forEach(([key, value]) => {
      cookieString += `; ${key}`;
      if (value !== true) {
        cookieString += `=${value}`;
      }
    });
    
    document.cookie = cookieString;
  }
};

// Apply theme, font, no-underlines and restore scroll
document.addEventListener('DOMContentLoaded', function() {
  // Read theme cookie or default
  const theme = Cookie.get('Theme') || 'silver';
  document.body.classList.add('theme-' + theme);
  const select = document.getElementById('theme-select');
  if (select) select.value = theme;

  // Read font cookie or default
  const font = Cookie.get('FontFamily') || 'sans-serif';
  const fontClasses = [
    'font-system', 'font-monospace', 'font-inter', 'font-roboto',
    'font-open-sans', 'font-source-sans', 'font-noto-sans',
    'font-lato', 'font-raleway', 'font-sans-serif'
  ];
  document.body.classList.remove(...fontClasses);
  document.body.classList.add('font-' + font);
  const fontSelect = document.getElementById('font-select');
  if (fontSelect) fontSelect.value = font;

  // No underlines setting
  const noUnderlines = Cookie.get('NoUnderlines');
  if (!noUnderlines || noUnderlines === '1') {
    document.body.classList.add('no-underlines');
  }

  // Restore scroll position
  restoreScrollPosition();
});

let pendingScrollRestoreAfterFontChange = false;
let scrollRestoreTimeout = null;

function finalRestoreScroll() {
  if (pendingScrollRestoreAfterFontChange) {
    restoreScrollPosition();
    pendingScrollRestoreAfterFontChange = false;
  }
}

function redirect() {
  saveScrollPosition();
  window.location = "/config";
}

// Improved auto-refresh with user activity tracking
const AutoRefresh = {
  interval: 3601 * 1000, // 1 hour + 1 second
  activityTimeout: 5 * 60 * 1000, // 5 minutes
  lastActivity: Date.now(),
  timer: null,
  
  init() {
    this.setupActivityTracking();
    this.start();
  },
  
  setupActivityTracking() {
    ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach(event => {
      document.addEventListener(event, () => {
        this.lastActivity = Date.now();
      }, { passive: true });
    });
    
    // Check if we're online
    window.addEventListener('online', () => this.start());
    window.addEventListener('offline', () => this.stop());
  },
  
  start() {
    if (this.timer) this.stop();
    this.timer = setInterval(() => this.check(), this.interval);
  },
  
  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  },
  
  check() {
    // Only refresh if:
    // 1. We're online
    // 2. User has been inactive
    // 3. No unsaved changes or open dialogs
    if (!navigator.onLine) return;
    
    const inactiveTime = Date.now() - this.lastActivity;
    if (inactiveTime < this.activityTimeout) return;
    
    const hasUnsavedChanges = document.querySelectorAll('form:invalid').length > 0;
    const hasOpenDialogs = document.querySelectorAll('dialog[open]').length > 0;
    
    if (!hasUnsavedChanges && !hasOpenDialogs) {
      self.location.reload();
    }
  }
};

// Initialize auto-refresh
AutoRefresh.init();

function setTheme(theme) {
  saveScrollPosition();
  Cookie.set('Theme', theme);
  window.location.reload();
}

function setFont(font) {
  saveScrollPosition();
  pendingScrollRestoreAfterFontChange = true;
  Cookie.set('FontFamily', font);
  
  const fontClasses = [
    'font-system', 'font-monospace', 'font-inter', 'font-roboto',
    'font-open-sans', 'font-source-sans', 'font-noto-sans',
    'font-lato', 'font-raleway', 'font-sans-serif'
  ];
  document.body.classList.remove(...fontClasses);
  document.body.classList.add('font-' + font);
  
  const fontSelect = document.getElementById('font-select');
  if (fontSelect) fontSelect.value = font;
  
  // Force reflow with minimal layout thrashing
  requestAnimationFrame(() => {
    document.body.style.display = 'none';
    requestAnimationFrame(() => {
      document.body.style.display = '';
      document.querySelectorAll('*').forEach(el => el.style.fontFamily = 'inherit');
      
      // Clear any existing timeout
      if (scrollRestoreTimeout) {
        clearTimeout(scrollRestoreTimeout);
      }
      scrollRestoreTimeout = setTimeout(finalRestoreScroll, 1000);
    });
  });
}

function saveScrollPosition() {
  try {
    localStorage.setItem('scrollPosition', JSON.stringify({
      position: window.scrollY,
      timestamp: Date.now()
    }));
  } catch (e) {
    console.error('Error saving scroll position:', e);
  }
}

function restoreScrollPosition() {
  try {
    const saved = localStorage.getItem('scrollPosition');
    if (!saved) return;
    
    const data = JSON.parse(saved);
    const scrollTimeout = 10000; // 10 seconds
    
    if (Date.now() - data.timestamp > scrollTimeout) {
      localStorage.removeItem('scrollPosition');
      return;
    }
    
    // Use requestAnimationFrame for smooth scrolling
    requestAnimationFrame(() => {
      window.scrollTo({
        top: data.position,
        behavior: 'instant' // Use instant to prevent smooth scrolling animation
      });
      localStorage.removeItem('scrollPosition');
    });
  } catch (e) {
    console.error('Error restoring scroll position:', e);
    localStorage.removeItem('scrollPosition');
  }
}

// Pagination controls with performance improvements
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.pagination-controls').forEach(feedControls => {
    const feedId = feedControls.dataset.feedId;
    const feedContainer = document.getElementById(feedId);
    if (!feedContainer) return;
    
    const items = Array.from(feedContainer.querySelectorAll('.linkclass'));
    const prevBtn = feedControls.querySelector('.prev-btn');
    const nextBtn = feedControls.querySelector('.next-btn');
    const itemsPerPage = 8;
    let currentPage = 0;
    const totalPages = Math.ceil(items.length / itemsPerPage);
    
    function update() {
      // Use requestAnimationFrame for smooth updates
      requestAnimationFrame(() => {
        const startIdx = currentPage * itemsPerPage;
        const endIdx = startIdx + itemsPerPage;
        
        items.forEach((item, i) => {
          if (currentViewMode === 'column') {
            item.style.display = (i >= startIdx && i < endIdx) ? 'block' : 'none';
          } else {
            item.style.display = 'block';
          }
        });
        
        if (prevBtn) prevBtn.disabled = currentPage === 0;
        if (nextBtn) nextBtn.disabled = currentPage >= totalPages - 1;
      });
    }
    
    if (prevBtn) {
      prevBtn.addEventListener('click', () => {
        if (currentPage > 0) {
          currentPage--;
          update();
        }
      });
    }
    
    if (nextBtn) {
      nextBtn.addEventListener('click', () => {
        if (currentPage < totalPages - 1) {
          currentPage++;
          update();
        }
      });
    }
    
    update();
  });
});

// Infinite Scroll View Mode
let currentViewMode = 'column';
let currentPage = 0;
const itemsPerPage = 20;

function toggleViewMode() {
    console.log('Toggling view mode from', currentViewMode);
    currentViewMode = currentViewMode === 'column' ? 'infinite' : 'column';
    const button = document.getElementById('view-mode-toggle');
    button.textContent = currentViewMode === 'column' ? 'Infinite View' : 'Column View';
    
    if (currentViewMode === 'infinite') {
        console.log('Switching to infinite view');
        // First collect all items while they're still visible
        const container = document.getElementById('infinite-content');
        container.innerHTML = '';
        currentPage = 0;
        
        // Make all items visible before collecting them
        document.querySelectorAll('.linkclass').forEach(item => {
            item.style.display = 'block';
        });
        
        loadInfiniteContent();
        
        // Then hide the row and show infinite container
        document.querySelector('.row').style.display = 'none';
        document.getElementById('infinite-scroll-container').style.display = 'block';
    } else {
        console.log('Switching to column view');
        // Show row and hide infinite container
        document.querySelector('.row').style.display = 'flex';
        document.getElementById('infinite-scroll-container').style.display = 'none';
        
        // Restore pagination
        document.querySelectorAll('.pagination-controls').forEach(feedControls => {
            const feedId = feedControls.dataset.feedId;
            const feedContainer = document.getElementById(feedId);
            if (!feedContainer) return;
            
            const items = Array.from(feedContainer.querySelectorAll('.linkclass'));
            const itemsPerPage = 8;
            
            // Show only first page of items
            items.forEach((item, i) => {
                item.style.display = (i < itemsPerPage) ? 'block' : 'none';
            });
        });
    }
    console.log('View mode toggled to', currentViewMode);
}

function loadInfiniteContent() {
    const container = document.getElementById('infinite-content');
    const loadingIndicator = document.getElementById('loading-indicator');
    
    console.log('Loading infinite content...');
    
    // Show loading indicator
    loadingIndicator.style.display = 'block';
    
    // Get all items from all columns
    const allItems = [];
    const columns = document.querySelectorAll('.column');
    console.log('Found columns:', columns.length);
    
    // Track sources we've found
    const foundSources = new Set();
    
    columns.forEach((column, colIndex) => {
        // Look for feed containers by their class
        const feedContainers = column.querySelectorAll('.box');
        console.log(`Column ${colIndex} has ${feedContainers.length} feed containers`);
        
        feedContainers.forEach((container, feedIndex) => {
            const feedId = container.id;
            const feedTitle = container.querySelector('a[target="_blank"]');
            const feedIcon = container.querySelector('img');
            
            if (!feedTitle || !feedIcon) {
                console.log(`Skipping feed ${feedId} - missing title or icon`);
                return;
            }
            
            // Extract feed name from the ID (which is the feed URL)
            const feedUrl = feedId.replace('feed-', '');
            let feedName = '';
            
            // Parse the URL to get a better feed name
            try {
                const url = new URL(feedUrl);
                // Get the last part of the path or the hostname
                feedName = url.pathname.split('/').filter(Boolean).pop() || url.hostname;
                // Clean up the name
                feedName = feedName
                    .replace(/\.(com|org|net|io)$/, '')
                    .replace(/-/g, ' ')
                    .replace(/\b\w/g, l => l.toUpperCase());
            } catch (e) {
                // If URL parsing fails, use the ID
                feedName = feedId.replace('feed-', '');
            }
            
            const feedIconSrc = feedIcon.src;
            const items = container.querySelectorAll('.linkclass');
            
            // Log only the first time we see a source
            if (!foundSources.has(feedName)) {
                console.log(`Found new source: ${feedName} with ${items.length} items`);
                foundSources.add(feedName);
            }
            
            items.forEach((item, itemIndex) => {
                // Only collect items that are currently visible
                if (window.getComputedStyle(item).display !== 'none') {
                    // Get the timestamp from the data-index attribute
                    const timestamp = parseInt(item.getAttribute('data-index') || '0');
                    
                    allItems.push({
                        title: item.textContent,
                        link: item.href,
                        source_name: feedName,
                        source_icon: feedIconSrc,
                        timestamp: timestamp
                    });
                }
            });
        });
    });
    
    console.log('Total items collected:', allItems.length);
    console.log('Sources found:', Array.from(foundSources));
    
    // Sort all items by timestamp (newest first)
    allItems.sort((a, b) => b.timestamp - a.timestamp);
    
    // Create a map of source information
    const sourceInfo = new Map();
    allItems.forEach(item => {
        if (!sourceInfo.has(item.source_name)) {
            sourceInfo.set(item.source_name, {
                name: item.source_name,
                icon: item.source_icon
            });
        }
    });
    
    // Group all items by source while maintaining timestamp order
    const groupedItems = [];
    let currentGroup = null;
    
    allItems.forEach(item => {
        if (!currentGroup || currentGroup.name !== item.source_name) {
            // Start a new group
            currentGroup = {
                name: item.source_name,
                icon: sourceInfo.get(item.source_name).icon,
                items: []
            };
            groupedItems.push(currentGroup);
        }
        currentGroup.items.push({
            title: item.title,
            link: item.link
        });
    });
    
    // Add all source groups to the infinite scroll container
    groupedItems.forEach(group => {
        const groupElement = createSourceGroupElement(group);
        container.appendChild(groupElement);
    });
    
    loadingIndicator.style.display = 'none';
    console.log('Finished loading infinite content');
}

function createSourceGroupElement(group) {
    const div = document.createElement('div');
    div.className = 'source-group';
    div.style.cssText = `
        margin: 20px 0;
        padding: 15px;
        border: 1px solid var(--btn-border);
        border-radius: 8px;
        background: var(--bg);
        max-width: 100%;
        box-sizing: border-box;
    `;
    
    const header = document.createElement('div');
    header.style.cssText = `
        display: flex;
        align-items: center;
        margin-bottom: 15px;
        padding-bottom: 10px;
        border-bottom: 1px solid var(--btn-border);
    `;
    
    const icon = document.createElement('img');
    icon.src = group.icon;
    icon.alt = group.name;
    icon.style.cssText = `
        width: 64px;
        height: 64px;
        margin-right: 16px;
        border-radius: 8px;
        object-fit: contain;
    `;
    
    const sourceName = document.createElement('h2');
    sourceName.textContent = group.name;
    sourceName.style.cssText = `
        margin: 0;
        font-size: 1.4em;
        color: var(--text);
    `;
    
    header.appendChild(icon);
    header.appendChild(sourceName);
    div.appendChild(header);
    
    // Add all items from this source
    group.items.forEach(item => {
        const itemElement = document.createElement('div');
        itemElement.style.cssText = `
            margin: 10px 0;
            padding: 12px;
            border-radius: 6px;
            background: var(--bg-secondary);
            transition: background-color 0.2s;
        `;
        
        itemElement.addEventListener('mouseover', () => {
            itemElement.style.background = 'var(--bg-hover)';
        });
        
        itemElement.addEventListener('mouseout', () => {
            itemElement.style.background = 'var(--bg-secondary)';
        });
        
        const title = document.createElement('a');
        title.href = item.link;
        title.target = '_blank';
        title.textContent = item.title;
        title.style.cssText = `
            color: var(--link);
            text-decoration: none;
            font-size: 1.1em;
            display: block;
            word-wrap: break-word;
            overflow-wrap: break-word;
            line-height: 1.4;
        `;
        
        itemElement.appendChild(title);
        div.appendChild(itemElement);
    });
    
    return div;
}

// Remove the intersection observer since we're showing all items at once
document.addEventListener('DOMContentLoaded', function() {
    const viewModeToggle = document.getElementById('view-mode-toggle');
    if (viewModeToggle) {
        viewModeToggle.addEventListener('click', toggleViewMode);
        
        // In debug mode, show a visual indicator that we're in debug mode
        if (document.body.classList.contains('desktop-view')) {
            viewModeToggle.style.border = '2px solid #ff0000';
            viewModeToggle.title = 'Debug Mode: Infinite Scroll';
        }
    }
});