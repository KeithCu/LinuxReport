![LinuxReport logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/linuxreportfancy.webp)
**and**
![CovidReport logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/covidreportfancy.webp)
**and**
![AIReport_logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/aireportfancy.webp)
--------------------------------------------------------------------------------
Simple and fast news site based on Python / Flask. Meant to be a http://drudgereport.com/ clone for Linux or Covid-19 news, updated automatically 24/7, and customizable by the user, including custom feeds and the critically important dark mode.

Here's the running code for Linux, Covid, and AI, Solar / PV, and Detroit Techno:

https://linuxreport.net 

https://covidreport.org

https://aireport.keithcu.com

https://pvreport.org

https://news.thedetroitilove.com

Takes advantage of thread pools and Apache process pools to be high-performance and scalable. Some people incorrectly say that Python is slow, but this app typically starts returning the page after less than 10 lines of my Python code.

It now auto-updates the top headlines using LLMs and https://api.together.ai/. They have inexpensive and high-performance inference. I can make 300 of these requests to Meta's Llama 3.3-70B for $1. I tried other models but they didn't work as well, but there are cheaper ones to consider. See https://github.com/KeithCu/LinuxReport/blob/master/auto_update.py.

Feel free to request more default RSS feeds, or send pull requests.

Web servers need a configuration file to tell it where the flask software is located. A sample Apache one is included.

```bash
$ git clone https://github.com/KeithCu/LinuxReport
$ cd linuxreport
$ sudo pip install -r requirements.txt
$ python -m flask run
```

## Admin Mode Security

The application has an admin mode that allows editing headlines and other admin-only functions. Admin mode is protected by a password stored in `config.yaml`.

The repository includes a default config file with a default password:

```yaml
# LinuxReport Configuration
# IMPORTANT: Change this default password for security!

# Admin settings
admin:
  password: "LinuxReportAdmin2024"
```

**IMPORTANT:** For security, you should change the default password immediately after cloning the repository by editing the `config.yaml` file.

Suggestions from O4-mini:
Here are some next‑step ideas that don't appear to be in place yet:

Metrics & monitoring
– Instrument page views, fetch success rates, and feed latencies; plug into Prometheus/Grafana or at least log structured metrics.

Dashboard & charts
– Visualize feed health over time (last‑fetch timestamps, entry counts) with a small admin dashboard.

User‑customizable templates
– Let advanced users tweak the HTML "sitebox" template or column layout via a settings page.

Automated testing
– Introduce pytest/unittest suites for your routes, forms, cache interactions, and utility modules; enforce coverage thresholds.

Server‑side user accounts & persistent settings
– Replace cookie‑only prefs with Flask‑Login (or OAuth) and store each user's favorites, feed order, dark/light mode in a database.

Read/unread and bookmarking
– Track which articles a user has seen and let them "star" or archive items for later.

Full‑text search & filtering
– Index entries (e.g. via Whoosh or Elasticsearch) so users can search across all feeds and filter by keyword, date, or tag.

Scheduled background jobs
– Instead of fetching on demand or thread triggers, use Celery or APScheduler to run periodic feed updates, prune old data, and send alerts.

Notifications & alerts
– Push e‑mail or Slack/Webhook notifications when keywords appear in new items or a feed fails.

API expansion & docs
– Expose a RESTful JSON API for feed listings, entries, and user settings; add Swagger/OpenAPI docs and rate limiting.

Internationalization
– Use Flask‑Babel so UI text and date formatting adapt to user locales.

Containerization & CI/CD
– Add a Dockerfile + docker‑compose, and set up GitHub Actions (lint, tests, build, deploy).


User-oriented features: 

1. Headline Search: Add a search bar to quickly find past headlines or stories by keyword or date.
2. Save/Bookmark Headlines: Allow users to save interesting headlines for later reading.
3. Trending Topics & Word Clouds: Visualize the most mentioned topics or keywords from recent headlines.
4. Headline Timeline: Let users browse headlines by date, seeing how stories evolved over time.
5. Headline Comparison: Highlight how different sources report the same story, showing side-by-side headlines or summaries.
6. Local News Integration: Show local news based on user location or selected region.
7. RSS/Atom Export: Let users export their custom feed or archive as RSS/Atom for use in other readers.
8. Newsletter/Email Alerts: Send users a daily or breaking-news email with top headlines or topics they follow.
9. Commenting & Reactions: Let users comment on or react to headlines (e.g., thumbs up/down, emojis).
10. "On This Day" Feature: Show headlines from the same day in previous years for historical context.
11. Fact-Check Highlights: Flag stories that have been fact-checked, with links to sources.
12. Audio Summaries: Offer text-to-speech for top headlines or summaries, so users can listen on the go.
13. Integration with Calendar: Let users add important news events to their calendar.
14. Polls & Quick Surveys: Engage users with polls about current events or site features.

These features can help make your site more interactive, personalized, and useful for regular visitors.

## Feature Suggestions (May 23, 2025 - Claude AI)

Here are some suggested features to enhance user engagement and functionality:

1. **User Accounts & Personalization** (High Impact)
   - Allow users to create accounts to save their preferences
   - Enable personalized feed curation and layout preferences
   - Store dark/light mode preference persistently
   - This would significantly increase user retention and engagement

2. **Enhanced Search & Filtering** (High Impact)
   - Add a search bar to find headlines across all feeds
   - Implement filters for date ranges, sources, and topics
   - Add tags/categories to headlines for better organization
   - This would make your site more useful for research and following specific topics

3. **Mobile App Experience** (High Impact)
   - Since you already have Mobility support, enhance the mobile experience
   - Add a "Add to Home Screen" feature for PWA support
   - Implement pull-to-refresh and infinite scroll
   - This would help capture mobile users who prefer app-like experiences

4. **Social Features** (Medium Impact)
   - Add ability to share headlines directly to social media
   - Implement a "Save for Later" feature
   - Add a "Most Popular" section based on user interactions
   - This would increase viral growth and user engagement

5. **Notification System** (Medium Impact)
   - Allow users to subscribe to breaking news alerts
   - Implement keyword-based notifications
   - Add email digests for daily summaries
   - This would increase return visits and user engagement

6. **Analytics Dashboard** (Medium Impact)
   - Add a simple dashboard showing most-read headlines
   - Display trending topics
   - Show feed health metrics
   - This would help users understand what's popular and what's working

7. **API Access** (Medium Impact)
   - Create a public API for your headlines
   - Allow developers to integrate your content
   - Add rate limiting and API keys
   - This would expand your reach to other platforms

8. **Enhanced Content Features** (Low Impact)
   - Add "Related Stories" section
   - Implement "On This Day" historical headlines
   - Add brief summaries for headlines
   - This would increase content engagement

9. **Performance Optimizations** (Low Impact)
   - Implement lazy loading for images
   - Add better caching strategies
   - Optimize mobile performance
   - This would improve user experience and retention

10. **Internationalization** (Low Impact)
    - Add support for multiple languages
    - Implement region-specific feeds
    - Add timezone support
    - This would expand your global reach

### AI-Enhanced Features
Building on your existing Together.ai integration:
- Add AI-generated summaries for headlines
- Implement AI-powered topic clustering
- Use AI to detect and highlight breaking news
- Add AI-powered content recommendations

