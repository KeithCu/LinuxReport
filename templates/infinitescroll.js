/**
 * infinitescroll.js - Refactored
 * 
 * Infinite scroll module for the LinuxReport application, integrated with the global app object.
 * Handles switching between column and infinite scroll views and dispatches view mode change events.
 * 
 * @author LinuxReport Team
 * @version 3.0.0
 */

(function(app) {
    'use strict';

    class InfiniteScrollManager {
        constructor() {
            this.currentViewMode = 'column';
            this.currentPage = 0;
            this.rowElement = document.querySelector('.row');
            this.infiniteContainer = document.getElementById('infinite-scroll-container');
            this.infiniteContent = document.getElementById('infinite-content');
            this.loadingIndicator = document.getElementById('loading-indicator');
        }

        toggleViewMode() {
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

            document.dispatchEvent(new CustomEvent('viewmodechange', { detail: { mode: this.currentViewMode } }));
        }

        switchToInfiniteView() {
            if (this.infiniteContent) this.infiniteContent.innerHTML = '';
            this.currentPage = 0;

            document.querySelectorAll('.linkclass').forEach(item => {
                item.style.display = 'block';
            });

            this.loadInfiniteContent();

            if (this.rowElement) this.rowElement.style.display = 'none';
            if (this.infiniteContainer) this.infiniteContainer.style.display = 'block';
        }

        switchToColumnView() {
            if (this.rowElement) this.rowElement.style.display = 'flex';
            if (this.infiniteContainer) this.infiniteContainer.style.display = 'none';
        }

        loadInfiniteContent() {
            if (!this.infiniteContent) return;
            if (this.loadingIndicator) this.loadingIndicator.style.display = 'block';

            const allItems = this.collectAllItems();
            const groupedItems = this.groupItemsBySource(allItems);
            this.renderGroupedItems(this.infiniteContent, groupedItems);

            if (this.loadingIndicator) this.loadingIndicator.style.display = 'none';
        }

        collectAllItems() {
            const allItems = [];
            const columns = document.querySelectorAll('.column');
            columns.forEach(column => {
                const feedContainers = column.querySelectorAll('.box');
                feedContainers.forEach(container => {
                    const feedId = container.id;
                    const feedTitle = container.querySelector('a[target="_blank"]');
                    const feedIcon = container.querySelector('img');
                    if (!feedTitle || !feedIcon) return;

                    const feedInfo = this.extractFeedInfo(feedId, feedIcon);
                    const items = container.querySelectorAll('.linkclass');
                    items.forEach(item => {
                        if (window.getComputedStyle(item).display !== 'none') {
                            const timestamp = parseInt(item.getAttribute('data-index') || '0');
                            const published = item.getAttribute('data-published') || '';
                            allItems.push({
                                title: item.textContent,
                                link: item.href,
                                source_name: feedInfo.name,
                                source_icon: feedInfo.icon,
                                timestamp: timestamp,
                                published: published
                            });
                        }
                    });
                });
            });
            return allItems;
        }

        extractFeedInfo(feedId, feedIcon) {
            const feedUrl = feedId.replace('feed-', '');
            let feedName = '';
            try {
                const url = new URL(feedUrl);
                feedName = url.pathname.split('/').filter(Boolean).pop() || url.hostname;
                feedName = feedName.replace(/\.(com|org|net|io)$/, '').replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            } catch (error) {
                feedName = feedId.replace('feed-', '');
            }
            return { name: feedName, icon: feedIcon.src };
        }

        groupItemsBySource(allItems) {
            allItems.sort((a, b) => b.timestamp - a.timestamp);
            const sourceInfo = new Map();
            allItems.forEach(item => {
                if (!sourceInfo.has(item.source_name)) {
                    sourceInfo.set(item.source_name, { name: item.source_name, icon: item.source_icon });
                }
            });

            const groupedItems = [];
            let currentGroup = null;
            allItems.forEach(item => {
                if (!currentGroup || currentGroup.name !== item.source_name) {
                    currentGroup = { name: item.source_name, icon: sourceInfo.get(item.source_name).icon, items: [] };
                    groupedItems.push(currentGroup);
                }
                currentGroup.items.push({ 
                    title: item.title, 
                    link: item.link, 
                    published: item.published,
                    timestamp: item.timestamp
                });
            });
            return groupedItems;
        }

        renderGroupedItems(container, groupedItems) {
            groupedItems.forEach(group => {
                const groupElement = this.createSourceGroupElement(group);
                container.appendChild(groupElement);
            });
        }

        createSourceGroupElement(group) {
            const div = document.createElement('div');
            div.className = 'source-group';
            div.innerHTML = `
                <div style="display: flex; align-items: center; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid var(--btn-border);">
                    <img src="${group.icon}" alt="${group.name}" style="width: 64px; height: 64px; margin-right: 16px; border-radius: 8px; object-fit: contain;">
                    <h2 style="margin: 0; font-size: 1.4em; color: var(--text);">${group.name}</h2>
                </div>
            `;
            group.items.forEach(item => {
                div.appendChild(this.createItemElement(item));
            });
            return div;
        }

        createItemElement(item) {
            const itemElement = document.createElement('div');
            itemElement.style.margin = '10px 0';
            itemElement.style.padding = '8px 0';
            itemElement.style.borderBottom = '1px solid var(--btn-border)';
            
            const titleElement = document.createElement('div');
            titleElement.innerHTML = `<a href="${item.link}" target="_blank" style="color: var(--link); text-decoration: none; font-size: 1.1em;">${item.title}</a>`;
            
            // Commented out published date display - uncomment to show timestamps
            /*
            const timeElement = document.createElement('div');
            timeElement.style.fontSize = '0.8em';
            timeElement.style.color = 'var(--text-secondary)';
            timeElement.style.marginTop = '4px';
            
            if (item.published) {
                // Try to parse and format the published time
                try {
                    const date = new Date(item.published);
                    if (!isNaN(date.getTime())) {
                        timeElement.textContent = `Published: ${date.toLocaleString()}`;
                    } else {
                        timeElement.textContent = `Published: ${item.published}`;
                    }
                } catch (e) {
                    timeElement.textContent = `Published: ${item.published}`;
                }
            } else {
                timeElement.textContent = `Timestamp: ${item.timestamp}`;
            }
            
            itemElement.appendChild(timeElement);
            */
            
            itemElement.appendChild(titleElement);
            return itemElement;
        }
    }

    app.modules.infiniteScroll = {
        create() {
            return new InfiniteScrollManager();
        }
    };

})(window.app);
