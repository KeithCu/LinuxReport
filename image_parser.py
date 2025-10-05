"""
Module: image_parser.py

Handles HTML parsing, image candidate extraction and selection,
and custom site-specific logic.
"""
import os
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import json
from shared import g_logger

# Import from image_utils
from image_utils import (
    get_actual_image_dimensions,
    HEADERS,
    extract_domain,
    IMAGE_EXT_RE,
    is_excluded,
    extract_dimensions_from_tag_or_style,
    parse_best_srcset,
    score_image_candidate
)

# Import from custom_site_handlers
from custom_site_handlers import custom_hacks

# === HTML/Parsing Logic ===

def extract_img_url_from_tag(img_tag, base_url):
    """Extract the best image URL from an <img> tag, considering src, srcset, and data-* attributes."""
    srcset = img_tag.get('srcset')
    if srcset:
        best, _ = parse_best_srcset(srcset)
        if best:
            return urljoin(base_url, best)
    src = img_tag.get('src', '')
    if src and not src.startswith('data:'):
        return urljoin(base_url, src)
    # Fallback: any attribute value that looks like an image URL
    ext = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg')
    for value in img_tag.attrs.values():
        if isinstance(value, str) and (value.startswith('http') or value.lower().endswith(ext)):
            return urljoin(base_url, value)
    return None

def add_candidate(candidate_images, processed_urls, url, metadata):
    if url and url not in processed_urls and not is_excluded(url):
        processed_urls.add(url)
        candidate_images.append((url, metadata))

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
                add_candidate(candidate_images, processed_urls, url, {'score': score, 'meta': True})

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
                        add_candidate(candidate_images, processed_urls, url, {'score': 8000000, 'meta': True})
        except json.JSONDecodeError as e:
            g_logger.debug(f"Error parsing JSON-LD: {e}")

    # 3. All <img> tags, robust lazy-load and data-* handling
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
    """Process a list of candidate images and return the best one based on a simplified scoring logic."""
    if not candidate_images:
        g_logger.warning("No candidate images available for processing.")
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
        g_logger.warning("No suitable candidates remain after processing.")
        return None

    # 4. Fallback: if no dimensions, use original score
    best = top_candidates[0]
    best_url = best[0]
    best_width = best[1].get('width', 0)
    best_height = best[1].get('height', 0)
    min_size = 100  # Minimum width and height for a valid image
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

# === Main Fetch Logic ===

def fetch_largest_image(url):
    """Fetch the largest image from a webpage using requests and BeautifulSoup."""
    if os.path.exists(url):
        with open(url, 'r', encoding='utf-8') as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        base_url = "file://" + os.path.abspath(url)
        candidate_images = parse_images_from_soup(soup, base_url)
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
        candidate_images = parse_images_from_soup(soup, base_url)

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

def custom_fetch_largest_image(url, underlying_link=None, html_content=None):
    """Main function to fetch the largest image from a URL, with special handling for certain sites."""
    if underlying_link:
        g_logger.info("Using underlying link provided")
        url_to_process = underlying_link
    elif html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        first_link = soup.find("a")
        if (first_link and first_link.get("href")):
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
        return fetch_largest_image(url_to_process)