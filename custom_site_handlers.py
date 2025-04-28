from bs4 import BeautifulSoup
from image_utils import HEADERS
import requests


def extract_underlying_url(url, selector_func):
    """Common function to extract an underlying URL from a webpage."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        underlying_url = selector_func(soup)
        if (underlying_url):
            print(f"Found underlying URL: {underlying_url}")
            return underlying_url

        print("No underlying URL found, falling back to original")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error extracting underlying URL: {e}")
        return None

def citizenfreepress_selector(soup):
    external_link_paragraph = soup.find('p', class_='external-link')
    if external_link_paragraph:
        link = external_link_paragraph.find('a')
        if link and 'href' in link.attrs:
            return link['href']
    return None

def linuxtoday_selector(soup):
    link = soup.find('a', class_='action-btn publication_source')
    if link and 'href' in link.attrs:
        return link['href']
    return None

def generic_custom_fetch(url, selector_func):
    from image_parser import fetch_largest_image  # Import here to avoid circular import
    underlying_url = extract_underlying_url(url, selector_func)
    return fetch_largest_image(underlying_url if underlying_url else url)

def citizenfreepress_custom_fetch(url):
    return generic_custom_fetch(url, citizenfreepress_selector)

def linuxtoday_custom_fetch(url):
    return generic_custom_fetch(url, linuxtoday_selector)

def custom_hack_miragenews(url):
    """Custom handler for miragenews.com to find the video thumbnail."""
    from image_parser import fetch_largest_image # Import locally
    return fetch_largest_image(url)

def custom_hack_justthenews(url):
    """Custom handler for justthenews.com to find the video thumbnail."""
    from image_parser import fetch_largest_image # Import locally
    return fetch_largest_image(url)

def reddit_custom_fetch(url, underlying_link=None, html_content=None):
    """Custom handler for Reddit pages: prioritize provided underlying_link or html_content before parsing the Reddit page."""
    from image_parser import fetch_largest_image
    # If underlying_link is provided and is external, use it
    if underlying_link and 'reddit' not in underlying_link:
        print(f"Reddit hack: using provided underlying link {underlying_link}")
        return fetch_largest_image(underlying_link)
    # If html_content is provided, find first external link
    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'reddit' not in href:
                print(f"Reddit hack: using link from html_content {href}")
                return fetch_largest_image(href)
    # No HTTP fetch fallback; if no external link found above, no image
    print(f"No images found in Reddit content, not bothering to try reddit.com: {url}")  # no query to Reddit
    return None

# Dictionary mapping domains to their custom handlers
custom_hacks = {
    'miragenews.com': custom_hack_miragenews,
    'justthenews.com': custom_hack_justthenews,
    'linuxtoday.com': linuxtoday_custom_fetch,
    'citizenfreepress.com': citizenfreepress_custom_fetch,
    'reddit.com': reddit_custom_fetch
}
