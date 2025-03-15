from datetime import datetime, timezone
import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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

# New helper function to extract post data
def extract_post_data(post, config, url, use_selenium):
    try:
        if use_selenium:
            title_element = post.find_element(By.CSS_SELECTOR, config["title_selector"])
            title = title_element.text.strip()
        else:
            title_element = post.select_one(config["title_selector"])
            if not title_element:
                return None
            title = title_element.text.strip()
    except Exception:
        return None
    if len(title.split()) < 2:
        return None
    try:
        if use_selenium:
            link_element = post.find_element(By.CSS_SELECTOR, config["link_selector"])
            link = link_element.get_attribute(config["link_attr"])
        else:
            link_element = post.select_one(config["link_selector"])
            if not link_element:
                return None
            link = link_element.get(config["link_attr"])
            if link and link.startswith('/'):
                link = urljoin(url, link)
    except Exception:
        return None
    filter_pattern = config.get("filter_pattern", "")
    if filter_pattern and filter_pattern not in link:
        return None
    return {"title": title, "link": link, "id": link, "summary": title}

# Site configurations
site_configs = {
    "https://patriots.win": {
        "needs_selenium": True,
        "post_container": ".post-item",
        "title_selector": ".title a",
        "link_selector": ".preview-parent",
        "link_attr": "href",
        "filter_pattern": ""  # No filter needed for Patriots.win
    },
    "https://breitbart.com/tech/": {
        "needs_selenium": False,
        "post_container": "article",
        "title_selector": "h2 a",
        "link_selector": "h2 a",
        "link_attr": "href",
        "published_selector": ".header_byline time",
        "filter_pattern": "/tech/"  # Ensure only tech articles are included
    },

    "https://revolver.news": {
        "needs_selenium": False,
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
    needs_selenium = config.get("needs_selenium", True)  # Default to using Selenium

    # Initialize caching variables
    etag = ""
    modified = datetime.now(timezone.utc)
    
    # Build entries in feedparser-like format
    entries = []
    driver = None
    
    if needs_selenium:
        driver = create_driver()
        driver.get(url)
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, post_container)))
            print(f"Posts loaded successfully for {site}")
        except Exception as e:
            print(f"Timeout waiting for posts to load on {site}")
        posts = driver.find_elements(By.CSS_SELECTOR, post_container)
    else:
        print(f"Fetching {site} using requests (no Selenium)")
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            posts = soup.select(post_container)
        except Exception as e:
            print(f"Error fetching {site} with requests: {e}")
            posts = []
    # Process posts with shared logic
    for post in posts:
        entry = extract_post_data(post, config, url, use_selenium=needs_selenium)
        if entry:
            entries.append(entry)

    if driver:
        driver.quit()

    
    # Construct feedparser-like result as a plain dict (same for both methods)
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