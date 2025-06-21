# LinuxReport - Multi-Platform News Aggregation

<div align="center">
  <img src="https://linuxreportstatic.us-ord-1.linodeobjects.com/linuxreportfancy.webp" alt="LinuxReport logo" width="200" style="margin: 10px;">
  <img src="https://linuxreportstatic.us-ord-1.linodeobjects.com/covidreportfancy.webp" alt="CovidReport logo" width="200" style="margin: 10px;">
  <img src="https://linuxreportstatic.us-ord-1.linodeobjects.com/aireportfancy.webp" alt="AIReport logo" width="200" style="margin: 10px;">
</div>

---

**Simple, fast, and intelligent news aggregation platform** built with Python/Flask. Designed as a modern [drudgereport.com](http://drudgereport.com/) clone that automatically aggregates and curates news from multiple categories, updated 24/7 with AI-powered headline generation.

This project is **free and open source software** released under the GNU Lesser General Public License v3.0 (LGPL v3).

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/KeithCu/LinuxReport)

> DeepWiki provides excellent analysis of the codebase, including visual dependency graphs.

## 🌐 Live Sites

| Category | URL | Focus |
|----------|-----|-------|
| **Linux** | [linuxreport.net](https://linuxreport.net) | Linux news, open source, tech |
| **COVID** | [covidreport.org](https://covidreport.org) | Health, pandemic updates |
| **AI** | [aireport.keithcu.com](https://aireport.keithcu.com) | Artificial intelligence, ML |
| **Solar/PV** | [pvreport.org](https://pvreport.org) | Solar energy, renewable tech |
| **Techno** | [news.thedetroitilove.com](https://news.thedetroitilove.com) | Detroit techno music |
| **Space** | [news.spaceelevatorwiki.com](https://news.spaceelevatorwiki.com) | Space exploration |

## ✨ Key Features

- **🚀 High Performance**: Thread pools and Apache process pools for scalability
- **🤖 AI-Powered Headlines**: Automatic headline curation using 30+ LLM models via [OpenRouter.ai](https://openrouter.ai)
- **🎯 Multi-Platform**: Support for multiple news categories in one codebase
- **🌙 Dark Mode**: User-customizable themes and font sizes
- **📱 Mobile Responsive**: Optimized for all devices
- **⚡ Advanced Caching**: Multi-layer caching system for optimal performance
- **🌐 CDN Support**: s3cmd integration with long cache expiration headers for optimal image delivery
- **🔒 Secure**: Rate limiting, admin authentication, input validation
- **🛠️ Configurable**: Easy RSS feed management and customization

## 🧠 AI-Powered Intelligence

The system uses sophisticated AI for headline generation through [OpenRouter.ai](https://openrouter.ai), randomly selecting from over 30 free models including:

- [Llama 4](https://openrouter.ai/models/meta-llama/llama-4-maverick)
- [Qwen](https://openrouter.ai/models/qwen/qwen3-32b) 
- [Mistral](https://openrouter.ai/models/mistralai/mistral-small-3.1-24b-instruct) variants

If a model fails, it automatically falls back to [Mistral Small](https://openrouter.ai/models/mistralai/mistral-small-3.1-24b-instruct) for reliability. See the [model selection logic](auto_update.py) for implementation details.

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/KeithCu/LinuxReport
cd LinuxReport

# Install dependencies
pip install -r requirements.txt

# Configure (see Configuration section below)
cp config.yaml.example config.yaml
# Edit config.yaml with your settings

# Run development server
python -m flask run
```

## 🏗️ Architecture Overview

LinuxReport uses a sophisticated multi-layered architecture designed for performance and scalability:

### Core Technologies

- **Backend**: Python 3.x + Flask with extensions (Login, Limiter, Assets, Mobility)
- **Database**: SQLite via Diskcache for high-performance persistent storage  
- **Caching**: Multi-layer system (disk, memory, file-based)
- **Frontend**: Responsive HTML/CSS/JS with automatic bundling and minification
- **Scraping**: BeautifulSoup4 + Selenium with Tor support for complex sites
- **Images**: Automatic WebP conversion and optimization

### Performance Features

The system achieves high performance through:

- **Thread Pools**: Concurrent RSS feed processing
- **Multi-layer Caching**: Disk, memory, and file-based caching strategies
- **CDN Integration**: s3cmd synchronization with long cache expiration headers for static assets
- **Asset Optimization**: Automatic JavaScript bundling and CSS minification  
- **Smart Deduplication**: Article deduplication across feeds and time periods
- **Rate Limiting**: Intelligent request throttling and IP blocking

## 📋 Configuration

### Required Setup

1. **Edit config.yaml** (copy from config.yaml.example if needed):
```yaml
# IMPORTANT: Change default password for security!
admin:
  password: "YOUR_SECURE_PASSWORD_HERE"
  secret_key: "your-super-secret-key-change-this-in-production"

# Configure your domains
settings:
  allowed_domains:
    - "https://yourdomain.com"
    - "https://www.yourdomain.com"
```

2. **Configure Report Types**: Edit `*_report_settings.py` files to customize RSS feeds and appearance for each report type.

3. **Production Deployment**: Use the included `httpd-vhosts-sample.conf` for Apache configuration.

### Adding New Report Types

To add a new report category:

1. Create `{type}_report_settings.py` with RSS feeds and configuration
2. Add HTML template `{type}reportabove.html` for custom headlines
3. Add logos and assets to `static/images/`
4. Configure automatic updates in systemd (optional)

## 🔧 Development

### Project Structure

```
LinuxReport/
├── app.py                    # Flask application setup and configuration
├── routes.py                 # Main routing and request handling
├── shared.py                 # Shared utilities and constants
├── models.py                 # Data models and configurations
├── workers.py                # Background feed processing
├── auto_update.py            # AI headline generation
├── caching.py                # Multi-layer caching system
├── *_report_settings.py      # Report-specific configurations
├── templates/                # Jinja2 templates + modular JavaScript
├── static/                   # CSS, images, compiled assets
├── tests/                    # Test suite
└── config.yaml               # Configuration file
```

### Key Features for Developers

- **Modular JavaScript**: Source files in `templates/` auto-bundle to `static/`
- **Hot Reload**: Development mode with unminified assets for debugging
- **Type Safety**: Type hints throughout the codebase
- **Comprehensive Caching**: See `Caching.md` for detailed documentation
- **Test Suite**: pytest-based testing in `tests/` directory

## 📖 Documentation

- **[agents.md](agents.md)**: Comprehensive guide for AI agents and developers
- **[Caching.md](Caching.md)**: Detailed caching system documentation  
- **[ROADMAP.md](ROADMAP.md)**: Future development plans
- **[Scaling.md](Scaling.md)**: Performance optimization strategies

## 🔒 Security

### Admin Mode Protection

Admin functionality is protected by authentication:

```yaml
# config.yaml
admin:
  password: "CHANGE_THIS_DEFAULT_PASSWORD"
```

**⚠️ IMPORTANT**: Change the default password immediately after installation!

### Security Features

- **Rate Limiting**: Configurable per-endpoint throttling
- **Input Validation**: Secure file uploads and form processing
- **CORS Protection**: Configurable domain allowlists
- **Security Headers**: XSS protection, content type validation
- **IP Blocking**: Persistent banned IP storage

## 🚀 Production Deployment

### Apache Configuration

Use the included `httpd-vhosts-sample.conf`:

```apache
<VirtualHost *:443>
    ServerName yourdomain.com
    WSGIDaemonProcess linuxreport python-path=/path/to/LinuxReport
    WSGIProcessGroup linuxreport
    WSGIScriptAlias / /path/to/LinuxReport/wsgi.py
    # SSL and other configurations...
</VirtualHost>
```

### Systemd Services

For automatic headline updates:

```bash
# Copy service files
sudo cp update-headlines.service /etc/systemd/system/
sudo cp update-headlines.timer /etc/systemd/system/

# Enable and start
sudo systemctl enable update-headlines.timer
sudo systemctl start update-headlines.timer
```

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Run tests: `pytest tests/`
4. Submit a pull request

Feel free to request new RSS feeds or suggest improvements.

## 📈 Performance

LinuxReport demonstrates that **Python can be incredibly fast** when properly architected. The system typically starts returning pages after less than 10 lines of Python code, dispelling myths about Python's performance.

Key performance metrics:
- **Ultra-fast response times**: Averaged 0.01 seconds over a 4-hour production period (on AMD EPYC, standard Python without PyPy)
- **Zero-read performance**: Multi-layer caching (page, sitebox) eliminates most database reads despite constant background feed updates
- **Concurrent processing** of 20+ RSS feeds
- **Automatic scaling** via Apache process pools
- **Intelligent caching** reduces redundant processing by 95%+

The architecture achieves this performance through smart cache layering that serves most requests from memory while background workers continuously update feeds, proving that well-designed caching can deliver enterprise-grade speed without requiring specialized hardware or runtime optimizations.

## 🔧 FastAPI vs Flask (Historical Context)

While FastAPI is a modern, high-performance framework with excellent async support, this project intentionally uses Flask for several reasons:

### Why Flask Works Best Here

1. **Simplicity**: Flask's synchronous model matches the project's needs perfectly
2. **Maturity**: Battle-tested with vast ecosystem and community support  
3. **Performance**: Current thread pool + caching implementation achieves excellent performance
4. **Development Speed**: Flask's simplicity enables rapid iteration and maintenance

### FastAPI Considerations

FastAPI offers benefits like automatic API documentation and modern async support, but these are less relevant because:
- The site primarily serves HTML pages rather than JSON APIs
- Current synchronous code already performs excellently  
- Existing thread pool implementation handles I/O efficiently
- The effort to migrate wouldn't justify the benefits for this use case

If considering a FastAPI migration, you would need to:
1. Rewrite core application logic
2. Modify Apache configuration  
3. Restructure the caching system
4. Update all dependencies and extensions

## 📄 License

This project is **free and open source software** released under the GNU Lesser General Public License v3.0 (LGPL v3). See the LICENSE file for complete details.

### CDN and Static Asset Delivery

LinuxReport includes sophisticated CDN support for optimal performance:

- **s3cmd Integration**: Automated synchronization of static images to object storage
- **Long Cache Headers**: HTTP expiration headers set to instruct clients to cache images for extended periods
- **Bandwidth Optimization**: Significantly reduces server bandwidth usage and improves global load times
- **Edge Delivery**: Static assets served from CDN edge locations closest to users

The CDN configuration is easily managed through `config.yaml` and automatically handles cache-busting when needed.

---

<div align="center">
  <strong>Built with ❤️ for the free and open source community</strong>
</div>

