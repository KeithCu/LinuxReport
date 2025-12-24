"""
Merged Image Fetching Module

Combines functionality from:
- image_parser.py (requests/BS4 parsing)
- image_utils.py (utilities and constants)
- image_processing.py (Selenium parsing)
- custom_site_handlers.py (site-specific handlers)

Preserves external API:
- custom_fetch_largest_image(url, underlying_link=None, html_content=None)

Selenium support included but opt-in via fetch_largest_image_selenium (unused externally).
"""

import os
import re
import requests
from io import BytesIO
from PIL import Image
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import json
from shared import g_logger

# Selenium imports (for optional JS-heavy sites)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException
from browser_fetch import get_shared_driver

import urllib.request
import urllib.error
import socket

# Constants from image_utils.py
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0'}
EXCLUDED_PATTERNS = ['logo', 'icon', 'avatar', 'banner', 'emoji', 'css', 'advertisement', 'michaellarabel']
EXCLUDED_RE = re.compile(r"(?:" + r"|".join(re.escape(p) for p in EXCLUDED_PATTERNS) + r")", re.IGNORECASE)
IMAGE_EXT_RE = re.compile(r"\\.(jpe?g|png|webp|gif|svg)([#?].*)?$", re.IGNORECASE)

# Utility functions from image_utils.py
def is_excluded(url):
    return bool(EXCLUDED_RE.search(url))

def parse_dimension(value):
    m = re.match(r'^\\s*(\\d+(?:\\.\\d+)?)', str(value))
    return float(m.group(1)) if m else 0

def extract_dimensions_from_tag_or_style(tag):
    width = 0
    height = 0
    try:
        if tag.get('width'):
            w = tag['width']
            if isinstance(w, str) and w.strip().endswith('px'):
                w = w.strip().rstrip('px')
            if str(w).isdigit():
                width = int(w)
        if tag.get('height'):
            h = tag['height']
            if isinstance(h, str) and h.strip().endswith('px'):
                h = h.strip().rstrip('px')
            if str(h).isdigit():
                height = int(h)
    except (ValueError, KeyError):
        pass
    if (width == 0 or height == 0) and tag.get('style'):
        style = tag['style']
        width_match = re.search(r'width:\\s*(\\d+)px', style)
        if width_match:
            width = int(width_match.group(1))
        height_match = re.search(r'height:\\s*(\\d+)px', style)
        if height_match:
            height = int(height_match.group(1))
    return width, height

def get_actual_image_dimensions(img_url):
    try:
        headers_with_referer = HEADERS.copy()
        headers_with_referer["Referer"] = img_url
        response = requests.get(img_url, headers=headers_with_referer, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '').lower()
        
        content_length_header = response.headers.get('Content-Length')
        if content_length_header is not None:
            try:
                content_length = int(content_length_header)
                if content_length < 100:
                    g_logger.debug(f"Skipping small image ({content_length} bytes): {img_url}")
                    return 0, 0
            except (ValueError, TypeError):
                pass
        
        if 'svg' in content_type:
            g_logger.debug(f"SVG image detected for {img_url}, attempting to parse dimensions")
            try:
                svg = ET.fromstring(response.content)
                width = svg.attrib.get('width')
                height = svg.attrib.get('height')
                
                def parse_svgdimension(value):
                    if not value:
                        return 0
                    if value.isdigit():
                        return int(value)
                    numeric_part = re.match(r'^(\\d+(\\.\\d+)?)', value)
                    if numeric_part:
                        return float(numeric_part.group(1))
                    return 0
                    
                if width and height:
                    width_val = parse_svgdimension(width)
                    height_val = parse_svgdimension(height)
                    if width_val > 0 and height_val > 0:
                        g_logger.debug(f"Parsed SVG dimensions from attributes for {img_url}: {int(width_val)}x{int(height_val)}")
                        return int(width_val), int(height_val)
                        
                viewBox = svg.attrib.get('viewBox')
                if viewBox:
                    parts = viewBox.split()
                    if len(parts) == 4:
                        try:
                            width = float(parts[2])
                            height = float(parts[3])
                            g_logger.debug(f"Parsed SVG dimensions from viewBox for {img_url}: {int(width)}x{int(height)}")
                            return int(width), int(height)
                        except (ValueError, IndexError):
                            pass
                             
                fallback_dim = min(max(int(len(response.content) ** 0.4), 200), 800)
                g_logger.debug(f"Fallback SVG dimensions based on file size for {img_url}: {fallback_dim}x{fallback_dim}")
                return fallback_dim, fallback_dim
            except ET.ParseError as e:
                g_logger.debug(f"Error parsing SVG for {img_url}: {e}")
                return 640, 480
        
        try:
            with Image.open(BytesIO(response.content)) as img:
                width, height = img.size
                g_logger.debug(f"Got actual dimensions for {img_url}: {width}x{height}")
                return width, height
        except Image.UnidentifiedImageError:
            g_logger.debug(f"Could not identify image file: {img_url}")
            return 0, 0
        except (IOError, OSError) as e:
            g_logger.debug(f"Error reading image dimensions with PIL for {img_url}: {e}")
            return 0, 0
    except requests.exceptions.RequestException as e:
        g_logger.debug(f"Request error getting dimensions for {img_url}: {e}")
        return 0, 0
    except (AttributeError, TypeError) as e:
        g_logger.debug(f"Generic error getting dimensions for {img_url}: {e}")
        return 0, 0

