from datetime import datetime, timezone
import sys

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager(
        chrome_type=ChromeType.CHROMIUM).install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

class FeedParserDict(dict):
    """Mimic feedparser's FeedParserDict for compatibility"""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"No attribute '{key}'")


# Site configurations
site_configs = {
    "https://patriots.win": {
        "post_container": ".post-item",
        "title_selector": ".title a",
        "link_selector": ".preview-parent",
        "link_attr": "href",
        "filter_pattern": ""  # No filter needed for Patriots.win
    },
    "https://breitbart.com/tech/": {
        "post_container": "article",
        "title_selector": "h2 a",
        "link_selector": "h2 a",
        "link_attr": "href",
        "published_selector": ".header_byline time",
        "filter_pattern": "/tech/"  # Ensure only tech articles are included
    },

    "https://revolver.news": {
        "post_container": "article.item",
        "title_selector": "h2.title a",
        "link_selector": "h2.title a",
        "link_attr": "href",
        "filter_pattern": ""
    },
}

def fetch_site_posts(site):
    # Retrieve the configuration for the specified site
    config = site_configs.get(site)
    if not config:
        print(f"Configuration for site '{site}' not found.")
        return []

    # Extract configuration values
    url = site
    post_container = config["post_container"]
    title_selector = config["title_selector"]
    link_selector = config["link_selector"]
    link_attr = config["link_attr"]
    published_selector = config.get("published_selector")  # Optional
    filter_pattern = config.get("filter_pattern", "")  # Optional, defaults to empty string

    # Initialize caching variables (placeholders, as Selenium doesn’t provide these natively)
    etag = ""
    modified = datetime.now(timezone.utc)

    # Set up Selenium
    driver = create_driver()
    driver.get(url)

    # Wait for posts to load
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, post_container)))
        print(f"Posts loaded successfully for {site}")
    except:
        print(f"Timeout waiting for posts to load on {site}")

    # Find all post containers
    posts = driver.find_elements(By.CSS_SELECTOR, post_container)

    # Build entries in feedparser-like format
    entries = []
    for post in posts:
        try:
            # Extract title
            title_element = post.find_element(By.CSS_SELECTOR, title_selector)
            title = title_element.text.strip()

            # Skip posts with titles shorter than 2 words (as in original code)
            if len(title.split()) < 2:
                continue

            # Extract link
            link_element = post.find_element(By.CSS_SELECTOR, link_selector)
            link = link_element.get_attribute(link_attr)

            # Apply filter if specified
            if filter_pattern and filter_pattern not in link:
                continue

            # Create entry dictionary mimicking feedparser
            entry = {
                "title": title,
                "link": link,
                "id": link,  # Use the link as the unique ID for simplicity
                "summary": title  # Use title as summary, consistent with original
            }
            entries.append(entry)
        except Exception as e:
            print(f"Error extracting post: {e}")
            continue

    # Clean up Selenium
    driver.quit()

    # Construct feedparser-like result as a plain dict
    result = {
        'entries': entries,
        'etag': etag,
        'modified': modified,
        'feed': {
            'title': url,
            'link': url,
            'description': ''
        },
        'href': url,
        'status': 200  # Mimics a successful fetch
    }

    return result