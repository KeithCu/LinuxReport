# Playwright Migration Guide

This guide explains how to migrate from Selenium to Playwright in the LinuxReport project.

## Overview

The `playwrightfetch.py` file provides a drop-in replacement for `seleniumfetch.py` with equivalent functionality but using Playwright instead of Selenium WebDriver.

## Key Differences

### Advantages of Playwright over Selenium

1. **Better Performance**: Playwright is generally faster and more reliable
2. **Better JavaScript Support**: More consistent handling of modern web applications
3. **Built-in Stealth**: Better anti-detection capabilities out of the box
4. **Simpler API**: More intuitive and consistent API design
5. **Better Error Handling**: More descriptive error messages and better debugging

### API Compatibility

The Playwright version maintains full API compatibility with the Selenium version:

- `fetch_site_posts(url, user_agent)` - Main function for fetching site content
- `SharedPlaywrightBrowser` - Equivalent to `SharedSeleniumDriver`
- `cleanup_playwright_browsers()` - Equivalent to `cleanup_selenium_drivers()`
- `DRIVER_RECYCLE_TIMEOUT` - Backward compatibility constant

## Installation

1. **Install Playwright**:
   ```bash
   python install_playwright.py
   ```

2. **Or manually**:
   ```bash
   pip install playwright
   playwright install chromium
   ```

## Migration Steps

### 1. Update Dependencies

The `requirements.txt` file has been updated to include Playwright:
```
playwright>=1.40.0
```

### 2. Update Imports

Replace Selenium imports with Playwright imports:

**Before (Selenium)**:
```python
from seleniumfetch import fetch_site_posts, SharedSeleniumDriver, cleanup_selenium_drivers
```

**After (Playwright)**:
```python
from playwrightfetch import fetch_site_posts, SharedPlaywrightBrowser, cleanup_playwright_browsers
```

### 3. Update Function Calls

The main function `fetch_site_posts()` has the same signature and behavior, so no changes are needed for basic usage.

For advanced usage, replace driver management:

**Before (Selenium)**:
```python
driver = SharedSeleniumDriver.get_driver(use_tor=False, user_agent=user_agent)
```

**After (Playwright)**:
```python
browser, context = SharedPlaywrightBrowser.get_browser_context(use_tor=False, user_agent=user_agent)
```

### 4. Update Tests

Run the Playwright test suite:
```bash
python tests/playwright_test.py
```

## Configuration

The Playwright version uses the same configuration system as the Selenium version:

- `CUSTOM_FETCH_CONFIG` - Site-specific configurations
- `needs_selenium` flag - Still used for compatibility (controls whether to use browser automation)
- `needs_tor` flag - Controls Tor proxy usage
- `use_random_user_agent` flag - Controls user agent randomization

## Performance Considerations

### Memory Usage
- Playwright generally uses less memory than Selenium
- Better garbage collection and resource management
- Automatic cleanup of browser contexts

### Speed
- Faster page loads and JavaScript execution
- Better handling of dynamic content
- More efficient element selection

### Reliability
- Better error handling and recovery
- More consistent behavior across different sites
- Better handling of network timeouts

## Troubleshooting

### Common Issues

1. **Browser Installation**:
   ```bash
   playwright install chromium
   ```

2. **Permission Issues** (Linux):
   ```bash
   playwright install-deps
   ```

3. **Memory Issues**:
   - Playwright uses less memory than Selenium
   - If issues persist, check system resources

### Debugging

Enable debug logging by setting the log level in your configuration:
```python
import logging
logging.getLogger('playwright').setLevel(logging.DEBUG)
```

## Testing

The test suite (`tests/playwright_test.py`) covers:

1. Basic browser creation and cleanup
2. Browser persistence and TTL management
3. Main fetch function functionality
4. Concurrent access and thread safety
5. Manual cleanup operations

Run tests:
```bash
python tests/playwright_test.py
```

## Rollback

If you need to rollback to Selenium:

1. Keep the original `seleniumfetch.py` file
2. Revert import changes
3. Remove Playwright from requirements.txt
4. Uninstall Playwright: `pip uninstall playwright`

## Support

For issues specific to Playwright:
- [Playwright Documentation](https://playwright.dev/python/)
- [Playwright GitHub Issues](https://github.com/microsoft/playwright-python/issues)

For issues with the LinuxReport integration:
- Check the test suite output
- Review the migration guide
- Compare with the original Selenium implementation
