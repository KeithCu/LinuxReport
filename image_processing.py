"""
Module: image_processing.py

This module provides the main entry points for image extraction and processing,
including Selenium-based fetching. It orchestrates calls to utility and parsing
functions defined in other modules.
"""

import sys
import urllib.request
import urllib.error
import socket
from shared import g_logger

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException
from browser_fetch import get_shared_driver

# Import from new modules
from image_utils import (
    HEADERS,
    is_excluded,
    score_image_candidate
)
from shared import g_logger
# Import from the new candidate selector module
from image_parser import process_candidate_images



def parse_images_from_selenium(driver):
    """Extracts and evaluates images using Selenium WebDriver."""
    candidate_images = []
    images = driver.find_elements(By.TAG_NAME, 'img')
    # processed_urls = set() # Removed - not in original logic here

    if not images:
        g_logger.warning("No images found on the page.")
        return candidate_images

    # Reverted evaluate_image_url closer to original logic/error handling
    def evaluate_image_url(img_url):
        try:
            # Use imported HEADERS
            req_headers = {
                "User-Agent": HEADERS.get("User-Agent"),
                "Referer": driver.current_url # Use current driver URL as referer
            }
            req = urllib.request.Request(img_url, headers=req_headers)
            # Use timeout for urlopen
            with urllib.request.urlopen(req, timeout=10) as response:
                image_data = response.read()
            image_size = len(image_data)
            g_logger.debug(f"Image size for {img_url}: {image_size} bytes")
            return image_size
        # Match original's broader exception catch here
        except (urllib.error.URLError, socket.timeout, ConnectionResetError) as e:
            g_logger.debug(f"Error downloading or measuring {img_url}: {e}")
            return 0

    for img in images:
        try:
            img_url_attr = img.get_attribute('src') # Use a distinct name
            # Skip missing, data URIs, or excluded URLs
            if not img_url_attr or img_url_attr.startswith('data:'):
                continue
            # Resolve relative URLs based on the current page URL
            img_url = urllib.parse.urljoin(driver.current_url, img_url_attr)
            if is_excluded(img_url): # Use resolved img_url
                continue

            # Get natural dimensions as reported by the browser
            try:
                natural_width = driver.execute_script("return arguments[0].naturalWidth;", img)
                natural_height = driver.execute_script("return arguments[0].naturalHeight;", img)
            except WebDriverException as e:
                g_logger.debug(f"Could not get natural dimensions: {e}")
                natural_width = natural_height = 0

            # Get display dimensions
            try:
                display_width = driver.execute_script("return arguments[0].clientWidth;", img)
                display_height = driver.execute_script("return arguments[0].clientHeight;", img)
            except WebDriverException as e:
                g_logger.debug(f"Could not get client dimensions: {e}")
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
            except (ValueError, WebDriverException):
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
            except WebDriverException:
                pass # Assume visible if script fails

            metadata = {
                'width': width,
                'height': height,
                'score': score_image_candidate(width, height, img.get_attribute('alt'))
            }

            # Evaluate file size only for potentially good candidates
            if metadata['score'] > 10000 or (natural_width > 200 and natural_height > 200):
                file_size = evaluate_image_url(img_url) # Use resolved img_url
                if file_size > 0:
                    metadata['filesize'] = file_size
                elif file_size == 0: # Skip if download failed
                    continue

            # Directly append, don't use add_candidate or processed_urls here
            candidate_images.append((img_url, metadata)) # Use resolved img_url

        except WebDriverException as e:
            g_logger.debug(f"Error processing image element with Selenium: {e}")
            continue
        except AttributeError as e:
            g_logger.debug(f"Unexpected attribute error processing image element: {e}")
            continue

    # Use imported process_candidate_images from image_candidate_selector
    return process_candidate_images(candidate_images)

def fetch_largest_image_selenium(url): # Renamed request_url to url
    """Fetch largest image using Selenium for JavaScript-heavy sites."""
    driver = None
    try:
        # Update get_shared_driver call with required arguments
        # Assuming no Tor needed for this fallback and use standard agent
        driver = get_shared_driver(use_tor=False, user_agent=HEADERS['User-Agent'])
        driver.get(url) # Use url

        try:
            # Keep generalized wait for body tag
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )
            g_logger.info(f"Page loaded successfully for Selenium processing: {url}") # Use url
        except TimeoutException as e:
            g_logger.warning(f"Timeout waiting for page to load via Selenium: {e}")
            # Don't necessarily return None, maybe some images loaded
        except WebDriverException as e:
            g_logger.error(f"WebDriver error waiting for page load: {e}")
            # Don't necessarily return None

        # Call local parse_images_from_selenium
        candidate_images = parse_images_from_selenium(driver)

        # Use imported process_candidate_images
        return process_candidate_images(candidate_images)

    except WebDriverException as e:
        g_logger.error(f"WebDriver error accessing the webpage or processing images: {e}")
        return None
    except (ConnectionError, IOError) as e:
        g_logger.error(f"Network error accessing the webpage or processing images: {e}")
        return None
    finally:
        if driver:
            driver.quit() # Close the browser


# === Main Execution Block ===

if __name__ == '__main__':
    # Keep sys import at top
    # Import the function that is now the main entry point
    from image_parser import custom_fetch_largest_image
    if len(sys.argv) > 1 and sys.argv[1] == '--test-urls':
        test_urls = [
            'https://www.sfchronicle.com/tech/article/waymo-private-sales-20294443.php',
            'https://www.reddit.com/r/LocalLLaMA/comments/1k8ncco/introducing_kimi_audio_7b_a_sota_audio_foundation/',
 #           'https://lwn.net/',
 #           'https://www.phoronix.com/news/GCC-15.1-Last-Minute-Znver5-Bit',
 #           'https://www.cnbc.com/2025/04/15/nvidia-says-it-will-record-5point5-billion-quarterly-charge-tied-to-h20-processors-exported-to-china.html'
        ]
        g_logger.info("Running test mode on sample URLs:\n")
        for url_test in test_urls: # Use different variable name
            g_logger.info(f"Testing: {url_test}")
            # Use the main entry point function from image_parser
            result = custom_fetch_largest_image(url_test)
            g_logger.info(f"  Result: {result}\n")
        g_logger.info("Test mode complete.")
    elif len(sys.argv) > 1:
        test_url = sys.argv[1]
        g_logger.info(f"Testing custom_fetch_largest_image with URL: {test_url}")
        # Use the main entry point function from image_parser
        result = custom_fetch_largest_image(test_url)
        if result:
            g_logger.info(f"Result: {result}")
        else:
            g_logger.info("No image found or an error occurred.")
    else:
        g_logger.info("Usage: python image_processing.py <URL> or --test-urls")