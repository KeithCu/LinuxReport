/**
 * config.js - Refactored
 * 
 * Configuration page module for the LinuxReport application, integrated with the global app object.
 * Handles theme/font settings, drag-and-drop URL reordering, and archive management.
 * 
 * @author LinuxReport Team
 * @version 3.0.0
 */

(function(app) {
    'use strict';

    class SettingsManager {
        static init() {
            this.initTheme();
            this.initFont();
            this.initUnderlines();
        }

        static initTheme() {
            const theme = app.utils.CookieManager.get('Theme') || app.config.DEFAULT_THEME;
            const select = document.querySelector('.config-container #theme-select');
            if (select) select.value = theme;
        }

        static initFont() {
            const font = app.utils.CookieManager.get('FontFamily') || app.config.DEFAULT_FONT;
            const select = document.querySelector('.config-container #font-select');
            if (select) select.value = font;
        }

        static initUnderlines() {
            const noUnderlines = app.utils.CookieManager.get('NoUnderlines');
            const checkbox = document.querySelector('.config-container input[name="no_underlines"]');
            if (checkbox) checkbox.checked = !noUnderlines || noUnderlines === '1';
        }
    }

    class DragDropManager {
        constructor() {
            this.draggedItem = null;
            this.init();
        }

        init() {
            document.querySelectorAll('.url-entry').forEach(entry => {
                entry.addEventListener('dragstart', e => this.handleDragStart(e, entry));
                entry.addEventListener('dragend', e => this.handleDragEnd(e, entry));
                entry.addEventListener('dragover', e => this.handleDragOver(e, entry));
                entry.addEventListener('drop', e => this.handleDrop(e, entry));
            });
        }

        handleDragStart(e, entry) {
            this.draggedItem = entry;
            entry.style.opacity = app.config.DRAG_OPACITY;
        }

        handleDragEnd(e, entry) {
            entry.style.opacity = app.config.DRAG_OPACITY_NORMAL;
            this.draggedItem = null;
        }

        handleDragOver(e, entry) {
            e.preventDefault();
            const container = entry.parentNode;
            const afterElement = this.getDragAfterElement(container, e.clientY);
            if (afterElement == null) {
                container.appendChild(this.draggedItem);
            } else {
                container.insertBefore(this.draggedItem, afterElement);
            }
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
                if (offset < 0 && offset > closest.offset) {
                    return { offset: offset, element: child };
                } else {
                    return closest;
                }
            }, { offset: Number.NEGATIVE_INFINITY }).element;
        }

        updatePriorities() {
            document.querySelectorAll('.url-entry').forEach((entry, index) => {
                const priorityInput = entry.querySelector('input[type="number"]');
                if (priorityInput) priorityInput.value = (index + 1) * app.config.PRIORITY_MULTIPLIER;
            });
        }
    }

    class ArchiveManager {
        constructor() {
            this.container = document.querySelector('.headline-archive-container');
            this.isAdmin = window.isAdmin || false;
            if (this.container && this.isAdmin) this.init();
        }

        init() {
            this.container.addEventListener('click', e => this.handleDelete(e));
        }

        async handleDelete(e) {
            if (!e.target.classList.contains('delete-headline-btn')) return;
            const entry = e.target.closest('.headline-entry');
            if (!entry) return;

            const { url, timestamp } = entry.dataset;
            if (!url || !timestamp || !confirm('Delete this headline?')) return;

            try {
                const response = await fetch(app.config.DELETE_HEADLINE_ENDPOINT, {
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
                alert(`Delete failed: ${error.message}`);
            }
        }
    }

    app.modules.config = {
        init() {
            if (!document.querySelector('.config-container')) return;
            SettingsManager.init();
            new DragDropManager();
            new ArchiveManager();
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        app.modules.config.init();
    });

})(window.app);