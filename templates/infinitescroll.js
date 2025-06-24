// =============================================================================
// INFINITE SCROLL VIEW MODE
// =============================================================================

/**
 * Infinite scroll view mode manager.
 * Handles switching between column and infinite scroll views.
 */
class InfiniteScrollManager {
  constructor() {
    this.currentViewMode = 'column';
    this.currentPage = 0;
  }
  
  /**
   * Toggle between column and infinite scroll view modes.
   */
  toggleViewMode() {
    console.log('Toggling view mode from', this.currentViewMode);
    
    this.currentViewMode = this.currentViewMode === 'column' ? 'infinite' : 'column';
    const button = document.getElementById('view-mode-toggle');
    
    if (button) {
      button.textContent = this.currentViewMode === 'column' ? 'Infinite View' : 'Column View';
    }
    
    if (this.currentViewMode === 'infinite') {
      this.switchToInfiniteView();
    } else {
      this.switchToColumnView();
    }
    
    console.log('View mode toggled to', this.currentViewMode);
  }
  
  /**
   * Switch to infinite scroll view mode.
   */
  switchToInfiniteView() {
    console.log('Switching to infinite view');
    
    const container = document.getElementById('infinite-content');
    if (container) {
      container.innerHTML = '';
    }
    
    this.currentPage = 0;
    
    // Make all items visible before collecting them
    document.querySelectorAll('.linkclass').forEach(item => {
      item.style.display = 'block';
    });
    
    this.loadInfiniteContent();
    
    // Hide column view and show infinite container
    const rowElement = document.querySelector('.row');
    const infiniteContainer = document.getElementById('infinite-scroll-container');
    
    if (rowElement) rowElement.style.display = 'none';
    if (infiniteContainer) infiniteContainer.style.display = 'block';
  }
  
  /**
   * Switch to column view mode.
   */
  switchToColumnView() {
    console.log('Switching to column view');
    
    // Show column view and hide infinite container
    const rowElement = document.querySelector('.row');
    const infiniteContainer = document.getElementById('infinite-scroll-container');
    
    if (rowElement) rowElement.style.display = 'flex';
    if (infiniteContainer) infiniteContainer.style.display = 'none';
    
    // Restore pagination
    PaginationManager.init();
  }
  
  /**
   * Load content for infinite scroll view.
   */
  loadInfiniteContent() {
    const container = document.getElementById('infinite-content');
    const loadingIndicator = document.getElementById('loading-indicator');
    
    if (!container) return;
    
    console.log('Loading infinite content...');
    
    if (loadingIndicator) {
      loadingIndicator.style.display = 'block';
    }
    
    const allItems = this.collectAllItems();
    const groupedItems = this.groupItemsBySource(allItems);
    
    this.renderGroupedItems(container, groupedItems);
    
    if (loadingIndicator) {
      loadingIndicator.style.display = 'none';
    }
    
    console.log('Finished loading infinite content');
  }
  
  /**
   * Collect all items from all feed columns.
   * 
   * @returns {Array} Array of item objects
   */
  collectAllItems() {
    const allItems = [];
    const columns = document.querySelectorAll('.column');
    const foundSources = new Set();
    
    console.log('Found columns:', columns.length);
    
    columns.forEach((column, colIndex) => {
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
        
        const feedInfo = this.extractFeedInfo(feedId, feedIcon);
        const items = container.querySelectorAll('.linkclass');
        
        if (!foundSources.has(feedInfo.name)) {
          console.log(`Found new source: ${feedInfo.name} with ${items.length} items`);
          foundSources.add(feedInfo.name);
        }
        
        items.forEach((item, itemIndex) => {
          if (window.getComputedStyle(item).display !== 'none') {
            const timestamp = parseInt(item.getAttribute('data-index') || '0');
            
            allItems.push({
              title: item.textContent,
              link: item.href,
              source_name: feedInfo.name,
              source_icon: feedInfo.icon,
              timestamp: timestamp
            });
          }
        });
      });
    });
    
    console.log('Total items collected:', allItems.length);
    console.log('Sources found:', Array.from(foundSources));
    
    return allItems;
  }
  
  /**
   * Extract feed information from container.
   * 
   * @param {string} feedId - The feed container ID
   * @param {HTMLElement} feedIcon - The feed icon element
   * @returns {Object} Object containing feed name and icon
   */
  extractFeedInfo(feedId, feedIcon) {
    const feedUrl = feedId.replace('feed-', '');
    let feedName = '';
    
    try {
      const url = new URL(feedUrl);
      feedName = url.pathname.split('/').filter(Boolean).pop() || url.hostname;
      feedName = feedName
        .replace(/\.(com|org|net|io)$/, '')
        .replace(/-/g, ' ')
        .replace(/\b\w/g, l => l.toUpperCase());
    } catch (error) {
      feedName = feedId.replace('feed-', '');
    }
    
    return {
      name: feedName,
      icon: feedIcon.src
    };
  }
  
  /**
   * Group items by source while maintaining timestamp order.
   * 
   * @param {Array} allItems - Array of all items
   * @returns {Array} Array of grouped items
   */
  groupItemsBySource(allItems) {
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
    
    return groupedItems;
  }
  
  /**
   * Render grouped items in the infinite scroll container.
   * 
   * @param {HTMLElement} container - The container element
   * @param {Array} groupedItems - Array of grouped items
   */
  renderGroupedItems(container, groupedItems) {
    groupedItems.forEach(group => {
      const groupElement = this.createSourceGroupElement(group);
      container.appendChild(groupElement);
    });
  }
  
  /**
   * Create a source group element for infinite scroll view.
   * 
   * @param {Object} group - The group object containing name, icon, and items
   * @returns {HTMLElement} The created group element
   */
  createSourceGroupElement(group) {
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
      const itemElement = this.createItemElement(item);
      div.appendChild(itemElement);
    });
    
    return div;
  }
  
  /**
   * Create an individual item element for infinite scroll view.
   * 
   * @param {Object} item - The item object containing title and link
   * @returns {HTMLElement} The created item element
   */
  createItemElement(item) {
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
    return itemElement;
  }
}

// Expose InfiniteScrollManager globally for browser usage
if (typeof window !== 'undefined') {
  window.InfiniteScrollManager = InfiniteScrollManager;
}
