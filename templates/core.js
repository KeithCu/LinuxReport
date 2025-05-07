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
          item.style.display = (i >= startIdx && i < endIdx) ? 'block' : 'none';
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