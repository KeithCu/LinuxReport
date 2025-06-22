# LinuxReport Roadmap

## User-Visible Features

These features are directly visible to and interact with your end users:

- **User Accounts & Personalization**
  - User registration/login (Flask-Login, implemented and working)
  - Persistent user preferences (feed curation, layout, dark/light mode)
  - Server-side storage of favorites, feed order, and settings

- **Headline Search & Filtering**
  - Search bar for headlines/stories by keyword or date
  - Filters for date ranges, sources, topics
  - Tag/category support for headlines

- **Save/Bookmark Headlines**
  - Save or bookmark interesting headlines for later reading
  - Read/unread tracking and archiving/starred items

- **Trending Topics & Analytics**
  - Trending topics/word clouds from recent headlines
  - "Most Popular" section based on user interactions

- **Headline Timeline & "On This Day"**
  - Browse headlines by date to see story evolution
  - Show headlines from the same day in previous years

- **Headline Comparison**
  - Side-by-side comparison of how different sources report the same story

- **Local News Integration**
  - Show local news based on user location or selected region

- **RSS/Atom Export**
  - Export custom feeds or archives as RSS/Atom

- **Newsletter/Email Alerts**
  - Daily or breaking-news email alerts with top headlines or followed topics

- **Commenting & Reactions**
  - Comment on or react to headlines (thumbs up/down, emojis)

- **Fact-Check Highlights**
  - Flag stories that have been fact-checked, with source links

- **Audio Summaries**
  - Text-to-speech for top headlines or summaries

- **Calendar Integration**
  - Add important news events to user calendars

- **Polls & Quick Surveys**
  - Engage users with polls or surveys about current events or site features

- **Mobile App Experience**
  - Enhanced mobile UI, PWA support, pull-to-refresh, infinite scroll

- **Social Features**
  - Share headlines to social media
  - "Save for Later" feature

- **Notifications**
  - Subscribe to breaking news or keyword-based alerts
  - Email digests for daily summaries

- **Enhanced Content Features**
  - "Related Stories" section
  - Brief summaries for headlines

- **Internationalization**
  - Multi-language support, region-specific feeds, timezone support

- **AI-Enhanced Features**
  - AI-generated summaries for headlines
  - AI-powered topic clustering and recommendations
  - AI-detected breaking news

---

## Non-User-Visible (Admin/Backend/Codebase) Features

These features improve the backend, admin experience, or codebase quality, but are not directly visible to end users:

- **Security & Protection**
  - Flask-WTF for CSRF protection and better form validation
  - Flask-Limiter for API rate limiting (implemented and working, continue to expand coverage and tune limits)
  - Flask-Compress for response compression
  - Flask-Principals for role-based access control

- **Performance & Monitoring**
  - Flask-MonitoringDashboard for request monitoring, performance metrics, error tracking, health checks
  - Instrument page views, fetch success rates, feed latencies (Prometheus/Grafana/logging)
  - Performance optimizations: lazy loading images, better caching, mobile performance

- **Database & Data Management**
  - Flask-SQLAlchemy for structured data (medium priority; may not be needed for simple blob storage)
  - Scheduled background jobs (Celery/APScheduler) for periodic feed updates, pruning, alerts
  - Full-text search and filtering (Whoosh/Elasticsearch)
  - API expansion: RESTful JSON API for feeds, entries, user settings; Swagger/OpenAPI docs; rate limiting and API keys

- **Admin Dashboard & Tools**
  - Admin dashboard for feed health, last-fetch timestamps, entry counts, trending topics, most-read headlines
  - Visualize feed health and metrics over time

- **User-Customizable Templates**
  - Allow advanced users (or admins) to tweak HTML templates or column layouts

- **Testing & Quality**
  - Automated testing with pytest/unittest for routes, forms, cache, utilities
  - Enforce test coverage thresholds

- **Notifications & Alerts (Admin)**
  - Flask-Mail for admin notifications about system issues or updates
  - Push email/Slack/Webhook notifications for feed failures or keyword matches

- **Containerization & CI/CD**
  - Dockerfile and docker-compose for containerization
  - GitHub Actions for linting, tests, build, deploy

---

## API Frameworks & Implementation Notes

- **Flask-RESTful** is now in use for the weather API and may be used for other endpoints. Continue expanding its use for a consistent API structure.
- **Flask-RESTx** is a possible alternative or supplement to Flask-RESTful, offering built-in Swagger/OpenAPI documentation and more features. Consider evaluating it for future API work.
- **Flask-Limiter** is implemented and working, but continue to expand its use and tune rate limits for all relevant endpoints.

---

## Plugin & Library Recommendations

- **High Priority**
  - Flask-Login (user authentication, implemented)
  - Flask-WTF (form security)
  - Flask-Limiter (rate limiting, implemented)
  - Flask-Compress (performance)

