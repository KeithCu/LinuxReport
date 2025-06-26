/**
 * core.js - Refactored
 * 
 * Core module for the LinuxReport application, integrated with the global app object.
 * Handles auto-refresh, pagination, and view mode management.
 * 
 * @author LinuxReport Team
 * @version 3.0.0
 */

(function(app) {
    'use strict';

    // =============================================================================
    // MODULE-SPECIFIC STATE
    // =============================================================================
    let autoRefreshManager;
    let infiniteScrollManager;

    // =============================================================================
    // AUTO-REFRESH MANAGEMENT
    // =============================================================================

    class AutoRefreshManager {
        constructor() {
            this.interval = app.config.AUTO_REFRESH_INTERVAL;
            this.activityTimeout = app.config.ACTIVITY_TIMEOUT;
            this.lastActivity = Date.now();
            this.timer = null;
        }

        init() {
            this.setupActivityTracking();
            this.start();
        }

        setupActivityTracking() {
            const activityEvents = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
            activityEvents.forEach(event => {
                document.addEventListener(event, () => {
                    this.lastActivity = Date.now();
                }, { passive: true });
            });
            window.addEventListener('online', () => this.start());
            window.addEventListener('offline', () => this.stop());
        }

        start() {
            if (this.timer) this.stop();
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
            const inactiveTime = Date.now() - this.lastActivity;
            if (inactiveTime < this.activityTimeout) return;
            const hasUnsavedChanges = document.querySelectorAll('form:invalid').length > 0;
            const hasOpenDialogs = document.querySelectorAll('dialog[open]').length > 0;
            if (!hasUnsavedChanges && !hasOpenDialogs) {
                app.utils.ScrollManager.savePosition();
                self.location.reload();
            }
        }
    }

    // =============================================================================
    // PAGINATION MANAGEMENT
    // =============================================================================

    class PaginationManager {
        static init() {
            document.querySelectorAll('.pagination-controls').forEach(feedControls => {
                new PaginationManager(feedControls);
            });
        }

        constructor(feedControls) {
            this.feedControls = feedControls;
            this.feedId = feedControls.dataset.feedId;
            this.feedContainer = document.getElementById(this.feedId);
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

    // =============================================================================
    // CORE MODULE DEFINITION
    // =============================================================================

    app.modules.core = {
        init() {
            app.utils.ThemeManager.applySettings();
            app.utils.ScrollManager.restorePosition();
            
            this.reinitPagination();

            autoRefreshManager = new AutoRefreshManager();
            autoRefreshManager.init();

            if (document.getElementById('infinite-scroll-container')) {
                infiniteScrollManager = app.modules.infiniteScroll.create();
            }

            const themeSelect = document.getElementById('theme-select');
            if (themeSelect) {
                themeSelect.addEventListener('change', (e) => app.setTheme(e.target.value));
            }

            const fontSelect = document.getElementById('font-select');
            if (fontSelect) {
                fontSelect.addEventListener('change', (e) => app.setFont(e.target.value));
            }

            const configBtn = document.getElementById('config-btn');
            if (configBtn) {
                configBtn.addEventListener('click', () => app.redirect());
            }

            const viewModeToggle = document.getElementById('view-mode-toggle');
            if (viewModeToggle) {
                viewModeToggle.addEventListener('click', () => this.toggleViewMode());
            }
            
            document.addEventListener('viewmodechange', (e) => {
                this.reinitPagination();
            });
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

    // =============================================================================
    // GLOBAL HELPER FUNCTIONS
    // =============================================================================

    app.redirect = function() {
        app.utils.ScrollManager.savePosition();
        window.location = "/config";
    };

    app.setTheme = function(theme) {
        app.utils.ThemeManager.setTheme(theme);
    };

    app.setFont = function(font) {
        app.utils.ThemeManager.setFont(font);
    };
    
    app.toggleViewMode = function() {
        app.modules.core.toggleViewMode();
    };

    // =============================================================================
    // INITIALIZATION
    // =============================================================================

    document.addEventListener('DOMContentLoaded', () => {
        app.modules.core.init();
    });

})(window.app);