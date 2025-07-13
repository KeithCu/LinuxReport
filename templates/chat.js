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
            // Consolidated state and element management
            this.elements = new Map();
            this.state = {
                isAdminMode: window.isAdmin || false,
                isDragging: false,
                lastComments: [],
                lastCommentTimestamp: null,
                beepEnabled: true
            };
            this.beepSound = null;
            this.initBeepSound();
            // Bind key methods
            this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
            this.handleResize = app.utils.debounce(this.handleResize.bind(this), app.config.CHAT_RESIZE_DEBOUNCE_DELAY);
            this.handleDrag = this.handleDrag.bind(this);
        }

        init() {
            const ids = [
                'chat-container', 'chat-header', 'chat-messages', 'chat-message-input',
                'chat-image-url-input', 'chat-send-btn', 'chat-close-btn',
                'chat-loading', 'chat-toggle-btn', 'chat-input-area'
            ];
            for (const id of ids) {
                const el = document.getElementById(id);
                if (!el) return false; // Early exit if an element is missing
                this.elements.set(id, el);
            }
            
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
            // Declarative event handling
            const eventMap = {
                'chat-close-btn': { event: 'click', handler: () => this.closeChat() },
                'chat-toggle-btn': { event: 'click', handler: () => this.toggleChat() },
                'chat-send-btn': { event: 'click', handler: () => this.sendComment() },
                'chat-message-input': { event: 'keypress', handler: e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        this.sendComment();
                    }
                }},
                'chat-header': { event: 'mousedown', handler: e => this.startDrag(e) },
                'chat-input-area': {
                    event: ['dragover', 'dragleave', 'drop'],
                    handler: e => {
                        e.preventDefault();
                        const inputArea = this.elements.get('chat-input-area');
                        switch(e.type) {
                            case 'dragover': inputArea.classList.add('dragover'); break;
                            case 'dragleave': inputArea.classList.remove('dragover'); break;
                            case 'drop': 
                                inputArea.classList.remove('dragover');
                                const file = e.dataTransfer.files[0];
                                if (file) this.uploadImage(file);
                                break;
                        }
                    }
                }
            };

            for (const [id, { event, handler }] of Object.entries(eventMap)) {
                const el = this.elements.get(id);
                if (!el) continue;
                
                if (Array.isArray(event)) {
                    event.forEach(e => el.addEventListener(e, handler));
                } else {
                    el.addEventListener(event, handler);
                }
            }
            
            document.addEventListener('mouseup', () => this.stopDrag());
        }

        startDrag(e) {
            if (e.target.closest('#chat-close-btn')) return;
            const container = this.elements.get('chat-container');
            
            this.state.isDragging = true;
            this.state.offsetX = e.clientX - container.offsetLeft;
            this.state.offsetY = e.clientY - container.offsetTop;
            container.style.cursor = 'grabbing';
            e.preventDefault();

            document.addEventListener('mousemove', this.handleDrag);
        }
        
        stopDrag() {
            if (!this.state.isDragging) return;
            this.state.isDragging = false;
            this.elements.get('chat-container').style.cursor = 'default';
            document.removeEventListener('mousemove', this.handleDrag);
        }

        handleDrag(e) {
            if (!this.state.isDragging) return;
            requestAnimationFrame(() => {
                const container = this.elements.get('chat-container');
                let newX = e.clientX - this.state.offsetX;
                let newY = e.clientY - this.state.offsetY;

                newX = Math.max(0, Math.min(newX, window.innerWidth - container.offsetWidth));
                newY = Math.max(0, Math.min(newY, window.innerHeight - container.offsetHeight));

                container.style.left = `${newX}px`;
                container.style.top = `${newY}px`;
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
            const messageInput = this.elements.get('chat-message-input');
            const imageUrlInput = this.elements.get('chat-image-url-input');
            const sendBtn = this.elements.get('chat-send-btn');

            const text = messageInput.value.trim();
            const imageUrl = imageUrlInput.value.trim();
            if (!text && !imageUrl) return;
            
            this.toggleSendButton(true, 'Sending...');

            try {
                const response = await fetch('/api/comments', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json', 
                        'X-CSRF-TOKEN': window.csrf_token 
                    },
                    body: JSON.stringify({ text, image_url: imageUrl })
                });

                if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);

                const data = await response.json();
                if (data.success) {
                    messageInput.value = '';
                    imageUrlInput.value = '';
                    if (!app.config.CHAT_USE_SSE) await this.fetchComments();
                } else {
                    throw new Error(data.error || 'Unknown error');
                }
            } catch (error) {
                alert(`Error: ${error.message}`);
                app.utils.handleError('Send Comment', error);
            } finally {
                this.toggleSendButton(false, 'Send');
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
            this.elements.get('chat-container').style.display = 'none';
            this.cleanup();
        }

        toggleChat() {
            const container = this.elements.get('chat-container');
            const isVisible = container.style.display !== 'none';

            if (isVisible) {
                this.closeChat();
            } else {
                container.style.display = 'flex';
                this.startChatSession();
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