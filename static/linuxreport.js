document.addEventListener('DOMContentLoaded', function() {
  // Read theme cookie or default
  var match = document.cookie.match(/(?:^|; )Theme=([^;]+)/);
  var theme = match ? match[1] : 'silver';
  // Apply theme class to body
  document.body.classList.add('theme-' + theme);
  // Set dropdown to current theme
  var select = document.getElementById('theme-select');
  if (select) select.value = theme;

  // Read font cookie or default to 'sans-serif'
  var fontMatch = document.cookie.match(/(?:^|; )FontFamily=([^;]+)/);
  var font = fontMatch ? fontMatch[1] : 'sans-serif'; // Default to sans-serifif';
  // Apply font class to body
  // Remove all existing font classes first to ensure a clean slate
  document.body.classList.remove(
    'font-system', 'font-monospace', 'font-inter',
    'font-roboto', 'font-open-sans', 'font-source-sans',
    'font-noto-sans', 'font-lato', 'font-raleway', 'font-sans-serif'
  );
  document.body.classList.add('font-' + font);
  // Set dropdown to current font
  var fontSelect = document.getElementById('font-select');
  if (fontSelect) fontSelect.value = font;

  // Apply no-underlines setting (default ON)
  var nu = document.cookie.match(/(?:^|; )NoUnderlines=([^;]+)/);
  if (!nu || nu[1] === '1') document.body.classList.add('no-underlines');

  // Restore scroll position
  restoreScrollPosition();
});

// Global flag to enable/disable weather widget toggle. Set to false to always show widget and hide toggle UI.
const weatherWidgetToggleEnabled = true;

// --- Weather Widget Toggle ---
const weatherDefaultCollapsed = false; // <<< SET TO true FOR COLLAPSED BY DEFAULT, false FOR OPEN BY DEFAULT >>>

document.addEventListener('DOMContentLoaded', function() {
  const weatherContainer = document.getElementById('weather-widget-container');
  const weatherContent = document.getElementById('weather-content');
  const weatherToggleBtn = document.getElementById('weather-toggle-btn');

  if (!weatherWidgetToggleEnabled) {
    // Ensure widget always open
    if (weatherContainer) weatherContainer.classList.remove('collapsed');
    if (weatherContent) weatherContent.style.display = '';
    // Hide toggle UI
    if (weatherToggleBtn) weatherToggleBtn.style.display = 'none';
    const label = document.getElementById('weather-collapsed-label');
    if (label) label.style.display = 'none';
    return;
  }

  if (!weatherContainer || !weatherContent || !weatherToggleBtn) {
    console.warn('Weather toggle elements not found.');
    return;
  }

  // Function to set state based on cookie OR default setting
  function setInitialWeatherState() {
    const cookieValue = document.cookie.split('; ').find(item => item.trim().startsWith('weatherCollapsed='));
    let isCollapsed;

    if (cookieValue) {
      // Use cookie value if it exists
      isCollapsed = cookieValue.split('=')[1] === 'true';
    } else {
      // Otherwise, use the default setting
      isCollapsed = weatherDefaultCollapsed;
    }

    if (isCollapsed) {
      weatherContainer.classList.add('collapsed');
      weatherToggleBtn.innerHTML = '&#9650;'; // Up arrow
    } else {
      weatherContainer.classList.remove('collapsed');
      weatherToggleBtn.innerHTML = '&#9660;'; // Down arrow
    }
  }

  // Set initial state on load
  setInitialWeatherState();

  // Add click listener to toggle button
  weatherToggleBtn.addEventListener('click', function(event) { // Added event parameter
    console.log('Weather toggle button clicked!'); // Add this line for debugging
    event.stopPropagation(); // Prevent the click from bubbling up
    const isCurrentlyCollapsed = weatherContainer.classList.toggle('collapsed');
    if (isCurrentlyCollapsed) {
      weatherToggleBtn.innerHTML = '&#9650;'; // Up arrow
      document.cookie = 'weatherCollapsed=true; path=/; max-age=31536000; SameSite=Lax'; // Added SameSite
    } else {
      weatherToggleBtn.innerHTML = '&#9660;'; // Down arrow
      document.cookie = 'weatherCollapsed=false; path=/; max-age=31536000; SameSite=Lax'; // Added SameSite
    }
  });
});
// --- End Weather Widget Toggle ---

