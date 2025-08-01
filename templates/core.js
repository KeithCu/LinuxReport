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

    let autoRefreshManager = null;
    let infiniteScrollManager = null;

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
            const isInactive = Date.now() - this.lastActivity >= this.activityTimeout;
            const hasUnsavedChanges = document.querySelector('form:invalid');
            const hasOpenDialogs = document.querySelector('dialog[open]');
            
            if (navigator.onLine && isInactive && !hasUnsavedChanges && !hasOpenDialogs) {
                app.utils.ScrollManager.savePosition();
                self.location.reload();
            }
        }
    }

    class PaginationManager {
        static init() {
            const paginationControls = document.querySelectorAll('.pagination-controls');
            
            paginationControls.forEach(feedControls => {
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
            if (this.prevBtn) {
                this.prevBtn.addEventListener('click', () => this.previousPage());
            }
            if (this.nextBtn) {
                this.nextBtn.addEventListener('click', () => this.nextPage());
            }
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
            const startIdx = this.currentPage * app.config.ITEMS_PER_PAGE;
            const endIdx = startIdx + app.config.ITEMS_PER_PAGE;

            this.items.forEach((item, i) => {
                const isVisible = i >= startIdx && i < endIdx;
                if (isVisible) {
                    item.classList.remove('hide');
                    item.classList.add('show');
                } else {
                    item.classList.remove('show');
                    item.classList.add('hide');
                }
            });

            const isFirstPage = this.currentPage === 0;
            const isLastPage = this.currentPage >= this.totalPages - 1;
            
            if (this.prevBtn) this.prevBtn.disabled = isFirstPage;
            if (this.nextBtn) this.nextBtn.disabled = isLastPage;
        }
    }

    app.modules.core = {
        // Cache frequently accessed DOM elements
        elements: null,
        
        getElements() {
            if (!this.elements) {
                this.elements = {
                    themeSelect: document.getElementById('theme-select'),
                    fontSelect: document.getElementById('font-select'),
                    configBtn: document.getElementById('config-btn'),
                    viewModeToggle: document.getElementById('view-mode-toggle'),
                    infiniteScrollContainer: document.getElementById('infinite-scroll-container')
                };
            }
            return this.elements;
        },
        
        init() {
            app.utils.UIManager.applySettings();
            app.utils.ScrollManager.restorePosition();
            
            this.reinitPagination();

            autoRefreshManager = new AutoRefreshManager();

            const { infiniteScrollContainer } = this.getElements();
            if (infiniteScrollContainer) {
                infiniteScrollManager = app.modules.infiniteScroll.create();
            }

            // Initialize timezone conversion for last-updated times
            app.utils.TimezoneManager.init();

            this.setupEventListeners();
        },

        setupEventListeners() {
            const { themeSelect, fontSelect, configBtn, viewModeToggle } = this.getElements();
            
            const handlers = [
                { element: themeSelect, event: 'change', handler: (e) => app.setTheme(e.target.value) },
                { element: fontSelect, event: 'change', handler: (e) => app.setFont(e.target.value) },
                { element: configBtn, event: 'click', handler: () => app.redirect() },
                { element: viewModeToggle, event: 'click', handler: () => this.toggleViewMode() }
            ];

            handlers.forEach(({ element, event, handler }) => {
                if (element) {
                    element.addEventListener(event, handler);
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
        window.location = "/config";
    };

    app.setTheme = (theme) => app.utils.UIManager.setTheme(theme);
    app.setFont = (font) => app.utils.UIManager.setFont(font);
    app.toggleViewMode = () => app.modules.core.toggleViewMode();

    document.addEventListener('DOMContentLoaded', () => {
        app.modules.core.init();
    });

})(window.app);