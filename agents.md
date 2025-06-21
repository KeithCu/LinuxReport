# AI Agent Guide for LinuxReport

This document provides guidance for AI agents (like Codex, GitHub Copilot, or other LLMs) working with the LinuxReport codebase.

## Project Overview

LinuxReport is a Python/Flask-based news aggregation platform that provides real-time updates across multiple report types including Linux, COVID-19, AI, Solar/PV, Space, Trump, and Detroit Techno news. The project uses thread pools and process pools for high performance and includes automatic headline updates using LLMs.

## Key Technologies

- **Primary Language**: Python 3.x
- **Web Framework**: Flask with extensions
- **Database**: SQLite via Diskcache for persistent storage
- **Template Engine**: Jinja2
- **Asset Management**: Flask-Assets for bundling/minification
- **Key Dependencies**:
  - Flask, Flask-Mobility, Flask-Login, Flask-Limiter for web framework
  - BeautifulSoup4 for HTML parsing
  - Feedparser for RSS feed handling
  - Selenium for web scraping (with Tor support)
  - Pillow for image processing and WebP conversion
  - OpenAI and sentence_transformers for LLM integration
  - Diskcache for high-performance SQLite caching
  - Cacheout for in-memory caching

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
├── *_report_settings.py      # Site-specific configurations (ai_, linux_, etc.)
├── templates/                # Jinja2 templates and modular JavaScript
│   ├── *.html               # HTML templates
│   ├── core.js              # Core JavaScript (themes, auto-refresh, scroll)
│   ├── config.js            # Configuration UI logic
│   ├── chat.js              # Chat interface functionality
│   └── weather.js           # Weather widget functionality
├── static/                   # Static assets and compiled JavaScript/CSS
│   ├── images/              # Site logos and favicons
│   ├── linuxreport.css      # Main stylesheet
│   └── linuxreport.js       # Compiled/bundled JavaScript (auto-generated)
├── forms.py                  # Flask-WTF forms for user input
├── tests/                    # Test directory with pytest tests
└── config.yaml              # Main configuration file
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

## Report Type System

LinuxReport supports multiple report types, each with its own configuration:

- **Report Settings Files**: `*_report_settings.py` (e.g., `ai_report_settings.py`, `linux_report_settings.py`)
- **Configuration Structure**: Each file contains a `CONFIG` object with:
  - `ALL_URLS`: Dictionary mapping RSS feeds to RssInfo objects
  - `SITE_URLS`: Ordered list of feeds to process
  - `CUSTOM_FETCH_CONFIG`: Special handling for sites requiring Selenium/Tor
  - `SCHEDULE`: Hours when automatic updates should occur
  - `WEB_TITLE`, `WEB_DESCRIPTION`: SEO and display information
  - `REPORT_PROMPT`: LLM prompt for generating headlines

## Database and Caching System

LinuxReport uses a sophisticated multi-layer caching system (see `Caching.md` for full details):

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
- **Rate Limiting**: Flask-Limiter with dynamic rate adjustment
- **CORS Configuration**: Configurable allowed domains for API access
- **Input Validation**: Secure file uploads with size/type restrictions
- **Security Headers**: CSP, XSS protection, frame options
- **IP Blocking**: Persistent banned IP storage in disk cache

## JavaScript Architecture

1. **Modular System**:
   - Source files in `templates/`: `core.js`, `config.js`, `chat.js`, `weather.js`
   - Automatic bundling into `static/linuxreport.js` via Flask-Assets
   - Development mode: unminified for debugging
   - Production mode: minified with source file headers

2. **Core Functionality**:
   - Theme management (dark/light mode persistence)
   - Font size controls with localStorage persistence
   - Infinite scroll with mobile detection
   - Auto-refresh with configurable intervals
   - CSRF token handling for secure AJAX requests

3. **Integration Patterns**:
   - Jinja2 templating for dynamic JavaScript content
   - Event delegation for performance
   - Progressive enhancement principles
   - Consistent error handling and logging

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
- **Use type hints** and follow existing code patterns
- **Test thoroughly** with pytest before deployment

### What to Avoid
- **DO NOT** bypass the caching system for performance-critical operations
- **DO NOT** hardcode configuration values; use config.yaml or settings files
- **DO NOT** modify auto-generated files in `static/` directory
- **DO NOT** create circular dependencies between modules
- **DO NOT** commit sensitive information like passwords or API keys

## Additional Documentation

Refer to these specialized documentation files for detailed information:

- `README.md`: Project overview and setup instructions
- `Caching.md`: Comprehensive caching system documentation
- `README_object_storage_sync.md`: Object storage and CDN configuration
- `config.yaml`: Configuration file with inline comments
- `httpd-vhosts-sample.conf`: Apache production deployment configuration

## Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Jinja2 Documentation](https://jinja.palletsprojects.com/)
- [Python Style Guide (PEP 8)](https://www.python.org/dev/peps/pep-0008/)
- [Flask-Assets Documentation](https://flask-assets.readthedocs.io/)
- [Diskcache Documentation](https://grantjenks.com/docs/diskcache/)