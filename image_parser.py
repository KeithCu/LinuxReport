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
    IMAGE_EXT_RE,
    # parse_best_srcset # Unused import
)

# Import from the renamed file
from image_html_parser import parse_images_from_soup
# Import from the new candidate selector module
from image_candidate_selector import process_candidate_images
# Import from custom_site_handlers
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

# === Main Fetch Logic ===

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
        # Use imported process_candidate_images from image_candidate_selector
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

        # Use imported process_candidate_images from image_candidate_selector
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
        if (first_link and first_link.get("href")):
            print("Using first link from HTML content")
            url_to_process = first_link["href"] # Use a different variable name
        else:
            print("HTML content provided but no link found, using original URL")
            url_to_process = url # Use original url if no link found in html
    else:
        url_to_process = url # Use original url if no underlying link or html content

    # Use imported extract_domain and custom_hacks from custom_site_handlers
    domain = extract_domain(url_to_process)
    if domain in custom_hacks:
        print(f"Using custom hack for {domain}")
        # The custom_hacks dictionary (imported from custom_site_handlers) should contain
        # references to the actual custom fetch functions.
        return custom_hacks[domain](url_to_process)
    else:
        # Call the local fetch_largest_image
        return fetch_largest_image(url_to_process)

