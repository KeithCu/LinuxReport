# Caching Mechanisms in the Application

This document outlines the different caching strategies employed within the codebase to improve performance and reduce redundant computations or data fetching.

## 1. In-Memory Caching (`cacheout` - via `g_cm`)

*   **Location:** Initialized in `shared.py` as `g_cm = Cache()`.
*   **Mechanism:** Uses an in-memory cache, the `cacheout` library.
*   **Uses:**
    *   **Full Page Caching:** (`routes.py`) Stores the entire rendered HTML output of the main page.
    *   **RSS Template Caching:** (`routes.py`, `workers.py`) Caches templates fetched based on site URLs (`rss_info.site_url`). Cache entries are deleted by the worker when a feed is updated. That doesn't work across threads, so at page rendering time, we check to see if the last_fetch time is different from last_render and if so, then regenerate the template.

## 2. Disk-Based Caching (`diskcache` - via `g_c`)

The application utilizes the `diskcache` library (accessed via the `g_c` object, storing cached data persistently on disk using an SQLite backend (indicated by `cache.db*` files).

*   **Weather Data Caching:**
    *   **Location:** `weather.py`
    *   **Mechanism:** Uses the generic disk cache (`g_cs`). This is a shared cache among all instances on the server. Weather data fetched from an API is stored.
    *   **Keying:** Keys are generated based on latitude and longitude, which are "bucketed" (grouped into nearby regions) to increase cache hits for close locations. Keys use the prefix `weather:cache_entry:`.
    *   **Expiration:** Cached entries have a timeout (`WEATHER_CACHE_TIMEOUT`, currently 4 hours) and are also validated against the current date to ensure freshness.
    *   **Concurrency:** Uses `DiskcacheSqliteLock` to prevent multiple processes/threads from fetching data for the same location simultaneously.

*   **Chat/Comments Caching:**
    *   **Location:** `routes.py` 
    *   **Mechanism:** Uses the disk cache retrieved via `get_chat_cache()` function, which returns either `g_c` (instance-specific cache) or `g_cs` (shared cache across instances) based on the `USE_SHARED_CACHE_FOR_CHAT` configuration value.
    *   **Purpose:** Stores chat comments (associated with `COMMENTS_KEY`) and a set of banned IP addresses (`BANNED_IPS_KEY`) persistently on disk.
    *   **Persistence:** Unlike in-memory caches, this data remains available across application restarts, enabling long-term storage of comments and banned IPs.

*   **Feed Fetching Synchronization:**
    *   **Location:** `workers.py`
    *   **Mechanism:** Uses `DiskcacheSqliteLock` wrapping `g_c`'s lock.
    *   **Purpose:** While not explicitly showing data caching with `g_c` here, it uses locks provided by `diskcache` to ensure that only one worker process attempts to fetch a specific feed URL at any given time. This prevents redundant network requests.

## 3. File-Based Caching (via `_file_cache`)

*   **AI-Generated Headlines Caching:**
    *   **Location:** `caching.py` (via `get_cached_file_content()` function used by `get_cached_above_html()` in `routes.py`)
    *   **Mechanism:** Uses a simple in-memory dictionary (`_file_cache`) that stores file content along with modification timestamps.
    *   **Process:**
        *   Stores file content with its last modified time (`mtime`) and last check time.
        *   Only re-reads the file from disk when:
            1. The file isn't in the cache
            2. The file's modification time has changed
            3. The check interval has passed (`_FILE_CHECK_INTERVAL_SECONDS`, set to 5 minutes)
    *   **Purpose:** Caches the content of the `{mode}reportabove.html` file (e.g., `linuxreportabove.html`, `aireportabove.html`), which contains AI-generated featured headlines that appear at the top of the page.
    *   **Management:** Can be edited by administrators through the config page and is programmatically generated through the `html_generation.py` module which renders headline templates with article titles and images.
    *   **Invalidation:** Cache entries are explicitly invalidated when an admin saves new headlines by removing the entry from `_file_cache` directly, forcing a re-read on the next request.
    *   **Key difference from disk cache:** This is a separate caching mechanism from `diskcache` and is primarily aimed at reducing disk I/O for frequently accessed but rarely changing files.

## 4. Flask-Assets Asset Management and Caching

*   **Location:** `app.py`
*   **Mechanism:** Uses Flask-Assets for automatic asset bundling, minification, and cache busting.
*   **Process:**
    *   **JavaScript Bundling:** Combines modular JS files (`core.js`, `weather.js`, `chat.js`, `config.js`) from the `templates` directory into a single `linuxreport.js` file in the `static` directory during application startup.
    *   **CSS Management:** Provides cache busting for `linuxreport.css` without modifying the original file.
    *   **Custom Header Filter:** Adds compilation metadata (timestamp, hash, source files) to bundled JavaScript files.
    *   **Conditional Minification:** JavaScript is only minified in production mode (when `DEBUG=False` and Flask debug mode is off), providing unminified code for easier debugging in development.
    *   **Automatic Cache Busting:** Flask-Assets generates unique URLs with version parameters that automatically update when files change.
    *   **Template Integration:** Assets are made available to templates via `{% assets %}` template tags, which automatically generate the correct URLs.
*   **Benefits:**
    *   **Development Friendly:** Unminified JavaScript in debug mode for easier debugging.
    *   **Production Optimized:** Minified JavaScript and CSS for faster loading in production.
    *   **Automatic Updates:** Changes to source files result in new cache-busting URLs, ensuring clients load the latest version.
    *   **Standard Tooling:** Uses Flask-Assets, a well-maintained library for asset management.
    *   **No Manual Build Steps:** Assets are built automatically on application startup.

## Summary

The application employs multiple caching layers:
1.  **`cacheout` (`g_cm`):** For process-local in-memory caching with TTL and size limits (e.g., full pages, RSS templates).
2.  **`diskcache` (`g_c`):** For persistent disk-based caching shared across processes (e.g., weather data, chat comments, banned IPs) and for providing cross-process locking mechanisms (feed fetching, weather fetching).
3.  **File-based caching (`_file_cache`):** For caching content of frequently accessed files (AI-generated headlines) with modification time tracking to avoid unnecessary disk reads.
4.  **Flask-Assets:** For automatic asset bundling, minification, and cache busting of JavaScript and CSS files, with conditional minification based on debug mode.
