// Chat widget: SSE/Polling, draggable, send/delete, mute-beep

document.addEventListener('DOMContentLoaded', function() {
  const chatContainer = document.getElementById('chat-container');
  const chatHeader = document.getElementById('chat-header');
  const chatMessages = document.getElementById('chat-messages');
  const messageInput = document.getElementById('chat-message-input');
  const imageUrlInput = document.getElementById('chat-image-url-input');
  const sendButton = document.getElementById('chat-send-btn');
  const closeButton = document.getElementById('chat-close-btn');
  const loadingIndicator = document.getElementById('chat-loading');
  const chatToggleButton = document.getElementById('chat-toggle-btn');
  const chatInputArea = document.getElementById('chat-input-area');

  if (!chatContainer || !chatHeader || !chatMessages || !messageInput || !imageUrlInput || !sendButton || !closeButton || !loadingIndicator || !chatToggleButton || !chatInputArea) {
    console.error("Chat UI elements not found. Chat functionality disabled.");
    return;
  }
  // --- Configuration ---
  const useSSE = false; // <<< SET TO true TO ENABLE SSE, false FOR POLLING >>>
  const pollingInterval = 15000;
  let isAdminMode = document.cookie.split('; ').some(item => item.trim().startsWith('isAdmin=1'));
  let isDragging = false, offsetX, offsetY;
  let lastComments = [], lastCommentTimestamp = null;
  const beepSound = new Audio('data:audio/wav;base64,UklGRlIAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAAD//w==');
  let eventSource = null, pollingTimer = null;

  // Draggable Window
  chatHeader.addEventListener('mousedown', e => {
    if (e.target === closeButton) return;
    isDragging = true;
    offsetX = e.clientX - chatContainer.offsetLeft;
    offsetY = e.clientY - chatContainer.offsetTop;
    chatContainer.style.cursor = 'grabbing'; e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!isDragging) return;
    let newX = Math.max(0, Math.min(e.clientX - offsetX, window.innerWidth - chatContainer.offsetWidth));
    let newY = Math.max(0, Math.min(e.clientY - offsetY, window.innerHeight - chatContainer.offsetHeight));
    chatContainer.style.left = newX + 'px'; chatContainer.style.top = newY + 'px';
  });
  document.addEventListener('mouseup', () => { if (isDragging) { isDragging = false; chatContainer.style.cursor = 'default'; }});

  // Close and Toggle
  closeButton.addEventListener('click', () => {
    chatContainer.style.display = 'none'; if (useSSE && eventSource) eventSource.close();
    if (!useSSE && pollingTimer) { clearInterval(pollingTimer); pollingTimer = null; }
  });
  chatToggleButton.addEventListener('click', () => {
    const isHidden = chatContainer.style.display === 'none' || chatContainer.style.display === '';
    chatContainer.style.display = isHidden ? 'flex' : 'none';
    if (isHidden) {
      if (useSSE) initializeSSE();
      else {
        if (lastComments.length === 0 && loadingIndicator.style.display !== 'none') fetchComments();
        if (!pollingTimer) pollingTimer = setInterval(fetchComments, pollingInterval);
      }
    } else {
      if (useSSE && eventSource) eventSource.close();
      if (!useSSE && pollingTimer) { clearInterval(pollingTimer); pollingTimer = null; }
    }
  });

  // Polling
  function fetchComments() {
    if (useSSE || chatContainer.style.display === 'none') return;
    const cacheBuster = Date.now();
    fetch(`/api/comments?_=${cacheBuster}`)
      .then(r => r.json())
      .then(renderComments)
      .catch(err => { console.error('Error fetching comments:', err); if (chatMessages.children.length <= 1) { loadingIndicator.textContent = 'Error loading messages.'; loadingIndicator.style.display = 'block'; }});
  }

  // SSE
  let sseReconnectTimer = null;
  function initializeSSE() {
    if (!useSSE || eventSource || chatContainer.style.display === 'none') return;
    eventSource = new EventSource('/api/comments/stream');
    eventSource.onopen = () => { loadingIndicator.style.display = 'none'; };
    eventSource.onmessage = e => { renderComments(JSON.parse(e.data)); };
    eventSource.onerror = () => { loadingIndicator.textContent = 'Connection error. Retrying...'; loadingIndicator.style.display = 'block'; eventSource.close(); eventSource = null; setTimeout(initializeSSE, 1000); };
  }

  // Render and delete
  function renderComments(comments) {
    let newMessagesExist = comments.length && (!lastCommentTimestamp || new Date(comments[0].timestamp).getTime() > lastCommentTimestamp);
    lastCommentTimestamp = comments.length ? new Date(comments[0].timestamp).getTime() : lastCommentTimestamp;
    if (newMessagesExist && chatContainer.style.display !== 'none') playBeep();
    if (JSON.stringify(comments) === JSON.stringify(lastComments)) return;
    let html = comments.length ? comments.map(c => `<div class="chat-message${c.is_admin?' admin-message':''}" data-comment-id="${c.id}"><span class="timestamp">${new Date(c.timestamp).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</span><span class="message-text">${c.text}</span>${c.image_url?`<br><a href="${c.image_url}" target="_blank"><img src="${c.image_url}" class="chat-image"></a>`:''}${isAdminMode?`<button class="delete-comment-btn" data-comment-id="${c.id}">❌</button>`:''}</div>`).join('') : '<div class="chat-message system-message">No messages yet.</div>';
    chatMessages.innerHTML = html;
    if (isAdminMode) document.querySelectorAll('.delete-comment-btn').forEach(btn => { btn.removeEventListener('click', handleDelete); btn.addEventListener('click', handleDelete); });
    lastComments = comments;
  }
  function handleDelete(e) {
    const id = e.target.getAttribute('data-comment-id'); if (!id) return;
    if (confirm('Are you sure you want to delete this comment?')) fetch(`/api/comments/${id}`,{method:'DELETE'}).then(r=>r.json()).then(d=>{ if(d.success){e.target.closest('.chat-message').remove(); if (!useSSE) fetchComments();} else alert('Error deleting comment: '+(d.error||'Unknown')); }).catch(()=>alert('Error deleting comment.'));
  }
  function playBeep() { beepSound.play().catch(console.error); }

  // Image upload drag-drop
  chatInputArea.addEventListener('dragover', e=>{e.preventDefault();chatInputArea.classList.add('dragover');});
  chatInputArea.addEventListener('dragleave', e=>{e.preventDefault();chatInputArea.classList.remove('dragover');});
  chatInputArea.addEventListener('drop', e=>{e.preventDefault();chatInputArea.classList.remove('dragover');if(e.dataTransfer.files[0])uploadImage(e.dataTransfer.files[0]);});
  function uploadImage(file) {const allowed=['image/png','image/jpeg','image/gif','image/webp'];if(!allowed.includes(file.type)){alert('Invalid file type.');return;}if(file.size>5*1024*1024){alert('File too large.');return;}let fd=new FormData();fd.append('image',file);imageUrlInput.value='Uploading...';imageUrlInput.disabled=true;fetch('/api/upload_image',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{if(d.success&&d.url){imageUrlInput.value=d.url;}else{alert('Upload failed: '+(d.error||'Unknown'));imageUrlInput.value='';}}).catch(()=>{alert('Upload failed.');imageUrlInput.value='';}).finally(()=>{imageUrlInput.disabled=false;if(imageUrlInput.value==='Uploading...')imageUrlInput.value='';});}

  sendButton.addEventListener('click', sendComment);
  messageInput.addEventListener('keypress', e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendComment();}});
  function sendComment(){const t=messageInput.value.trim(),u=imageUrlInput.value.trim();if(!t&&!u){alert('Please enter a message or an image URL.');return;}sendButton.disabled=true;sendButton.textContent='Sending...';fetch('/api/comments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t,image_url:u})}).then(r=>r.json()).then(d=>{if(d.success){messageInput.value='';imageUrlInput.value='';if(!useSSE)fetchComments();}else alert('Error sending comment: '+(d.error||'Unknown'));}).catch(()=>{alert('Error sending comment.');}).finally(()=>{sendButton.disabled=false;sendButton.textContent='Send';});}

  console.log("Chat will not poll or fetch until made visible by user.");
});