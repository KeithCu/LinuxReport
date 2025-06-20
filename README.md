![LinuxReport logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/linuxreportfancy.webp)
**and**
![CovidReport logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/covidreportfancy.webp)
**and**
![AIReport_logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/aireportfancy.webp)
--------------------------------------------------------------------------------
Simple and fast news site based on Python / Flask. Meant to be a http://drudgereport.com/ clone for Linux or Covid-19 news, updated automatically 24/7, and customizable by the user, including custom feeds and the critically important dark mode.

Here's the running code for Linux, Covid, and AI, Solar / PV, and Detroit Techno:

https://linuxreport.net 

https://covidreport.org

https://aireport.keithcu.com

https://pvreport.org

https://news.thedetroitilove.com

Takes advantage of thread pools and Apache process pools to be high-performance and scalable. Some people incorrectly say that Python is slow, but this app typically starts returning the page after less than 10 lines of my Python code.

It now auto-updates the top headlines using LLMs through [OpenRouter.ai](https://openrouter.ai), which provides access to a wide variety of AI models. To keep things interesting, the system randomly selects from over 30 free models, including [Llama 4](https://openrouter.ai/models/meta-llama/llama-4-maverick), [Qwen](https://openrouter.ai/models/qwen/qwen3-32b), and [Mistral](https://openrouter.ai/models/mistralai/mistral-small-3.1-24b-instruct) variants. If a model fails, it falls back to [Mistral Small](https://openrouter.ai/models/mistralai/mistral-small-3.1-24b-instruct) - a solid, inexpensive model that consistently delivers good headlines. See the [model selection logic](https://github.com/KeithCu/LinuxReport/blob/master/auto_update.py) in `auto_update.py`.

Feel free to request more default RSS feeds, or send pull requests.

Web servers need a configuration file to tell it where the flask software is located. A sample Apache one is included.

```bash
$ git clone https://github.com/KeithCu/LinuxReport
$ cd linuxreport
$ sudo pip install -r requirements.txt
$ python -m flask run
```

## FastAPI vs Flask for This Project

While FastAPI is a modern, high-performance framework with excellent async support, this project intentionally uses Flask for several reasons:

1. **Simplicity**: Flask's synchronous model is straightforward and matches the project's needs. The current implementation uses thread pools and Apache process pools for scaling, which works well for this use case.

2. **Maturity**: Flask has been battle-tested for years and has a vast ecosystem of extensions and community support.

3. **Performance**: The current implementation achieves good performance through thread pools and caching.

4. **Development Speed**: Flask's simplicity allows for rapid development and easier maintenance, which is crucial for a project that needs to be easily modifiable.

While FastAPI offers benefits like automatic API documentation, better type checking, and modern async support, these advantages are less relevant for this project because:
- The site primarily serves HTML pages rather than JSON APIs
- The current synchronous code is already performant enough
- The project doesn't heavily utilize type hints
- The existing thread pool implementation works well for the use case

If you're considering switching to FastAPI, you would need to:
1. Rewrite the core application logic
2. Modify the Apache configuration
3. Potentially restructure the caching system
4. Update all dependencies and extensions

The effort required for this switch might not justify the benefits for this specific use case.

## Admin Mode Security

The application has an admin mode that allows editing headlines and other admin-only functions. Admin mode is protected by a password stored in `config.yaml`.

The repository includes a default config file with a default password:

```yaml
# LinuxReport Configuration
# IMPORTANT: Change this default password for security!

# Admin settings
admin:
  password: "LinuxReportAdmin2024"
```

**IMPORTANT:** For security, you should change the default password immediately after cloning the repository by editing the `config.yaml` file.

Suggestions from O4-mini:
Here are some next‑step ideas that don't appear to be in place yet:

Metrics & monitoring
– Instrument page views, fetch success rates, and feed latencies; plug into Prometheus/Grafana or at least log structured metrics.

Dashboard & charts
– Visualize feed health over time (last‑fetch timestamps, entry counts) with a small admin dashboard.

User‑customizable templates
– Let advanced users tweak the HTML "sitebox" template or column layout via a settings page.

Automated testing
– Introduce pytest/unittest suites for your routes, forms, cache interactions, and utility modules; enforce coverage thresholds.

Server‑side user accounts & persistent settings
– Replace cookie‑only prefs with Flask‑Login (or OAuth) and store each user's favorites, feed order, dark/light mode in a database.

Read/unread and bookmarking
– Track which articles a user has seen and let them "star" or archive items for later.

Full‑text search & filtering
– Index entries (e.g. via Whoosh or Elasticsearch) so users can search across all feeds and filter by keyword, date, or tag.

Scheduled background jobs
– Instead of fetching on demand or thread triggers, use Celery or APScheduler to run periodic feed updates, prune old data, and send alerts.

Notifications & alerts
– Push e‑mail or Slack/Webhook notifications when keywords appear in new items or a feed fails.

API expansion & docs
– Expose a RESTful JSON API for feed listings, entries, and user settings; add Swagger/OpenAPI docs and rate limiting.

Internationalization
– Use Flask‑Babel so UI text and date formatting adapt to user locales.

Containerization & CI/CD
– Add a Dockerfile + docker‑compose, and set up GitHub Actions (lint, tests, build, deploy).


User-oriented features: 

1. Headline Search: Add a search bar to quickly find past headlines or stories by keyword or date.
2. Save/Bookmark Headlines: Allow users to save interesting headlines for later reading.
3. Trending Topics & Word Clouds: Visualize the most mentioned topics or keywords from recent headlines.
4. Headline Timeline: Let users browse headlines by date, seeing how stories evolved over time.
5. Headline Comparison: Highlight how different sources report the same story, showing side-by-side headlines or summaries.
6. Local News Integration: Show local news based on user location or selected region.
7. RSS/Atom Export: Let users export their custom feed or archive as RSS/Atom for use in other readers.
8. Newsletter/Email Alerts: Send users a daily or breaking-news email with top headlines or topics they follow.
9. Commenting & Reactions: Let users comment on or react to headlines (e.g., thumbs up/down, emojis).
10. "On This Day" Feature: Show headlines from the same day in previous years for historical context.
11. Fact-Check Highlights: Flag stories that have been fact-checked, with links to sources.
12. Audio Summaries: Offer text-to-speech for top headlines or summaries, so users can listen on the go.
13. Integration with Calendar: Let users add important news events to their calendar.
14. Polls & Quick Surveys: Engage users with polls about current events or site features.

These features can help make your site more interactive, personalized, and useful for regular visitors.

## Feature Suggestions (May 23, 2025 - Claude AI)

Here are some suggested features to enhance user engagement and functionality:

1. **User Accounts & Personalization** (High Impact)
   - Allow users to create accounts to save their preferences
   - Enable personalized feed curation and layout preferences
   - Store dark/light mode preference persistently
   - This would significantly increase user retention and engagement

2. **Enhanced Search & Filtering** (High Impact)
   - Add a search bar to find headlines across all feeds
   - Implement filters for date ranges, sources, and topics
   - Add tags/categories to headlines for better organization
   - This would make your site more useful for research and following specific topics

3. **Mobile App Experience** (High Impact)
   - Since you already have Mobility support, enhance the mobile experience
   - Add a "Add to Home Screen" feature for PWA support
   - Implement pull-to-refresh and infinite scroll
   - This would help capture mobile users who prefer app-like experiences

4. **Social Features** (Medium Impact)
   - Add ability to share headlines directly to social media
   - Implement a "Save for Later" feature
   - Add a "Most Popular" section based on user interactions
   - This would increase viral growth and user engagement

5. **Notification System** (Medium Impact)
   - Allow users to subscribe to breaking news alerts
   - Implement keyword-based notifications
   - Add email digests for daily summaries
   - This would increase return visits and user engagement

6. **Analytics Dashboard** (Medium Impact)
   - Add a simple dashboard showing most-read headlines
   - Display trending topics
   - Show feed health metrics
   - This would help users understand what's popular and what's working

7. **API Access** (Medium Impact)
   - Create a public API for your headlines
   - Allow developers to integrate your content
   - Add rate limiting and API keys
   - This would expand your reach to other platforms

8. **Enhanced Content Features** (Low Impact)
   - Add "Related Stories" section
   - Implement "On This Day" historical headlines
   - Add brief summaries for headlines
   - This would increase content engagement

9. **Performance Optimizations** (Low Impact)
   - Implement lazy loading for images
   - Add better caching strategies
   - Optimize mobile performance
   - This would improve user experience and retention

10. **Internationalization** (Low Impact)
    - Add support for multiple languages
    - Implement region-specific feeds
    - Add timezone support
    - This would expand your global reach

### AI-Enhanced Features
Building on your existing Together.ai integration:
- Add AI-generated summaries for headlines
- Implement AI-powered topic clustering
- Use AI to detect and highlight breaking news
- Add AI-powered content recommendations

## Progressive Web App (PWA) Implementation Plan

### Overview
This plan outlines the steps to transform LinuxReport into a Progressive Web App, enabling offline access and an app-like experience while maintaining the site's simplicity and performance.

### Implementation Steps

1. **Phase 1: Foundation Setup (2-3 hours)**
   - Create `templates/service-worker.js` with your existing cache system
   - Integrate with your current JavaScript compilation system in `app.py`
   - Add service worker registration to your existing `core.js`
   - Create `static/manifest.json` with your site's branding
   -(don't do now) Generate PWA icons in `static/icons/` using your existing logo
   - Update `templates/base.html` with PWA meta tags

2. **Phase 2: Flask Integration (1-2 hours)**
   - Add service worker route to `routes.py`
   - Add manifest route to `routes.py`
   - Update static file serving in Apache config (Updated the file httpd-vhosts-sample.conf)
   - Integrate with your existing `diskcache` system
   - Update service worker caching strategy
   - Implement cache versioning with your existing system

3. **Phase 3: Performance Optimization (1-2 hours)**
   - Optimize PWA icons using your existing image processing
   - Implement proper caching strategies
   - Use your existing static file optimization
   - Implement proper preloading
   - Use your existing JavaScript optimization
   - Leverage your current caching system

4. **Phase 4: Security and Testing (1-2 hours)**
   - Ensure HTTPS requirement
   - Update Apache configuration
   - Implement proper cache headers
   - Set appropriate cache durations
   - Test offline functionality
   - Verify cache behavior
   - Check cross-browser compatibility
   - Validate PWA requirements

5. **Phase 5: Integration with Existing Systems (1-2 hours)**
   - Update your existing `core.js` compilation
   - Integrate with your current cache busting
   - Add PWA-specific functionality
   - Update your Apache configuration
   - Ensure proper serving of PWA assets
   - Integrate with your CDN setup

6. **Phase 6: Documentation and Deployment (1-2 hours)**
   - Update `README.md` with PWA information
   - Document PWA features in `agents.md`
   - Add PWA configuration to `config.yaml`
   - Update deployment scripts
   - Configure production environment
   - Set up monitoring for PWA metrics

### Implementation Details

1. **Service Worker Integration**
   ```javascript
   // Add this to your existing JavaScript file (e.g., linuxreport.js)
   if ('serviceWorker' in navigator) {
       window.addEventListener('load', () => {
           navigator.serviceWorker.register('/service-worker.js')
               .then(registration => {
                   console.log('ServiceWorker registration successful');
               })
               .catch(err => {
                   console.log('ServiceWorker registration failed: ', err);
               });
       });
   }
   ```

2. **Service Worker File** (must be separate file: `service-worker.js`)
   ```javascript
   // This must be in a separate file: service-worker.js
   //Service workers run in a different context than your main JavaScript
   //They need to be able to intercept network requests
   //They need to be able to work even when your main JavaScript isn't running
   //They need to be able to update independently of your main application

   const CACHE_VERSION = 'v1';
   const CACHE_NAME = `linuxreport-${CACHE_VERSION}`;
   const STATIC_ASSETS = [
       '/',
       '/static/linuxreport.css',
       '/static/linuxreport.js',
       '/static/manifest.json'
   ];

   self.addEventListener('install', (event) => {
       event.waitUntil(
           caches.open(CACHE_NAME)
               .then(cache => cache.addAll(STATIC_ASSETS))
       );
   });

   self.addEventListener('fetch', (event) => {
       event.respondWith(
           caches.match(event.request)
               .then(response => response || fetch(event.request))
       );
   });
   ```

3. **Flask Integration**
   ```python
   # app.py additions
   @app.route('/service-worker.js')
   def service_worker():
       response = make_response(
           send_from_directory('static/js', 'service-worker.js')
       )
       response.headers['Content-Type'] = 'application/javascript'
       response.headers['Service-Worker-Allowed'] = '/'
       return response

   @app.route('/static/manifest.json')
   def manifest():
       return send_from_directory('static', 'manifest.json')
   ```

4. **Apache Configuration**
   ```apache
   # httpd-vhosts-sample.conf additions
   <VirtualHost *:80>
       # ... existing configuration ...
       
       # PWA specific headers
       Header set Service-Worker-Allowed "/"
       Header set Cache-Control "public, max-age=31536000"
       
       # ... rest of configuration ...
   </VirtualHost>
   ```

5. **JavaScript Integration**
   ```javascript
   // templates/core.js additions
   if ('serviceWorker' in navigator) {
       window.addEventListener('load', () => {
           navigator.serviceWorker.register('/static/js/service-worker.js')
               .then(registration => {
                   console.log('ServiceWorker registration successful');
               })
               .catch(err => {
                   console.log('ServiceWorker registration failed: ', err);
               });
       });
   }
   ```

This implementation plan takes advantage of your existing:
- JavaScript compilation system
- Cache management
- Static file serving
- Apache configuration
- Image processing
- Documentation structure

The implementation follows your existing patterns and integrates seamlessly with your current architecture while adding PWA capabilities.

## PWA Caching Integration

The application uses multiple caching layers that need to be integrated with the PWA service worker:

### Existing Caching System

1. **In-Memory Caching** (`cacheout` - via `g_cm`)
   - Location: `shared.py`
   - Purpose: Caches full pages and RSS templates
   - Integration: Use for dynamic content caching in service worker

2. **Disk-Based Caching** (`diskcache` - via `g_c`)
   - Location: `shared.py`
   - Purpose: Persistent storage for weather data, chat comments, banned IPs
   - Integration: Use for offline data storage

3. **Flask-Assets Asset Management**
   - Location: `app.py`
   - Purpose: Automatic asset bundling, minification, and cache busting
   - Integration: Use compiled assets for service worker

### Service Worker Implementation

1. **Cache Strategies**
   - Static Assets: Cache First with Flask-Assets versioning
   - Dynamic Content: Network First with fallback to cache
   - API Responses: Stale While Revalidate
   - Offline Content: Cache First with offline fallback

2. **Cache Management**
   - Use separate caches for different content types
   - Implement cache cleanup based on size and age
   - Handle cache versioning using Flask-Assets system

3. **Offline Support**
   - Cache essential static assets
   - Store dynamic content in IndexedDB
   - Provide offline fallback page
   - Sync data when back online

4. **Performance Optimization**
   - Use Flask-Assets compiled assets
   - Implement proper cache headers
   - Optimize asset loading
   - Handle background sync

### Implementation Steps

1. **Service Worker Setup**


2. **Cache Configuration**
   ```javascript
   // Cache names
   const STATIC_CACHE = 'static-v1';
   const DYNAMIC_CACHE = 'dynamic-v1';
   const OFFLINE_CACHE = 'offline-v1';
   ```

3. **Cache Strategies**
   ```javascript
   // Static assets - Cache First
   async function cacheFirst(request) {
     const cached = await caches.match(request);
     return cached || fetch(request);
   }

   // Dynamic content - Network First
   async function networkFirst(request) {
     try {
       const response = await fetch(request);
       const cache = await caches.open(DYNAMIC_CACHE);
       cache.put(request, response.clone());
       return response;
     } catch (error) {
       return caches.match(request);
     }
   }
   ```

4. **Offline Support**
   ```javascript
   // Offline fallback
   async function offlineFallback() {
     const cache = await caches.open(OFFLINE_CACHE);
     return cache.match('/offline.html');
   }
   ```

### Important Notes

1. **Cache Versioning**
   - Use Flask-Assets versioning
   - Update cache names when content changes
   - Handle cache cleanup properly

2. **Performance Considerations**
   - Cache only necessary assets
   - Implement proper cache headers
   - Use compression for cached content
   - Handle cache size limits

3. **Security**
   - Validate cached content
   - Handle sensitive data properly
   - Implement proper CORS headers
   - Use HTTPS for all requests

4. **Testing**
   - Test offline functionality
   - Verify cache strategies
   - Check performance impact
   - Validate security measures

## Phase 2: Flask Integration

### 1. Update Flask Configuration

1. **Add PWA Configuration**
   ```python
   # In app.py
   PWA_CONFIG = {
       'name': 'LinuxReport',
       'short_name': 'LR',
       'description': 'Linux, AI, and Tech News Aggregator',
       'start_url': '/',
       'display': 'standalone',
       'background_color': '#ffffff',
       'theme_color': '#000000',
       'icons': [
           {
               'src': '/static/icons/icon-192x192.png',
               'sizes': '192x192',
               'type': 'image/png'
           },
           {
               'src': '/static/icons/icon-512x512.png',
               'sizes': '512x512',
               'type': 'image/png'
           }
       ]
   }
   ```

2. **Add PWA Routes**
   ```python
   # In routes.py
   @app.route('/manifest.json')
   def manifest():
       return jsonify(PWA_CONFIG)

   @app.route('/offline.html')
   def offline():
       return render_template('offline.html')

   @app.route('/service-worker.js')
   def service_worker():
       response = make_response(
           render_template('service-worker.js'),
           200,
           {'Content-Type': 'application/javascript'}
       )
       response.headers['Service-Worker-Allowed'] = '/'
       return response
   ```

3. **Update Base Template**
   ```html
   <!-- In templates/base.html -->
   <head>
       <!-- Add these lines -->
       <link rel="manifest" href="{{ url_for('manifest') }}">
       <meta name="theme-color" content="#000000">
       <meta name="apple-mobile-web-app-capable" content="yes">
       <meta name="apple-mobile-web-app-status-bar-style" content="black">
       <link rel="apple-touch-icon" href="{{ url_for('static', filename='icons/icon-192x192.png') }}">
   </head>
   ```

### 2. Create PWA Templates

1. **Create offline.html**
   ```html
   <!-- In templates/offline.html -->
   <!DOCTYPE html>
   <html>
   <head>
       <title>Offline - LinuxReport</title>
       <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
   </head>
   <body>
       <div class="offline-container">
           <h1>You're Offline</h1>
           <p>Please check your internet connection and try again.</p>
           <button onclick="window.location.reload()">Retry</button>
       </div>
   </body>
   </html>
   ```

2. **Create service-worker.js Template**
   ```javascript
   // In templates/service-worker.js
   const CACHE_NAME = 'linuxreport-v1';
   const OFFLINE_URL = '/offline.html';

   const STATIC_ASSETS = [
       '/',
       '/offline.html',
       '/static/css/style.css',
       '/static/js/linuxreport.js',
       '/static/icons/icon-192x192.png',
       '/static/icons/icon-512x512.png'
   ];

   self.addEventListener('install', (event) => {
       event.waitUntil(
           caches.open(CACHE_NAME)
               .then((cache) => cache.addAll(STATIC_ASSETS))
       );
   });

   self.addEventListener('fetch', (event) => {
       if (event.request.mode === 'navigate') {
           event.respondWith(
               fetch(event.request)
                   .catch(() => caches.match(OFFLINE_URL))
           );
       } else {
           event.respondWith(
               caches.match(event.request)
                   .then((response) => response || fetch(event.request))
           );
       }
   });
   ```

### 3. Add PWA Registration

1. **Update core.js**
   ```javascript
   // In templates/core.js
   // Add at the beginning of the file
   if ('serviceWorker' in navigator) {
       window.addEventListener('load', () => {
           navigator.serviceWorker.register('/service-worker.js')
               .then(registration => {
                   console.log('ServiceWorker registration successful');
               })
               .catch(err => {
                   console.log('ServiceWorker registration failed: ', err);
               });
       });
   }
   ```

### 4. Create PWA Icons

1. **Generate Icons**
   - Create 192x192 and 512x512 PNG icons
   - Place in `static/icons/` directory
   - Ensure icons follow PWA guidelines:
     - Simple, recognizable design
     - No transparency
     - Safe area for different devices
     - Proper padding

2. **Icon Requirements**
   - Format: PNG
   - Sizes: 192x192 and 512x512
   - Background: Solid color
   - No transparency
   - Clear visibility at small sizes

### 5. Update Static File Handling

1. **Add Cache Headers**
   ```python
   # In app.py
   @app.after_request
   def add_cache_headers(response):
       if request.path.startswith('/static/'):
           response.headers['Cache-Control'] = 'public, max-age=31536000'
       return response
   ```

2. **Update Static File Hash Function**
   ```python
   # In app.py
   @lru_cache()
   def static_file_hash(filename):
       """Generate hash for static files, including PWA assets."""
       if filename == 'linuxreport.js':
           return get_combined_hash()
       try:
           with open(os.path.join(app.static_folder, filename), 'rb') as f:
               return hashlib.md5(f.read()).hexdigest()
       except:
           return str(time.time())
   ```

### 6. Testing Checklist

1. **Basic PWA Features**
   - [ ] Manifest loads correctly
   - [ ] Service worker registers
   - [ ] Icons display properly
   - [ ] Offline page works
   - [ ] Add to home screen works

2. **Caching**
   - [ ] Static assets cache properly
   - [ ] Dynamic content updates
   - [ ] Offline functionality works
   - [ ] Cache versioning works

3. **Performance**
   - [ ] Page loads quickly
   - [ ] Assets load from cache
   - [ ] No unnecessary network requests
   - [ ] Smooth offline experience

4. **Browser Compatibility**
   - [ ] Works in Chrome
   - [ ] Works in Firefox
   - [ ] Works in Safari
   - [ ] Works in Edge

