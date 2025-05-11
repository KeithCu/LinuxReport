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
  - Move static assets to CDN using URL_IMAGES variable for offloading bandwidth / HTTP gets, also go faster(DONE)
  - Implement PyPy instead of CPython for significant performance boost (3-5x for CPU-bound operations)
  - These changes amplify the benefit of every subsequent scaling effort
  - Worth implementing early as they require minimal code changes with maximum impact=
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

### Implementation Details

#### Initial Optimization (Pre-scaling)
- Ensure Python-level page caching is maximized
- Profile application to identify bottlenecks
- Move static assets to CDN using URL_IMAGES variable (DONE)

#### Handling Cache-Busting for Static Assets

The application already utilizes cache-busting for CSS and JS files using version query parameters:

```html
<link rel="stylesheet" href="/static/linuxreport.css?v={{ static_file_hash('linuxreport.css') }}">
<script src="/static/linuxreport.js?v={{ static_file_hash('linuxreport.js') }}"></script>
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
