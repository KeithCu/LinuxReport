/**
 * accessibility.js
 *
 * Accessibility module for the LinuxReport application.
 * Handles keyboard navigation, focus management, and screen reader support.
 *
 * @author LinuxReport Team
 * @version 1.1.0
 */

(function(app) {
    'use strict';

    class AccessibilityManager {
        constructor() {
            this.currentFocusIndex = 0;
            this.focusableElements = [];
            this.isNavigating = false;
            this.skipLink = null;
            this.observer = null;
            this.announcementElement = null;

            // Debounce expensive operations
            this.debouncedUpdateFocusableElements = app.utils.debounce(() => this.updateFocusableElements(), 150);
            this.debouncedUpdateAriaAttributes = app.utils.debounce(() => this.updateAriaAttributes(), 150);

            try {
                this.init();
            } catch (error) {
                app.utils.logger.error('[Accessibility] Initialization failed:', error);
            }
        }

        init() {
            this.setupReducedMotion();
            this.setupSkipLink();
            this.setupKeyboardNavigation();
            this.setupAnnouncementElement();
            this.setupObservers();
            this.updateFocusableElements();
            this.updateAriaAttributes();
        }

        setupReducedMotion() {
            if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
                document.documentElement.classList.add('reduced-motion');
            }
        }

        setupSkipLink() {
            this.skipLink = document.querySelector('.skip-link');
            if (this.skipLink) {
                this.skipLink.addEventListener('click', (e) => {
                    e.preventDefault();
                    const targetId = this.skipLink.getAttribute('href').substring(1);
                    const target = document.getElementById(targetId);
                    if (target) {
                        target.setAttribute('tabindex', '-1');
                        target.focus();
                        target.scrollIntoView({ behavior: 'smooth' });
                        target.addEventListener('blur', () => target.removeAttribute('tabindex'), { once: true });
                    }
                });
            }
        }

        setupKeyboardNavigation() {
            document.addEventListener('keydown', (e) => {
                if (this.isFormElement(e.target)) return;

                const keyMap = {
                    'ArrowUp': () => this.navigateArticles(-1),
                    'ArrowDown': () => this.navigateArticles(1),
                    'Home': () => this.navigateToFirst(),
                    'End': () => this.navigateToLast(),
                    'Escape': () => this.handleEscapeKey(),
                };

                if (keyMap[e.key]) {
                    e.preventDefault();
                    keyMap[e.key]();
                }
            });
        }

        setupAnnouncementElement() {
            this.announcementElement = document.createElement('div');
            this.announcementElement.id = 'sr-announcement';
            this.announcementElement.setAttribute('aria-live', 'polite');
            this.announcementElement.setAttribute('aria-atomic', 'true');
            this.announcementElement.className = 'sr-only';
            document.body.appendChild(this.announcementElement);
        }

        setupObservers() {
            this.observer = new MutationObserver((mutations) => {
                let updateFocus = false;
                let updateAria = false;

                for (const mutation of mutations) {
                    if (mutation.type === 'childList') {
                        updateFocus = true;
                        updateAria = true;
                    } else if (mutation.type === 'attributes') {
                        if (mutation.attributeName === 'aria-expanded' || mutation.attributeName === 'aria-hidden' || mutation.attributeName === 'disabled') {
                            updateAria = true;
                        }
                    }
                }

                if (updateFocus) this.debouncedUpdateFocusableElements();
                if (updateAria) this.debouncedUpdateAriaAttributes();
            });

            this.observer.observe(document.body, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ['class', 'style', 'aria-expanded', 'aria-hidden', 'disabled']
            });
        }

        updateFocusableElements() {
            const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
            this.focusableElements = Array.from(document.querySelectorAll(focusableSelector)).filter(el =>
                el.offsetParent !== null && !el.closest('[aria-hidden="true"]')
            );
        }

        updateAriaAttributes() {
            // Update pagination controls
            document.querySelectorAll('.pagination-controls').forEach(control => {
                const prevBtn = control.querySelector('.prev-btn');
                const nextBtn = control.querySelector('.next-btn');
                if (prevBtn) prevBtn.setAttribute('aria-disabled', prevBtn.disabled);
                if (nextBtn) nextBtn.setAttribute('aria-disabled', nextBtn.disabled);
            });

            // Update toggle buttons
            const ariaControls = [
                { btn: 'weather-toggle-btn', container: 'weather-widget-container', stateClass: 'collapsed' },
                { btn: 'chat-toggle-btn', container: 'chat-container', stateAttr: 'aria-hidden' }
            ];

            ariaControls.forEach(({ btn, container, stateClass, stateAttr }) => {
                const toggle = document.getElementById(btn);
                const target = document.getElementById(container);
                if (toggle && target) {
                    let isExpanded;
                    if (stateClass) {
                        isExpanded = !target.classList.contains(stateClass);
                    } else {
                        isExpanded = target.getAttribute(stateAttr) !== 'true';
                    }
                    toggle.setAttribute('aria-expanded', isExpanded);
                }
            });
        }

        navigateArticles(direction) {
            if (this.isNavigating) return;
            this.isNavigating = true;

            const articles = this.focusableElements.filter(el => el.closest('.linkclass'));
            if (articles.length === 0) {
                this.isNavigating = false;
                return;
            }

            let currentArticleIndex = articles.indexOf(document.activeElement);
            currentArticleIndex += direction;

            if (currentArticleIndex < 0) {
                currentArticleIndex = articles.length - 1;
            } else if (currentArticleIndex >= articles.length) {
                currentArticleIndex = 0;
            }

            const targetArticle = articles[currentArticleIndex];
            if (targetArticle) {
                targetArticle.focus();
                targetArticle.scrollIntoView({ behavior: 'smooth', block: 'center' });
                this.announceToScreenReader(`Article ${currentArticleIndex + 1} of ${articles.length}: ${targetArticle.textContent.trim()}`);
            }

            setTimeout(() => { this.isNavigating = false; }, 300);
        }

        navigateToFirst() {
            const firstArticle = this.focusableElements.find(el => el.closest('.linkclass'));
            if (firstArticle) {
                firstArticle.focus();
                firstArticle.scrollIntoView({ behavior: 'smooth', block: 'start' });
                this.announceToScreenReader(`First article: ${firstArticle.textContent.trim()}`);
            }
        }

        navigateToLast() {
            const articles = this.focusableElements.filter(el => el.closest('.linkclass'));
            if (articles.length > 0) {
                const lastArticle = articles[articles.length - 1];
                lastArticle.focus();
                lastArticle.scrollIntoView({ behavior: 'smooth', block: 'end' });
                this.announceToScreenReader(`Last article: ${lastArticle.textContent.trim()}`);
            }
        }

        handleEscapeKey() {
            const chatContainer = document.getElementById('chat-container');
            if (chatContainer && chatContainer.getAttribute('aria-hidden') !== 'true') {
                document.getElementById('chat-close-btn')?.click();
            }
        }

        isFormElement(element) {
            return element.matches('input, textarea, select, [contenteditable="true"]');
        }

        announceToScreenReader(message) {
            if (this.announcementElement) {
                this.announcementElement.textContent = message;
                setTimeout(() => {
                    if(this.announcementElement) this.announcementElement.textContent = '';
                }, 2000);
            }
        }

        destroy() {
            if (this.observer) {
                this.observer.disconnect();
                this.observer = null;
            }
            if (this.announcementElement) {
                this.announcementElement.remove();
                this.announcementElement = null;
            }
            // Remove other event listeners if necessary, though they are on the document
            // and will be removed when the page is unloaded.
        }

        // Public API
        focusFirstArticle() {
            this.navigateToFirst();
        }

        announcePageChange(pageNumber, totalPages) {
            this.announceToScreenReader(`Page ${pageNumber} of ${totalPages}`);
        }

        announceLoading(message) {
            this.announceToScreenReader(message);
        }
    }

    // Initialize accessibility manager
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            app.modules.AccessibilityManager = new AccessibilityManager();
        });
    } else {
        app.modules.AccessibilityManager = new AccessibilityManager();
    }

})(window.app);