function redirect() {
  window.location = "/config"
}
var timer = setInterval(autoRefresh, 3601 * 1000);
function autoRefresh(){self.location.reload();}

// Change theme via cookie and reload
function setTheme(theme) {
  // Save current scroll position with timestamp
  const scrollData = {
    position: window.scrollY,
    timestamp: Date.now()
  };
  localStorage.setItem('scrollPosition', JSON.stringify(scrollData));
  document.cookie = 'Theme=' + theme + ';path=/';
  window.location.reload();
}

// Change font via cookie and update dynamically
function setFont(font) {
  // Save current scroll position with timestamp
  const scrollData = {
    position: window.scrollY,
    timestamp: Date.now()
  };
  localStorage.setItem('scrollPosition', JSON.stringify(scrollData));
  
  // Set the cookie
  document.cookie = 'FontFamily=' + font + ';path=/';
  
  // Remove all existing font classes
  document.body.classList.remove(
    'font-system', 'font-monospace', 'font-inter',
    'font-roboto', 'font-open-sans', 'font-source-sans',
    'font-noto-sans', 'font-lato', 'font-raleway', 'font-sans-serif'
  );
  
  // Add the new font class
  document.body.classList.add('font-' + font);
  
  // Update the dropdown to match
  var fontSelect = document.getElementById('font-select');
  if (fontSelect) fontSelect.value = font;
  
  // Force a reflow to ensure the font change takes effect
  document.body.style.display = 'none';
  document.body.offsetHeight; // Force reflow
  document.body.style.display = '';

  // Force font change on all elements
  const allElements = document.querySelectorAll('*');
  allElements.forEach(element => {
    element.style.fontFamily = 'inherit';
  });

  // Restore scroll position after font change
  restoreScrollPosition();
}

// Function to restore scroll position
function restoreScrollPosition() {
  try {
    const savedData = localStorage.getItem('scrollPosition');
    if (!savedData) return;

    const scrollData = JSON.parse(savedData);
    const now = Date.now();
    
    // Only restore if the saved position is less than 5 seconds old
    if (now - scrollData.timestamp > 5000) {
      localStorage.removeItem('scrollPosition');
      return;
    }

    // Try multiple approaches to ensure scroll restoration
    const scrollToPosition = () => {
      window.scrollTo(0, scrollData.position);
      // Also try scrollIntoView as a backup
      if (document.body.scrollHeight > scrollData.position) {
        const tempElement = document.createElement('div');
        tempElement.style.position = 'absolute';
        tempElement.style.top = scrollData.position + 'px';
        document.body.appendChild(tempElement);
        tempElement.scrollIntoView();
        document.body.removeChild(tempElement);
      }
    };

    // Try immediate scroll
    scrollToPosition();

    // Also try after a short delay
    setTimeout(scrollToPosition, 100);

    // And try after images and other resources load
    window.addEventListener('load', scrollToPosition);

    // Clean up
    localStorage.removeItem('scrollPosition');
  } catch (error) {
    console.error('Error restoring scroll position:', error);
    localStorage.removeItem('scrollPosition');
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const feeds = document.querySelectorAll(".pagination-controls");

  feeds.forEach(feedControls => {
    const feedId = feedControls.dataset.feedId;
    const feedContainer = document.getElementById(feedId);

    if (!feedContainer) {
      console.error(`Feed container with ID "${feedId}" not found.`);
      return; // Skip this feed if the container is missing
    }

    const items = feedContainer.querySelectorAll(".linkclass");
    const prevBtn = feedControls.querySelector(".prev-btn");
    const nextBtn = feedControls.querySelector(".next-btn");

    if (items.length === 0) {
      console.warn(`No items found for feed "${feedId}".`);
      if (prevBtn) prevBtn.disabled = true;
      if (nextBtn) nextBtn.disabled = true;
      return;
    }

    const itemsPerPage = 8; // Entries per page
    let currentPage = 0;
    const totalItems = items.length;
    const totalPages = Math.ceil(totalItems / itemsPerPage);

    function updatePagination() {
      const start = currentPage * itemsPerPage;
      const end = start + itemsPerPage;

      items.forEach((item, index) => {
        item.style.display = index >= start && index < end ? "block" : "none";
      });

      if (prevBtn) prevBtn.disabled = currentPage === 0;
      if (nextBtn) nextBtn.disabled = currentPage >= totalPages - 1;
    }

    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        if (currentPage > 0) {
          currentPage--;
          updatePagination();
        }
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (currentPage < totalPages - 1) {
          currentPage++;
          updatePagination();
        }
      });
    }

    // Initialize pagination for this feed
    updatePagination();
  });
});

