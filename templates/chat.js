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

        setupEventListeners() {
            this.setupDraggable();
            this.setupImageUpload();
            
            const eventMap = {
                'chat-close-btn': () => this.closeChat(),
                'chat-toggle-btn': () => this.toggleChat(),
                'chat-send-btn': () => this.sendComment()
            };
            
            Object.entries(eventMap).forEach(([id, handler]) => {
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
                if (this.elements['chat-messages'].children.length <= 1) {
                    this.elements['chat-loading'].textContent = 'Error loading. Click to retry.';
                    this.elements['chat-loading'].onclick = () => this.fetchComments();
                }
            }
        }

        async renderComments(comments) {
            const newMessagesExist = comments.length && 
                (!this.state.lastCommentTimestamp || new Date(comments[0].timestamp).getTime() > this.state.lastCommentTimestamp);
            
            this.state.lastCommentTimestamp = comments.length ? 
                new Date(comments[0].timestamp).getTime() : this.state.lastCommentTimestamp;

            if (newMessagesExist && this.elements['chat-container'].style.display !== 'none' && 
                this.state.beepEnabled && !document.hidden) {
                this.playBeep();
            }

            if (JSON.stringify(comments) === JSON.stringify(this.state.lastComments)) return;

            const fragment = document.createDocumentFragment();
            if (comments.length) {
                comments.forEach(comment => fragment.appendChild(this.createMessageElement(comment)));
            } else {
                const noMessages = document.createElement('div');
                noMessages.className = 'chat-message system-message';
                noMessages.textContent = 'No messages yet.';
                fragment.appendChild(noMessages);
            }
            
            this.elements['chat-messages'].innerHTML = '';
            this.elements['chat-messages'].appendChild(fragment);
            this.state.lastComments = comments;
        }

        createMessageElement(comment) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `chat-message${comment.is_admin ? ' admin-message' : ''}`;
            messageDiv.dataset.commentId = comment.id;
            
            const timeStr = new Date(comment.timestamp).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
            messageDiv.innerHTML = `
                <span class="timestamp">${timeStr}</span>
                <span class="message-text">${comment.text}</span>
            `;

            if (comment.image_url) {
                const link = document.createElement('a');
                link.href = comment.image_url;
                link.target = '_blank';
                link.rel = 'noopener';
                link.innerHTML = `<br><img src="${comment.image_url}" class="chat-image" alt="Chat image">`;
                messageDiv.appendChild(link);
            }

            if (this.state.isAdminMode) {
                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'delete-comment-btn';
                deleteBtn.dataset.commentId = comment.id;
                deleteBtn.textContent = '❌';
                deleteBtn.onclick = e => this.handleDelete(e);
                messageDiv.appendChild(deleteBtn);
            }
            return messageDiv;
        }

        async handleDelete(e) {
            const id = e.target.dataset.commentId;
            if (!id || !confirm('Are you sure?')) return;
            
            try {
                const response = await fetch(`/api/comments/${id}`, { method: 'DELETE' });
                const data = await response.json();
                
                if (data.success) {
                    e.target.closest('.chat-message').remove();
                    if (!app.config.CHAT_USE_SSE) await this.fetchComments();
                } else {
                    throw new Error(data.error || 'Unknown error');
                }
            } catch (error) {
                alert(`Error deleting comment: ${error.message}`);
            }
        }

        initializeSSE() {
            if (!app.config.CHAT_USE_SSE || this.state.eventSource || 
                this.elements['chat-container'].style.display === 'none') return;
            
            let retryCount = 0;
            const connect = () => {
                this.state.eventSource = new EventSource('/api/comments/stream');
                this.state.eventSource.onopen = () => { 
                    this.elements['chat-loading'].style.display = 'none'; 
                    retryCount = 0; 
                };
                this.state.eventSource.onmessage = async e => { 
                    await this.renderComments(JSON.parse(e.data)); 
                };
                this.state.eventSource.onerror = () => {
                    this.elements['chat-loading'].textContent = 'Connection error. Retrying...';
                    this.elements['chat-loading'].style.display = 'block';
                    if (this.state.eventSource) this.state.eventSource.close();
                    this.state.eventSource = null;
                    
                    if (retryCount < app.config.CHAT_MAX_RETRIES) {
                        setTimeout(connect, Math.min(
                            app.config.CHAT_BASE_RETRY_DELAY * (2 ** retryCount), 
                            app.config.CHAT_MAX_RETRY_DELAY
                        ));
                        retryCount++;
                    } else {
                        this.elements['chat-loading'].textContent = 'Connection failed. Please refresh.';
                    }
                };
            };
            connect();
        }

        handleVisibilityChange() {
            if (document.hidden) {
                this.cleanup();
            } else if (this.elements['chat-container'].style.display !== 'none') {
                if (app.config.CHAT_USE_SSE) this.initializeSSE(); 
                else this.fetchComments();
            }
        }

        handleResize() {
            const container = this.elements['chat-container'];
            if (container.style.display === 'none') return;
            
            const rect = container.getBoundingClientRect();
            if (rect.left > window.innerWidth - rect.width) {
                container.style.left = `${window.innerWidth - rect.width}px`;
            }
            if (rect.top > window.innerHeight - rect.height) {
                container.style.top = `${window.innerHeight - rect.height}px`;
            }
        }

        closeChat() {
            this.elements['chat-container'].style.display = 'none';
            this.cleanup();
        }

        toggleChat() {
            const isHidden = this.elements['chat-container'].style.display === 'none' || 
                            this.elements['chat-container'].style.display === '';
            
            this.elements['chat-container'].style.display = isHidden ? 'flex' : 'none';
            
            if (isHidden) {
                if (app.config.CHAT_USE_SSE) {
                    this.initializeSSE();
                } else {
                    if (this.state.lastComments.length === 0) this.fetchComments();
                    if (!this.state.pollingTimer) {
                        this.state.pollingTimer = setInterval(() => this.fetchComments(), app.config.CHAT_POLLING_INTERVAL);
                    }
                }
            } else {
                this.cleanup();
            }
        }

        cleanup() {
            if (app.config.CHAT_USE_SSE && this.state.eventSource) {
                this.state.eventSource.close();
                this.state.eventSource = null;
            }
            if (!app.config.CHAT_USE_SSE && this.state.pollingTimer) {
                clearInterval(this.state.pollingTimer);
                this.state.pollingTimer = null;
            }
        }

        playBeep() {
            if (this.beepSound) this.beepSound.play().catch(console.error);
        }
    }

    app.modules.chat = {
        init() {
            const chatWidget = new ChatWidget();
            if (chatWidget.init()) {
                window.chatWidget = chatWidget;
            }
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        app.modules.chat.init();
    });

})(window.app);