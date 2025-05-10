![LinuxReport logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/linuxreportfancy.webp)
**and**
![CovidReport logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/covidreportfancy.webp)
**and**
![AIReport_logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/aireportfancy.webp)
--------------------------------------------------------------------------------
Simple and fast news site based on Python / Flask. Meant to be a http://drudgereport.com/ clone for Linux or Covid-19 news, updated automatically 24/7, and customizable by the user, including custom feeds and the critically important dark mode.

Here's the running code for Linux, Covid, and AI:

https://linuxreport.net 

https://covidreport.org

https://aireport.keithcu.com/

Takes advantage of thread pools and process pools to be high-performance and scalable. Some people incorrectly say that Python is slow, but this app typically starts returning the page after less than 10 lines of my Python code.

It now auto-updates the top headlines using LLMs and https://api.together.ai/. They have inexpensive and high-performance inference. I can make 300 of these requests to Meta's Llama 3.3-70B for $1. I tried other models but they didn't work as well, but there are cheaper ones to consider. See https://github.com/KeithCu/LinuxReport/blob/master/auto_update.py.

Feel free to request more default RSS feeds, or send pull requests.

Web servers need a configuration file to tell it where the flask software is located. A sample Apache one is included.

```bash
$ git clone https://github.com/KeithCu/LinuxReport
$ cd linuxreport
$ sudo pip install -r requirements.txt
$ python -m flask run
```

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

## Scaling Plan

As LinuxReport grows in popularity, this scaling plan provides a roadmap for efficiently handling increased traffic while maintaining cost-effectiveness.