document.addEventListener("DOMContentLoaded", function() {
  // Weather functionality
  function loadWeather() {
    const weatherContainer = document.getElementById('weather-container');
    if (!weatherContainer) return;
    // Only fetch weather if widget is visible
    const widgetWrapper = document.getElementById('weather-widget-container');
    if ((widgetWrapper && widgetWrapper.classList.contains('collapsed')) ||
        getComputedStyle(weatherContainer).display === 'none') return;
    fetchWeatherData();
  }
  function fetchWeatherData() {
    // Add cache-busting param using YYYYMMDDHH to avoid browser caching across days/hours
    const now = new Date();
    const year = now.getFullYear();
    const month = (now.getMonth() + 1).toString().padStart(2, '0'); // Months are 0-indexed
    const day = now.getDate().toString().padStart(2, '0');
    const hour = now.getHours().toString().padStart(2, '0');
    const cacheBuster = `${year}${month}${day}${hour}`;
    
    // Use Intl API to determine if user prefers metric system
    const userLocale = new Intl.Locale(navigator.language || 'en-US');
    // Regions primarily using Fahrenheit:
    // US: United States, BS: Bahamas, BZ: Belize, KY: Cayman Islands, PW: Palau
    const prefersFahrenheit = ['US', 'BS', 'BZ', 'KY', 'PW'].includes(userLocale.region);
    const useMetric = !prefersFahrenheit;
    
    fetch(`/api/weather?units=${useMetric ? 'metric' : 'imperial'}&_=${cacheBuster}`)
      .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
      })
      .then(data => {
        renderWeatherData(data, useMetric);
      })
      .catch(error => {
        if (document.getElementById('weather-loading')) document.getElementById('weather-loading').style.display = "none";
        if (document.getElementById('weather-error')) document.getElementById('weather-error').style.display = "block";
      });
  }
  function renderWeatherData(data, useMetric) {
    const weatherForecast = document.getElementById('weather-forecast');
    const weatherLoading = document.getElementById('weather-loading');
    const weatherError = document.getElementById('weather-error');
    if (!weatherForecast || !weatherLoading || !weatherError) return; // Ensure elements exist
    if (!data.daily || data.daily.length === 0) {
      weatherLoading.style.display = "none";
      weatherError.style.display = "block";
      weatherError.textContent = "No weather data available.";
      return;
    }
    weatherForecast.innerHTML = '';
    weatherForecast.className = 'weather-forecast';
    const today = new Date();
    const todayYear = today.getFullYear();
    const todayMonth = today.getMonth();
    const todayDate = today.getDate();
    data.daily.forEach((day, i) => {
      const dayElement = document.createElement('div');
      dayElement.className = 'weather-day';
      const date = new Date(day.dt * 1000);
      const userLocale = navigator.language || 'en-US';
      let dayName;
      if (
        date.getFullYear() === todayYear &&
        date.getMonth() === todayMonth &&
        date.getDate() === todayDate
      ) {
        if (userLocale.startsWith('en')) {
          dayName = 'Today';
        } else {
          dayName = date.toLocaleDateString(userLocale, { weekday: 'long' });
        }
      } else {
        dayName = date.toLocaleDateString(userLocale, { weekday: 'short' });
      }
      dayElement.innerHTML = `
        <div class="weather-day-name">${dayName}</div>
        <img class="weather-icon" src="https://openweathermap.org/img/wn/${day.weather_icon}.png" alt="${day.weather}">
        <div class="weather-temp">
          <span class="temp-max">${Math.round(day.temp_max)}°${useMetric ? 'C' : 'F'}</span> /
          <span class="temp-min">${Math.round(day.temp_min)}°${useMetric ? 'C' : 'F'}</span>
        </div>
        <div class="weather-precip">${Math.round(day.precipitation)}% precip</div>
      `;
      weatherForecast.appendChild(dayElement);
    });
    weatherLoading.style.display = "none";
    weatherForecast.style.display = "flex";
  }
  setTimeout(loadWeather, 100);

  // Fetch weather when widget is toggled open
  const weatherToggleBtn = document.getElementById('weather-toggle-btn');
  if (weatherToggleBtn) {
    weatherToggleBtn.addEventListener('click', function() {
      // Delay slightly to allow UI state to update
      setTimeout(loadWeather, 100);
    });
  }
});

