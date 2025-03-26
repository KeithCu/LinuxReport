from datetime import datetime, timezone
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

from fake_useragent import UserAgent

from Tor import renew_tor_ip
ua = UserAgent()

def create_driver(use_tor, user_agent):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={user_agent}")
    if use_tor:
        options.add_argument("--proxy-server=socks5://127.0.0.1:9050")

    service = Service(ChromeDriverManager(
        chrome_type=ChromeType.CHROMIUM).install())
    driver = webdriver.Chrome(service=service, options=options)
    # Disable compression by setting Accept-Encoding to identity via CDP
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Accept-Encoding": "identity"}})
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
    return {"title": title, "link": link, "id": link, "summary": post.text.strip()}

# Site configurations
site_configs = {
    "https://patriots.win": {
        "needs_selenium": True,
        "needs_tor": False,
        "post_container": ".post-item",
        "title_selector": ".title a",
        "link_selector": ".preview-parent",
        "link_attr": "href",
        "filter_pattern": ""  # No filter needed for Patriots.win
    },
    "https://breitbart.com": {
        "needs_selenium": False,
        "needs_tor": False,
        "post_container": "article",
        "title_selector": "h2 a",
        "link_selector": "h2 a",
        "link_attr": "href",
        "published_selector": ".header_byline time",
        "filter_pattern": "/tech/"  # Ensure only tech articles are included
    },

    "https://revolver.news": {
        "needs_selenium": False,
        "needs_tor": False,
        "post_container": "article.item",
        "title_selector": "h2.title a",
        "link_selector": "h2.title a",
        "link_attr": "href",
        "filter_pattern": ""
    },

    "https://www.reddit.com": {
        "needs_selenium": True,
        "needs_tor": True,
        "post_container": "article",
        "title_selector": "a[id^='post-title-']",
        "link_selector": "a[id^='post-title-']",
        "link_attr": "href",
        "filter_pattern": ""
    },
}

def fetch_site_posts(url, user_agent):
    # Extract site from full URL
    parsed = urlparse(url)
    base_site = f"{parsed.scheme}://{parsed.netloc}"
    site = base_site

    # Retrieve the configuration for the specified site
    config = site_configs.get(site)
    if not config:
        print(f"Configuration for site '{site}' not found.")
        return []

    etag = ""
    modified = datetime.now(timezone.utc)
    entries = []

    if config.get("needs_selenium", True):
        max_attempts = 3 if config.get("needs_tor") else 1
        for attempt in range(max_attempts):
            
            if "reddit" in site: #For reddit, we always pick a random user agent.
                user_agent = ua.random

            driver = create_driver(config["needs_tor"], user_agent)
            try:
                driver.get(url)

                log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selenium_fetch_logs")
                os.makedirs(log_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_site = site.replace("https://", "").replace("http://", "").replace(".", "_")
                filename = f"{safe_site}_attempt{attempt+1}_{timestamp}.html"
                filepath_log = os.path.join(log_dir, filename)
                with open(filepath_log, "w", encoding="utf-8") as log_file:
                    log_file.write(driver.page_source)

                if site == "https://www.reddit.com":
                    pass
                    #WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, config["title_selector"])))
                else:
                    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, config["post_container"])))
                print(f"Posts loaded successfully on attempt {attempt+1} for {url}")

                posts = driver.find_elements(By.CSS_SELECTOR, config["post_container"])
                if not posts:
                    snippet = driver.page_source[:200]
                    print("No posts found. Page source snippet:", snippet)
                    raise Exception("No posts found")
                # Extract post data while driver is still active
                for post in posts:
                    entry = extract_post_data(post, config, url, use_selenium=True)
                    if entry:
                        entries.append(entry)
                break  # Successful extraction; exit loop.
            except Exception as e:
                print(f"Attempt {attempt+1} error on {url}: {e}")
                if attempt < max_attempts - 1:
                    renew_tor_ip()
                    print(f"Attempt {attempt+1} failed, renewing TOR IP and trying again...")
                continue
            finally:
                driver.quit()
    else:
        print(f"Fetching {site} using requests (no Selenium)")
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            posts = soup.select(config["post_container"])
        except Exception as e:
            print(f"Error fetching {site} with requests: {e}")
            posts = []
        for post in posts:
            entry = extract_post_data(post, config, url, use_selenium=False)
            if entry:
                entries.append(entry)

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