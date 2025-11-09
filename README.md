# LinuxReport - Multi-Platform News Aggregation

<div align="center">
  <img src="https://linuxreportstatic.us-ord-1.linodeobjects.com/linuxreportfancy.webp" alt="LinuxReport logo" width="200" style="margin: 10px;">
  <img src="https://linuxreportstatic.us-ord-1.linodeobjects.com/covidreportfancy.webp" alt="CovidReport logo" width="200" style="margin: 10px;">
  <img src="https://linuxreportstatic.us-ord-1.linodeobjects.com/aireportfancy2.webp" alt="AIReport logo" width="200" style="margin: 10px;">
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

- 🚀 High performance with thread pools and efficient caching
- 🤖 AI-powered headlines via [OpenRouter.ai](https://openrouter.ai) using a curated set of reliable models
- 🎯 Multi-site support: multiple news categories from one shared codebase
- 🌙 Dark mode, font controls, and mobile-friendly layout
- ⚡ Multi-layer caching and optional CDN for fast responses
- 🔒 Security best practices: rate limiting, admin auth, config-based secrets
- 🛠️ Easy configuration of feeds and report types

## 🧠 AI-Powered Headlines

LinuxReport uses LLMs via [OpenRouter.ai](https://openrouter.ai) to generate and refine headlines.

- Uses multiple high-quality models; failures fall back to a reliable default.
- Logic is implemented in [auto_update.py](auto_update.py:1) (model selection and retries).

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

High-level design:

- Backend:
  - Python 3.x + Flask.
  - Background workers for scraping and updating feeds.
- Storage and caching:
  - SQLite via Diskcache for persistent, high-performance caching.
  - In-memory cache for hot data.
  - File-based HTML snippets for AI-generated headline sections.
- Frontend:
  - Jinja2 templates with modular JS/CSS.
  - Bundled/minified assets for production.
- Scraping:
  - feedparser + BeautifulSoup4 for most sites.
  - Optional Selenium + Tor for complex/JS-heavy or privacy-sensitive sources.
- Images:
  - Automatic optimization and WebP support.

## 📋 Configuration

1. Copy and edit config.yaml:
   - Set a strong admin password and secret_key.
   - Configure allowed_domains and any deployment-specific settings.
2. Configure report types:
   - Edit *_report_settings.py to define feeds, titles, and behavior for each site.
3. For production:
   - Use httpd-vhosts-sample.conf or equivalent web server configuration as a starting point.

## 🔧 Development

### Project Structure (essential only)

- app.py: Flask application setup and configuration.
- routes.py: Main routing and request handling.
- shared.py: Shared utilities, feature flags, and caches.
- workers.py: Background feed processing.
- auto_update.py: AI headline generation and scheduling.
- *_report_settings.py: Report-specific configuration.
- templates/: Jinja2 templates and modular JS/CSS (edit here).
- static/: Bundled assets and images (do not hand-edit generated bundles).
- tests/: pytest suite.
- config.yaml: Runtime configuration.

### Developer Notes

- JS/CSS:
  - Edit source files in templates/; they are bundled into static/linuxreport.js and static/linuxreport.css.
- Caching:
  - Multi-layer caching is central to performance.
  - See Caching.md or agents.md for deeper technical details.
- Tests:
  - Use pytest to validate changes.

## 📖 Documentation

- [agents.md](agents.md): Technical guide for AI agents and contributors.
- [Caching.md](Caching.md): Detailed caching and performance internals.
- [ROADMAP.md](ROADMAP.md): Planned features and improvements.
- [Scaling.md](Scaling.md): Scaling and performance notes.

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

## 🚀 Production Deployment (quick overview)

- Use a WSGI-capable web server (e.g., Apache with mod_wsgi, or gunicorn/uwsgi + nginx).
- Use httpd-vhosts-sample.conf as a reference if deploying with Apache.
- Run background tasks (e.g., headline updates) via systemd timers or cron:
  - Example units/scripts are provided; adjust paths and commands for your environment.

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Run tests: `pytest tests/`
4. Submit a pull request

Feel free to request new RSS feeds or suggest improvements.

## 📈 Performance (summary)

LinuxReport is designed to be fast in real-world deployments:

- Multi-layer caching minimizes database reads and external calls.
- Concurrent processing handles many feeds efficiently.
- Works well with multi-process setups; each process uses its own in-memory cache on top of shared persistent cache.


## 📄 License

This project is **free and open source software** released under the GNU Lesser General Public License v3.0 (LGPL v3). See the LICENSE file for complete details.

### CDN and Static Asset Delivery

- Optional CDN/object storage integration via s3cmd.
- Long cache headers for static assets.
- Configuration driven from config.yaml.

---

<div align="center">
  <strong>Built with ❤️ for the free and open source community</strong>
</div>

