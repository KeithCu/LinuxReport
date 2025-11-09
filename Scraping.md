# Scraping and Site Debugging Guide for LinuxReport

Practical guide for quickly fixing broken scraping when a source site changes.

Primary job:
- Make small, surgical tweaks (usually CSS selectors or minor parsing logic) so headlines and links for a given site work again.
- Do not redesign architecture; use the existing tools and patterns.

Backend fetch choice:
- Whether a site uses plain HTTP, Selenium, or (future) Playwright is decided centrally (e.g. in `*_report_settings.py` and shared fetch helpers).
- For now, assume Selenium is used where a headless browser is required; you generally do not need to change how that is selected.
- Focus on: given the HTML/DOM we already fetch, extract the right items via minimal, local changes.

Audience:
- Humans and LLM agents maintaining feed scraping.
- Focused, step-by-step, and aligned with existing tooling:
  - `site_debugger.py`
  - `test_site_debug.py`
  - `custom_site_handlers.py`
  - `seleniumfetch.py`
  - `*_report_settings.py`

---

## 1. Quick Triage: Is This a Scraping Problem?

Use this checklist when a site shows missing or empty items:

- Confirm only one/few sites are broken:
  - If all feeds are empty → check network, config, or global logic.
  - If only specific sites are empty or weird → likely per-site scraping issue.

- Check logs:
  - Look in:
    - `linuxreport.log`
    - Any relevant service logs (systemd, web server)
  - Search for:
    - HTTP errors (403/404/500)
    - Timeouts
    - Parsing errors
    - Messages from `seleniumfetch.py` / `playwrightfetch.py` about empty content or failed selectors.

If logs confirm "no entries found" or DOM mismatch for a specific site, continue below.

---

## 2. Use site_debugger.py to Inspect the Site

`site_debugger.py` is your primary tool to see what LinuxReport actually receives from a site.

Typical workflow (examples; adjust arguments to your env):

1. Run debugger against a problematic URL:
   - Check `site_debugger.py` usage (arguments/options) to:
     - Fetch the page similarly to production.
     - Optionally use the same user agent, headers, and Tor/Selenium/Playwright paths.

2. Inspect outputs:
   - Look for:
     - HTTP status.
     - Final URL after redirects.
     - Snippets of HTML around the expected headline/link elements.
     - Whether content is loaded server-side or via JavaScript only.

3. Decide:
   - If HTML contains the items in clear tags, this is a selector/parsing issue.
   - If HTML is mostly empty but browser shows content:
     - Site is JS-heavy → should use `seleniumfetch.py` or `playwrightfetch.py`.
   - If you see bot-blocking or captcha pages:
     - Consider Tor, different user agents, or backing off that source.

Use `test_site_debug.py` to:
- Validate that `site_debugger.py` semantics stay correct.
- Provide regression protection when modifying debugging utilities.

---

## 3. Fixing Selectors and Parsing

Most breakages are due to minor HTML structure changes.

Key places:

- `custom_site_handlers.py`:
  - Site-specific parsing logic and normalizers.
  - Add/update handlers here rather than hacking generic code.

- `image_parser.py` and `image_utils.py`:
  - Responsible for image candidate extraction and scoring.
  - Adjust only if image selection is broken across sites or for a class of layouts.

General approach:

1. Use `site_debugger.py` to capture current HTML.
2. Identify the new CSS selectors / DOM patterns for:
   - Article containers
   - Title/URL
   - (Optional) summary, date, image
3. Implement or adjust a handler in `custom_site_handlers.py`:
   - Keep it narrowly scoped to that domain.
   - Reuse shared helpers where possible.
4. Update the relevant `*_report_settings.py` if:
   - Feed endpoints changed.
   - Site switched from RSS to HTML-only or vice versa.

Then:

- Run targeted tests:
  - `pytest tests/test_extract_titles.py`
  - `pytest tests/test_dedup.py` (if you changed how items are normalized)

---

## 4. Notes on Selenium / Browser-based Fetching

Most fixes do not involve changing how sites are fetched.

Key points:
- The decision to use Selenium vs plain HTTP is made centrally (e.g. in `*_report_settings.py` and shared fetch utilities).
- For broken sites, assume:
  - The correct fetch path (including Selenium when needed) is already chosen.
  - Your job is to adjust how we parse the HTML/DOM returned by that path, usually in `custom_site_handlers.py`.

Only consider fetch-path changes if:
- Logs + `site_debugger.py` clearly show we are consistently hitting bot-block pages, CAPTCHAs, or empty shells that cannot be parsed.
- In that rare case:
  - Update the relevant `*_report_settings.py` and/or shared fetch config following existing patterns.
  - Keep logic centralized; do not add ad-hoc Selenium calls scattered around.
  - Run `pytest tests/test_browser_switch.py` and `pytest tests/selenium_test.py` if you changed fetch-selection logic.

---

## 5. Using Logs Effectively

Your pipelines already log hints when scraping returns no entries.

When a site breaks:

- Search logs for:
  - That site’s domain
  - Messages like:
    - "no entries found"
    - "failed to extract"
    - timeouts or HTTP status
- Map log messages back to:
  - `custom_site_handlers.py`
  - `seleniumfetch.py`
  - `playwrightfetch.py`
  - relevant `*_report_settings.py` entry

Then:

- Adjust the appropriate handler or configuration.
- Re-run:
  - `site_debugger.py` for that site
  - Targeted tests as in previous sections

---

## 6. Safe Patterns and Rules for Scraping Fixes

Follow these constraints to keep the system robust:

- Keep site-specific logic isolated:
  - Prefer functions/blocks in `custom_site_handlers.py` keyed by domain or pattern.
  - Avoid hardcoding site-specific behavior deep inside generic code.

- Maintain consistent data shape:
  - Handlers should output entries that look like existing feedparser-based entries.
  - This ensures deduplication, templates, and downstream logic keep working.

- Let central config drive Selenium usage:
  - Assume Selenium vs HTTP choice is already correct unless logs/debugging prove otherwise.
  - Reuse existing Selenium helpers; do not implement your own driver management.

- Respect caching:
  - If you change scraping logic:
    - Consider whether caches should be invalidated or keys adjusted.
    - Avoid designs that cause cache stampedes or bypass caches.

- Validate with tests:
  - Always run:
    - `pytest tests/test_extract_titles.py`
  - And any specialized tests matching the components you modified.

---

## 7. Minimal Workflow Summary (Copy/Paste Playbook)

When a site breaks:

1. Confirm it’s isolated:
   - Compare with other sites; inspect `linuxreport.log`.

2. Debug fetch:
   - Run `site_debugger.py` for that URL.
   - Inspect HTML/DOM and HTTP status.

3. Fix logic:
   - Update or add handler in `custom_site_handlers.py`.
   - If JS-heavy, configure Selenium/Playwright via `*_report_settings.py` and existing fetch helpers.

4. Re-check locally:
   - Run `site_debugger.py` again.
   - Confirm expected entries appear.

5. Run targeted tests:
   - `pytest tests/test_extract_titles.py`
   - `pytest tests/test_dedup.py` (if normalization changed)
   - Selenium/Playwright tests if those paths were touched.

6. Deploy and monitor:
   - Watch logs for the domain.
   - Verify entries appear on the live site.

This document is intentionally scoped and practical. From agents.md, link to Scraping.md when scraping-specific work is needed, and use this guide as the canonical playbook for fixing broken sites.