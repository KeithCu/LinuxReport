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
            this.init();
        }

        init() {
            this.initSettings();
            this.initDragDrop();
            this.initArchive();
        }

        initSettings() {
            const settingsConfig = {
                'theme-select': { cookie: 'Theme', default: app.config.DEFAULT_THEME },
                'font-select': { cookie: 'FontFamily', default: app.config.DEFAULT_FONT },
                'input[name="no_underlines"]': { cookie: 'NoUnderlines', type: 'checkbox', default: '1' }
            };

            for (const [selector, config] of Object.entries(settingsConfig)) {
                const element = document.querySelector(`.config-container ${selector}`);
                if (!element) continue;

                const cookieValue = app.utils.CookieManager.get(config.cookie);
                
                if (config.type === 'checkbox') {
                    element.checked = cookieValue === null || cookieValue === config.default;
                } else {
                    element.value = cookieValue || config.default;
                }
            }
        }

        initDragDrop() {
            app.utils.DragDropManager.init({
                containerSelector: '.url-list',
                itemSelector: '.url-entry',
                onDrop: () => this.updatePriorities()
            });
        }

        updatePriorities() {
            document.querySelectorAll('.url-entry').forEach((entry, index) => {
                const priorityInput = entry.querySelector('input[type="number"]');
                if (priorityInput) priorityInput.value = (index + 1) * app.config.PRIORITY_MULTIPLIER;
            });
        }

        initArchive() {
            const container = document.querySelector('.headline-archive-container');
            if (!container || !window.isAdmin) return;

            container.addEventListener('click', async (e) => {
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
            if (document.querySelector('.config-container')) {
                new ConfigManager();
            }
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        app.modules.config.init();
    });

})(window.app);