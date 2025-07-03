# AI Agent Guide for LinuxReport

This document provides guidance for AI agents (like Codex, GitHub Copilot, or other LLMs) working with the LinuxReport codebase.

## Project Overview

LinuxReport is a Python/Flask-based news aggregation platform that provides real-time updates across multiple report types including Linux, COVID-19, AI, Solar/PV, Space, Trump, and Detroit Techno news. The project uses thread pools and process pools for high performance and includes automatic headline updates using LLMs.

**License**: This project is free and open source software released under the GNU Lesser General Public License v3.0 (LGPL v3).

## Key Technologies

- **Primary Language**: Python 3.x
- **Web Framework**: Flask with extensions
- **Database**: SQLite via Diskcache for persistent storage
- **Template Engine**: Jinja2
- **Asset Management**: Flask-Assets for bundling/minification
- **Key Dependencies**:
  - Flask, Flask-Mobility, Flask-Login, Flask-Limiter for web framework
  - Flask-WTF for CSRF protection and form validation
  - BeautifulSoup4 for HTML parsing
  - Feedparser for RSS feed handling
  - Selenium for web scraping (with Tor support)
  - Pillow for image processing and WebP conversion
  - OpenAI and sentence_transformers for LLM integration
  - Diskcache for high-performance SQLite caching
  - Cacheout for in-memory TTL caching

## Project Structure

```
.
├── app.py                    # Main Flask application entry point and setup
├── shared.py                 # Shared utilities, constants, and configuration
├── routes.py                 # Main routing file and route module initializer
├── models.py                 # Data models, configurations, and user management
├── config.py                 # Configuration page routes and logic
├── weather.py                # Weather API routes and functionality
├── chat.py                   # Chat/comments system routes
├── admin_stats.py            # Admin statistics and performance monitoring
├── workers.py                # Background worker processes for feed fetching
├── auto_update.py            # Automatic headline updates using LLMs
├── caching.py                # Core caching functionality and utilities
├── html_generation.py        # AI headline generation and HTML rendering
├── app_config.py             # Application configuration and setup utilities
├── request_utils.py          # HTTP request utilities and helpers
├── seleniumfetch.py          # Selenium-based web scraping functionality
├── Tor.py                    # Tor network integration and utilities
├── SqliteLock.py             # SQLite locking mechanisms for concurrency
├── ObjectStorageLock.py      # Object storage locking for distributed systems
├── article_deduplication.py  # Article deduplication algorithms
├── FeedHistory.py            # Feed history tracking and management
├── Reddit.py                 # Reddit-specific fetching and processing
├── custom_site_handlers.py   # Custom site-specific handlers
├── image_processing.py       # Main entry points for image extraction and processing
├── image_parser.py           # HTML parsing, image candidate extraction and selection
├── image_utils.py            # Core utility functions, constants, and image dimension logic
├── combinefiles.py           # File combination utilities
├── convert_png_to_webp.py    # PNG to WebP conversion utilities
├── feedfilter.py             # RSS feed filtering and processing
├── old_headlines.py          # Legacy headlines processing
├── stats.py                  # Statistics and analytics
├── forms.py                  # Flask-WTF forms for user input with CSRF protection
├── object_storage_config.py  # Object storage configuration
├── object_storage_sync.py    # Object storage synchronization
├── migrate_to_sqlite.py      # Database migration utilities
├── sync_static.py            # Static file synchronization
├── generate_dependency_graph.py # Dependency graph generation
├── generate_docs.py          # Documentation generation utilities
├── *_report_settings.py      # Site-specific configurations (ai_, linux_, covid_, space_, trump_, pv_, techno_)
├── templates/                # Jinja2 templates and modular JavaScript
│   ├── *.html               # HTML templates
│   ├── app.js               # Main application JavaScript
│   ├── core.js              # Core JavaScript (themes, auto-refresh, scroll)
│   ├── config.js            # Configuration UI logic
│   ├── chat.js              # Chat interface functionality
│   ├── weather.js           # Weather widget functionality
│   ├── infinitescroll.js    # Infinite scroll functionality
├── static/                   # Static assets and compiled JavaScript/CSS
│   ├── images/              # Site logos and favicons
│   ├── linuxreport.css      # Main stylesheet
│   └── linuxreport.js       # Compiled/bundled JavaScript (auto-generated)
├── tests/                    # Test directory with pytest tests
│   ├── __init__.py          # Test package initialization
│   ├── test_article_deduplication.py # Article deduplication tests
│   ├── test_extract_titles.py # Title extraction tests
│   ├── test_sqlitelock.py   # SQLite lock tests
│   └── selenium_test.py     # Selenium integration tests
├── config.yaml              # Main configuration file
├── requirements.txt          # Python dependencies
├── pyproject.toml           # Project configuration
└── LICENSE                  # GNU LGPL v3 license
```