document.addEventListener('DOMContentLoaded', function() {
  const chatContainer = document.getElementById('chat-container');
  const chatHeader = document.getElementById('chat-header');
  const chatMessages = document.getElementById('chat-messages');
  const messageInput = document.getElementById('chat-message-input');
  const imageUrlInput = document.getElementById('chat-image-url-input');
  const sendButton = document.getElementById('chat-send-btn');
  const closeButton = document.getElementById('chat-close-btn');
  const loadingIndicator = document.getElementById('chat-loading');
  const chatToggleButton = document.getElementById('chat-toggle-btn'); // Get the toggle button
  const chatInputArea = document.getElementById('chat-input-area'); // Get input area for drag/drop

  // Ensure all elements exist before proceeding
  if (!chatContainer || !chatHeader || !chatMessages || !messageInput || !imageUrlInput || !sendButton || !closeButton || !loadingIndicator || !chatToggleButton || !chatInputArea) {
    console.error("Chat UI elements not found. Chat functionality disabled.");
    return;
  }

  // --- Configuration ---
  const useSSE = false; // <<< SET TO true TO ENABLE SSE, false FOR POLLING >>>
  const pollingInterval = 15000; // Poll every 15 seconds if SSE is disabled
  // ---------------------

  let isAdminMode = document.cookie.split('; ').some(item => item.trim().startsWith('isAdmin=1')); // Check for admin cookie
  let isDragging = false;
  let offsetX, offsetY;
  let lastComments = []; // Store last fetched comments to avoid duplicates
  let lastCommentTimestamp = null; // Store timestamp of the latest known comment
  const beepSound = new Audio('data:audio/wav;base64,UklGRlIAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAAD//w=='); // Simple short beep
  let eventSource = null; // Variable to hold the EventSource instance for SSE
  let pollingTimer = null; // Variable to hold the polling interval timer

  // --- Draggable Window ---
  chatHeader.addEventListener('mousedown', (e) => {
    // Prevent dragging if clicking on the close button
    if (e.target === closeButton) return;
    isDragging = true;
    // Calculate offset from the top-left corner of the chat window
    offsetX = e.clientX - chatContainer.offsetLeft;
    offsetY = e.clientY - chatContainer.offsetTop;
    chatContainer.style.cursor = 'grabbing'; // Change cursor while dragging
    // Prevent text selection while dragging
    e.preventDefault();
  });

  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    // Calculate new position
    let newX = e.clientX - offsetX;
    let newY = e.clientY - offsetY;

    // Boundary checks (keep within viewport)
    const minX = 0;
    const minY = 0;
    const maxX = window.innerWidth - chatContainer.offsetWidth;
    const maxY = window.innerHeight - chatContainer.offsetHeight;

    newX = Math.max(minX, Math.min(newX, maxX));
    newY = Math.max(minY, Math.min(newY, maxY));

    chatContainer.style.left = newX + 'px';
    chatContainer.style.top = newY + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (isDragging) {
      isDragging = false;
      chatContainer.style.cursor = 'default'; // Reset cursor
    }
  });

  // --- Close Button ---
  closeButton.addEventListener('click', () => {
    chatContainer.style.display = 'none'; // Hide the chat window
    if (useSSE) closeSSE();
    if (!useSSE && pollingTimer) {
        console.log("Stopping polling timer.");
        clearInterval(pollingTimer);
        pollingTimer = null;
    }
  });

  // --- Toggle Button ---
  chatToggleButton.addEventListener('click', () => {
    const isHidden = chatContainer.style.display === 'none' || chatContainer.style.display === '';
    chatContainer.style.display = isHidden ? 'flex' : 'none'; // Toggle visibility
    if (isHidden) {
       // If opening the chat:
       if (useSSE) {
           initializeSSE(); // Start SSE if enabled
       } else {
           // Fetch comments immediately via polling if it was hidden and hasn't loaded yet
           if (lastComments.length === 0 && loadingIndicator.style.display !== 'none') {
               fetchComments();
           }
           // Start polling if not already started
           if (!pollingTimer) {
               console.log(`Starting polling timer. Interval: ${pollingInterval}ms`);
               pollingTimer = setInterval(fetchComments, pollingInterval);
           }
       }
    } else {
        // If closing the chat:
        if (useSSE) closeSSE();
        if (!useSSE && pollingTimer) {
            console.log("Stopping polling timer via toggle.");
            clearInterval(pollingTimer);
            pollingTimer = null;
        }
    }
  });


  // --- Fetch Comments (Used for Polling) ---
  function fetchComments() {
    // *** Only fetch if chat is visible AND SSE is DISABLED ***
    if (useSSE || chatContainer.style.display === 'none') {
        // console.log("Skipping fetch: SSE enabled or Chat hidden.");
        return;
    }

    // Add cache-busting parameter with current timestamp (including seconds)
    const cacheBuster = new Date().getTime();
    console.log("Polling for comments..."); // Log polling action
    fetch(`/api/comments?_=${cacheBuster}`) // Append timestamp here
      .then(response => response.json())
      .then(comments => {
        loadingIndicator.style.display = 'none';
        renderComments(comments);
      })
      .catch(error => {
        console.error('Error fetching comments:', error);
        if (chatMessages.children.length <= 1) { // Only show if no messages are displayed
            loadingIndicator.textContent = 'Error loading messages.';
            loadingIndicator.style.display = 'block';
        }
      });
  }

  // --- Render Comments ---
  function renderComments(comments) {
     // console.log("renderComments received:", JSON.stringify(comments));

     // Determine if there are genuinely new messages since the last render (for beep)
     let newMessagesExist = false;
     let latestTimestampInBatch = null;
     if (comments.length > 0) {
         // Find the timestamp of the newest comment in the received batch
         latestTimestampInBatch = new Date(comments[0].timestamp).getTime(); // Assuming newest is first
         // If we have a previous timestamp, check if the newest in batch is newer
         if (lastCommentTimestamp && latestTimestampInBatch > lastCommentTimestamp) {
             newMessagesExist = true;
         }
         // Update the last known timestamp to the newest one from this batch
         lastCommentTimestamp = latestTimestampInBatch;
     }

     // Compare stringified content to avoid unnecessary DOM manipulation if content is identical
     if (JSON.stringify(comments) === JSON.stringify(lastComments)) {
         // console.log("No change in comments, skipping DOM update.");
         return; // Exit if comments haven't changed
     }

     // Play beep only if new messages arrived and chat is visible
     if (newMessagesExist && chatContainer.style.display !== 'none') {
         playBeep();
     }

     // *** Build HTML string for all comments ***
     let messagesHTML = '';
     if (comments.length === 0) {
         messagesHTML = '<div class="chat-message system-message">No messages yet.</div>';
     } else {
         comments.forEach(comment => {
             const messageDate = new Date(comment.timestamp);
             const timeString = messageDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
             const isAdminClass = comment.is_admin ? ' admin-message' : '';
             const deleteButtonHTML = isAdminMode ? `<button class="delete-comment-btn" data-comment-id="${comment.id}">❌</button>` : '';
             const imageHTML = comment.image_url ? `<br><a href="${comment.image_url}" target="_blank"><img src="${comment.image_url}" alt="User image" class="chat-image"></a>` : '';

             messagesHTML += `
                 <div class="chat-message${isAdminClass}" data-comment-id="${comment.id}">
                     <span class="timestamp">${timeString}</span>
                     <span class="message-text">${comment.text}</span>
                     ${imageHTML}
                     ${deleteButtonHTML}
                 </div>
             `;
         });
     }

     // *** Set innerHTML once ***
     // console.log("Setting innerHTML with:", messagesHTML);
     chatMessages.innerHTML = messagesHTML;

     // *** Add delete listeners AFTER setting innerHTML ***
     if (isAdminMode) {
         addDeleteButtonListeners();
     }

     lastComments = comments; // Update the cache
  }

  // --- Helper to add delete listeners ---
  function addDeleteButtonListeners() {
      document.querySelectorAll('.delete-comment-btn').forEach(button => {
          // Remove existing listener to prevent duplicates if re-rendering
          button.removeEventListener('click', handleDeleteComment);
          // Add the listener
          button.addEventListener('click', handleDeleteComment);
      });
  }

  // --- Handle Delete Comment ---
  function handleDeleteComment(event) {
      const commentId = event.target.getAttribute('data-comment-id');
      if (!commentId) return;

      if (confirm('Are you sure you want to delete this comment?')) {
          fetch(`/api/comments/${commentId}`, {
              method: 'DELETE',
          })
          .then(response => response.json())
          .then(data => {
              if (data.success) {
                  // Remove the comment element from the DOM immediately
                  const commentElement = event.target.closest('.chat-message');
                  if (commentElement) {
                      commentElement.remove();
                  }
                  // Optionally, re-fetch comments if not using SSE to ensure consistency
                  if (!useSSE) {
                      fetchComments();
                  }
              } else {
                  alert('Error deleting comment: ' + (data.error || 'Unknown error'));
              }
          })
          .catch(error => {
              console.error('Error deleting comment:', error);
              alert('Error deleting comment. Please try again.');
          });
      }
  }

  // --- Play Beep ---
  function playBeep() {
      beepSound.play().catch(error => console.error("Error playing beep:", error));
  }

  // --- Handle Image Upload ---
  function uploadImage(file) {
      // Client-side validation (optional but good UX)
      const allowedTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
      if (!allowedTypes.includes(file.type)) {
          alert('Invalid file type. Please upload PNG, JPG, GIF, or WEBP.');
          return;
      }
      if (file.size > 5 * 1024 * 1024) { // 5MB limit
          alert('File is too large. Maximum size is 5MB.');
          return;
      }

      const formData = new FormData();
      formData.append('image', file);

      // Display temporary feedback (optional)
      imageUrlInput.value = 'Uploading...';
      imageUrlInput.disabled = true;

      fetch('/api/upload_image', {
          method: 'POST',
          body: formData
      })
      .then(response => response.json())
      .then(data => {
          if (data.success && data.url) {
              imageUrlInput.value = data.url; // Set the URL in the input field
              // Optionally send the message automatically after upload
              // sendComment(); // <-- Keep this commented or uncomment based on desired UX
          } else {
              alert('Image upload failed: ' + (data.error || 'Unknown error'));
              imageUrlInput.value = ''; // Clear field on error
          }
      })
      .catch(error => {
          console.error('Error uploading image:', error);
          alert('Image upload failed. Please try again.');
          imageUrlInput.value = ''; // Clear field on error
      })
      .finally(() => {
           imageUrlInput.disabled = false; // Re-enable input
           // If not auto-sending, keep 'Uploading...' text until user clears/sends
           if (imageUrlInput.value === 'Uploading...') {
               imageUrlInput.value = '';
           }
      });
  }

  // --- Send Comment ---
  function sendComment() {
    const text = messageInput.value.trim();
    const imageUrl = imageUrlInput.value.trim();

    if (!text && !imageUrl) {
      alert('Please enter a message or an image URL.');
      return;
    }

    sendButton.disabled = true; // Prevent double sending
    sendButton.textContent = 'Sending...';

    fetch('/api/comments', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text: text, image_url: imageUrl }),
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        messageInput.value = ''; // Clear input fields
        imageUrlInput.value = '';
        // Fetch comments immediately ONLY if using polling
        if (!useSSE) {
            fetchComments();
        }
        // If using SSE, the update will arrive via the stream
      } else {
        alert('Error sending comment: ' + (data.error || 'Unknown error'));
      }
    })
    .catch(error => {
      console.error('Error sending comment:', error);
      alert('Error sending comment. Please try again.');
    })
    .finally(() => {
      sendButton.disabled = false;
      sendButton.textContent = 'Send';
    });
  }

  // --- Drag and Drop ---
  chatInputArea.addEventListener('dragover', (e) => {
      e.preventDefault(); // Prevent default behavior (opening file)
      e.stopPropagation();
      chatInputArea.classList.add('dragover'); // Add visual feedback class
  });

  chatInputArea.addEventListener('dragleave', (e) => {
      e.preventDefault();
      e.stopPropagation();
      chatInputArea.classList.remove('dragover'); // Remove visual feedback
  });

  chatInputArea.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      chatInputArea.classList.remove('dragover'); // Remove visual feedback

      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          const file = e.dataTransfer.files[0]; // Handle the first dropped file
          uploadImage(file);
          e.dataTransfer.clearData(); // Clear drag data cache
      }
  });

  // --- Event Listeners ---
  sendButton.addEventListener('click', sendComment); // Add listener for send button

  // Add listener for Enter key in textarea
  messageInput.addEventListener('keypress', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) { // Send on Enter, allow Shift+Enter for newline
          e.preventDefault(); // Prevent default Enter behavior (newline)
          sendComment();
      }
  });

  // --- Initialize SSE Connection (Only if useSSE is true) ---
  let sseReconnectTimer = null;
  const SSE_MAX_LIFETIME = 15000; // 15 seconds
  const SSE_RECONNECT_DELAY = 1000; // 1 second
  let sseLastActivity = null;
  let enableSSEReconnect = false; // Set to true to enable periodic disconnect/reconnect

  function closeSSE() {
      if (eventSource) {
          eventSource.close();
          eventSource = null;
      }
      if (sseReconnectTimer) {
          clearTimeout(sseReconnectTimer);
          sseReconnectTimer = null;
      }
  }

  function scheduleSSEReconnect() {
      if (!enableSSEReconnect) return;
      if (sseReconnectTimer) clearTimeout(sseReconnectTimer);
      sseReconnectTimer = setTimeout(() => {
          if (eventSource) {
              eventSource.close();
              eventSource = null;
          }
          setTimeout(() => {
              if (chatContainer.style.display !== 'none') {
                  initializeSSE();
              }
          }, SSE_RECONNECT_DELAY);
      }, SSE_MAX_LIFETIME);
  }

  function initializeSSE() {
      if (!useSSE || eventSource) {
          return;
      }
      if (chatContainer.style.display === 'none') {
          return;
      }
      eventSource = new EventSource('/api/comments/stream');
      sseLastActivity = Date.now();
      scheduleSSEReconnect();
      eventSource.onopen = function() {
          loadingIndicator.style.display = 'none';
          sseLastActivity = Date.now();
          scheduleSSEReconnect();
      };
      eventSource.onmessage = function(event) {
          try {
              const comments = JSON.parse(event.data);
              renderComments(comments);
          } catch (e) {
              console.error("Error parsing SSE data:", e);
          }
          sseLastActivity = Date.now();
          scheduleSSEReconnect();
      };
      eventSource.addEventListener('new_comment', function(event) {
          try {
              const comments = JSON.parse(event.data);
              renderComments(comments);
          } catch (e) {
              console.error("Error parsing SSE new_comment:", e);
          }
          sseLastActivity = Date.now();
          scheduleSSEReconnect();
      });
      eventSource.onerror = function(err) {
          loadingIndicator.textContent = 'Connection error. Retrying...';
          loadingIndicator.style.display = 'block';
          if (eventSource) eventSource.close();
          eventSource = null;
          if (sseReconnectTimer) clearTimeout(sseReconnectTimer);
          setTimeout(() => {
              if (chatContainer.style.display !== 'none') {
                  initializeSSE();
              }
          }, SSE_RECONNECT_DELAY);
      };
  }

  // --- Initial Load & Polling/SSE Start ---
  // Do NOT start polling or SSE until chat is made visible by the user.
  // (No polling or fetching on page load)
  // If chat starts hidden, SSE/Polling will be started by the toggle button.
  console.log("Chat will not poll or fetch until made visible by user.");

});

