#!/usr/bin
from urllib.parse import urlparse, urljoin
import re
import json
import urllib.request
import requests

from bs4 import BeautifulSoup

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

#from shared import FeedHistory, RssFeed, TZ, Mode, MODE, g_c
from seleniumfetch import create_driver

custom_hacks = {}

DEBUG_LOGGING = True

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0'}

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

def get_meta_image(soup):
    """Extract image URL from various meta tags"""
    # Check OpenGraph image (highest priority)
    og_image = soup.find('meta', property='og:image')
    if (og_image and og_image.get('content')):
        return og_image['content']

    # Check Twitter card
    twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
    if (twitter_image and twitter_image.get('content')):
        return twitter_image['content']

    # Check Schema.org image in JSON-LD
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                if 'image' in data:
                    return data['image'] if isinstance(data['image'], str) else data['image'][0]
        except:
            pass

    return None

def evaluate_image_url(img_url):
    """Evaluate an image by downloading it and checking its size."""
    try:
        with urllib.request.urlopen(img_url) as response:
            image_data = response.read()
        image_size = len(image_data)
        print(f"Image size for {img_url}: {image_size} bytes")
        return image_size
    except Exception as e:
        print(f"Error downloading or measuring {img_url}: {e}")
        return 0

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

def get_image_dimensions_from_attributes(img_tag):
    """Extract width and height from an <img> tag's attributes."""
    width = 0
    height = 0
    try:
        if img_tag.get('width') and img_tag['width'].isdigit():
            width = int(img_tag['width'])
        if img_tag.get('height') and img_tag['height'].isdigit():
            height = int(img_tag['height'])
    except (ValueError, KeyError):
        pass
    return width, height

def process_candidate_images(candidate_images):
    """Process a list of candidate images and return the best one based on a refined scoring logic."""
    if not candidate_images:
        print("No candidate images available for processing.")
        return None

    # Sort candidate images based on a score that prioritizes explicit dimensions and srcset widths
    def calculate_score(item):
        url, metadata = item
        score = metadata.get('score', 0)
        width = metadata.get('width', 0)
        height = metadata.get('height', 0)
        srcset_width = metadata.get('srcset_width', 0)

        # Prioritize images with larger explicit dimensions or srcset widths
        if width > 0 and height > 0:
            score += width * height * 1.5  # Give more weight to explicit dimensions
        elif srcset_width > 0:
            score += srcset_width * srcset_width # Use squared width as a proxy for area

        return score

    candidate_images.sort(key=calculate_score, reverse=True)

    if candidate_images:
        best_image_url = candidate_images[0][0]
        print(f"Best image found: {best_image_url}")
        return best_image_url
    else:
        print("No suitable images found.")
        return None

def parse_images_from_soup(soup, base_url):
    candidate_images = []

    # 1. Check meta tags (score remains high but we'll rely more on actual dimensions later)
    meta_image_url = soup.find('meta', property='og:image')
    if meta_image_url and meta_image_url.get('content'):
        absolute_meta_url = urljoin(base_url, meta_image_url['content'])
        candidate_images.append((absolute_meta_url, {'score': 2000000}))
        print(f"Found meta image: {absolute_meta_url}")

    twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
    if twitter_image and twitter_image.get('content'):
        absolute_twitter_url = urljoin(base_url, twitter_image['content'])
        candidate_images.append((absolute_twitter_url, {'score': 1500000})) # Slightly lower score
        print(f"Found Twitter image: {absolute_twitter_url}")

    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and 'image' in data:
                image_url = data['image'] if isinstance(data['image'], str) else data['image'][0]
                absolute_schema_url = urljoin(base_url, image_url)
                candidate_images.append((absolute_schema_url, {'score': 1000000})) # Even lower score
                print(f"Found Schema.org image: {absolute_schema_url}")
        except:
            pass

    # 2. Check for picture elements with srcset
    for picture in soup.find_all('picture'):
        max_width = 0
        best_source = None

        for source in picture.find_all('source'):
            if source.get('srcset'):
                best_src, width = parse_best_srcset(source['srcset'])
                if width > max_width:
                    max_width = width
                    best_source = best_src

        img = picture.find('img')
        if img:
            img_best_src, img_width = (None, 0)
            if img.get('srcset'):
                img_best_src, img_width = parse_best_srcset(img['srcset'])
                if img_width > max_width:
                    max_width = img_width
                    best_source = img_best_src
            elif img.get('src'):
                if max_width == 0: # Use img src if no better source in <picture>
                    best_source = img['src']
                    width_attr, height_attr = get_image_dimensions_from_attributes(img)
                    max_width = width_attr # Use width as a proxy if available

        if best_source:
            absolute_url = urljoin(base_url, best_source)
            candidate_images.append((absolute_url, {'srcset_width': max_width}))

    # 3. Process all img tags
    for img in soup.find_all('img'):
        src = None
        srcset_url = None
        srcset_width = 0

        for attr in ['src', 'data-src', 'data-lazy-src', 'data-original']:
            if img.get(attr):
                src = img[attr]
                break

        if 'srcset' in img.attrs or 'data-srcset' in img.attrs:
            srcset = img.get('srcset', img.get('data-srcset', ''))
            srcset_url, srcset_width = parse_best_srcset(srcset)
            if srcset_url:
                src = srcset_url

        if not src:
            continue

        width, height = get_image_dimensions_from_attributes(img)

        style = img.get('style', '')
        if 'display:none' in style or 'visibility:hidden' in style:
            continue

        if (width < 50 or height < 50) and srcset_width < 50:
            continue

        absolute_url = urljoin(base_url, src)
        metadata = {}
        if width > 0:
            metadata['width'] = width
        if height > 0:
            metadata['height'] = height
        if srcset_width > 0:
            metadata['srcset_width'] = srcset_width
        metadata['score'] = width * height # Fallback score

        exclude_patterns = ['logo', 'icon', 'avatar', 'banner', 'emoji', 'Linux_opengraph']
        if not any(pattern in absolute_url.lower() for pattern in exclude_patterns):
            candidate_images.append((absolute_url, metadata))

    return candidate_images

def fetch_largest_image(url):
    try:
        response = get_final_response(url, HEADERS)
        if response is None:
            print("No response received.")
            return None
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '').lower()
        if content_type.startswith('image/'):
            print(f"URL is an image: {url}")
            return url

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

def custom_fetch_largest_image(url):
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

    for img in images:
        try:
            img_url = img.get_attribute('src')
            if not img_url or 'data:' in img_url:  # Skip data URLs or invalid URLs
                continue

            # Extract width and height attributes for scoring
            width = height = 100  # Default estimates
            try:
                width_attr = img.get_attribute('width')
                height_attr = img.get_attribute('height')
                if width_attr and width_attr.isdigit():
                    width = int(width_attr)
                if height_attr and height_attr.isdigit():
                    height = int(height_attr)
            except Exception:
                pass

            # Check if image is too small
            if width < 50 and height < 50:
                continue

            # Calculate initial score based on displayed dimensions
            initial_score = width * height

            # For high-scoring candidates, check actual download size
            if initial_score > 10000:  # Only evaluate promising images
                image_size = evaluate_image_url(img_url)
                if image_size > 0:
                    candidate_images.append((img_url, image_size))

        except Exception as e:
            print(f"Error processing image element: {e}")
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
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        print(f"Testing custom_fetch_largest_image with URL: {test_url}")
        result = custom_fetch_largest_image(test_url)
        if result:
            print(f"Result: {result}")
        else:
            print("No image found or an error occurred.")
    else:
        print("Usage: python auto_update_utils.py <URL>")