def extract_domain(url):
    parsed = urlparse(url)
    netloc = parsed.netloc
    if netloc.startswith("www."):
        return netloc[4:]
    return netloc

def parse_best_srcset(srcset):
    if not srcset:
        return None, 0

    entries = []
    for part in srcset.split(','):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        url = tokens[0]
        width = 0
        for descriptor in tokens[1:]:
            if descriptor.endswith('w') and descriptor[:-1].isdigit():
                width = int(descriptor[:-1])
                break
            if descriptor.endswith('x'):
                try:
                    width = int(1000 * float(descriptor[:-1]))
                    break
                except ValueError:
                    pass
        entries.append((width, url))
    if not entries:
        return None, 0
    best_width, best_url = max(entries, key=lambda x: x[0])
    return best_url, best_width

def score_image_candidate(width, height, alt_text=None):
    area = width * height if width > 0 and height > 0 else 0
    score = area if area > 0 else 640 * 480
    if alt_text and len(alt_text) > 10:
        score *= 1.2
    return score

# Custom site handlers from custom_site_handlers.py
def extract_underlying_url(url, selector_func):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        underlying_url = selector_func(soup)
        if underlying_url:
            g_logger.info(f"Found underlying URL: {underlying_url}")
            return underlying_url

        g_logger.info("No underlying URL found, falling back to original")
        return None
    except requests.exceptions.RequestException as e:
        g_logger.warning(f"Error extracting underlying URL: {e}")
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
    underlying_url = extract_underlying_url(url, selector_func)
    return fetch_largest_image_requests(underlying_url if underlying_url else url)

def custom_hack_miragenews(url):
    return fetch_largest_image_requests(url)

def custom_hack_justthenews(url):
    return fetch_largest_image_requests(url)

def citizenfreepress_custom_fetch(url):
    return generic_custom_fetch(url, citizenfreepress_selector)

def linuxtoday_custom_fetch(url):
    return generic_custom_fetch(url, linuxtoday_selector)

def reddit_custom_fetch(url, underlying_link=None, html_content=None):
    if underlying_link and 'reddit' not in underlying_link:
        g_logger.info(f"Reddit hack: using provided underlying link {underlying_link}")
        return fetch_largest_image_requests(underlying_link)
    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'reddit' not in href:
                g_logger.info(f"Reddit hack: using link from html_content {href}")
                return fetch_largest_image_requests(href)
    g_logger.info(f"No images found in Reddit content, not bothering to try reddit.com: {url}")
    return None

custom_hacks = {
    'miragenews.com': custom_hack_miragenews,
    'justthenews.com': custom_hack_justthenews,
    'linuxtoday.com': linuxtoday_custom_fetch,
    'citizenfreepress.com': citizenfreepress_custom_fetch,
    'reddit.com': reddit_custom_fetch
}

# Core image parsing from image_parser.py
def extract_img_url_from_tag(img_tag, base_url):
    srcset = img_tag.get('srcset')
    if srcset:
        best, _ = parse_best_srcset(srcset)
        if best:
            return urljoin(base_url, best)
    src = img_tag.get('src', '')
    if src and not src.startswith('data:'):
        return urljoin(base_url, src)
    ext = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg')
    for value in img_tag.attrs.values():
        if isinstance(value, str) and (value.startswith('http') or value.lower().endswith(ext)):
            return urljoin(base_url, value)
    return None

