#!/usr/bin/python3
from urllib.parse import urlparse, urljoin
import re
import json
import urllib.request
import requests
from io import BytesIO
from PIL import Image

from bs4 import BeautifulSoup

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from seleniumfetch import create_driver

custom_hacks = {}

DEBUG_LOGGING = True

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0'}

EXCLUDED_PATTERNS = ['logo', 'icon', 'avatar', 'banner', 'emoji', 'css', 'advertisement', 'michaellarabel']

def debug_print(message):
    if DEBUG_LOGGING:
        print(f"[DEBUG] {message}")

def get_final_response(url, headers, max_redirects=2):
    for _ in range(max_redirects):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
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

    print("Error: Too many meta refresh redirects")
    return None

# --- Centralized image dimension extraction ---
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
    # Check for dimensions in style attribute
    if (width == 0 or height == 0) and tag.get('style'):
        style = tag['style']
        width_match = re.search(r'width:\s*(\d+)px', style)
        if width_match:
            width = int(width_match.group(1))
        height_match = re.search(r'height:\s*(\d+)px', style)
        if height_match:
            height = int(height_match.group(1))
    return width, height

def get_actual_image_dimensions(img_url):
    """Fetch an image and get its actual dimensions. Special handling for SVG images with approximate dimensions."""
    try:
        headers_with_referer = HEADERS.copy()
        headers_with_referer["Referer"] = img_url  # Added Referer header
        response = requests.get(img_url, headers=headers_with_referer, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '').lower()
        
        # Use content-length as a quick check for valid images, but only skip if present and small
        content_length_header = response.headers.get('Content-Length')
        if content_length_header is not None:
            try:
                content_length = int(content_length_header)
                if content_length < 100:  # Skip very small images that are likely icons
                    debug_print(f"Skipping small image ({content_length} bytes): {img_url}")
                    return 0, 0
            except Exception:
                pass
        
        if 'svg' in content_type:
            debug_print(f"SVG image detected for {img_url}, attempting to parse dimensions")
            try:
                import xml.etree.ElementTree as ET
                svg = ET.fromstring(response.content)
                width = svg.attrib.get('width')
                height = svg.attrib.get('height')
                
                # Improved SVG dimension parsing with unit handling
                def parse_dimension(value):
                    if not value:
                        return 0
                    if value.isdigit():
                        return int(value)
                    # Handle px, em, pt, etc.
                    numeric_part = re.match(r'^(\d+(\.\d+)?)', value)
                    if numeric_part:
                        return float(numeric_part.group(1))
                    return 0
                    
                if width and height:
                    width_val = parse_dimension(width)
                    height_val = parse_dimension(height)
                    if width_val > 0 and height_val > 0:
                        debug_print(f"Parsed SVG dimensions from attributes for {img_url}: {int(width_val)}x{int(height_val)}")
                        return int(width_val), int(height_val)
                        
                viewBox = svg.attrib.get('viewBox')
                if viewBox:
                    parts = viewBox.split()
                    if len(parts) == 4:
                        try:
                            width = float(parts[2])
                            height = float(parts[3])
                            debug_print(f"Parsed SVG dimensions from viewBox for {img_url}: {int(width)}x{int(height)}")
                            return int(width), int(height)
                        except Exception:
                            pass
                            
                # More realistic fallback based on SVG content complexity
                fallback_dim = min(max(int(len(response.content) ** 0.4), 200), 800)
                debug_print(f"Fallback SVG dimensions based on file size for {img_url}: {fallback_dim}x{fallback_dim}")
                return fallback_dim, fallback_dim
            except Exception as e:
                debug_print(f"Error parsing SVG for {img_url}: {e}")
                return 640, 480  # Default fallback dimensions
        
        # More efficient image dimension detection using image header only
        try:
            with Image.open(BytesIO(response.content)) as img:
                width, height = img.size
                debug_print(f"Got actual dimensions for {img_url}: {width}x{height}")
                return width, height
        except Image.UnidentifiedImageError:
            debug_print(f"Could not identify image file: {img_url}")
            return 0, 0
        except Exception as e:
            debug_print(f"Error reading image dimensions with PIL for {img_url}: {e}")
            return 0, 0
    except requests.exceptions.RequestException as e:
        debug_print(f"Request error getting dimensions for {img_url}: {e}")
        return 0, 0
    except Exception as e:
        debug_print(f"Generic error getting dimensions for {img_url}: {e}")
        return 0, 0