## Core Application Files

1. **app.py**:
   - Flask application initialization and configuration
   - Flask-Login setup for authentication
   - Flask-Assets configuration for JavaScript/CSS bundling
   - Flask-Compress for response compression
   - Conditional Flask-MonitoringDashboard integration
   - Security headers and CORS configuration

2. **shared.py**:
   - Mode enumeration for different report types (Linux, AI, COVID, etc.)
   - Global cache instances (g_c for disk cache, g_cm for memory cache)
   - Rate limiting configuration and utilities
   - Shared constants and configuration loading
   - Cross-module utility functions

3. **routes.py**:
   - Primary route definitions (index, login, logout)
   - Route module initialization for weather, chat, config, etc.
   - Error handling (429 Rate Limit, 404, 500)
   - Security headers and CORS configuration
   - Full page caching and performance optimization

4. **models.py**:
   - SiteConfig and RssInfo data structures
   - User authentication model for Flask-Login
   - Reddit fetch configuration templates
   - Configuration loading utilities

5. **app_config.py**:
   - Application configuration utilities
   - Environment-specific setup functions
   - Configuration validation and loading

6. **request_utils.py**:
   - HTTP request utilities and helpers
   - Request retry logic and error handling
   - User agent management and request headers

7. **seleniumfetch.py**:
   - Selenium-based web scraping functionality
   - Browser automation for complex sites
   - JavaScript rendering support

8. **Tor.py**:
   - Tor network integration and utilities
   - Anonymous browsing capabilities
   - Tor circuit management

9. **SqliteLock.py**:
   - SQLite locking mechanisms for concurrency
   - Database-level locking utilities
   - Thread-safe database operations

10. **ObjectStorageLock.py**:
    - Object storage locking for distributed systems
    - Cloud storage synchronization
    - Distributed lock management

11. **image_parser.py**:
    - Main entry point for image fetching via `custom_fetch_largest_image`
    - HTML parsing and image candidate extraction
    - Image selection and scoring algorithms
    - Integration with custom site handlers

12. **image_processing.py**:
    - Selenium-based image extraction for JavaScript-heavy sites
    - Orchestration of image processing pipeline
    - Browser automation for complex image extraction scenarios

13. **image_utils.py**:
    - Core utility functions for image processing
    - Image dimension extraction and scoring
    - SVG image handling and srcset parsing
    - Shared constants and configuration

## Report Type System

LinuxReport supports multiple report types, each with its own configuration:

- **Report Settings Files**: `*_report_settings.py` (e.g., `ai_report_settings.py`, `linux_report_settings.py`, `covid_report_settings.py`, `space_report_settings.py`, `trump_report_settings.py`, `pv_report_settings.py`, `techno_report_settings.py`)
- **Configuration Structure**: Each file contains a `CONFIG` object with:
  - `ALL_URLS`: Dictionary mapping RSS feeds to RssInfo objects
  - `SITE_URLS`: Ordered list of feeds to process
  - `CUSTOM_FETCH_CONFIG`: Special handling for sites requiring Selenium/Tor
  - `SCHEDULE`: Hours when automatic updates should occur
  - `WEB_TITLE`, `WEB_DESCRIPTION`: SEO and display information
  - `REPORT_PROMPT`: LLM prompt for generating headlines

## Database and Caching System

LinuxReport uses a sophisticated multi-layer caching system (see `Caching.md` for full details):

### CDN and Image Delivery

The system includes CDN support for optimal image delivery:

- **s3cmd Integration**: Images are synchronized to object storage using `s3cmd` with long cache expiration headers
- **Client-Side Caching**: HTTP headers are set to instruct browsers to cache images for extended periods, reducing server load
- **CDN Configuration**: Configurable CDN URL in `config.yaml` for serving static images from edge locations
- **Performance Optimization**: Long expiration dates significantly reduce bandwidth usage and improve load times

### Core Caching Layers

