/**
 * chat.js
 * 
 * Chat widget module for the LinuxReport application, integrated with the global app object.
 * Handles real-time messaging, SSE/polling communication, draggable interface, and image uploads.
 * 
 * @author LinuxReport Team
 * @version 3.1.0
 */

(function(app) {
    'use strict';

    class ChatWidget {
        constructor() {
            this.elements = {};
            this.state = {
                isAdminMode: window.isAdmin || false,
                isDragging: false,
                offsetX: 0,
                offsetY: 0,
                lastComments: [],
                lastCommentTimestamp: null,
                eventSource: null,
                pollingTimer: null,
                beepEnabled: true
            };
            this.beepSound = null;
            this.initBeepSound();
            this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
            this.handleResize = app.utils.debounce(this.handleResize.bind(this), app.config.CHAT_RESIZE_DEBOUNCE_DELAY);
        }

        init() {
            const requiredElements = [
                'chat-container', 'chat-header', 'chat-messages', 'chat-message-input',
                'chat-image-url-input', 'chat-send-btn', 'chat-close-btn',
                'chat-loading', 'chat-toggle-btn', 'chat-input-area'
            ];
            
            requiredElements.forEach(id => this.elements[id] = document.getElementById(id));
            if (requiredElements.some(id => !this.elements[id])) return false;

            this.setupChatLayout();
            this.setupEventListeners();
            document.addEventListener('visibilitychange', this.handleVisibilityChange);
            window.addEventListener('resize', this.handleResize);
            return true;
        }

        initBeepSound() {
            const loadBeep = () => {
                if (!this.beepSound) {
                    this.beepSound = new Audio('data:audio/wav;base64,UklGRlIAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAAD//w==');
                }
            };
            ['click', 'touchstart', 'keydown'].forEach(event => 
                document.addEventListener(event, loadBeep, { once: true })
            );
        }

        setupChatLayout() {
            // Chat layout is now handled by CSS
            // This method is kept for potential future layout adjustments
        }

        setupEventListeners() {
            this.setupDraggable();
            this.setupImageUpload();
            
            // Simplified event handling
            const events = {
                'chat-close-btn': () => this.closeChat(),
                'chat-toggle-btn': () => this.toggleChat(),
                'chat-send-btn': () => this.sendComment()
            };
            
            Object.entries(events).forEach(([id, handler]) => {
                this.elements[id].addEventListener('click', handler);
            });
            
            this.elements['chat-message-input'].addEventListener('keypress', e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendComment();
                }
            });
        }

        setupDraggable() {
            const { 'chat-header': header, 'chat-container': container } = this.elements;
            
            header.addEventListener('mousedown', e => {
                if (e.target === this.elements['chat-close-btn']) return;
                this.state.isDragging = true;
                this.state.offsetX = e.clientX - container.offsetLeft;
                this.state.offsetY = e.clientY - container.offsetTop;
                container.style.cursor = 'grabbing';
                e.preventDefault();
            });
            
            document.addEventListener('mousemove', app.utils.throttle(e => {
                if (!this.state.isDragging) return;
                const newX = Math.max(0, Math.min(e.clientX - this.state.offsetX, window.innerWidth - container.offsetWidth));
                const newY = Math.max(0, Math.min(e.clientY - this.state.offsetY, window.innerHeight - container.offsetHeight));
                container.style.left = `${newX}px`;
                container.style.top = `${newY}px`;
            }, app.config.CHAT_DRAG_THROTTLE_DELAY));
            
            document.addEventListener('mouseup', () => {
                if (this.state.isDragging) {
                    this.state.isDragging = false;
                    container.style.cursor = 'default';
                }
            });
        }

        setupImageUpload() {
            const inputArea = this.elements['chat-input-area'];
            ['dragover', 'dragleave', 'drop'].forEach(event => {
                inputArea.addEventListener(event, e => {
                    e.preventDefault();
                    if (event === 'drop') {
                        inputArea.classList.remove('dragover');
                        const file = e.dataTransfer.files[0];
                        if (file) this.uploadImage(file);
                    } else {
                        inputArea.classList.toggle('dragover', event === 'dragover');
                    }
                });
            });
        }

        async uploadImage(file) {
            if (!app.config.CHAT_ALLOWED_FILE_TYPES.includes(file.type) || file.size > app.config.CHAT_MAX_FILE_SIZE) {
                alert('Invalid file type or size.');
                return;
            }
            
            const imageUrlInput = this.elements['chat-image-url-input'];
            try {
                imageUrlInput.value = 'Uploading...';
                imageUrlInput.disabled = true;
                
                const formData = new FormData();
                formData.append('image', file);
                const response = await fetch('/api/upload_image', { method: 'POST', body: formData });
                const data = await response.json();
                
                if (data.success && data.url) {
                    imageUrlInput.value = data.url;
                } else {
                    throw new Error(data.error || 'Unknown error');
                }
            } catch (error) {
                alert(`Upload failed: ${error.message}`);
                app.utils.handleError('Image Upload', error);
                imageUrlInput.value = '';
            } finally {
                imageUrlInput.disabled = false;
            }
        }

        async sendComment() {
            const text = this.elements['chat-message-input'].value.trim();
            const imageUrl = this.elements['chat-image-url-input'].value.trim();
            if (!text && !imageUrl) return;

            const sendButton = this.elements['chat-send-btn'];
            try {
                sendButton.disabled = true;
                sendButton.textContent = 'Sending...';
                
                const response = await fetch('/api/comments', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text, image_url: imageUrl })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                
                if (data.success) {
                    this.elements['chat-message-input'].value = '';
                    this.elements['chat-image-url-input'].value = '';
                    if (!app.config.CHAT_USE_SSE) await this.fetchComments();
                } else {
                    throw new Error(data.error || 'Unknown error');
                }
            } catch (error) {
                alert(`Error sending comment: ${error.message}`);
                app.utils.handleError('Send Comment', error);
            } finally {
                sendButton.disabled = false;
                sendButton.textContent = 'Send';
            }
        }

        async fetchComments() {
            if (app.config.CHAT_USE_SSE || this.elements['chat-container'].style.display === 'none') return;
            
            try {
                const response = await fetch(`/api/comments?_=${Date.now()}`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                await this.renderComments(await response.json());
            } catch (error) {
                console.error('Error fetching comments:', error);
            }
        }

        async renderComments(comments) {
            if (!comments || !Array.isArray(comments)) return;
            
            const messagesContainer = this.elements['chat-messages'];
            if (!messagesContainer) return;

            // Hide loading message once we have comments
            const loadingElement = this.elements['chat-loading'];
            if (loadingElement && comments.length > 0) {
                loadingElement.style.display = 'none';
            }

            // Check for new comments
            const newComments = comments.filter(comment => 
                !this.state.lastComments.some(last => 
                    last.id === comment.id && last.timestamp === comment.timestamp
                )
            );

            if (newComments.length > 0) {
                newComments.forEach(comment => {
                    messagesContainer.appendChild(this.createMessageElement(comment));
                });
                
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
                this.state.lastComments = comments;
                
                // Play beep for new comments if not from current user
                if (this.state.beepEnabled && newComments.some(c => !c.is_own)) {
                    this.playBeep();
                }
            }
        }

        createMessageElement(comment) {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'chat-message';
            messageDiv.style.margin = '8px 0';
            messageDiv.style.padding = '8px';
            messageDiv.style.borderRadius = '8px';
            messageDiv.style.backgroundColor = comment.is_own ? 'var(--accent)' : 'var(--bg-secondary)';
            messageDiv.style.color = comment.is_own ? 'white' : 'var(--text)';
            
            const textDiv = document.createElement('div');
            textDiv.textContent = comment.text;
            messageDiv.appendChild(textDiv);
            
            if (comment.image_url) {
                const img = document.createElement('img');
                img.src = comment.image_url;
                img.style.maxWidth = '200px';
                img.style.maxHeight = '200px';
                img.style.marginTop = '8px';
                img.style.borderRadius = '4px';
                messageDiv.appendChild(img);
            }
            
            if (this.state.isAdminMode && comment.id) {
                const deleteBtn = document.createElement('button');
                deleteBtn.textContent = '✕';
                deleteBtn.style.marginTop = '4px';
                deleteBtn.style.fontSize = '1.2em';
                deleteBtn.style.padding = '0';
                deleteBtn.style.background = 'none';
                deleteBtn.style.border = 'none';
                deleteBtn.style.color = 'var(--muted, #888)';
                deleteBtn.style.cursor = 'pointer';
                deleteBtn.style.lineHeight = '1';
                deleteBtn.title = 'Delete';
                deleteBtn.addEventListener('click', (e) => this.handleDelete(e, comment.id));
                messageDiv.appendChild(deleteBtn);
            }
            
            return messageDiv;
        }

        async handleDelete(e, commentId) {
            e.preventDefault();
            if (!confirm('Delete this comment?')) return;
            
            try {
                const response = await fetch(`/api/comments/${commentId}`, { method: 'DELETE' });
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                
                const data = await response.json();
                if (data.success) {
                    e.target.closest('.chat-message').remove();
                } else {
                    throw new Error(data.error || 'Unknown error');
                }
            } catch (error) {
                alert(`Delete failed: ${error.message}`);
                app.utils.handleError('Delete Comment', error);
            }
        }

        initializeSSE() {
            if (!app.config.CHAT_USE_SSE) return;
            
            const connect = () => {
                try {
                    this.state.eventSource = new EventSource('/api/comments/stream');
                    
                    this.state.eventSource.onmessage = (event) => {
                        try {
                            const comment = JSON.parse(event.data);
                            this.renderComments([comment]);
                        } catch (error) {
                            console.error('Error parsing SSE data:', error);
                        }
                    };
                    
                    this.state.eventSource.onerror = () => {
                        this.state.eventSource.close();
                        setTimeout(connect, app.config.CHAT_BASE_RETRY_DELAY);
                    };
                } catch (error) {
                    console.error('SSE connection failed:', error);
                    setTimeout(connect, app.config.CHAT_BASE_RETRY_DELAY);
                }
            };
            
            connect();
        }

        handleVisibilityChange() {
            if (document.hidden) {
                this.cleanup();
            } else {
                // Only reconnect if chat is currently visible
                const container = this.elements['chat-container'];
                const computedStyle = getComputedStyle(container);
                if (computedStyle.display !== 'none') {
                    this.initializeSSE();
                    if (!app.config.CHAT_USE_SSE) {
                        this.fetchComments();
                    }
                }
            }
        }

        handleResize() {
            const container = this.elements['chat-container'];
            if (!container) return;
            
            // Ensure chat stays within viewport bounds
            const rect = container.getBoundingClientRect();
            if (rect.right > window.innerWidth) {
                container.style.left = `${window.innerWidth - rect.width}px`;
            }
            if (rect.bottom > window.innerHeight) {
                container.style.top = `${window.innerHeight - rect.height}px`;
            }
        }

        closeChat() {
            this.elements['chat-container'].style.display = 'none';
            this.cleanup();
        }

        toggleChat() {
            const container = this.elements['chat-container'];
            const computedStyle = getComputedStyle(container);
            const isVisible = computedStyle.display !== 'none';
            
            if (isVisible) {
                this.closeChat();
            } else {
                container.style.display = 'flex';
                this.initializeSSE();
                if (!app.config.CHAT_USE_SSE) {
                    this.fetchComments();
                }
            }
        }

        cleanup() {
            if (this.state.eventSource) {
                this.state.eventSource.close();
                this.state.eventSource = null;
            }
            if (this.state.pollingTimer) {
                clearInterval(this.state.pollingTimer);
                this.state.pollingTimer = null;
            }
        }

        playBeep() {
            if (this.beepSound && this.state.beepEnabled) {
                this.beepSound.play().catch(() => {});
            }
        }
    }

    app.modules.chat = {
        init() {
            const chatWidget = new ChatWidget();
            if (chatWidget.init()) {
                // Don't initialize SSE or fetch comments until chat is opened
                // The chat container starts hidden by default
            }
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        app.modules.chat.init();
    });

})(window.app);