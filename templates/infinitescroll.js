/**
 * infinitescroll.js
 * 
 * Infinite scroll module for the LinuxReport application, integrated with the global app object.
 * Handles switching between column and infinite scroll views and dispatches view mode change events.
 * 
 * @author LinuxReport Team
 * @version 3.1.0
 */

(function(app) {
    'use strict';

    class InfiniteScrollManager {
        constructor() {
            this.currentViewMode = 'column';
            this.currentPage = 0;
            this.elements = {
                row: document.querySelector('.row'),
                infiniteContainer: document.getElementById('infinite-scroll-container'),
                infiniteContent: document.getElementById('infinite-content'),
                loadingIndicator: document.getElementById('loading-indicator')
            };
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

            document.dispatchEvent(new CustomEvent('viewmodechange', { 
                detail: { mode: this.currentViewMode } 
            }));
        }

        switchToInfiniteView() {
            if (this.elements.infiniteContent) this.elements.infiniteContent.innerHTML = '';
            this.currentPage = 0;

            document.querySelectorAll('.linkclass').forEach(item => {
                item.style.display = 'block';
            });

            this.loadInfiniteContent();

            if (this.elements.row) {
                this.elements.row.classList.remove('show-flex');
                this.elements.row.classList.add('hide');
            }
            if (this.elements.infiniteContainer) {
                this.elements.infiniteContainer.classList.remove('hide');
                this.elements.infiniteContainer.classList.add('show');
            }
        }

        switchToColumnView() {
            if (this.elements.row) {
                this.elements.row.classList.remove('hide');
                this.elements.row.classList.add('show-flex');
            }
            if (this.elements.infiniteContainer) {
                this.elements.infiniteContainer.classList.remove('show');
                this.elements.infiniteContainer.classList.add('hide');
            }
        }

        loadInfiniteContent() {
            if (!this.elements.infiniteContent) return;
            
            if (this.elements.loadingIndicator) this.elements.loadingIndicator.style.display = 'block';

            const allItems = this.collectAllItems();
            const groupedItems = this.groupItemsBySource(allItems);
            this.renderGroupedItems(this.elements.infiniteContent, groupedItems);

            if (this.elements.loadingIndicator) this.elements.loadingIndicator.style.display = 'none';
        }

        collectAllItems() {
            return Array.from(document.querySelectorAll('.column .box')).flatMap(container => {
                const feedId = container.id;
                const feedIcon = container.querySelector('img');
                if (!feedIcon) return [];

                const feedInfo = this.extractFeedInfo(feedId, feedIcon);
                
                return Array.from(container.querySelectorAll('.linkclass')).map(item => {
                    const linkElement = item.querySelector('a[target="_blank"]');
                    if (!linkElement) return null;

                    return {
                        title: linkElement.textContent.trim(),
                        link: linkElement.href,
                        source_name: feedInfo.name,
                        source_icon: feedInfo.icon,
                        timestamp: parseInt(item.dataset.index || '0', 10),
                        published: item.dataset.published || ''
                    };
                }).filter(Boolean);
            });
        }

        extractFeedInfo(feedId, feedIcon) {
            const feedUrl = feedId.replace(/^feed-/, '');
            let feedName;
            
            try {
                const url = new URL(feedUrl);
                const pathParts = url.pathname.split('/').filter(Boolean);
                const baseName = pathParts.pop() || url.hostname;
                feedName = baseName.replace(/\.(com|org|net|io)$/, '').replace(/[\-_]/g, ' ');
                feedName = feedName.replace(/\b\w/g, l => l.toUpperCase());
            } catch (error) {
                feedName = feedId.replace(/^feed-/, '').replace(/[\-_]/g, ' ');
            }

            return { name: feedName, icon: feedIcon.src };
        }

        groupItemsBySource(allItems) {
            allItems.sort((a, b) => b.timestamp - a.timestamp);

            const groupedMap = allItems.reduce((acc, item) => {
                let group = acc.get(item.source_name);
                if (!group) {
                    group = {
                        name: item.source_name,
                        icon: item.source_icon,
                        items: []
                    };
                    acc.set(item.source_name, group);
                }
                group.items.push(item);
                return acc;
            }, new Map());
            
            return Array.from(groupedMap.values());
        }

        renderGroupedItems(container, groupedItems) {
            const fragment = document.createDocumentFragment();
            groupedItems.forEach(group => {
                fragment.appendChild(this.createSourceGroupElement(group));
            });
            container.appendChild(fragment);
        }

        createSourceGroupElement(group) {
            const groupEl = document.createElement('div');
            groupEl.className = 'source-group';
            
            groupEl.innerHTML = `
                <div class="source-header">
                    <img src="${group.icon}" alt="${group.name}" class="source-icon">
                    <h3 class="source-name">${group.name}</h3>
                </div>
                ${group.items.map(item => this.createItemHTML(item)).join('')}
            `;
            return groupEl;
        }

        createItemHTML(item) {
            let timeString = `Timestamp: ${item.timestamp}`;
            if (item.published) {
                try {
                    const date = new Date(item.published);
                    timeString = `Published: ${isNaN(date.getTime()) ? item.published : date.toLocaleString()}`;
                } catch (e) {
                    timeString = `Published: ${item.published}`;
                }
            }
            
            return `
                <div class="infinite-item">
                    <div class="item-title">
                        <a href="${item.link}" target="_blank">${item.title}</a>
                    </div>
                    <div class="item-time">
                        ${timeString}
                    </div>
                </div>
            `;
        }
    }

    app.modules.infiniteScroll = {
        create() {
            return new InfiniteScrollManager();
        }
    };

})(window.app);
