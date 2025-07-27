/**
 * config.js
 * 
 * Configuration page module for the LinuxReport application, integrated with the global app object.
 * Handles theme/font settings, drag-and-drop URL reordering, and archive management.
 * 
 * @author LinuxReport Team
 * @version 3.1.0
 */

(function(app) {
    'use strict';

    class ConfigManager {
        constructor() {
            this.draggedItem = null;
            this.elements = null;
            this.init();
        }

        getElements() {
            if (!this.elements) {
                this.elements = {
                    themeSelect: document.querySelector('.config-container #theme-select'),
                    fontSelect: document.querySelector('.config-container #font-select'),
                    noUnderlinesInput: document.querySelector('.config-container input[name="no_underlines"]'),
                    urlEntries: document.querySelectorAll('.url-entry'),
                    headlineArchiveContainer: document.querySelector('.headline-archive-container'),
                    configContainer: document.querySelector('.config-container')
                };
            }
            return this.elements;
        }

        init() {
            this.initSettings();
            this.initDragDrop();
            this.initArchive();
        }

        initSettings() {
            const { themeSelect, fontSelect, noUnderlinesInput } = this.getElements();
            
            const settingsConfig = [
                { element: themeSelect, cookie: 'Theme', default: app.config.DEFAULT_THEME },
                { element: fontSelect, cookie: 'FontFamily', default: app.config.DEFAULT_FONT },
                { element: noUnderlinesInput, cookie: 'NoUnderlines', type: 'checkbox', default: '1' }
            ];

            settingsConfig.forEach(({ element, cookie, type, default: defaultValue }) => {
                if (!element) return;

                const cookieValue = app.utils.CookieManager.get(cookie);
                
                if (type === 'checkbox') {
                    element.checked = cookieValue === null || cookieValue === defaultValue;
                } else {
                    element.value = cookieValue || defaultValue;
                }
            });
        }

        initDragDrop() {
            app.utils.DragDropManager.init({
                containerSelector: '.url-list',
                itemSelector: '.url-entry',
                onDrop: () => this.updatePriorities()
            });
        }

        updatePriorities() {
            const { urlEntries } = this.getElements();
            urlEntries.forEach((entry, index) => {
                const priorityInput = entry.querySelector('input[type="number"]');
                if (priorityInput) priorityInput.value = (index + 1) * app.config.PRIORITY_MULTIPLIER;
            });
        }

        initArchive() {
            const { headlineArchiveContainer } = this.getElements();
            if (!headlineArchiveContainer || !window.isAdmin) return;

            headlineArchiveContainer.addEventListener('click', async (e) => {
                const deleteBtn = e.target.closest('.delete-headline-btn');
                if (!deleteBtn) return;

                const entry = deleteBtn.closest('.headline-entry');
                const { url, timestamp } = entry.dataset;

                if (!url || !timestamp || !confirm(`Delete headline: ${url}?`)) return;

                try {
                    const response = await fetch(app.config.DELETE_HEADLINE_ENDPOINT, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': window.csrf_token },
                        body: JSON.stringify({ url, timestamp })
                    });

                    if (!response.ok) {
                        const errorData = await response.json().catch(() => ({ error: 'Invalid JSON response' }));
                        throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
                    }

                    const data = await response.json();
                    if (data.success) {
                        entry.remove();
                    } else {
                        throw new Error(data.error || 'Unknown deletion error');
                    }
                } catch (error) {
                    alert(`Delete failed: ${error.message}`);
                    app.utils.handleError('Delete Headline', error);
                }
            });
        }
    }

    app.modules.config = {
        init() {
            const configContainer = document.querySelector('.config-container');
            if (configContainer) {
                new ConfigManager();
            }
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        app.modules.config.init();
    });

})(window.app);