- **Medium Priority**
  - Flask-SQLAlchemy (database, only if more complex data storage is needed)
  - Flask-Mail (email notifications)
  - Flask-Principals (role-based access)
  - Flask-SocketIO (real-time features; see notes below)
  - Flask-MonitoringDashboard (monitoring)
  - Flask-RESTx (API framework, see above)

- **Not Recommended**
  - Flask-Admin (see below)
  - Flask-RESTful (already in use, but RESTx may be a better long-term fit)
  - Flask-Babel (no i18n needs yet)
  - Flask-OAuthlib (no OAuth requirements)

---

## Flask-SocketIO & WSGI/Apache Notes

- Flask-SocketIO enables real-time features (WebSockets, live updates, etc.), but compatibility with mod_wsgi and Apache (worker/event MPM) is limited. WebSocket support is not native to WSGI; production use typically requires a separate async server (e.g., eventlet, gevent, or running behind a reverse proxy like nginx with a dedicated socketio server). Research and test thoroughly before committing to this stack for real-time features.

---

## Flask-Admin: What Does It Provide?

- Flask-Admin is a general-purpose admin interface generator for Flask apps. It provides a web UI for managing database models, users, and other objects. Features include CRUD operations, search, filtering, and custom views. It is powerful but can be overkill for simple admin needs, and adds dependencies and complexity. Consider only if you need a full-featured admin backend for managing lots of structured data.

---

## Implementation Reminders

- Continue expanding Flask-Limiter coverage and tuning limits.
- Continue implementing and expanding Flask-RESTful endpoints; consider Flask-RESTx for future API work.
- Research Flask-SocketIO compatibility with your deployment stack (mod_wsgi, Apache worker/event MPM).
- Re-evaluate Flask-Admin if you need a more robust admin interface in the future.

---

## Example: Flask-MonitoringDashboard Setup

```python
from flask_monitoringdashboard import MonitoringDashboard
from flask_monitoringdashboard.core.config import Config

# Configure for memory-only storage
config = Config()
config.DATABASE = 'sqlite:///:memory:'  # In-memory SQLite
# OR for pure memory (no disk at all):
# config.DATABASE = 'memory://'

# Initialize
dashboard = MonitoringDashboard()
dashboard.init_app(app, config)
```

## 🧩 Additional Python Libraries to Consider

Based on LinuxReport's architecture and goals, here are some targeted Python libraries (beyond Flask extensions) that could further enhance your project:

### News, Feeds, and Parsing
- **newspaper3k**: Advanced news article extraction (handles paywalls, text, images, authors, etc.)
- **dateparser**: Robust date parsing for feeds with inconsistent or non-English date formats
- **langdetect**: Detect article/headline language for better filtering and i18n
- **python-slugify**: Clean, SEO-friendly slugs for URLs and headlines

### AI, NLP, and Summarization
- **transformers** (HuggingFace): Run state-of-the-art LLMs locally for summarization, clustering, or classification
- **spaCy**: Fast NLP for entity recognition, keyword extraction, and topic modeling
- **sumy**: Local text summarization (for fallback or privacy)
- **textblob**: Simple sentiment analysis and text processing
- **gTTS** / **pyttsx3**: Text-to-speech for audio summaries (gTTS for cloud, pyttsx3 for offline)

### Analytics, Trends, and Visualization
- **pandas**: Powerful data analysis for trending topics, user stats, and feed analytics
- **scikit-learn**: Clustering, recommendations, and topic modeling
- **wordcloud**: Generate trending topic word clouds for the UI
- **plotly**: Interactive charts for admin dashboards or analytics

### Performance, Caching, and Concurrency
- **orjson**: Ultra-fast JSON serialization for API endpoints and caching
- **psutil**: System resource monitoring for admin stats and health checks
- **joblib**: Efficient parallelization and disk/memory caching for heavy data tasks

### Security and Validation
- **bleach**: Sanitize HTML in comments or user content
- **passlib**: Advanced password hashing if you expand user auth
- **cryptography**: For any advanced encryption or signing needs
- **python-dotenv**: Securely manage environment variables and secrets

### Web, APIs, and DevOps
- **httpx**: Modern async HTTP client (for scraping or API integrations)
- **requests-cache**: Transparent HTTP caching for feed fetching
- **pytest-cov**: Test coverage reporting for your pytest suite
- **pre-commit**: Git hook management for code quality and linting
- **watchdog**: File system monitoring (auto-reload, asset changes)
- **rich** / **loguru**: Beautiful logging and terminal output for debugging and admin scripts

These libraries are widely used, well-maintained, and align with LinuxReport's modular, high-performance, and AI-driven design. Consider them as you expand features, analytics, or performance optimizations.