def add_candidate(candidate_images, processed_urls, url, metadata):
    if url and url not in processed_urls and not is_excluded(url):
        processed_urls.add(url)
        candidate_images.append((url, metadata))

def parse_images_requests(soup, base_url):
    candidate_images = []
    processed_urls = set()

    # Meta tags
    meta_tags = [
        ('meta[property="og:image"]', 'content', 10000000),
        ('meta[name="twitter:image"]', 'content', 9000000),
        ('meta[name="twitter:image:src"]', 'content', 9000000),
        ('meta[property="og:image:secure_url"]', 'content', 10000000),
        ('meta[itemprop="image"]', 'content', 8000000),
    ]
    for selector, attr, score in meta_tags:
        for tag in soup.select(selector):
            if tag.get(attr):
                url = urljoin(base_url, tag[attr])
                add_candidate(candidate_images, processed_urls, url, {'score': score, 'meta': True})

    # JSON-LD
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                image_candidates = []
                if 'image' in data:
                    if isinstance(data['image'], str):
                        image_candidates.append(data['image'])
                    elif isinstance(data['image'], list):
                        image_candidates.extend(data['image'])
                    elif isinstance(data['image'], dict) and 'url' in data['image']:
                        image_candidates.append(data['image']['url'])
                if '@graph' in data and isinstance(data['@graph'], list):
                    for item in data['@graph']:
                        if isinstance(item, dict) and 'image' in item:
                            if isinstance(item['image'], str):
                                image_candidates.append(item['image'])
                            elif isinstance(item['image'], list):
                                image_candidates.extend(x for x in item['image'] if isinstance(x, str))
                for img_url in image_candidates:
                    if isinstance(img_url, str):
                        url = urljoin(base_url, img_url)
                        add_candidate(candidate_images, processed_urls, url, {'score': 8000000, 'meta': True})
        except json.JSONDecodeError as e:
            g_logger.debug(f"Error parsing JSON-LD: {e}")

    # Img tags
    for img in soup.find_all('img'):
        url = extract_img_url_from_tag(img, base_url)
        if not url or is_excluded(url):
            continue
        width, height = extract_dimensions_from_tag_or_style(img)
        metadata = {}
        if width > 0:
            metadata['width'] = width
        if height > 0:
            metadata['height'] = height
        alt_text = img.get('alt', '')
        metadata['score'] = score_image_candidate(width, height, alt_text)
        add_candidate(candidate_images, processed_urls, url, metadata)

    return candidate_images

def process_candidate_images(candidate_images):
    if not candidate_images:
        g_logger.warning("No candidate images available for processing.")
        return None

    meta_images = [(url, meta) for url, meta in candidate_images if meta.get('meta')]
    if meta_images:
        candidate_images = meta_images

    top_candidates = sorted(candidate_images, key=lambda item: item[1].get('score', 0), reverse=True)[:5]
    for i, (url, meta) in enumerate(top_candidates):
        width = meta.get('width', 0)
        height = meta.get('height', 0)
        if width == 0 or height == 0:
            actual_width, actual_height = get_actual_image_dimensions(url)
            if actual_width > 0 and actual_height > 0:
                meta['width'] = actual_width
                meta['height'] = actual_height
                meta['score'] = actual_width * actual_height
                top_candidates[i] = (url, meta)

    top_candidates.sort(key=lambda item: item[1].get('width', 0) * item[1].get('height', 0), reverse=True)

    if not top_candidates:
        g_logger.warning("No suitable candidates remain after processing.")
        return None

    best = top_candidates[0]
    best_url = best[0]
    best_width = best[1].get('width', 0)
    best_height = best[1].get('height', 0)
    min_size = 100
    if best_width < min_size or best_height < min_size:
        g_logger.warning("No suitable images found (all images too small).")
        return None
    g_logger.info(f"Best image found: {best_url} (score: {best[1].get('score')}, size: {best_width}x{best_height})")
    return best_url

