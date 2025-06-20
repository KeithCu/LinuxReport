## Scaling Plan

As LinuxReport grows in popularity, this scaling plan provides a roadmap for efficiently handling increased traffic while maintaining cost-effectiveness.

### Note on Database Replication Solutions
While database replication solutions like Litestream and rqlite exist, they are not suitable for this scaling scenario:
- **Litestream**: Designed primarily for disaster recovery, not for replicating two live databases. It's excellent for backup and recovery but doesn't solve the scaling problem of having multiple live servers.
- **rqlite**: Requires using its own API instead of direct SQLite calls. Since LinuxReport uses the standard diskcache / SQLite API directly, this would require significant code changes and isn't a practical solution.

Instead, this plan focuses on a more appropriate architecture using object storage as the central data store, allowing for true horizontal scaling without the complexity of database replication.

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

### Implementation Details

#### Initial Optimization (Pre-scaling)
- Ensure Python-level page caching is maximized
- Profile application to identify bottlenecks
- Move static assets to CDN using URL_IMAGES variable (DONE)

#### Handling Cache-Busting for Static Assets

The application utilizes Flask-Assets for automatic cache-busting of CSS and JS files:

```html
<!-- Link external CSS using Flask-Assets -->
{% assets "css_all" %}
<link rel="stylesheet" type="text/css" href="{{ ASSET_URL }}">
{% endassets %}

<!-- Link external JS using Flask-Assets -->
{% assets "js_all" %}
<script type="text/javascript" src="{{ ASSET_URL }}"></script>
{% endassets %}
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
  <!-- Link external CSS using Flask-Assets -->
  {% assets "css_all" %}
  <link rel="stylesheet" type="text/css" href="{{ ASSET_URL }}">
  {% endassets %}
  
  <!-- Link external JS using Flask-Assets -->
  {% assets "js_all" %}
  <script type="text/javascript" src="{{ ASSET_URL }}"></script>
  {% endassets %}
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

#### Multi-Server File Synchronization Strategies

When scaling to multiple servers, file synchronization becomes more complex, especially for files that can be edited by administrators. Here are several approaches to handle this:

##### 1. Object Storage as Source of Truth

The recommended approach using S3-compatible storage, optimized for low-latency datacenter environments:

```bash
# /usr/local/bin/sync-admin-files.sh
#!/bin/bash

# Directory containing files
FILES_DIR="/path/to/files"
BUCKET="your-bucket-name"

# Ensure directory exists
mkdir -p "$FILES_DIR"

# Sync files from S3 (with low-latency optimizations)
s3cmd sync "s3://${BUCKET}/" "${FILES_DIR}/" --delete-removed --no-progress

# Log sync
echo "Files synced at $(date)" >> /var/log/file-sync.log
```

**Pros:**
- Simple to implement
- Works with any number of servers
- Built-in redundancy
- No need for additional infrastructure
- Can use existing S3cmd tools
- Easy to backup and restore
- Excellent performance in same-datacenter setup (0.1ms latency)
- Minimal operational overhead

**Cons:**
- No built-in version history
- No conflict resolution
- Last-write-wins for concurrent edits

**Implementation Details:**

1. **Initial Setup:**
```bash
# Configure s3cmd if not already done
s3cmd --configure

# Create bucket if needed
s3cmd mb s3://your-bucket-name

# Upload initial files
s3cmd put linuxreportabove.html s3://your-bucket-name/
s3cmd put headlines_archive.json s3://your-bucket-name/
```

2. **Systemd Timer:**
```ini
# /etc/systemd/system/file-sync.timer
[Unit]
Description=File sync timer

[Timer]
# Run at 5 minutes past every hour
OnCalendar=*:05
Unit=file-sync.service

[Install]
WantedBy=timers.target
```

3. **Service:**
```ini
# /etc/systemd/system/file-sync.service
[Unit]
Description=File sync service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/sync-admin-files.sh
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

4. **Update Server Workflow:**
```bash
# On the update server, after generating new content:
s3cmd put linuxreportabove.html s3://your-bucket-name/
s3cmd put headlines_archive.json s3://your-bucket-name/

# To check current files:
s3cmd ls s3://your-bucket-name/
```

**Best Practices:**

1. **File Organization:**
   - Keep files at the root of the bucket for simplicity
   - Use consistent naming conventions
   - Include timestamps in filenames if needed

