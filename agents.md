# AI Agent Guide for LinuxReport

This document provides guidance for AI agents (like Codex, GitHub Copilot, or other LLMs) working with the LinuxReport codebase.

## Project Overview

LinuxReport is a Python/Flask-based news aggregation site that provides real-time updates for Linux, Covid-19, AI, Solar/PV, and Detroit Techno news. The project uses thread pools and process pools for high performance and includes automatic headline updates using LLMs.

## Key Technologies

- **Primary Language**: Python 3.x
- **Web Framework**: Flask
- **Database**: Sqlite via Diskcache
- **Template Engine**: Jinja2
- **Key Dependencies**:
  - Flask and Flask_Mobility for web framework
  - BeautifulSoup4 for HTML parsing
  - Feedparser for RSS feed handling
  - Selenium for web scraping
  - Pillow for image processing
  - OpenAI and sentence_transformers for LLM integration

## Project Structure

```
.
├── app.py                 # Main application entry point and core Flask setup
├── shared.py             # Shared utilities and core functionality
├── routes.py             # Route definitions
├── models.py             # Database models
├── templates/            # Jinja2 templates and JavaScript files
│   ├── *.html           # HTML templates
│   ├── core.js          # Core JavaScript functionality
│   ├── config.js        # Configuration UI logic
│   ├── chat.js          # Chat interface functionality
│   └── weather.js       # Weather widget functionality
├── static/              # Static assets
├── *_report_settings.py  # Site-specific settings
├── auto_update.py       # Automatic headline updates
├── workers.py           # Background worker processes
└── tests/               # Test directory
```

## Core Application Files

1. **app.py**:
   - Main application entry point
   - Flask application initialization and configuration
   - Core middleware setup
   - Global error handlers
   - Application-wide settings
   - Database connection management
   - Template configuration
   - Static file serving setup

2. **shared.py**:
   - Core utility functions used across the application
   - Shared data structures and constants
   - Common helper functions
   - Cross-module functionality
   - Reusable business logic
   - Common error handling
   - Shared configuration management

These files form the foundation of the application and should be carefully considered when making changes. They contain critical functionality that other parts of the application depend on.

## Coding Conventions

1. **File Organization**:
   - Place new Python modules in the root directory
   - Keep related functionality in dedicated modules

2. **Code Style**:
   - Follow PEP 8 guidelines
   - Use 4 spaces for indentation
   - Maximum line length of 160 characters
   - Use type hints where appropriate

3. **Naming Conventions**:
   - Classes: PascalCase
   - Functions and variables: snake_case
   - Constants: UPPER_SNAKE_CASE
   - Module names: lowercase with underscores

## Key Workflows

1. **Development Setup**:
   ```bash
   git clone https://github.com/KeithCu/LinuxReport
   cd linuxreport
   pip install -r requirements.txt
   python -m flask run
   ```

2. **Testing**:
   - Run tests in the `tests/` directory
   - Use pytest for testing
   - Maintain test coverage for critical components

3. **Deployment**:
   - Apache configuration provided in `httpd-vhosts-sample.conf`
   - Systemd service files for background tasks
   - Object storage sync for static assets

## Important Guidelines

1. **Configuration**:
   - Use `config.yaml` for configuration
   - Never commit sensitive data
   - Change default admin password


3. **Feed Processing**:
   - Follow patterns in `workers.py`
   - Use thread pools for concurrent processing
   - Implement proper error handling

4. **Image Processing**:
   - Use provided image utilities
   - Convert images to WebP format
   - Follow existing image processing patterns

## What to Avoid

1. **DO NOT**:
   - Modify auto-generated files
   - Hardcode sensitive information
   - Bypass security measures
   - Create circular dependencies

2. **Security Considerations**:
   - Always validate user input
   - Use proper authentication checks
   - Follow secure coding practices
   - Protect admin functionality

## Best Practices

1. **Code Changes**:
   - Keep changes focused and atomic
   - Add appropriate comments
   - Update tests when modifying functionality
   - Follow existing patterns

2. **Performance**:
   - Use caching appropriately
   - Implement proper error handling
   - Consider scalability in design
   - Use async operations where beneficial

3. **Documentation**:
   - Document new features
   - Update README when necessary
   - Include docstrings for new functions
   - Document configuration changes

## Common Tasks

1. **Adding New Features**:
   - Create new route in `routes.py`
   - Add template in `templates/`
   - Update static assets in `static/`
   - Add tests in `tests/`

2. **Modifying Existing Features**:
   - Review existing implementation
   - Update related tests
   - Maintain backward compatibility
   - Document changes

3. **Debugging**:
   - Use logging for debugging
   - Check error logs
   - Verify database state
   - Test in isolation

## JavaScript Organization

1. **Template-based JavaScript**:
   - JavaScript files are stored in the `templates/` directory
   - These files are compiled and served as part of the application
   - Key JavaScript modules:
     - `core.js`: Core functionality (theme, font, scroll, auto-refresh)
     - `config.js`: Configuration UI and settings management
     - `chat.js`: Chat interface implementation
     - `weather.js`: Weather widget functionality

2. **JavaScript Conventions**:
   - Use ES6+ features and modern JavaScript practices
   - Follow modular organization with clear separation of concerns
   - Implement proper error handling and logging
   - Use event delegation for better performance
   - Maintain consistent naming conventions with Python code

3. **Integration with Flask**:
   - JavaScript files are served through Flask's template system
   - Use Jinja2 templating for dynamic JavaScript content
   - Follow Flask's static file serving patterns
   - Implement proper CSRF protection for AJAX requests

4. **Best Practices**:
   - Keep JavaScript modules focused and single-purpose
   - Use proper error handling and logging
   - Implement progressive enhancement
   - Follow security best practices
   - Maintain browser compatibility

## Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Jinja2 Documentation](https://jinja.palletsprojects.com/)
- [Python Style Guide](https://www.python.org/dev/peps/pep-0008/)

## Additional Documentation

The codebase includes several specialized documentation files that provide detailed information about specific aspects of the system. Please read the caching.md file so that your code understand the existing implementation and uses it properly.

1. **Main Documentation**:
   - `README.md`: Main project documentation with setup instructions and overview
   - `agents.md`: This file - guide for AI agents working with the codebase

2. **System Architecture**:
   - `Caching.md`: Documentation about the caching system and strategies including how Javascript is handled.

3. **Storage and Sync**:
   - `README_object_storage_sync.md`: Documentation for object storage synchronization

4. **Configuration**:
   - `config.yaml`: Main configuration file (with sensitive defaults)
   - `httpd-vhosts-sample.conf`: Sample Apache configuration
   - `update-headlines.service`: Systemd service configuration

When working with the codebase, refer to these documentation files for specific implementation details and best practices. Each file focuses on a particular aspect of the system and provides in-depth information about that component. 