# AI Agent Guide for LinuxReport

Concise guide for AI agents and humans working on LinuxReport. Focus: correct mental model, key files, critical toggles, and non-obvious rules.

## Project Overview

LinuxReport is a Python/Flask-based news aggregation platform that builds multiple reports (Linux, AI, COVID-19, PV/Solar, Space, Trump, Detroit Techno, etc.) from RSS/HTML sources. It uses:

- Multi-layer caching (memory + SQLite + file) for performance.
- Background workers for feed fetching and processing.
- Optional Selenium/Tor for complex or sensitive sites.
- LLMs for automatic headlines and summaries.

License: GNU LGPL v3.

## Key Technologies (what matters to your code)

- Python 3.x, Flask.
- Package management: uv (recommended, 10-100x faster) or pip (traditional)
- Diskcache (SQLite-backed) and Cacheout for caching.
- Feedparser, BeautifulSoup4 for feeds/HTML.
- Selenium (+ optional Tor) for JS-heavy sites.
- LLMs: OpenAI, sentence_transformers.
- Jinja2 templates; Flask-Assets bundles JS/CSS from templates/ into static/.

## Key Files and Layout (mental map)

Only the most relevant files for contributors/agents:

- app.py:
  - Creates Flask app and core extensions.
  - Registers routes and assets, configures compression and security headers.

- shared.py:
  - Mode enums for report types.
  - Global caches (g_c = diskcache, g_cm = memory).
  - Important feature flags and rate limiting configuration.
  - Common utilities used across the project.

- routes.py:
  - Main routes and blueprint-style initialization for feature modules.
  - Error handlers, security headers, CORS.
  - Page-level caching patterns.

- workers.py:
  - Threaded feed fetching and processing pipeline.
  - Integrates report settings, caching, image selection, and deduplication.

- *_report_settings.py:
  - Per-report CONFIG definitions (feeds, schedule, titles, prompts, special handling).
  - Adding or changing a report type starts here.

- Reddit.py:
  - Reddit API client integration and helpers.

- custom_site_handlers.py:
  - Site-specific scraping/normalization for tricky domains.

- image_parser.py / image_utils.py / image_processing.py:
  - Image candidate extraction, scoring, and JS-heavy site handling.

- templates/:
  - *.html Jinja templates.
  - app.js, core.js, config.js, chat.js, weather.js, infinitescroll.js.
  - themes.css, core.css, weather.css, chat.css, config.css.
  - These are the source of truth for front-end; they are bundled into static/.

- static/:
  - Generated/bundled JS/CSS and static assets.
  - Do not hand-edit generated linuxreport.js / linuxreport.css.

- tests/:
  - Pytest tests for core behavior (locking, dedup, extraction, etc.).

- config.yaml:
  - Runtime configuration (domains, credentials, feature toggles). Never hardcode sensitive values.


## Report Type System

Each report type is driven by a dedicated settings file:

- Files: *_report_settings.py (ai_, linux_, covid_, space_, trump_, pv_, techno_, etc.).
- Each defines a CONFIG object specifying:
  - ALL_URLS: map of feed URL → RssInfo.
  - SITE_URLS: ordered list of feeds to process.
  - CUSTOM_FETCH_CONFIG: special cases (Selenium/Tor/custom handlers).
  - SCHEDULE: hours to auto-update.
  - WEB_TITLE / WEB_DESCRIPTION, REPORT_PROMPT, and related metadata.

Agents:
- When adding/editing a report, adjust CONFIG here instead of scattering constants.
- Keep schedules, feeds, and prompts consistent and centralized.

## Weather System (short)

- Core endpoint: /api/weather.
- Takes lat/lon; otherwise uses backend logic to infer/fallback.
- Behavior is controlled by flags:
  - DISABLE_CLIENT_GEOLOCATION (front-end): when True, do not ask the browser for location.
  - DISABLE_IP_GEOLOCATION (shared.py): when True, fallback is Detroit; when False, use IP geolocation.
- Results are cached to avoid repeated lookups.
- Agents modifying weather behavior must:
  - Respect these flags.
  - Preserve caching to avoid hammering external APIs.

## Caching and Storage (read this; do not bypass)

LinuxReport relies heavily on caching. Agents must integrate with these layers correctly.

Core layers:

1) Disk cache (g_c, via diskcache / SQLite)
- Persistent and shared across processes.
- Stores:
  - Weather and geolocation buckets.
  - Chat comments, banned IPs, rate limiting and lock state.
  - Feed content and other durable data.
- Use for: values that must survive restarts or be shared between workers.

2) Memory cache (g_cm, via cacheout)
- In-process, fast, TTL-based.
- Use for:
  - Hot data, e.g., full page HTML, parsed feeds, small computed results.
