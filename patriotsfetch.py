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


def fetch_patriots():
    url = "https://patriots.win"
    
    # Initialize caching variables
    etag = ''  # Placeholder (Selenium doesn’t provide this natively)
    modified = datetime.now(timezone.utc)

    # Set up Selenium
    driver = create_driver()
    driver.get(url)

    # Wait for posts to load
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "post-item"))
        )
        print("Posts loaded successfully")
    except:
        print("Timeout waiting for posts to load")
        driver.quit()
        sys.exit(1)

    # Find all post containers
    posts = driver.find_elements(By.CLASS_NAME, "post-item")

    # Build entries in feedparser format
    entries = []
    for post in posts:
        try:
            # Title
            title_element = post.find_element(By.CLASS_NAME, "title")
            title = title_element.find_element(By.TAG_NAME, "a").text

            if len(title.split()) < 2:
                continue

            # Link (external URL from preview-parent)
            link_element = post.find_element(By.CLASS_NAME, "preview-parent")
            link = link_element.get_attribute("href")

            # Additional feedparser-like fields
            post_id = post.get_attribute("id")  # e.g., "7518513"
            published = datetime.now(timezone.utc).isoformat()  # Approximate

            # Entry dict mimicking feedparser
            entry = {
                'title': title,
                'link': link,
                'id': f"{url}/p/{post_id}",  # Unique ID
                'published': published,
                'published_parsed': datetime.now(timezone.utc).timetuple(),  # For compatibility
                'summary': title  # Optional: mimics feedparser behavior
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
            'title': 'The Donald - patriots.win',
            'link': url,
            'description': 'A never-ending rally of patriots dedicated to Donald J. Trump'
        },
        'href': url,
        'status': 200  # Mimics a successful fetch
    }

    return result