### Current Setup
- Single server (Linode Nanode 1GB/$5/month)
- All components (web server, feed fetching, content generation) on one machine
- Good performance for current traffic levels with existing Python page caching
- Benchmark: ~350 requests per second on a single processor (CPU-saturated)
  - Using standard CPython (not PyPy yet) with mod_wsgi and 2 worker processes
  - Running on AMD EPYC processor (Linode's standard CPU)
  - Performance scales near-linearly with additional CPUs/cores running their own processes
  - Current configuration of 2 worker processes saturates a single CPU core
- User capacity: Can handle approximately 2-3 million daily active users
  - Assuming average user loads 2-3 pages per visit
  - With typical diurnal traffic patterns (peak:average ratio of ~3:1)
  - Translates to ~30 million daily page views

### Scaling Stages

#### Stage 1: Vertical Scaling (1-4 CPUs)
- Remain on Nanode 1GB ($5) until necessary
- Upgrade to Linode 2GB ($12) or 4GB ($24) when needed
- Optimize WSGI configuration
- **Foundational optimizations** that multiply the effectiveness of all other scaling strategies:
  - Move static assets to CDN using URL_IMAGES variable for offloading bandwidth (DONE)
  - Implement PyPy instead of CPython for significant performance boost (3-5x for CPU-bound operations)
  - These changes amplify the benefit of every subsequent scaling effort
  - Worth implementing early as they require minimal code changes with maximum impact
- **PyPy performance boost:** Consider using PyPy instead of CPython for a significant performance boost
  - Can provide 3-5x better throughput for CPU-bound operations
  - Compatible with most pure Python libraries used in LinuxReport
  - Simple change that requires minimal code modifications
  - Particularly effective for template rendering and feed processing
- **Cost:** $5-24/month + $5 / month CDN costs
- **When to implement:** When current server CPU consistently exceeds 70% during peak hours

#### Stage 2: Separation of Concerns (scaling to many front-ends)
- Split into dedicated servers:
  - Web server(s) (Linode 4GB/$24 each)
  - Single backend/feed processing server (Linode 4GB/$24 or 8GB/$48)
- No ZMQ needed at this stage (only one backend server)
- Add Apache front-end caching for non-customized content
  - Cookie-based cache bypass for custom layouts and admin mode
  - Separate caches for mobile vs. desktop views
- **Optional Simplified Front-End Architecture:**
  - Deploy full application code to all front-end servers
  - Two operational modes controlled by configuration:
    - **Master mode**: Runs background threads for feed fetching and auto-updates
    - **Front-end mode**: Disables background threads, fetches processed content from master
  - Front-end servers fetch and cache pre-processed content from backend:
    - Periodically retrieve already-fetched feed data from central backend
    - No direct proxying of feed fetching requests
    - Front-ends cache feed content until notified of updates
    - Only the backend directly interacts with source websites
  - Centralized backend responsibilities:
    - Feed fetching from source websites (with proper rate limiting)
      - Prevents IP bans from multiple servers hitting the same sources
      - Uses specialized access methods where needed (e.g., TOR for Reddit)
    - Auto-update process for headline generation
    - Notifying front-ends when new content is available
    - Weather data collection (centralized to minimize API requests)
      - Aggregates requests for the same cities
      - Maintains proper rate limiting for weather APIs
      - Distributes weather data to front-ends
  - Front-end servers handle everything else locally:
    - Page rendering
    - User customization
    - Static assets
    - Admin interface display
  - Benefits:
    - Simpler deployment (identical codebase with different mode settings)
    - Lower latency for most operations
    - Prevents getting banned by maintaining controlled access to source websites
    - Front-ends operate independently except for content refreshes
    - Easier fallback if backend goes down (can serve slightly stale content)
- **Highly scalable:** Can support 20-30+ front-end servers with a single backend
- **Cost:** $48+/month + CDN costs (scales with number of front-end servers)
- **When to implement:** When Stage 1 server consistently exceeds 70% CPU

#### Stage 3: Multi-Backend Architecture (for very high traffic)
- Continue scaling the Apache front-end cluster from Stage 2
- Add multiple backend servers (Linode 8GB/$48 each)
- Use lightweight synchronization options:
  - **Simple approach:** Periodic object storage checks (every 5-10 minutes)
    - Stagger check times across servers to minimize backend load
    - Can support dozens of backend servers with minimal overhead
    - Acceptable for feeds that update hourly
  - **Real-time approach:** Implement ZMQ for immediate feed update notifications
- **Cost:** $96+/month + storage and CDN costs
- **When to implement:** When approaching 20-30 front-end servers or when a single backend server reaches 70-80% CPU usage

### Implementation Details

#### Initial Optimization (Pre-scaling)
- Ensure Python-level page caching is maximized
- Profile application to identify bottlenecks
- Move static assets to CDN using URL_IMAGES variable (DONE)

#### Custom Front-End Caching Options

##### Option 1: Apache-Based Caching
- Standard approach using Apache's caching mechanisms
- Well-documented and stable solution
- Example Apache configuration:
  ```apache
  # Enable caching modules
  LoadModule cache_module modules/mod_cache.so
  LoadModule cache_disk_module modules/mod_cache_disk.so
  
  # Set up the cache location
  CacheRoot /var/cache/apache2/mod_cache_disk
  CacheDirLevels 2
  CacheDirLength 1
  
  # Cache only successful responses for a maximum of 1 hour
  CacheEnable disk /
  CacheHeader on
  CacheDefaultExpire 3600
  
  # Don't cache requests with cookies for custom layouts or admin
  <LocationMatch "/">
    CacheDisable "expr=%{HTTP_COOKIE} =~ /(custom_layout|is_admin)/"
  </LocationMatch>
  
  # Don't cache mobile views separately from desktop
  <LocationMatch "/">
    CacheDisable "expr=%{HTTP_USER_AGENT} =~ /(Mobile|Android|iPhone|iPad)/"
  </LocationMatch>
  
  # Configure backend proxy
  ProxyPass / http://backend-server:5000/
  ProxyPassReverse / http://backend-server:5000/
  ```

##### Option 2: Lightweight Python Caching Server (~20 lines)
- Simple WSGI app that sits in front of the main application
- Checks for special cookies (admin mode, custom layouts)
- Serves from memory for regular users
- Forwards requests to backend only when needed
- **Optimization:** Implement a webhook or simple notification system from backend to front-ends that invalidates cache when content changes
  - Allows indefinite caching with immediate updates 
  - Much more efficient than time-based expiration
- Very low memory footprint
- Easier to customize than Apache configurations
- Example Python implementation (conceptual):
  ```python
  import requests
  from flask import Flask, request, Response
  
  app = Flask(__name__)
  cache = {}  # Simple in-memory cache
  BACKEND_URL = "http://backend-server:5000"
  
  @app.route('/', defaults={'path': ''})
  @app.route('/<path:path>')
  def proxy(path):
      # Check for custom layout or admin cookies
      if 'custom_layout' in request.cookies or 'is_admin' in request.cookies:
          # Pass directly to backend
          return forward_to_backend(path)
          
      # Check for mobile user agent
      is_mobile = any(agent in request.headers.get('User-Agent', '') 
                      for agent in ['Mobile', 'Android', 'iPhone', 'iPad'])
          
      # Create cache key based on path and mobile status
      cache_key = f"{path}:{'mobile' if is_mobile else 'desktop'}"
      
      # Return cached response if available
      if cache_key in cache:
          return cache[cache_key]
      
      # Forward to backend and cache response
      response = forward_to_backend(path)
      cache[cache_key] = response
      return response
      
  def forward_to_backend(path):
      url = f"{BACKEND_URL}/{path}"
      resp = requests.request(
          method=request.method,
          url=url,
          headers={k: v for k, v in request.headers if k != 'Host'},
          data=request.get_data(),
          cookies=request.cookies,
          allow_redirects=False)
          
      return Response(resp.content, resp.status_code, resp.headers.items())
      
  # Webhook endpoint for cache invalidation
  @app.route('/invalidate_cache', methods=['POST'])
  def invalidate_cache():
      cache.clear()  # Simple full cache invalidation
      return "Cache cleared", 200
      
  if __name__ == '__main__':
      app.run(host='0.0.0.0', port=80)
  ```

#### Handling Cache-Busting for Static Assets

The application already utilizes cache-busting for CSS and JS files using version query parameters:

```html
<link rel="stylesheet" href="/static/linuxreport.css?v={{ static_file_hash('linuxreport.css') }}">
<script src="/static/linuxreport.js?v={{ static_file_hash('linuxreport.js') }}"></script>
```

This approach works well with both caching strategies:

##### With Apache-Based Caching
- Apache will recognize the different URLs as separate resources
- When files change, the `static_file_hash` function generates a new hash
- Updated files automatically get a new URL, bypassing previously cached versions
- No special configuration needed beyond the standard Apache cache setup

##### With Python Caching Server
- The caching server should preserve query parameters in cache keys
- **Properly cache static files** to avoid unnecessary backend requests
- Example implementation for static assets:
  ```python
  # Static file caching - efficient handling with version parameter
  @app.route('/static/<path:filename>')
  def serve_static(filename):
      # Include version parameter in cache key
      version = request.args.get('v', '')
      cache_key = f"static:{filename}:{version}"
      
      # Return cached version if available
      if cache_key in cache:
          return cache[cache_key]
      
      # Only request from backend when not in cache
      response = forward_to_backend(f"static/{filename}?{request.query_string.decode()}")
      
      # Cache indefinitely (static files with version params never change)
      # The version parameter ensures we get fresh content when files change
      cache[cache_key] = response
      return response
  ```

- **Graceful handling of outdated clients:**
  - Users with cached HTML pages from before an update will still request old JS/CSS versions
  - This approach serves those old versions from cache without hitting the backend
  - As users naturally refresh or navigate, they'll get the latest HTML with updated references
  - No forced refreshes or broken experiences for users with outdated cached pages
  - Server maintains ability to serve both old and new static asset versions simultaneously
  - Particularly helpful during gradual rollouts or when users have multiple tabs open

#### CDN with Versioned Filenames

For even better CDN performance, consider embedding the version hash directly in the filename instead of using query parameters:

- **Implementation approach:**
  - Modify the build process to generate versioned filenames:
    ```
    linuxreport-[hash].css
    linuxreport-[hash].js
    ```
  - Update the Flask code to track these filenames and provide them to templates
  - Benefits:
    - Better caching with some CDNs that ignore query strings
    - Longer cache lifetimes (set max-age to years)
    - Eliminate edge case caching issues entirely
  
- **Example implementation:**
  ```python
  # During JS/CSS compilation
  def compile_js_files():
      file_hash = get_combined_hash()
      output_file = f"linuxreport-{file_hash}.js"
      # Store the current versioned filename
      with open('static/js_version.json', 'w') as f:
          json.dump({'current': output_file}, f)
      # Write the combined JS to the versioned file
      # ...
  
  # In Flask app
  @lru_cache()
  def get_versioned_static_file(base_name):
      """Get the current versioned filename for a static asset"""
      if base_name == 'linuxreport.js':
          with open('static/js_version.json', 'r') as f:
              return json.load(f)['current']
      # Similar for CSS...
      
  # In Jinja template context
  app.jinja_env.globals['versioned_static'] = get_versioned_static_file
  
  # In the template
  # <script src="/static/{{ versioned_static('linuxreport.js') }}"></script>
  ```

- **CDN integration:**
  - Configure CDN to pull from your origin server
  - Set very long cache TTLs (1 year+) for versioned assets
  - Content is naturally invalidated when new files with new names are requested
  - Old versions can stay on the CDN indefinitely without any harm
  - No need to purge or invalidate cache entries

#### Gunicorn vs. mod_wsgi Considerations

When scaling beyond a single server, choosing the right WSGI server becomes important. Here's how the two primary options compare:

##### Gunicorn
- **Standalone WSGI server** that can run independently or behind Apache/Nginx
- **Worker flexibility:** Supports various worker types for different workloads
- **Performance:** Good throughput with proper worker configuration
- **Implementation:** Simpler setup with direct Python management
- **Scaling advantages:**
  - Configurable for different workload patterns
  - Worker processes automatically restart if they crash
  - Built-in load balancing between worker processes
- **Worker types for consideration:**
  - `sync`: Simple synchronous workers, good baseline option
  - `threads`: Thread-based workers for I/O-bound applications
  - `gthread`: Thread-based workers with a thread pool, better for more stable performance
  - `preload`: Pre-loads your application to save memory across workers
- **When to use:** Ideal when moving to Stage 2 with multiple front-ends and when you want more control over your Python processes

##### mod_wsgi
- **Apache module** that embeds Python within the Apache process
- **Integration:** Tighter integration with Apache's features and security model
- **Performance:** Good performance for CPU-bound applications
- **Resource usage:** Can be more memory-efficient as it shares resources with Apache
- **Scaling considerations:**
  - Works well when you're already using Apache for other purposes
  - Simplifies deployment with a single server process to manage
  - Benefits from Apache's mature connection handling
- **When to use:** Best for Stage 1 when you're on a single server and already using Apache

##### Recommendation
- **Stage 1 (single server):** mod_wsgi is simple and effective if you're already using Apache
- **Stage 2 (multiple front-ends):** Consider switching to Gunicorn with thread-based workers (`threads` or `gthread`) for better handling of connections
- **Worker count:** A good rule of thumb is (2 × CPU cores) + 1 for CPU-bound applications

##### LinuxReport Worker Compatibility Analysis

Based on the LinuxReport codebase structure:

- **`sync` workers:** Fully compatible with your Flask application. Simple and reliable, but each worker is completely independent and handles one request at a time.

- **`threads` workers:** Compatible with your codebase. Your Flask application doesn't appear to use any thread-unsafe components. The page caching with `lru_cache` and `cacheout` should work well with threaded workers, allowing better connection handling.

- **`gthread` workers:** Recommended for your application. Similar to `threads` but with a more efficient thread pool, which should work well with your mixed I/O (feed fetching) and CPU (page rendering) workloads.

- **`preload` option:** Highly recommended for your application. LinuxReport loads various modules at startup and compiles JS files. Using preload would share this memory across workers, reducing the overall memory footprint.

##### Worker Count for 4GB RAM Server

For a 4GB RAM server running LinuxReport:

- **Memory analysis:**
  - Base Flask application with dependencies: ~100-150MB per worker
  - Page cache in memory: ~50-100MB (depending on number of feeds)
  - OS and other processes: ~500MB

- **Recommended configuration:**
  - For a 2-core system: 3-4 workers (`(2 × 2) + 1 = 5`, but limited by RAM)
  - With `preload` option: 4-5 workers (better memory efficiency)
  - **Thread count per worker:** 2-4 threads per worker
    - 2 threads: Conservative setting, minimal overhead (total: 6-16 concurrent requests)
    - 4 threads: Better concurrency for I/O operations (total: 12-16 concurrent requests)
    - Balance between: 3 worker processes with 4 threads each (12 concurrent requests)
  - Set a per-worker memory limit to prevent memory exhaustion

- **Example Gunicorn command for 4GB server:**
  ```
  gunicorn --workers=3 --threads=4 --worker-class=gthread --preload --max-requests=1000 --max-requests-jitter=100 app:app
  ```

- **Memory monitoring:** Implement monitoring to ensure workers aren't consuming too much memory. If memory usage grows over time, add `--max-requests` to recycle workers periodically.

#### Multi-Server Caching Strategy
- **Anonymous users:** Cache aggressively at Apache level (1 hour TTL)
- **Cookie checks:** Only forward to backend when:
  - Admin mode cookie present
  - Custom feed/layout cookies present
  - Mobile vs. desktop differentiation

#### Backend Optimization
- Object storage synchronization for feeds (see README_object_storage_sync.md)
- Scheduled background jobs for feed updates

#### Monitoring
- Implement basic monitoring to track:
  - Server load/CPU usage
  - Memory consumption
  - Request latency
  - Cache hit/miss rates

This scaling plan leverages your existing fast Python code and page caching in the early stages, deferring more complex infrastructure changes until they're truly needed. The focus is on maximizing current performance and only adding complexity when traffic demands require it.

#### Specialized Data Handling Considerations

##### Weather Data Management
- **Challenge:** Weather data (weather.py) is city-specific but requires API request minimization
- **Current approach:** Local caching per server instance
- **Scaling solutions:**
  - **Redis-based approach:**
    - Central Redis instance stores weather data by city
    - All front-ends query Redis instead of weather APIs directly
    - Master server maintains Redis with fresh weather data
    - Includes TTL (time-to-live) for automatic expiration
    - Provides atomic operations for concurrent updates
  - **Message queue approach:**
    - Front-ends publish weather data requests to queue
    - Master consumes queue, fetches data, publishes responses
    - Handles request deduplication for same cities
    - Options: RabbitMQ, ZeroMQ, or lightweight Redis-based queues
  - **Libcloud/object storage approach:**
    - Master writes weather data to object storage (S3-compatible)
    - Front-ends periodically check and cache object storage
    - Simple implementation with minimal dependencies
    - Works well when weather update frequency is low (e.g., hourly)
  - **Recommendation:** Start with the simplest approach (libcloud/object storage) and move to Redis if/when more real-time updates are needed