def get_final_response(url, headers, max_redirects=2):
    for _ in range(max_redirects):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            g_logger.error(f"Error fetching {url}: {e}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        meta_refresh = soup.find('meta', attrs={'http-equiv': lambda x: x and x.lower() == 'refresh'})

        if not meta_refresh:
            return response

        content = meta_refresh.get('content', '')
        parts = content.split(';')
        target_url = None
        for part in parts:
            if part.strip().lower().startswith('url='):
                target_url = part.strip()[4:].strip()
                break

        if target_url:
            url = urljoin(url, target_url)
            continue
        else:
            return response

    g_logger.error("Error: Too many meta refresh redirects")
    return None

def fetch_largest_image_requests(url):
    if os.path.exists(url):
        with open(url, 'r', encoding='utf-8') as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        base_url = "file://" + os.path.abspath(url)
        candidate_images = parse_images_requests(soup, base_url)
        if not candidate_images:
            g_logger.warning("No suitable images found in local file.")
            return None
        return process_candidate_images(candidate_images)

    try:
        is_direct_image = False
        if IMAGE_EXT_RE.search(url):
            g_logger.debug(f"URL appears to be an image by extension: {url}")
            try:
                response = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
                response.raise_for_status()
                content_type = response.headers.get('Content-Type', '').lower()
                g_logger.debug(f"HEAD Content-Type for {url}: {content_type}")
                if 'image/' in content_type:
                    is_direct_image = True
                else:
                    g_logger.debug(f"Rejected image URL {url} based on HEAD Content-Type: {content_type}")
            except requests.exceptions.RequestException as e:
                g_logger.debug(f"HEAD request failed for {url}: {e}, will proceed with GET")

        if is_direct_image:
            width, height = get_actual_image_dimensions(url)
            g_logger.debug(f"Fetched dimensions for direct image {url}: {width}x{height}")
            if width > 100 and height > 100:
                g_logger.debug(f"Accepting direct image URL {url} with size {width}x{height}")
                return url
            else:
                g_logger.debug(f"Rejected direct image URL {url} due to insufficient size {width}x{height}")

        response = get_final_response(url, HEADERS)
        if response is None:
            g_logger.error(f"No valid response received for {url}.")
            return None

        content_type = response.headers.get('Content-Type', '').lower()
        g_logger.debug(f"GET Content-Type for {url}: {content_type}")
        if content_type.startswith('image/') and not is_direct_image:
            g_logger.debug(f"URL is an image by GET Content-Type: {url}")
            width, height = get_actual_image_dimensions(url)
            g_logger.debug(f"Fetched dimensions for {url}: {width}x{height}")
            if width > 100 and height > 100:
                g_logger.debug(f"Accepting image URL {url} with size {width}x{height}")
                return url
            else:
                g_logger.debug(f"Rejected image URL {url} due to invalid size {width}x{height}")
                return None

        if 'html' not in content_type:
            g_logger.debug(f"Content-Type ({content_type}) is not HTML or image, skipping image parsing for {url}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        base_url = response.url
        candidate_images = parse_images_requests(soup, base_url)

        if not candidate_images:
            g_logger.warning("No suitable images found.")
            return None

        return process_candidate_images(candidate_images)

    except requests.exceptions.RequestException as e:
        g_logger.error(f"Request Error fetching image: {e}")
        return None
    except (AttributeError, TypeError, ValueError) as e:
        g_logger.error(f"Error processing image data: {e}")
        return None

# Selenium functions from image_processing.py
def evaluate_image_url(img_url):
    try:
        req_headers = {
            "User-Agent": HEADERS.get("User-Agent"),
            "Referer": img_url
        }
        req = urllib.request.Request(img_url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            image_data = response.read()
        image_size = len(image_data)
        g_logger.debug(f"Image size for {img_url}: {image_size} bytes")
        return image_size
    except (urllib.error.URLError, socket.timeout, ConnectionResetError) as e:
        g_logger.debug(f"Error downloading or measuring {img_url}: {e}")
        return 0

def parse_images_selenium(driver):
    candidate_images = []
    images = driver.find_elements(By.TAG_NAME, 'img')

    if not images:
        g_logger.warning("No images found on the page.")
        return candidate_images

    for img in images:
        try:
            img_url_attr = img.get_attribute('src')
            if not img_url_attr or img_url_attr.startswith('data:'):
                continue
            img_url = urllib.parse.urljoin(driver.current_url, img_url_attr)
            if is_excluded(img_url):
                continue

            try:
                natural_width = driver.execute_script("return arguments[0].naturalWidth;", img)
                natural_height = driver.execute_script("return arguments[0].naturalHeight;", img)
            except WebDriverException as e:
                g_logger.debug(f"Could not get natural dimensions: {e}")
                natural_width = natural_height = 0

            try:
                display_width = driver.execute_script("return arguments[0].clientWidth;", img)
                display_height = driver.execute_script("return arguments[0].clientHeight;", img)
            except WebDriverException as e:
                g_logger.debug(f"Could not get client dimensions: {e}")
                display_width = display_height = 0

            width = height = 0
            try:
                width_attr = img.get_attribute('width')
                height_attr = img.get_attribute('height')
                if width_attr and width_attr.isdigit():
                    width = int(width_attr)
                if height_attr and height_attr.isdigit():
                    height = int(height_attr)
            except (ValueError, WebDriverException):
                pass

            if natural_width > 0 and natural_height > 0:
                width, height = natural_width, natural_height
            elif display_width > 0 and display_height > 0:
                width, height = display_width, display_height

            try:
                is_visible = driver.execute_script(
                    "var elem = arguments[0], box = elem.getBoundingClientRect(); " +
                    "return box.top < window.innerHeight && box.bottom > 0 && " +
                    "box.left < window.innerWidth && box.right > 0 && " +
                    "getComputedStyle(elem).visibility !== 'hidden' && " +
                    "getComputedStyle(elem).display !== 'none';", img)
                if not is_visible:
                    continue
            except WebDriverException:
                pass

            metadata = {
                'width': width,
                'height': height,
                'score': score_image_candidate(width, height, img.get_attribute('alt'))
            }

            if metadata['score'] > 10000 or (natural_width > 200 and natural_height > 200):
                file_size = evaluate_image_url(img_url)
                if file_size > 0:
                    metadata['filesize'] = file_size
                elif file_size == 0:
                    continue

            candidate_images.append((img_url, metadata))

        except WebDriverException as e:
            g_logger.debug(f"Error processing image element with Selenium: {e}")
            continue
        except AttributeError as e:
            g_logger.debug(f"Unexpected attribute error processing image element: {e}")
            continue

    return process_candidate_images(candidate_images)

def fetch_largest_image_selenium(url):
    driver = None
    try:
        driver = get_shared_driver(use_tor=False, user_agent=HEADERS['User-Agent'])
        driver.get(url)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )
            g_logger.info(f"Page loaded successfully for Selenium processing: {url}")
        except TimeoutException as e:
            g_logger.warning(f"Timeout waiting for page to load via Selenium: {e}")
        except WebDriverException as e:
            g_logger.error(f"WebDriver error waiting for page load: {e}")

        candidate_images = parse_images_selenium(driver)
        return process_candidate_images(candidate_images)

    except WebDriverException as e:
        g_logger.error(f"WebDriver error accessing the webpage or processing images: {e}")
        return None
    except (ConnectionError, IOError) as e:
        g_logger.error(f"Network error accessing the webpage or processing images: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# Main public API from image_parser.py
def custom_fetch_largest_image(url, underlying_link=None, html_content=None):
    if underlying_link:
        g_logger.info("Using underlying link provided")
        url_to_process = underlying_link
    elif html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        first_link = soup.find("a")
        if first_link and first_link.get("href"):
            g_logger.info("Using first link from HTML content")
            url_to_process = first_link["href"]
        else:
            g_logger.info("HTML content provided but no link found, using original URL")
            url_to_process = url
    else:
        url_to_process = url

    domain = extract_domain(url_to_process)
    if domain in custom_hacks:
        g_logger.info(f"Using custom hack for {domain}")
        return custom_hacks[domain](url_to_process)
    else:
        return fetch_largest_image_requests(url_to_process)

# Test block from image_processing.py
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test-urls':
        test_urls = [
            'https://www.sfchronicle.com/tech/article/waymo-private-sales-20294443.php',
            'https://www.reddit.com/r/LocalLLaMA/comments/1k8ncco/introducing_kimi_audio_7b_a_sota_audio_foundation/',
        ]
        g_logger.info("Running test mode on sample URLs:\n")
        for url_test in test_urls:
            g_logger.info(f"Testing: {url_test}")
            result = custom_fetch_largest_image(url_test)
            g_logger.info(f"  Result: {result}\n")
        g_logger.info("Test mode complete.")
    elif len(sys.argv) > 1:
        test_url = sys.argv[1]
        g_logger.info(f"Testing custom_fetch_largest_image with URL: {test_url}")
        result = custom_fetch_largest_image(test_url)
        if result:
            g_logger.info(f"Result: {result}")
        else:
            g_logger.info("No image found or an error occurred.")
    else:
        g_logger.info("Usage: python image_fetch.py <URL> or python image_fetch.py --test-urls")
