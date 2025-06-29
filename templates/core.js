/**
 * core.js
 * 
 * Core module for the LinuxReport application, integrated with the global app object.
 * Handles auto-refresh, pagination, and view mode management.
 * 
 * @author LinuxReport Team
 * @version 3.1.0
 */

(function(app) {
    'use strict';

    let autoRefreshManager;
    let infiniteScrollManager;

    class AutoRefreshManager {
        constructor() {
            this.interval = app.config.AUTO_REFRESH_INTERVAL;
            this.activityTimeout = app.config.ACTIVITY_TIMEOUT;
            this.lastActivity = Date.now();
            this.timer = null;
            this.init();
        }

        init() {
            ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach(event => {
                document.addEventListener(event, () => this.lastActivity = Date.now(), { passive: true });
            });
            window.addEventListener('online', () => this.start());
            window.addEventListener('offline', () => this.stop());
            this.start();
        }

        start() {
            this.stop();
            this.timer = setInterval(() => this.check(), this.interval);
        }

        stop() {
            if (this.timer) {
                clearInterval(this.timer);
                this.timer = null;
            }
        }

        check() {
            if (!navigator.onLine) return;
            if (Date.now() - this.lastActivity < this.activityTimeout) return;
            
            const hasUnsavedChanges = document.querySelectorAll('form:invalid').length > 0;
            const hasOpenDialogs = document.querySelectorAll('dialog[open]').length > 0;
            
            if (!hasUnsavedChanges && !hasOpenDialogs) {
                app.utils.ScrollManager.savePosition();
                self.location.reload();
            }
        }
    }

    class PaginationManager {
        static init() {
            document.querySelectorAll('.pagination-controls').forEach(feedControls => {
                new PaginationManager(feedControls);
            });
        }

        constructor(feedControls) {
            this.feedControls = feedControls;
            this.feedContainer = document.getElementById(feedControls.dataset.feedId);
            if (!this.feedContainer) return;

            this.items = Array.from(this.feedContainer.querySelectorAll('.linkclass'));
            this.prevBtn = feedControls.querySelector('.prev-btn');
            this.nextBtn = feedControls.querySelector('.next-btn');
            this.currentPage = 0;
            this.totalPages = Math.ceil(this.items.length / app.config.ITEMS_PER_PAGE);

            this.setupEventListeners();
            this.update();
        }

        setupEventListeners() {
            if (this.prevBtn) this.prevBtn.addEventListener('click', () => this.previousPage());
            if (this.nextBtn) this.nextBtn.addEventListener('click', () => this.nextPage());
        }

        previousPage() {
            if (this.currentPage > 0) {
                this.currentPage--;
                this.update();
            }
        }

        nextPage() {
            if (this.currentPage < this.totalPages - 1) {
                this.currentPage++;
                this.update();
            }
        }

        update() {
            requestAnimationFrame(() => {
                const startIdx = this.currentPage * app.config.ITEMS_PER_PAGE;
                const endIdx = startIdx + app.config.ITEMS_PER_PAGE;
                
                this.items.forEach((item, i) => {
                    item.style.display = (i >= startIdx && i < endIdx) ? 'block' : 'none';
                });

                if (this.prevBtn) this.prevBtn.disabled = this.currentPage === 0;
                if (this.nextBtn) this.nextBtn.disabled = this.currentPage >= this.totalPages - 1;
            });
        }
    }

    app.modules.core = {
        init() {
            app.utils.ThemeManager.applySettings();
            app.utils.ScrollManager.restorePosition();
            
            this.reinitPagination();

            autoRefreshManager = new AutoRefreshManager();

            if (document.getElementById('infinite-scroll-container')) {
                infiniteScrollManager = app.modules.infiniteScroll.create();
            }

            this.setupEventListeners();
        },

        setupEventListeners() {
            const eventMap = {
                'theme-select': (e) => app.setTheme(e.target.value),
                'font-select': (e) => app.setFont(e.target.value),
                'config-btn': () => app.redirect(),
                'view-mode-toggle': () => this.toggleViewMode()
            };

            Object.entries(eventMap).forEach(([id, handler]) => {
                const element = document.getElementById(id);
                if (element) {
                    element.addEventListener(id.includes('select') ? 'change' : 'click', handler);
                }
            });

            document.addEventListener('viewmodechange', () => this.reinitPagination());
        },

        toggleViewMode() {
            if (infiniteScrollManager) {
                infiniteScrollManager.toggleViewMode();
            }
        },
        
        reinitPagination() {
            PaginationManager.init();
        }
    };

    // Global helper functions
    app.redirect = () => {
        app.utils.ScrollManager.savePosition();
        window.location = "/config";
    };

    app.setTheme = (theme) => app.utils.ThemeManager.setTheme(theme);
    app.setFont = (font) => app.utils.ThemeManager.setFont(font);
    app.toggleViewMode = () => app.modules.core.toggleViewMode();

    document.addEventListener('DOMContentLoaded', () => {
        app.modules.core.init();
    });

})(window.app);