1. **Disk Cache (`diskcache` via `g_c`)**:
   - Primary persistent storage using SQLite backend
   - Weather data with geographical bucketing
   - Chat comments and banned IP addresses
   - Cross-process locking for feed synchronization

2. **Memory Cache (`cacheout` via `g_cm`)**:
   - Full page caching with TTL
   - RSS template caching with invalidation
   - Performance-critical data with size limits

3. **File-based Caching (`_file_cache`)**:
   - AI-generated headlines from `{mode}reportabove.html` files
   - Modification time tracking to avoid unnecessary disk I/O
   - Administrative content that changes infrequently

4. **Asset Management (Flask-Assets)**:
   - Automatic JavaScript bundling from modular files in templates/
   - Conditional minification (debug vs production)
   - Cache busting with automatic versioning
   - Custom header injection with compilation metadata

## Feed Processing and Workers

- **Thread Pool Architecture**: Uses `workers.py` for concurrent feed fetching
- **Tor Integration**: Selenium with Tor support for sites requiring anonymity
- **Custom Site Handlers**: Special configurations for Reddit, complex sites
- **Deduplication**: Article deduplication across feeds and time periods
- **Image Processing**: Automatic WebP conversion and optimization

## Image Processing System

The project includes a comprehensive image processing pipeline:

1. **image_processing.py**: Main entry points for image extraction and processing, including Selenium-based fetching. Orchestrates calls to utility and parsing functions defined in other modules.

2. **image_parser.py**: Handles HTML parsing, image candidate extraction and selection, and custom site-specific logic. Contains the main `custom_fetch_largest_image` function that serves as the primary entry point for image fetching.

3. **image_utils.py**: Contains core utility functions, constants, and image dimension logic. Includes functions for scoring image candidates, parsing srcset attributes, extracting dimensions, and handling SVG images.

4. **convert_png_to_webp.py**: PNG to WebP conversion utilities for image optimization.

The image processing system has been refactored to consolidate functionality into these core modules, with `image_parser.py` serving as the main entry point and `image_utils.py` providing shared utilities and constants.

## Coding Conventions

1. **File Organization**:
   - New Python modules in root directory
   - Report-specific settings in `*_report_settings.py` files
   - Templates in `templates/`, static assets in `static/`

2. **Code Style**:
   - Follow PEP 8 guidelines
   - Use 4 spaces for indentation
   - Maximum line length of 160 characters
   - Type hints for function parameters and returns

3. **Naming Conventions**:
   - Classes: PascalCase (`SiteConfig`, `RssInfo`)
   - Functions and variables: snake_case
   - Constants: UPPER_SNAKE_CASE
   - File names: lowercase with underscores

## Security and Authentication

- **Admin Authentication**: Flask-Login with config.yaml password storage
- **Form Security**: Flask-WTF with CSRF protection and comprehensive form validation
- **Rate Limiting**: Flask-Limiter with dynamic rate adjustment
- **CORS Configuration**: Configurable allowed domains for API access
- **Input Validation**: Secure file uploads with size/type restrictions
- **Security Headers**: CSP, XSS protection, frame options
- **IP Blocking**: Persistent banned IP storage in disk cache

## JavaScript Architecture

1. **Modular System**:
   - Source files in `templates/`: `app.js`, `core.js`, `config.js`, `chat.js`, `weather.js`, `infinitescroll.js`
   - Automatic bundling into `static/linuxreport.js` via Flask-Assets
   - Development mode: unminified for debugging
   - Production mode: minified with source file headers

2. **Core Functionality**:
   - Theme management (dark/light mode persistence)
   - Font size controls with localStorage persistence
   - Infinite scroll with mobile detection
   - Auto-refresh with configurable intervals
   - CSRF token handling for secure AJAX requests
   - Image optimization utilities (currently unused)

3. **Integration Patterns**:
   - Jinja2 templating for dynamic JavaScript content
   - Event delegation for performance
   - Progressive enhancement principles
   - Consistent error handling and logging
   - CSRF token handling for secure AJAX requests

## Configuration Management

- **Primary Config**: `config.yaml` with admin credentials, storage settings, domain allowlists
- **Environment-Specific**: Report settings files for different news categories
- **Security**: Never commit sensitive data; change default passwords
- **Validation**: Input validation for admin configuration changes

## Common Tasks

### Adding a New Report Type

