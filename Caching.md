# Caching Mechanisms in the Application

This document outlines the different caching strategies employed within the codebase to improve performance and reduce redundant computations or data fetching.

## 1. In-Memory Caching (`functools.lru_cache`)

*   **Location:** `app.py`
*   **Function:** `static_file_hash`
*   **Mechanism:** Uses Python's built-in `@lru_cache()` decorator.
*   **Purpose:** Caches the MD5 hash of static file contents (e.g., CSS, JavaScript) in memory. This avoids reading and hashing these files repeatedly when generating cache-busting URLs for static assets in templates.
*   **Persistence:** The cache exists only in memory for the duration of the application process. It is cleared upon application restart.
*   **Special handling for `linuxreport.js`:** For this compiled JavaScript file, the function doesn't hash the output file directly but instead uses `get_combined_hash()` to generate a hash based on all source JS modules.

## 2. In-Memory Caching (`cacheout` - via `g_cm`)

*   **Location:** Initialized in `shared.py` as `g_cm = Cache()`.
*   **Mechanism:** Uses an in-memory cache, the `cacheout` library.
*   **Uses:**
    *   **Full Page Caching:** (`routes.py`) Stores the entire rendered HTML output of the main page. Keys are based on request parameters (page order, mobile flag). Allows serving previously rendered pages directly from memory.
    *   **RSS Template Caching:** (`routes.py`, `workers.py`) Caches templates fetched based on site URLs (`rss_info.site_url`). Cache entries are deleted by the worker when a feed is updated.
*   **Persistence:** The cache exists only in memory for the duration of the application process. It is cleared upon application restart or when items expire/are evicted.

## 3. Disk-Based Caching (`diskcache` - via `g_c`)

The application utilizes the `diskcache` library (accessed via the `g_c` object, storing cached data persistently on disk using an SQLite backend (indicated by `cache.db*` files).

*   **Weather Data Caching:**
    *   **Location:** `weather.py`
    *   **Mechanism:** Uses the generic disk cache (`g_c`). Weather data fetched from an API is stored.
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
    *   **Mechanism:** Uses `DiskcacheSqliteLock` (via `get_lock` function, likely wrapping `g_c`'s lock).
    *   **Purpose:** While not explicitly showing data caching with `g_c` here, it uses locks provided by `diskcache` to ensure that only one worker process attempts to fetch a specific feed URL at any given time. This prevents redundant network requests.

## 4. File-Based Caching (via `_file_cache`)

*   **AI-Generated Headlines Caching:**
    *   **Location:** `shared.py` (via `get_cached_file_content()` function used by `get_cached_above_html()` in `routes.py`)
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

## 5. JavaScript Compilation and Caching

*   **Location:** `app.py`
*   **Mechanism:** Uses a modular approach to JavaScript organization with compilation at application startup.
*   **Process:**
    *   **File Organization:** JavaScript is split into multiple modular files (`core.js`, `weather.js`, `chat.js`, `config.js`) located in the `templates` directory for easier maintenance.
    *   **Compilation:** The `compile_js_files()` function combines these separate modules into a single `linuxreport.js` file in the `static` directory during application startup.
    *   **Metadata:** The compiled file includes a header with compilation timestamp, a content hash, and a list of source files.
    *   **Content Hash Generation:** The `get_combined_hash()` function creates an MD5 hash of all source JS files' contents, used both for the file header and for cache-busting URLs.
    *   **Cache Busting:** The `static_file_hash()` function (which is cached via `@lru_cache`) provides a hash value that's appended to static file URLs in templates to force browsers to reload resources when their content changes.
    *   **Template Integration:** The hash function is made available to all templates via `g_app.jinja_env.globals['static_file_hash'] = static_file_hash`.
*   **Benefits:**
    *   **Development Friendly:** Maintains JavaScript in separate, focused files for easier development.
    *   **Production Optimized:** Serves a single combined file to reduce HTTP requests.
    *   **Automatic Updates:** Changes to source files result in a new hash, ensuring clients load the latest version.
    *   **No External Build Tools:** Handles the compilation process within the application without requiring external build systems.

## Summary

The application employs multiple caching layers:
1.  **`functools.lru_cache`:** For simple, process-local in-memory caching (e.g., static file hashes).
2.  **`cacheout` (`g_cm`):** For broader, process-local in-memory caching with TTL and size limits (e.g., full pages, RSS templates).
3.  **`diskcache` (`g_c`):** For persistent disk-based caching shared across processes (e.g., weather data, chat comments, banned IPs) and for providing cross-process locking mechanisms (feed fetching, weather fetching).
4.  **File-based caching (`_file_cache`):** For caching content of frequently accessed files (AI-generated headlines) with modification time tracking to avoid unnecessary disk reads.
5.  **JavaScript Compilation:** Combines modular JS files at startup with cache-busting mechanisms to optimize both development workflow and production performance.