def parse_best_srcset(srcset):
    """Parse srcset attribute and return the best (largest) image URL and its estimated width."""
    if not srcset:
        return None, 0

    best_width = 0
    best_url = None

    parts = srcset.strip().split(',')

    for part in parts:
        part = part.strip()
        if not part:
            continue

        subparts = part.split()
        url = subparts[0].strip()
        width = 0

        for subpart in subparts[1:]:
            width_match = re.search(r'(\d+)w', subpart)
            if width_match:
                width = int(width_match.group(1))
                break
            density_match = re.search(r'(\d+(\.\d+)?)x', subpart)
            if density_match:
                # Estimate width based on pixel density (assuming a base width of 1000 for 1x)
                width = int(1000 * float(density_match.group(1)))
                break

        if width > best_width:
            best_width = width
            best_url = url
        elif best_width == 0 and best_url is None:
            best_url = url
            best_width = 1 # Assign a default width if no descriptor is found

    return best_url, best_width

def extract_img_url_from_tag(img_tag, base_url):
    """Extract the best image URL from an <img> tag, considering src, srcset, and data-* attributes."""
    # Check srcset first
    if img_tag.get('srcset'):
        best_src, _ = parse_best_srcset(img_tag['srcset'])
        if best_src:
            return urljoin(base_url, best_src)
    # Check src
    if img_tag.get('src') and not img_tag['src'].startswith('data:'):
        return urljoin(base_url, img_tag['src'])
    # Check any data-* attribute that looks like an image URL
    for attr, value in img_tag.attrs.items():
        if attr.startswith('data-') and isinstance(value, str) and (value.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg')) or value.startswith('http')):
            return urljoin(base_url, value)
    return None


def parse_images_from_soup(soup, base_url):
    """Extract image candidates from HTML using BeautifulSoup with improved handling."""
    candidate_images = []
    processed_urls = set()

    # 1. Get meta tag images (high priority)
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
                if url not in processed_urls and not any(pattern in url.lower() for pattern in EXCLUDED_PATTERNS):
                    processed_urls.add(url)
                    candidate_images.append((url, {'score': score, 'meta': True}))

    # 2. Schema.org image in JSON-LD
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
                        if url not in processed_urls and not any(pattern in url.lower() for pattern in EXCLUDED_PATTERNS):
                            processed_urls.add(url)
                            candidate_images.append((url, {'score': 8000000, 'meta': True}))
        except Exception as e:
            debug_print(f"Error parsing JSON-LD: {e}")

    # 3. All <img> tags, robust lazy-load and data-* handling
    for img in soup.find_all('img'):
        url = extract_img_url_from_tag(img, base_url)
        if not url or url in processed_urls or any(pattern in url.lower() for pattern in EXCLUDED_PATTERNS):
            continue
        processed_urls.add(url)
        width, height = extract_dimensions_from_tag_or_style(img)
        metadata = {}
        if width > 0:
            metadata['width'] = width
        if height > 0:
            metadata['height'] = height
        alt_text = img.get('alt', '')
        # Score: prefer larger area, boost for alt text
        area = width * height if width > 0 and height > 0 else 0
        metadata['score'] = area if area > 0 else 307200  # 640x480 default
        if alt_text and len(alt_text) > 10:
            metadata['score'] *= 1.2
        candidate_images.append((url, metadata))

    return candidate_images


def process_candidate_images(candidate_images):
    """Process a list of candidate images and return the best one based on a simplified scoring logic."""
    if not candidate_images:
        print("No candidate images available for processing.")
        return None

    # 1. Prioritize meta images
    meta_images = [(url, meta) for url, meta in candidate_images if meta.get('meta')]
    if meta_images:
        candidate_images = meta_images

    # 2. For each candidate, fetch dimensions if missing (for top 5 only)
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

    # 3. Resort by area (width*height)
    top_candidates.sort(key=lambda item: item[1].get('width', 0) * item[1].get('height', 0), reverse=True)

    # Ensure we still have candidates after filtering/sorting
    if not top_candidates:
        print("No suitable candidates remain after processing.")
        return None

    # 4. Fallback: if no dimensions, use original score
    best = top_candidates[0]
    best_url = best[0]
    best_width = best[1].get('width', 0)
    best_height = best[1].get('height', 0)
    min_size = 100  # Minimum width and height for a valid image
    if best_width < min_size or best_height < min_size:
        print("No suitable images found (all images too small).")
        return None
    print(f"Best image found: {best_url} (score: {best[1].get('score')}, size: {best_width}x{best_height})")
    return best_url

def fetch_largest_image(url):
    import os
    # Debug feature: if the provided URL is a local file, load its content
    if os.path.exists(url):
        with open(url, 'r', encoding='utf-8') as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        base_url = "file://" + os.path.abspath(url)
        candidate_images = parse_images_from_soup(soup, base_url)
        if not candidate_images:
            print("No suitable images found in local file.")
            return None
        return process_candidate_images(candidate_images)

    try:
        is_direct_image = False
        # Handle URLs that might be direct images (check extension first)
        if re.search(r'\.(jpe?g|png|webp|gif|svg)([?#].*)?$', url.lower()):
            debug_print(f"URL appears to be an image by extension: {url}")
            try:
                response = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
                response.raise_for_status()
                content_type = response.headers.get('Content-Type', '').lower()
                debug_print(f"HEAD Content-Type for {url}: {content_type}")
                if 'image/' in content_type:
                    is_direct_image = True
                else:
                    debug_print(f"Rejected image URL {url} based on HEAD Content-Type: {content_type}")
            except requests.exceptions.RequestException as e:
                debug_print(f"HEAD request failed for {url}: {e}, will proceed with GET")

        # If it looks like a direct image, get dimensions and return if valid
        if is_direct_image:
            width, height = get_actual_image_dimensions(url)
            debug_print(f"Fetched dimensions for direct image {url}: {width}x{height}")
            if width > 100 and height > 100: # Use a threshold like in process_candidate_images
                debug_print(f"Accepting direct image URL {url} with size {width}x{height}")
                return url
            else:
                debug_print(f"Rejected direct image URL {url} due to insufficient size {width}x{height}")
                # Don't return None yet, maybe the page it links *from* has a better image via meta tags

        # Standard HTML page fetch (or if direct image check failed/was rejected)
        response = get_final_response(url, HEADERS)
        if response is None:
            print(f"No valid response received for {url}.")
            return None

        # Check Content-Type again after GET, in case HEAD failed or it wasn't checked by extension
        content_type = response.headers.get('Content-Type', '').lower()
        debug_print(f"GET Content-Type for {url}: {content_type}")
        if content_type.startswith('image/') and not is_direct_image: # Check only if not already identified as image
            debug_print(f"URL is an image by GET Content-Type: {url}")
            width, height = get_actual_image_dimensions(url) # Re-fetch might be redundant but ensures consistency
            debug_print(f"Fetched dimensions for {url}: {width}x{height}")
            if width > 100 and height > 100:
                debug_print(f"Accepting image URL {url} with size {width}x{height}")
                return url
            else:
                debug_print(f"Rejected image URL {url} due to invalid size {width}x{height}")
                return None # If it IS an image but too small, stop here.

        # If not an image content type, parse HTML
        if 'html' not in content_type:
            debug_print(f"Content-Type ({content_type}) is not HTML or image, skipping image parsing for {url}")
            return None

        # Parse HTML and look for images
        soup = BeautifulSoup(response.text, 'html.parser')
        base_url = response.url
        candidate_images = parse_images_from_soup(soup, base_url)

        if not candidate_images:
            print("No suitable images found.")
            return None

        return process_candidate_images(candidate_images)

    except Exception as e:
        print(f"Error fetching image: {e}")
        return None

def extract_domain(url):
    parsed = urlparse(url)
    netloc = parsed.netloc
    if netloc.startswith("www."):
        return netloc[4:]
    return netloc

def extract_underlying_url(url, selector_func):
    """Common function to extract an underlying URL from a webpage."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        underlying_url = selector_func(soup)
        if underlying_url:
            print(f"Found underlying URL: {underlying_url}")
            return underlying_url

        print("No underlying URL found, falling back to original")
        return None
    except Exception as e:
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
    underlying_url = extract_underlying_url(url, selector_func)
    return fetch_largest_image(underlying_url if underlying_url else url)

def citizenfreepress_custom_fetch(url):
    return generic_custom_fetch(url, citizenfreepress_selector)

def linuxtoday_custom_fetch(url):
    return generic_custom_fetch(url, linuxtoday_selector)

custom_hacks["linuxtoday.com"] =  linuxtoday_custom_fetch
custom_hacks["citizenfreepress.com"] = citizenfreepress_custom_fetch

def custom_fetch_largest_image(url, underlying_link=None, html_content=None):
    # Use underlying_link if provided
    if underlying_link:
        print("Using underlying link provided")
        url = underlying_link
    # Otherwise, if html_content is provided, parse it to find the first link
    elif html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        first_link = soup.find("a")
        if first_link and first_link.get("href"):
            print("Using first link from HTML content")
            url = first_link["href"]
    domain = extract_domain(url)
    if domain in custom_hacks:
        print(f"Using custom hack for {domain}")
        return custom_hacks[domain](url)
    else:
        return fetch_largest_image(url)

def parse_images_from_selenium(driver):
    candidate_images = []
    images = driver.find_elements(By.TAG_NAME, 'img')

    if not images:
        print("No images found on the page.")
        return candidate_images

    def evaluate_image_url(img_url):
        try:
            req_headers = {
                "User-Agent": HEADERS.get("User-Agent"),
                "Referer": img_url
            }
            req = urllib.request.Request(img_url, headers=req_headers)
            with urllib.request.urlopen(req) as response:
                image_data = response.read()
            image_size = len(image_data)
            debug_print(f"Image size for {img_url}: {image_size} bytes")
            return image_size
        except Exception as e:
            debug_print(f"Error downloading or measuring {img_url}: {e}")
            return 0

    for img in images:
        try:
            img_url = img.get_attribute('src')
            if not img_url or 'data:' in img_url or any(pattern in img_url.lower() for pattern in EXCLUDED_PATTERNS):
                continue

            # Get natural dimensions as reported by the browser
            try:
                natural_width = driver.execute_script("return arguments[0].naturalWidth;", img)
                natural_height = driver.execute_script("return arguments[0].naturalHeight;", img)
            except Exception as e:
                debug_print(f"Could not get natural dimensions: {e}")
                natural_width = natural_height = 0

            # Get display dimensions
            try:
                display_width = driver.execute_script("return arguments[0].clientWidth;", img)
                display_height = driver.execute_script("return arguments[0].clientHeight;", img)
            except Exception as e:
                debug_print(f"Could not get client dimensions: {e}")
                display_width = display_height = 0

            # Extract width and height attributes for scoring
            width = height = 0
            try:
                width_attr = img.get_attribute('width')
                height_attr = img.get_attribute('height')
                if width_attr and width_attr.isdigit():
                    width = int(width_attr)
                if height_attr and height_attr.isdigit():
                    height = int(height_attr)
            except Exception:
                pass

            # Use the best available dimensions
            if natural_width > 0 and natural_height > 0:
                width, height = natural_width, natural_height
            elif display_width > 0 and display_height > 0:
                width, height = display_width, display_height

            # Check if visible in viewport
            try:
                is_visible = driver.execute_script(
                    "var elem = arguments[0], box = elem.getBoundingClientRect(); " +
                    "return box.top < window.innerHeight && box.bottom > 0 && " +
                    "box.left < window.innerWidth && box.right > 0 && " +
                    "getComputedStyle(elem).visibility !== 'hidden' && " +
                    "getComputedStyle(elem).display !== 'none';", img)
                if not is_visible:
                    continue
            except:
                pass

            metadata = {
                'width': width,
                'height': height,
                'score': width * height if width > 0 and height > 0 else 640 * 480
            }

            if metadata['score'] > 10000 or (natural_width > 200 and natural_height > 200):
                file_size = evaluate_image_url(img_url)
                if file_size > 0:
                    metadata['filesize'] = file_size

            candidate_images.append((img_url, metadata))

        except Exception as e:
            debug_print(f"Error processing image element: {e}")
            continue

    return candidate_images

def fetch_largest_image_selenium(url):
    try:
        driver = create_driver()
        driver.get(url)

        try:
            # Example: Wait for the Twitter search bar (class or ID might change, so verify current Twitter HTML)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Search query"]'))
            )
            print("Twitter page loaded successfully.")
        except Exception as e:
            print(f"Timeout waiting for Twitter page to load: {e}")
            driver.quit()
            return None

        candidate_images = parse_images_from_selenium(driver)

        driver.quit()  # Close the browser

        # Use shared processing function
        return process_candidate_images(candidate_images)

    except Exception as e:
        print(f"Error accessing the webpage or processing images: {e}")
        if 'driver' in locals():
            driver.quit()
        return None

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test-urls':
        test_urls = [
            'https://justthenews.com/government/congress/watch-live-marjorie-taylor-greene-holds-town-hall-georgia',
            'https://www.miragenews.com/new-bat-cell-lines-advance-hantavirus-1445117/',
            'https://lwn.net/',
            'https://www.phoronix.com/news/GCC-15.1-Last-Minute-Znver5-Bit',
            'https://www.cnbc.com/2025/04/15/nvidia-says-it-will-record-5point5-billion-quarterly-charge-tied-to-h20-processors-exported-to-china.html'
        ]
        print("Running test mode on sample URLs:\n")
        for url in test_urls:
            print(f"Testing: {url}")
            result = custom_fetch_largest_image(url)
            print(f"  Result: {result}\n")
        print("Test mode complete.")
    elif len(sys.argv) > 1:
        test_url = sys.argv[1]
        print(f"Testing custom_fetch_largest_image with URL: {test_url}")
        result = custom_fetch_largest_image(test_url)
        if result:
            print(f"Result: {result}")
        else:
            print("No image found or an error occurred.")
    else:
        print("Usage: python auto_update_utils.py <URL> or --test-urls")