1. Create `{type}_report_settings.py` with CONFIG object:
   ```python
   from models import SiteConfig, RssInfo
   CONFIG = SiteConfig(
       ALL_URLS={...},
       SITE_URLS=[...],
       WEB_TITLE="...",
       REPORT_PROMPT="...",
       # ... other settings
   )
   ```

2. Add corresponding HTML template `{type}reportabove.html`
3. Add static assets (logos, favicons) in `static/images/`
4. Update domain configuration in `config.yaml` if needed
5. Configure systemd timers for automatic updates

### Adding New Routes/Features

1. Create feature module (e.g., `my_feature.py`)
2. Define `init_my_feature_routes(app)` function
3. Import and call in `routes.py`'s `init_app()` function
4. Add templates and static assets as needed
5. Write tests in `tests/` directory

### Modifying Caching Behavior

1. **Page Caching**: Modify cache keys and TTL in `routes.py`
2. **Data Caching**: Use appropriate cache layer (`g_c` for persistence, `g_cm` for speed)
3. **File Caching**: Update `_file_cache` patterns in `caching.py`
4. **Cache Invalidation**: Implement proper cache clearing on data updates

## Development Workflows

1. **Setup**:
   ```bash
   git clone <repository>
   cd LinuxReport
   pip install -r requirements.txt
   # Edit config.yaml with your settings
   python app.py
   ```

2. **Testing**:
   ```bash
   pytest tests/
   # Run specific test: pytest tests/test_specific.py
   ```

3. **Asset Development**:
   - Edit JavaScript in `templates/` directory
   - Flask-Assets automatically rebuilds on startup
   - Debug mode serves unminified assets

## Performance Considerations

- **Caching Strategy**: Use appropriate cache layer for data lifecycle
- **Database Operations**: Leverage diskcache for high-performance SQLite access
- **Concurrent Processing**: Use thread pools for I/O-bound operations
- **Asset Optimization**: Automatic minification and bundling in production
- **Rate Limiting**: Protect against abuse while allowing legitimate usage

## Troubleshooting

1. **Cache Issues**:
   - Check disk space and `cache.db` permissions
   - Review cache key naming and TTL settings
   - Monitor cache hit rates in admin stats

2. **Feed Processing**:
   - Verify network connectivity and SSL certificates
   - Check custom fetch configurations for complex sites
   - Review Selenium/Tor setup for sites requiring special handling

3. **Asset Loading**:
   - Ensure Flask-Assets properly bundles JavaScript
   - Check for compilation errors in asset pipeline
   - Verify static file serving configuration

4. **Authentication**:
   - Confirm config.yaml password settings
   - Check Flask-Login session configuration
   - Verify admin route protections

## Important Guidelines

### What to Do
- **Use existing caching infrastructure** rather than implementing custom storage
- **Follow the modular route pattern** for new features  
- **Leverage the multi-layer cache system** for optimal performance
- **Configure CDN properly** for static asset delivery with appropriate cache headers
- **Use type hints** and follow existing code patterns
- **Test thoroughly** with pytest before deployment

### What to Avoid
- **DO NOT** bypass the caching system for performance-critical operations
- **DO NOT** hardcode configuration values; use config.yaml or settings files
- **DO NOT** modify auto-generated files in `static/` directory
- **DO NOT** create circular dependencies between modules
- **DO NOT** commit sensitive information like passwords or API keys
- **DO NOT** serve images locally when CDN is properly configured - always use the CDN URL for better performance

## Additional Documentation

Refer to these specialized documentation files for detailed information:

- `README.md`: Project overview and setup instructions
- `Caching.md`: Comprehensive caching system documentation
- `README_object_storage_sync.md`: Object storage and CDN configuration
- `PWA.md`: Progressive Web App implementation details
- `PERFORMANCE_OPTIMIZATIONS.md`: Performance optimization strategies
- `MONITORING.md`: Application monitoring and metrics
- `Scaling.md`: Scaling strategies and considerations
- `api_docs.md`: API documentation and endpoints
- `function_dependencies.md`: Function dependency analysis
- `ROADMAP.md`: Project roadmap and future plans
- `config.yaml`: Configuration file with inline comments
- `httpd-vhosts-sample.conf`: Apache production deployment configuration

## Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Jinja2 Documentation](https://jinja.palletsprojects.com/)
- [Python Style Guide (PEP 8)](https://www.python.org/dev/peps/pep-0008/)
- [Flask-Assets Documentation](https://flask-assets.readthedocs.io/)
- [Diskcache Documentation](https://grantjenks.com/docs/diskcache/)