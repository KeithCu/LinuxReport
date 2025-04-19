"""
Module: image_parser.py

Handles HTML parsing, image candidate extraction and selection,
and custom site-specific logic.
"""
import os
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

# Import from image_utils
from image_utils import (
    debug_print,
    get_actual_image_dimensions,
    HEADERS,
    extract_domain,
    IMAGE_EXT_RE
)

from html_image_extraction import parse_images_from_soup
from custom_site_handlers import custom_hacks

# === HTML/Parsing Logic ===

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


def parse_best_srcset(srcset):
    """Parse srcset attribute and return the best (largest) image URL and its estimated width."""
    if not srcset:
        return None, 0

    # Parse each srcset entry to collect (width, url) pairs
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
    # Choose the entry with the maximum width
    best_width, best_url = max(entries, key=lambda x: x[0])
    return best_url, best_width

# === Candidate Selection ===

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


def fetch_largest_image(url): # Renamed request_url to url
    """Fetch the largest image from a webpage using requests and BeautifulSoup."""
    # Debug feature: if the provided URL is a local file, load its content
    if os.path.exists(url): # Use url
        with open(url, 'r', encoding='utf-8') as f: # Use url
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        # Assuming file URLs don't need complex base URL logic here
        base_url = "file://" + os.path.abspath(url) # Use url
        # Use imported parse_images_from_soup
        candidate_images = parse_images_from_soup(soup, base_url)
        if not candidate_images:
            print("No suitable images found in local file.")
            return None
        # Use imported process_candidate_images
        return process_candidate_images(candidate_images)

    try:
        is_direct_image = False
        # Handle URLs that might be direct images (check extension first)
        # Use imported IMAGE_EXT_RE and debug_print
        if IMAGE_EXT_RE.search(url): # Use url
            debug_print(f"URL appears to be an image by extension: {url}") # Use url
            try:
                # Use imported HEADERS
                response = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True) # Use url
                response.raise_for_status()
                content_type = response.headers.get('Content-Type', '').lower()
                debug_print(f"HEAD Content-Type for {url}: {content_type}") # Use url
                if 'image/' in content_type:
                    is_direct_image = True
                else:
                    debug_print(f"Rejected image URL {url} based on HEAD Content-Type: {content_type}") # Use url
            except requests.exceptions.RequestException as e:
                debug_print(f"HEAD request failed for {url}: {e}, will proceed with GET") # Use url

        # If it looks like a direct image, get dimensions and return if valid
        if is_direct_image:
            # Use imported get_actual_image_dimensions and debug_print
            width, height = get_actual_image_dimensions(url) # Use url
            debug_print(f"Fetched dimensions for direct image {url}: {width}x{height}") # Use url
            if width > 100 and height > 100: # Use a threshold like in process_candidate_images
                debug_print(f"Accepting direct image URL {url} with size {width}x{height}") # Use url
                return url # Use url
            else:
                debug_print(f"Rejected direct image URL {url} due to insufficient size {width}x{height}") # Use url
                # Don't return None yet, maybe the page it links *from* has a better image via meta tags

        # Standard HTML page fetch (or if direct image check failed/was rejected)
        # Use imported get_final_response and HEADERS
        response = get_final_response(url, HEADERS) # Use url
        if response is None:
            print(f"No valid response received for {url}.") # Use url
            return None

        # Check Content-Type again after GET, in case HEAD failed or it wasn't checked by extension
        content_type = response.headers.get('Content-Type', '').lower()
        debug_print(f"GET Content-Type for {url}: {content_type}") # Use url
        if content_type.startswith('image/') and not is_direct_image: # Check only if not already identified as image
            debug_print(f"URL is an image by GET Content-Type: {url}") # Use url
            # Use imported get_actual_image_dimensions and debug_print
            width, height = get_actual_image_dimensions(url) # Use url # Re-fetch might be redundant but ensures consistency
            debug_print(f"Fetched dimensions for {url}: {width}x{height}") # Use url
            if width > 100 and height > 100:
                debug_print(f"Accepting image URL {url} with size {width}x{height}") # Use url
                return url # Use url
            else:
                debug_print(f"Rejected image URL {url} due to invalid size {width}x{height}") # Use url
                return None # If it IS an image but too small, stop here.

        # If not an image content type, parse HTML
        if 'html' not in content_type:
            debug_print(f"Content-Type ({content_type}) is not HTML or image, skipping image parsing for {url}") # Use url
            return None

        # Parse HTML and look for images
        soup = BeautifulSoup(response.text, 'html.parser')
        base_url = response.url
        # Use imported parse_images_from_soup
        candidate_images = parse_images_from_soup(soup, base_url)

        if not candidate_images:
            print("No suitable images found.")
            return None

        # Use imported process_candidate_images
        return process_candidate_images(candidate_images)

    except requests.exceptions.RequestException as e:
        print(f"Request Error fetching image: {e}")
        return None
    except Exception as e:
        print(f"Error fetching image: {e}")
        return None

def custom_fetch_largest_image(url, underlying_link=None, html_content=None): # Renamed request_url to url
    """Main function to fetch the largest image from a URL, with special handling for certain sites."""
    # Use underlying_link if provided
    if underlying_link:
        print("Using underlying link provided")
        url_to_process = underlying_link # Use a different variable name
    # Otherwise, if html_content is provided, parse it to find the first link
    elif html_content:
        # Need BeautifulSoup here if it wasn't already imported globally
        # from bs4 import BeautifulSoup # Ensure imported at top
        soup = BeautifulSoup(html_content, "html.parser")
        first_link = soup.find("a")
        if first_link and first_link.get("href"):
            print("Using first link from HTML content")
            url_to_process = first_link["href"] # Use a different variable name
        else:
            print("HTML content provided but no link found, using original URL")
            url_to_process = url # Use original url if no link found in html
    else:
        url_to_process = url # Use original url if no underlying link or html content

    # Use imported extract_domain and custom_hacks
    domain = extract_domain(url_to_process)
    if domain in custom_hacks:
        print(f"Using custom hack for {domain}")
        # The custom_hacks dictionary (imported from image_parser) should contain
        # references to the actual custom fetch functions defined in image_parser.py
        # Make sure those functions in image_parser.py call fetch_largest_image (defined here)
        # appropriately, potentially by passing it as an argument.
        return custom_hacks[domain](url_to_process)
    else:
        # Call the local fetch_largest_image
        return fetch_largest_image(url_to_process)