// Config page JS: apply settings and enable drag-and-drop ordering
document.addEventListener('DOMContentLoaded', function() {
  // Only run on config page
  if (!document.querySelector('.config-container')) return;

  // Theme and font classes are already applied by the main DOMContentLoaded listener.
  // We just need to ensure the dropdowns on the config page reflect the cookie values.

  var themeMatch = document.cookie.match(/(?:^|; )Theme=([^;]+)/);
  var currentTheme = themeMatch ? themeMatch[1] : 'silver';
  var themeSelectConfig = document.querySelector('.config-container #theme-select'); // More specific selector
  if (themeSelectConfig) themeSelectConfig.value = currentTheme;


  var fontMatchCookie = document.cookie.match(/(?:^|; )FontFamily=([^;]+)/);
  var currentFont = fontMatchCookie ? fontMatchCookie[1] : 'sans-serif';
  var fontSelectConfig = document.querySelector('.config-container #font-select'); // More specific selector
  if (fontSelectConfig) fontSelectConfig.value = currentFont;


  var nuMatch = document.cookie.match(/(?:^|; )NoUnderlines=([^;]+)/);
  var noUnderlinesConfig = document.querySelector('.config-container input[name="no_underlines"]'); // Adjust if selector is different
  if (noUnderlinesConfig) noUnderlinesConfig.checked = (!nuMatch || nuMatch[1] === '1');


  // Drag-and-drop for URL entries
  const urlEntries = document.querySelectorAll('.url-entry');
  let draggedItem = null;
  urlEntries.forEach(entry => {
    entry.addEventListener('dragstart', function() {
      draggedItem = this;
      setTimeout(() => this.style.display = 'none', 0);
    });
    entry.addEventListener('dragend', function() {
      setTimeout(() => {
        this.style.display = 'block';
        draggedItem = null;
      }, 0);
    });
    entry.addEventListener('dragover', function(e) { e.preventDefault(); });
    entry.addEventListener('dragenter', function(e) {
      e.preventDefault();
      this.style.border = '2px dashed #000';
    });
    entry.addEventListener('dragleave', function() { this.style.border = ''; });
    entry.addEventListener('drop', function() {
      this.style.border = '';
      if (this !== draggedItem) {
        const allEntries = Array.from(urlEntries);
        const draggedIndex = allEntries.indexOf(draggedItem);
        const targetIndex = allEntries.indexOf(this);
        if (draggedIndex < targetIndex) {
          this.parentNode.insertBefore(draggedItem, this.nextSibling);
        } else {
          this.parentNode.insertBefore(draggedItem, this);
        }
        // Update priority inputs
        const updatedEntries = document.querySelectorAll('.url-entry');
        updatedEntries.forEach((ent, idx) => {
          const priorityInput = ent.querySelector('input[type="number"]');
          if (priorityInput) priorityInput.value = (idx + 1) * 10;
        });
      }
    });
  });
});

// --- Old Headlines Admin Delete Button ---
(function() {
  // Only run on old_headlines page
  const archiveContainer = document.querySelector('.headline-archive-container');
  if (!archiveContainer) return;
  // is_admin is injected as a global variable by Jinja
  const isAdmin = typeof window.isAdmin !== 'undefined' ? window.isAdmin : (document.cookie.split('; ').some(item => item.trim().startsWith('isAdmin=1')));
  if (isAdmin) {
    archiveContainer.addEventListener('click', function(e) {
      if (e.target.classList.contains('delete-headline-btn')) {
        const entry = e.target.closest('.headline-entry');
        const url = entry.getAttribute('data-url');
        const timestamp = entry.getAttribute('data-timestamp');
        if (confirm('Delete this headline?')) {
          fetch('/api/delete_headline', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, timestamp })
          })
          .then(r => r.json())
          .then(resp => {
            if (resp.success) {
              entry.remove();
            } else {
              alert('Delete failed: ' + (resp.error || 'Unknown error'));
            }
          })
          .catch(() => alert('Delete failed.'));
        }
      }
    });
  }
})();