- Do not rely on it for correctness; it is an optimization only.

3) File-based cache
- AI-generated HTML snippets like {mode}reportabove.html.
- Used as a lightweight content store and mtime indicator.
- Avoid extra file I/O when mtime/content matches expectations.

4) Assets and CDN
- JS/CSS are built from templates/ into static/linuxreport.js and static/linuxreport.css (often served via CDN).
- Long cache lifetimes are assumed.
- When changing front-end behavior, update templates/*; let the build/bundling pipeline regenerate static assets.

Agent rules:
- Do:
  - Prefer existing cache helpers instead of creating ad-hoc caches.
  - Reuse cache keys/patterns where the codebase already uses them.
- Do not:
  - Introduce separate SQLite/databases for similar data.
  - Bypass caching for hot paths (feeds, weather, front page) unless debugging.
  - Modify generated static/* files by hand.

## Feed Processing and Workers

- workers.py:
  - Uses thread pools for concurrent feed fetching and processing.
  - Integrates:
    - *_report_settings.py for which feeds to hit and how.
    - Deduplication, caching, and image selection.
    - Optional Tor/Selenium paths for complex sources.
- Custom site handlers:
  - Implement site-specific scraping/normalization logic without cluttering generic pipelines.
- Tor/Selenium:
  - Encapsulated in seleniumfetch.py, Tor.py, and custom handlers.
  - Toggle or extend here; do not scatter Selenium/Tor usage.

### Reddit Integration (important toggle)

- Controlled by ENABLE_REDDIT_API_FETCH in [shared.py](shared.py:202).
- When ENABLE_REDDIT_API_FETCH = False (default):
  - Legacy behavior:
    - Reddit URLs fetched via legacy RedditFetcher in [workers.py](workers.py:163) using Tor and/or RSS/feedparser flows.
- When ENABLE_REDDIT_API_FETCH = True:
  - New behavior:
    - Reddit URLs fetched via fetch_reddit_feed_as_feedparser() in [Reddit.py](Reddit.py:346) through RedditFetcher in [workers.py](workers.py:163).
    - Returns feedparser-like entries; workers do not need special handling.
- Bootstrapping:
  - Run [Reddit.py](Reddit.py:487) once interactively on the server to obtain tokens and write reddit_token.json (mode 0600).
  - Do not commit credentials or reddit_token.json.

This flag only affects how Reddit feeds are fetched; other feeds are unaffected.


## Coding Conventions (brief but binding)

- Follow PEP 8.
- Indent with 4 spaces.
- Target max line length: 160 chars.
- Use type hints for public functions where practical.
- Use existing patterns:
  - Classes: PascalCase (SiteConfig, RssInfo).
  - Functions/vars: snake_case.
  - Constants: UPPER_SNAKE_CASE.
  - Filenames: lowercase_with_underscores.py.
- Place:
  - New core modules at repo root.
  - New report configs in *_report_settings.py.
  - New Jinja templates in templates/.
  - New static assets under static/images/ (or appropriate subdir).

## Security and Authentication (project-specific points)

- Admin:
  - Flask-Login for authentication; credentials/config from config.yaml.
- Forms:
  - Flask-WTF with CSRF—reuse existing patterns for new forms.
- Rate limiting:
  - Flask-Limiter configured centrally; follow its helpers/utilities for new endpoints.
- CORS and headers:
  - Security headers and allowed domains are set in core routes; align new endpoints with these defaults.
- IP blocking:
  - Banned IPs stored persistently (diskcache); use the same mechanism when extending protections.
- Never:
  - Commit secrets, tokens, passwords, or private keys.
  - Introduce unauthenticated admin-style endpoints.

## JavaScript and CSS Architecture (minimal operational view)

- Edit JS/CSS source only in templates/:
  - JS: app.js, core.js, config.js, chat.js, weather.js, infinitescroll.js.
  - CSS: themes.css, core.css, weather.css, chat.css, config.css.
- These are bundled into:
  - static/linuxreport.js
  - static/linuxreport.css
- Rules:
  - Do not edit static/linuxreport.* directly.
  - Keep CSRF handling and existing event/delegation patterns consistent.
  - Respect theme, font-size, infinite scroll, and auto-refresh behavior already implemented.

## Configuration Management

- config.yaml:
  - Central runtime config: domains, credentials, feature flags, storage settings.
- *_report_settings.py:
  - Per-report source and behavior.
- Guidelines:
  - Never hardcode sensitive values into Python/JS.
  - Keep configuration-driven behavior in these files instead of scattering constants.

## Common Tasks (quick recipes)

Adding a new report type:
1) Create {type}_report_settings.py with a CONFIG object:
   - Use existing *_report_settings.py as reference.
2) Add {type}reportabove.html template and relevant branding in static/images/.
3) Wire any domain/routing needs in config.yaml and routes.py (following existing patterns).
4) Ensure workers pick it up (typically automatic via CONFIG structure).

Adding a new feature/route:
1) Create a module, e.g. my_feature.py, that exposes init_my_feature_routes(app).
2) Call that initializer from routes.py.
3) Add templates/static assets under templates/ and static/ as needed.
4) Add or update tests under tests/ (see "Relevant tests" below).

Modifying caching behavior:
1) For page caching: adjust keys/TTLs where caching decorators or helpers are used (often in routes.py or shared utilities).
2) For data caching:
   - Use g_c for persistent/shared data.
   - Use g_cm for hot ephemeral data.
3) When changing data flows:
   - Implement appropriate invalidation or key versioning.
4) After cache-related changes, run the relevant cache/perf tests.

## Development Workflows (minimal)

Setup:
- git clone <repo>
- cd LinuxReport
- Copy/edit config.yaml for local settings.

Dependency installation options:

**Option 1: uv (recommended - 10-100x faster, reproducible builds)**
- Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- uv sync
- uv run python app.py

**Option 2: pip (traditional, widely supported)**
- pip install -r requirements.txt
- python app.py

Testing:
- Run the full suite when in doubt:
  - pytest tests/
- Prefer targeted tests after specific changes.

Assets:
- Edit JS/CSS in templates/.
- Let the asset pipeline (Flask-Assets or equivalent) regenerate static bundles.

## Relevant tests (what to run after changes)

When modifying specific areas, run at least the corresponding tests:

- Caching / compression / infra:
  - tests/test_compression.py
  - tests/test_sqlitelock.py

- Feed parsing, titles, deduplication:
  - tests/test_extract_titles.py
  - tests/test_dedup.py

- Forms and input handling:
  - tests/test_forms.py

- Browser / scraper behavior:
  - tests/test_browser_switch.py
  - tests/playwright_test.py
  - tests/playwright_simple_test.py
  - tests/selenium_test.py

- Tor / network behavior:
  - tests/tortest.py

Note:
- Additional benchmark scripts exist under tests/ for historical performance experiments.
  They are optional and not part of the normal regression suite.

## Performance Considerations

- Use caching correctly before optimizing elsewhere.
- Keep I/O-bound work in workers/thread pools rather than blocking request handlers.
- Leverage existing minified/bundled assets in production.
- Respect rate limiting and avoid adding unbounded per-request work.

## Troubleshooting (short checklist)

- Cache/db:
  - Verify cache.db exists and is writable.
  - Confirm cache keys and TTLs are sane when debugging stale/fresh data.
- Feeds:
  - Check network/SSL.
  - Verify related *_report_settings.py and custom_site_handlers.py entries.
  - Inspect workers and Tor/Selenium configuration for special sites.
- Assets:
  - Ensure bundling runs; check console/network for 404s or JS errors.
- Auth:
  - Confirm config.yaml credentials.
  - Verify Flask-Login wiring and protected routes.

## Important Guidelines (agent checklist)

Do:
- Use existing caching infrastructure and helpers.
- Follow the modular route pattern for new features.
- Keep behavior configuration-driven (config.yaml, *_report_settings.py).
- Use type hints and match existing style/patterns.
- Add or update tests for non-trivial changes.

Avoid:
- Bypassing caches on hot paths.
- Hardcoding config, secrets, or environment-specific values.
- Editing generated static/ assets directly.
- Creating circular imports.
- Shipping credentials, tokens, or private keys in the repo.

## Reddit API Setup (for agents and operators)

- Create a Reddit "script" app in your Reddit preferences.
- Set redirect URI to a URL handled by /reddit/callback (see [routes.py](routes.py:748)); this route is cosmetic.
- On the server, run [Reddit.py](Reddit.py:487) once:
  - Provide client_id, client_secret, username, password.
  - It writes reddit_token.json (mode 0600) with tokens.
- Toggle:
  - ENABLE_REDDIT_API_FETCH in [shared.py](shared.py:205).
    - False: legacy Tor/Selenium/RSS pipeline.
    - True: Reddit API via [Reddit.py](Reddit.py:346) + [workers.py](workers.py:163).
- Never commit reddit_token.json or credentials.

## Additional Documentation (if available)

If present in the repo/deploy environment, see:

- README.md: setup and high-level overview.
- Caching.md: deeper caching internals.
- README_object_storage_sync.md: CDN/object storage sync configuration.
- PWA.md, Scaling.md, ROADMAP.md: advanced deployment and roadmap details.
- httpd-vhosts-sample.conf: sample Apache deployment.

External references:

- Flask, Jinja2, PEP 8, Flask-Assets, Diskcache docs for library specifics.