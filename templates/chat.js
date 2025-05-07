// Chat widget: SSE/Polling, draggable, send/delete, mute-beep

class ChatWidget {
  constructor() {
    this.elements = {};
    this.state = {
      isAdminMode: Cookie.get('isAdmin') === '1',
      isDragging: false,
      offsetX: 0,
      offsetY: 0,
      lastComments: [],
      lastCommentTimestamp: null,
      eventSource: null,
      pollingTimer: null,
      beepEnabled: true,
      // Add debounce timers
      fetchDebounceTimer: null,
      renderDebounceTimer: null
    };

    // Configuration
    this.config = {
      useSSE: false, // <<< SET TO true TO ENABLE SSE, false FOR POLLING >>>
      pollingInterval: 15000,
      maxRetries: 5,
      baseRetryDelay: 1000,
      maxRetryDelay: 30000,
      // Add configuration for debouncing and throttling
      fetchDebounceDelay: 1000,
      renderDebounceDelay: 100,
      dragThrottleDelay: 16 // ~60fps
    };

    // Initialize beep sound with lazy loading
    this.beepSound = null;
    this.initBeepSound();

    // Bind methods to prevent memory leaks
    this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
    this.handleResize = this.debounce(this.handleResize.bind(this), 250);
  }

  init() {
    // Get all required elements
    const requiredElements = [
      'chat-container',
      'chat-header',
      'chat-messages',
      'chat-message-input',
      'chat-image-url-input',
      'chat-send-btn',
      'chat-close-btn',
      'chat-loading',
      'chat-toggle-btn',
      'chat-input-area'
    ];

    // Check all required elements exist
    const missingElements = requiredElements.filter(id => {
      const element = document.getElementById(id);
      if (element) {
        this.elements[id] = element;
        return false;
      }
      return true;
    });

    if (missingElements.length > 0) {
      console.error("Missing chat UI elements:", missingElements.join(', '));
      return false;
    }

    this.setupEventListeners();
    
    // Add visibility and resize handlers
    document.addEventListener('visibilitychange', this.handleVisibilityChange);
    window.addEventListener('resize', this.handleResize);
    
    return true;
  }

  // Add utility methods for debouncing and throttling
  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
      if (!inThrottle) {
        func(...args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  }

  // Add handlers for visibility and resize
  handleVisibilityChange() {
    if (document.hidden) {
      this.cleanup();
    } else if (this.elements['chat-container'].style.display !== 'none') {
      if (this.config.useSSE) {
        this.initializeSSE();
      } else {
        this.fetchComments();
      }
    }
  }

  handleResize() {
    const container = this.elements['chat-container'];
    if (container.style.display === 'none') return;

    // Ensure chat container stays within viewport
    const rect = container.getBoundingClientRect();
    const maxX = window.innerWidth - rect.width;
    const maxY = window.innerHeight - rect.height;

    if (rect.left > maxX) container.style.left = maxX + 'px';
    if (rect.top > maxY) container.style.top = maxY + 'px';
  }

  initBeepSound() {
    // Lazy load the beep sound
    const loadBeep = () => {
      if (!this.beepSound) {
        this.beepSound = new Audio('data:audio/wav;base64,UklGRlIAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAAD//w==');
      }
    };

    // Load beep sound on first user interaction
    const userInteractionEvents = ['click', 'touchstart', 'keydown'];
    const loadBeepOnce = () => {
      loadBeep();
      userInteractionEvents.forEach(event => 
        document.removeEventListener(event, loadBeepOnce)
      );
    };
    userInteractionEvents.forEach(event => 
      document.addEventListener(event, loadBeepOnce, { once: true })
    );
  }

  setupEventListeners() {
    // Draggable window
    this.setupDraggable();

    // Close and toggle handlers
    this.elements['chat-close-btn'].addEventListener('click', () => this.closeChat());
    this.elements['chat-toggle-btn'].addEventListener('click', () => this.toggleChat());

    // Send message handlers
    this.elements['chat-send-btn'].addEventListener('click', () => this.sendComment());
    this.elements['chat-message-input'].addEventListener('keypress', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendComment();
      }
    });