2. **Error Handling:**
```bash
#!/bin/bash
# Enhanced sync script with error handling

FILES_DIR="/path/to/files"
BUCKET="your-bucket-name"
LOG_FILE="/var/log/file-sync.log"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Ensure directory exists
mkdir -p "$FILES_DIR"

# Sync files from S3
if s3cmd sync "s3://${BUCKET}/" "${FILES_DIR}/" --delete-removed --no-progress; then
    log_message "Sync completed successfully"
else
    log_message "ERROR: Sync failed"
    exit 1
fi
```

3. **Monitoring:**
   - Check sync logs regularly
   - Monitor S3 bucket size
   - Set up alerts for sync failures
   - Monitor sync latency (should be very low in same datacenter)

4. **Backup Strategy:**
   - Enable versioning on the S3 bucket
   - Keep daily backups of the bucket
   - Test restore procedures regularly

This approach is particularly well-suited for LinuxReport because:
- It's simple to implement and maintain
- Works well with your existing S3cmd setup
- Scales easily to any number of servers
- Requires minimal infrastructure
- Provides a clear source of truth
- Easy to backup and restore
- Excellent performance in your low-latency datacenter environment
- No additional complexity needed
- Perfect timing (5 minutes past hour) for your update cycle

The key advantages are:
- Simpler implementation
- Works with any number of servers without additional complexity
- Can use existing S3 tools and infrastructure
- Easier to monitor and debug
- Near-instantaneous syncs in same datacenter
- Minimal operational overhead
- Clear separation between update server and sync servers

**Update Server Strategy:**
- Primary role: Content generation and updates
- Secondary role: Light request handling
- Load balancer configuration:
  - Minimal traffic (just enough to keep server active)
  - Majority of user requests go to replica servers
  - Health checks every 30 seconds
- Future improvements when necessary:
  - Implement automatic failover
  - Further isolate update server for better reliability

**Health Monitoring:**
```bash
# Example health check script
#!/bin/bash
# /usr/local/bin/check-update-server.sh

# Check if update processes are running
if ! pgrep -f "your_update_script.py" > /dev/null; then
    echo "Update process not running"
    exit 1
fi

# Check if files were updated in the last hour
if [ ! -f "/path/to/last_update.txt" ] || [ $(($(date +%s) - $(stat -c %Y "/path/to/last_update.txt"))) -gt 3600 ]; then
    echo "Files not updated in the last hour"
    exit 1
fi

exit 0
```

This approach ensures:
- Update server stays active but not overloaded
- Clear separation of concerns
- Efficient resource utilization
- Simple monitoring and maintenance
- No need to manage load balancer configuration
- Current high reliability through server stability
- Future improvements planned for even better reliability

#### New Scale-Out Architecture

The new scaling approach focuses on separating feed processing from UI serving, using object storage as the central data store:

1. **Backend Servers (Feed Processing)**
   - Multiple backend servers process feeds independently
   - Each server publishes processed data directly to object storage
   - No need for complex replication or synchronization
   - Simple, stateless operation
   - Can scale horizontally by adding more backend servers
   - Each server can process a subset of feeds
   - No need for ObjectStorageCacheWrapper or ObjectStorageLock
   - Direct publishing of processed data to object storage

2. **Frontend Servers (UI Serving)**
   - Multiple frontend servers serve the UI
   - Read data from object storage instead of direct remote servers
   - Implement local caching for performance (1 hr, then start checking every 10 minutes)
   - Use simple routines from object_storage_sync to fetch data
   - Cache data in memory for fast access
   - No need for complex replication
   - Can scale horizontally by adding more frontend servers
   - Each server maintains its own cache

3. **Weather Data Handling**
   - Weather data is a simpler case that can be handled separately
   - Can use a dedicated weather processing server
   - Publish weather data to object storage
   - Frontend servers cache weather data locally
   - Simple TTL-based cache invalidation
   - No need for complex synchronization

4. **Implementation Details**
   - Use existing object_storage_sync routines for data fetching
   - Implement simple in-memory caching on frontend servers
   - No need for complex distributed caching
   - Each server can operate independently
   - Simple health checks and monitoring
   - Easy to scale by adding more servers
   - Clear separation of concerns

This new architecture provides several advantages:
- Simpler implementation
- Easier to scale
- No complex replication needed
- Clear separation of concerns
- Better resource utilization
- More cost-effective
- Easier to maintain and monitor
- Better reliability through simplicity
- No single point of failure
- Can scale each component independently

The key is that we're not trying to replicate live databases, but rather using object storage as a central data store that both backend and frontend servers can access. This is a much simpler and more scalable approach than trying to replicate live databases between servers.
