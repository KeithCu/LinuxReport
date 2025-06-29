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
            const settings = {
                'theme-select': 'Theme',
                'font-select': 'FontFamily',
                'input[name="no_underlines"]': 'NoUnderlines'
            };

            Object.entries(settings).forEach(([selector, cookieName]) => {
                const element = document.querySelector(`.config-container ${selector}`);
                if (!element) return;

                if (element.type === 'checkbox') {
                    const value = app.utils.CookieManager.get(cookieName);
                    element.checked = !value || value === '1';
                } else {
                    const defaultValue = cookieName === 'Theme' ? app.config.DEFAULT_THEME : 
                                       cookieName === 'FontFamily' ? app.config.DEFAULT_FONT : '';
                    element.value = app.utils.CookieManager.get(cookieName) || defaultValue;
                }
            });
        }

        initDragDrop() {
            document.querySelectorAll('.url-entry').forEach(entry => {
                ['dragstart', 'dragend', 'dragover', 'drop'].forEach(event => {
                    entry.addEventListener(event, e => this[`handle${event.charAt(0).toUpperCase() + event.slice(1)}`](e, entry));
                });
            });
        }

        handleDragstart(e, entry) {
            this.draggedItem = entry;
            entry.style.opacity = app.config.DRAG_OPACITY;
        }

        handleDragend(e, entry) {
            entry.style.opacity = app.config.DRAG_OPACITY_NORMAL;
            this.draggedItem = null;
        }

        handleDragover(e, entry) {
            e.preventDefault();
            const container = entry.parentNode;
            const afterElement = this.getDragAfterElement(container, e.clientY);
            container.insertBefore(this.draggedItem, afterElement);
        }

        handleDrop(e, entry) {
            e.preventDefault();
            this.updatePriorities();
        }

        getDragAfterElement(container, y) {
            const draggableElements = [...container.querySelectorAll('.url-entry:not(.dragging)')];
            return draggableElements.reduce((closest, child) => {
                const box = child.getBoundingClientRect();
                const offset = y - box.top - box.height / 2;
                return offset < 0 && offset > closest.offset ? { offset, element: child } : closest;
            }, { offset: Number.NEGATIVE_INFINITY }).element;
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

            container.addEventListener('click', async e => {
                if (!e.target.classList.contains('delete-headline-btn')) return;
                
                const entry = e.target.closest('.headline-entry');
                if (!entry?.dataset?.url || !entry.dataset.timestamp || !confirm('Delete this headline?')) return;

                try {
                    const response = await fetch(app.config.DELETE_HEADLINE_ENDPOINT, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            url: entry.dataset.url, 
                            timestamp: entry.dataset.timestamp 
                        })
                    });
                    
                    const data = await response.json();
                    if (data.success) {
                        entry.remove();
                    } else {
                        throw new Error(data.error || 'Unknown error');
                    }
                } catch (error) {
                    alert(`Delete failed: ${error.message}`);
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