    // Image upload handlers
    this.setupImageUpload();

    // Cleanup on page unload
    window.addEventListener('unload', () => this.cleanup());
  }

  setupDraggable() {
    const header = this.elements['chat-header'];
    const container = this.elements['chat-container'];
    const closeBtn = this.elements['chat-close-btn'];

    const onMouseDown = e => {
      if (e.target === closeBtn) return;
      this.state.isDragging = true;
      this.state.offsetX = e.clientX - container.offsetLeft;
      this.state.offsetY = e.clientY - container.offsetTop;
      container.style.cursor = 'grabbing';
      e.preventDefault();

      // Add dragging class for styling
      container.classList.add('dragging');
    };

    // Throttle mouse move for better performance
    const onMouseMove = this.throttle(e => {
      if (!this.state.isDragging) return;
      requestAnimationFrame(() => {
        const newX = Math.max(0, Math.min(e.clientX - this.state.offsetX, 
          window.innerWidth - container.offsetWidth));
        const newY = Math.max(0, Math.min(e.clientY - this.state.offsetY, 
          window.innerHeight - container.offsetHeight));
        container.style.left = newX + 'px';
        container.style.top = newY + 'px';
      });
    }, this.config.dragThrottleDelay);

    const onMouseUp = () => {
      if (this.state.isDragging) {
        this.state.isDragging = false;
        container.style.cursor = 'default';
        container.classList.remove('dragging');
      }
    };

    header.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);

    // Store handlers for cleanup
    this.dragHandlers = { onMouseDown, onMouseMove, onMouseUp };
  }

  setupImageUpload() {
    const inputArea = this.elements['chat-input-area'];
    
    const dragEvents = {
      dragover: e => {
        e.preventDefault();
        inputArea.classList.add('dragover');
      },
      dragleave: e => {
        e.preventDefault();
        inputArea.classList.remove('dragover');
      },
      drop: e => {
        e.preventDefault();
        inputArea.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file) this.uploadImage(file);
      }
    };

    Object.entries(dragEvents).forEach(([event, handler]) => {
      inputArea.addEventListener(event, handler);
    });

    // Store handlers for cleanup
    this.dragUploadHandlers = dragEvents;
  }

  async uploadImage(file) {
    const allowed = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
    const maxSize = 5 * 1024 * 1024; // 5MB

    if (!allowed.includes(file.type)) {
      alert('Invalid file type. Allowed types: PNG, JPEG, GIF, WebP');
      return;
    }

    if (file.size > maxSize) {
      alert('File too large. Maximum size: 5MB');
      return;
    }

    const imageUrlInput = this.elements['chat-image-url-input'];
    const formData = new FormData();
    formData.append('image', file);

    try {
      imageUrlInput.value = 'Uploading...';
      imageUrlInput.disabled = true;

      const response = await fetch('/api/upload_image', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      if (data.success && data.url) {
        imageUrlInput.value = data.url;
      } else {
        throw new Error(data.error || 'Unknown error');
      }
    } catch (error) {
      console.error('Upload failed:', error);
      alert('Upload failed: ' + error.message);
      imageUrlInput.value = '';
    } finally {
      imageUrlInput.disabled = false;
    }
  }

  async sendComment() {
    const messageInput = this.elements['chat-message-input'];
    const imageUrlInput = this.elements['chat-image-url-input'];
    const sendButton = this.elements['chat-send-btn'];

    const text = messageInput.value.trim();
    const imageUrl = imageUrlInput.value.trim();

    if (!text && !imageUrl) {
      alert('Please enter a message or an image URL.');
      return;
    }

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
        messageInput.value = '';
        imageUrlInput.value = '';
        if (!this.config.useSSE) {
          await this.fetchComments();
        }
      } else {
        throw new Error(data.error || 'Unknown error');
      }
    } catch (error) {
      console.error('Send failed:', error);
      alert('Error sending comment: ' + error.message);
    } finally {
      sendButton.disabled = false;
      sendButton.textContent = 'Send';
    }
  }

  async fetchComments() {
    if (this.config.useSSE || this.elements['chat-container'].style.display === 'none') {
      return;
    }

    // Debounce fetch requests
    if (this.state.fetchDebounceTimer) {
      clearTimeout(this.state.fetchDebounceTimer);
    }

    this.state.fetchDebounceTimer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/comments?_=${Date.now()}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        await this.renderComments(data);
      } catch (error) {
        console.error('Error fetching comments:', error);
        if (this.elements['chat-messages'].children.length <= 1) {
          const loading = this.elements['chat-loading'];
          loading.textContent = 'Error loading messages. Click to retry.';
          loading.style.display = 'block';
          loading.onclick = () => this.fetchComments();
        }
      }
    }, this.config.fetchDebounceDelay);
  }

  async renderComments(comments) {
    // Debounce render updates
    if (this.state.renderDebounceTimer) {
      clearTimeout(this.state.renderDebounceTimer);
    }

    this.state.renderDebounceTimer = setTimeout(() => {
      const messagesContainer = this.elements['chat-messages'];
      
      // Check for new messages
      const newMessagesExist = comments.length && 
        (!this.state.lastCommentTimestamp || 
         new Date(comments[0].timestamp).getTime() > this.state.lastCommentTimestamp);

      // Update timestamp
      this.state.lastCommentTimestamp = comments.length ? 
        new Date(comments[0].timestamp).getTime() : 
        this.state.lastCommentTimestamp;

      // Play beep for new messages if chat is visible
      if (newMessagesExist && 
          this.elements['chat-container'].style.display !== 'none' && 
          this.state.beepEnabled &&
          !document.hidden) {  // Only play when tab is visible
        this.playBeep();
      }

      // Skip render if no changes
      if (JSON.stringify(comments) === JSON.stringify(this.state.lastComments)) {
        return;
      }

      // Use IntersectionObserver for lazy loading images
      const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            img.src = img.dataset.src;
            observer.unobserve(img);
          }
        });
      });

      // Create document fragment for better performance
      const fragment = document.createDocumentFragment();

      if (comments.length) {
        comments.forEach(comment => {
          const messageDiv = document.createElement('div');
          messageDiv.className = `chat-message${comment.is_admin ? ' admin-message' : ''}`;
          messageDiv.dataset.commentId = comment.id;

          // Create timestamp
          const timestamp = document.createElement('span');
          timestamp.className = 'timestamp';
          timestamp.textContent = new Date(comment.timestamp)
            .toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
          messageDiv.appendChild(timestamp);

          // Create message text (safely)
          const messageText = document.createElement('span');
          messageText.className = 'message-text';
          messageText.textContent = comment.text;
          messageDiv.appendChild(messageText);

          // Add image if present
          if (comment.image_url) {
            const br = document.createElement('br');
            const link = document.createElement('a');
            link.href = comment.image_url;
            link.target = '_blank';
            link.rel = 'noopener'; // Security improvement
            
            const img = document.createElement('img');
            img.dataset.src = comment.image_url; // Use data-src for lazy loading
            img.className = 'chat-image';
            img.loading = 'lazy';
            img.alt = 'Chat image';
            img.onerror = () => {
              img.src = '/static/image-error.png';
              img.alt = 'Image failed to load';
            };
            
            link.appendChild(img);
            messageDiv.appendChild(br);
            messageDiv.appendChild(link);

            // Observe image for lazy loading
            imageObserver.observe(img);
          }

          // Add delete button for admin
          if (this.state.isAdminMode) {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'delete-comment-btn';
            deleteBtn.dataset.commentId = comment.id;
            deleteBtn.textContent = '❌';
            deleteBtn.onclick = e => this.handleDelete(e);
            messageDiv.appendChild(deleteBtn);
          }

          fragment.appendChild(messageDiv);
        });
      } else {
        const noMessages = document.createElement('div');
        noMessages.className = 'chat-message system-message';
        noMessages.textContent = 'No messages yet.';
        fragment.appendChild(noMessages);
      }

      // Update DOM
      messagesContainer.innerHTML = '';
      messagesContainer.appendChild(fragment);
      this.state.lastComments = comments;

      // Disconnect observer after use
      imageObserver.disconnect();
    }, this.config.renderDebounceDelay);
  }

  async handleDelete(e) {
    const id = e.target.dataset.commentId;
    if (!id) return;

    if (!confirm('Are you sure you want to delete this comment?')) {
      return;
    }

    try {
      const response = await fetch(`/api/comments/${id}`, {
        method: 'DELETE'
      });

      const data = await response.json();
      
      if (data.success) {
        e.target.closest('.chat-message').remove();
        if (!this.config.useSSE) {
          await this.fetchComments();
        }
      } else {
        throw new Error(data.error || 'Unknown error');
      }
    } catch (error) {
      console.error('Delete failed:', error);
      alert('Error deleting comment: ' + error.message);
    }
  }

  initializeSSE() {
    if (!this.config.useSSE || 
        this.state.eventSource || 
        this.elements['chat-container'].style.display === 'none') {
      return;
    }

    let retryCount = 0;
    const connect = () => {
      this.state.eventSource = new EventSource('/api/comments/stream');

      this.state.eventSource.onopen = () => {
        this.elements['chat-loading'].style.display = 'none';
        retryCount = 0;
      };

      this.state.eventSource.onmessage = async e => {
        try {
          const data = JSON.parse(e.data);
          await this.renderComments(data);
        } catch (error) {
          console.error('Error processing SSE message:', error);
        }
      };

      this.state.eventSource.onerror = () => {
        this.elements['chat-loading'].textContent = 'Connection error. Retrying...';
        this.elements['chat-loading'].style.display = 'block';
        
        if (this.state.eventSource) {
          this.state.eventSource.close();
          this.state.eventSource = null;
        }

        if (retryCount < this.config.maxRetries) {
          const delay = Math.min(
            this.config.baseRetryDelay * Math.pow(2, retryCount),
            this.config.maxRetryDelay
          );
          setTimeout(connect, delay);
          retryCount++;
        } else {
          this.elements['chat-loading'].textContent = 
            'Connection failed. Please refresh the page.';
        }
      };
    };

    connect();
  }

  closeChat() {
    this.elements['chat-container'].style.display = 'none';
    this.cleanup();
  }

  toggleChat() {
    const container = this.elements['chat-container'];
    const isHidden = container.style.display === 'none' || 
                     container.style.display === '';
    
    container.style.display = isHidden ? 'flex' : 'none';

    if (isHidden) {
      if (this.config.useSSE) {
        this.initializeSSE();
      } else {
        if (this.state.lastComments.length === 0 && 
            this.elements['chat-loading'].style.display !== 'none') {
          this.fetchComments();
        }
        if (!this.state.pollingTimer) {
          this.state.pollingTimer = setInterval(
            () => this.fetchComments(), 
            this.config.pollingInterval
          );
        }
      }
    } else {
      this.cleanup();
    }
  }

  cleanup() {
    // Clean up SSE
    if (this.config.useSSE && this.state.eventSource) {
      this.state.eventSource.close();
      this.state.eventSource = null;
    }

    // Clean up polling
    if (!this.config.useSSE && this.state.pollingTimer) {
      clearInterval(this.state.pollingTimer);
      this.state.pollingTimer = null;
    }

    // Clean up debounce timers
    if (this.state.fetchDebounceTimer) {
      clearTimeout(this.state.fetchDebounceTimer);
    }
    if (this.state.renderDebounceTimer) {
      clearTimeout(this.state.renderDebounceTimer);
    }

    // Remove event listeners
    document.removeEventListener('visibilitychange', this.handleVisibilityChange);
    window.removeEventListener('resize', this.handleResize);
  }

  playBeep() {
    if (this.beepSound) {
      this.beepSound.play().catch(console.error);
    }
  }
}

// Initialize chat widget when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const chat = new ChatWidget();
  if (chat.init()) {
    // Store instance for potential external access
    window.chatWidget = chat;
  }
});