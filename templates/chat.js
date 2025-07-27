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
            // Beep sound will be initialized in init() method to avoid CSP issues
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
            
            // Initialize beep sound after everything else is set up
            // This way CSP errors won't prevent chat from working
            try {
                this.initBeepSound();
            } catch (error) {
                console.warn('[Chat] Beep sound initialization failed, but chat will continue to work:', error.message);
            }
            
            return true;
        }

        initBeepSound() {
            const loadBeep = () => {
                if (!this.beepSound) {
                    try {
                        // Try to load beep sound file, but make it completely optional
                        this.beepSound = new Audio('/static/beep.wav');
                        // Test if the audio loads successfully
                        this.beepSound.addEventListener('canplaythrough', () => {
                            app.utils.logger.debug('[Chat] Beep sound loaded successfully');
                        });
                        this.beepSound.addEventListener('error', () => {
                            app.utils.logger.debug('[Chat] Beep sound file not found, continuing without beep');
                            this.beepSound = null;
                        });
                    } catch (error) {
                        app.utils.logger.debug('[Chat] Beep sound disabled, continuing without beep');
                        this.beepSound = null;
                    }
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
                'chat-send-btn': { event: 'click', handler: (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.sendComment();
                }},
                'chat-message-input': { event: 'keypress', handler: e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        this.sendComment();
                    }
                }},
                'chat-header': { event: 'mousedown', handler: e => this.startDrag(e) },
                'chat-input-area': {
                    event: ['dragover', 'dragleave', 'drop', 'submit'],
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
                            case 'submit':
                                this.sendComment();
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
            
            // TUTORIAL: Inline style for cursor change during drag
            // This cannot be moved to CSS because:
            // 1. The cursor state is dynamic and changes based on user interaction
            // 2. CSS cannot respond to JavaScript state changes (isDragging)
            // 3. The cursor needs to change immediately when drag starts/stops
            // Alternative: Could use CSS classes with :active pseudo-selector, but that's less reliable
            container.style.cursor = 'grabbing';
            e.preventDefault();

            document.addEventListener('mousemove', this.handleDrag);
        }
        
        stopDrag() {
            if (!this.state.isDragging) return;
            this.state.isDragging = false;
            
            // TUTORIAL: Inline style for cursor reset after drag
            // This cannot be moved to CSS because:
            // 1. The cursor needs to be reset when drag ends, not on mouse release
            // 2. CSS :active pseudo-selector only works while mouse is pressed
            // 3. The cursor state depends on JavaScript drag state, not CSS state
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

                // TUTORIAL: Inline styles for dynamic positioning during drag
                // These cannot be moved to CSS because:
                // 1. The position values are calculated dynamically based on mouse movement
                // 2. CSS cannot access JavaScript variables or perform calculations
                // 3. The position needs to update in real-time as the user drags
                // 4. The values depend on window size, container size, and mouse position
                // Alternative: Could use CSS transforms, but would still need JS for calculations
                container.style.left = `${newX}px`;
                container.style.top = `${newY}px`;
            });
        }

        async uploadImage(file) {
            if (!app.config.CHAT_ALLOWED_FILE_TYPES.includes(file.type) || file.size > app.config.CHAT_MAX_FILE_SIZE) {
                alert('Invalid file type or size.');
                return;
            }
            
            const imageUrlInput = this.elements.get('chat-image-url-input');
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
                    if (!app.config.CHAT_USE_SSE) {
                        await this.fetchComments();
                    }
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
            const chatContainer = this.elements.get('chat-container');
            const isHidden = chatContainer.style.display === 'none' || window.getComputedStyle(chatContainer).display === 'none';
            if (app.config.CHAT_USE_SSE || !chatContainer || isHidden) {
                return;
            }
            
            try {
                const response = await fetch(`/api/comments?_=${Date.now()}`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const comments = await response.json();
                await this.renderComments(comments);
            } catch (error) {
                console.error('Error fetching comments:', error);
            }
        }

        async renderComments(comments) {
            if (!comments || !Array.isArray(comments)) return;
            
            const messagesContainer = this.elements.get('chat-messages');
            if (!messagesContainer) return;

            // Hide loading message once we have comments
            const loadingElement = this.elements.get('chat-loading');
            if (loadingElement && comments.length > 0) {
                loadingElement.classList.add('hide');
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
            messageDiv.className = `chat-message ${comment.is_own ? 'chat-message-own' : 'chat-message-other'}`;
            
            const textDiv = document.createElement('div');
            textDiv.textContent = comment.text;
            messageDiv.appendChild(textDiv);
            
            if (comment.image_url) {
                const img = document.createElement('img');
                img.src = comment.image_url;
                messageDiv.appendChild(img);
            }
            
            if (this.state.isAdminMode && comment.id) {
                const deleteBtn = document.createElement('button');
                deleteBtn.textContent = '✕';
                deleteBtn.className = 'chat-delete-btn';
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
                const container = this.elements.get('chat-container');
                if (container && !container.classList.contains('hide')) {
                    this.initializeSSE();
                    if (!app.config.CHAT_USE_SSE) {
                        this.fetchComments();
                    }
                }
            }
        }

        handleResize() {
            const container = this.elements.get('chat-container');
            if (!container) return;
            
            // Ensure chat stays within viewport bounds
            const rect = container.getBoundingClientRect();
            
            // TUTORIAL: Inline styles for viewport boundary correction
            // These cannot be moved to CSS because:
            // 1. The position values are calculated based on viewport size and element size
            // 2. CSS cannot access window.innerWidth or getBoundingClientRect()
            // 3. The correction only happens when the element goes outside viewport bounds
            // 4. The values are dynamic and depend on current window size
            // Alternative: Could use CSS position: fixed with max-width/max-height, but less precise
            if (rect.right > window.innerWidth) {
                container.style.left = `${window.innerWidth - rect.width}px`;
            }
            if (rect.bottom > window.innerHeight) {
                container.style.top = `${window.innerHeight - rect.height}px`;
            }
        }

        closeChat() {
            const container = this.elements.get('chat-container');
            container.style.display = 'none';
            this.cleanup();
        }

        startChatSession() {
            // Initialize chat session
            this.initializeSSE();
            if (!app.config.CHAT_USE_SSE) {
                this.fetchComments();
            }
        }

        toggleChat() {
            const container = this.elements.get('chat-container');
            // Check both inline style and computed style to handle CSS vs inline conflicts
            const inlineDisplay = container.style.display;
            const computedDisplay = window.getComputedStyle(container).display;
            const isVisible = inlineDisplay !== 'none' && computedDisplay !== 'none';

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

        toggleSendButton(disabled, text) {
            const sendBtn = this.elements.get('chat-send-btn');
            if (sendBtn) {
                sendBtn.disabled = disabled;
                sendBtn.textContent = text;
            }
        }

        playBeep() {
            if (this.beepSound && this.state.beepEnabled) {
                this.beepSound.play().catch((error) => {
                    // Silently ignore beep sound errors - it's optional
                    app.utils.logger.debug('[Chat] Beep sound not available');
                });
            }
            // If no beep sound, just continue silently - it's optional
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