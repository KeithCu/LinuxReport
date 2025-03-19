#!/usr/bin/python3
from urllib.parse import urlparse, urljoin
import re
import json
import urllib.request
import requests
from io import BytesIO
from PIL import Image  # Add Pillow dependency

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

def get_actual_image_dimensions(img_url):
    """Fetch an image and get its actual dimensions. Special handling for SVG images with approximate dimensions."""
    try:
        headers_with_referer = HEADERS.copy()
        headers_with_referer["Referer"] = img_url  # Added Referer header
        response = requests.get(img_url, headers=headers_with_referer, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '').lower()
        
        # Use content-length as a quick check for valid images
        content_length = int(response.headers.get('Content-Length', 0))
        if content_length < 100:  # Skip very small images that are likely icons
            debug_print(f"Skipping small image ({content_length} bytes): {img_url}")
            return 0, 0
            
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
        except Exception as e:
            debug_print(f"Error reading image dimensions: {e}")
            return 0, 0
    except Exception as e:
        debug_print(f"Error getting dimensions for {img_url}: {e}")
        return 0, 0

def evaluate_image_url(img_url):
    """Evaluate an image by downloading it and checking its size."""
    try:
        req_headers = {
            "User-Agent": HEADERS.get("User-Agent"),
            "Referer": img_url  # Added Referer header
        }
        req = urllib.request.Request(img_url, headers=req_headers)
        with urllib.request.urlopen(req) as response:
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
        if img_tag.get('width'):
            if img_tag['width'].isdigit():
                width = int(img_tag['width'])
            elif isinstance(img_tag['width'], str) and img_tag['width'].strip().endswith('px'):
                width_str = img_tag['width'].strip().rstrip('px')
                if width_str.isdigit():
                    width = int(width_str)

        if img_tag.get('height'):
            if img_tag['height'].isdigit():
                height = int(img_tag['height'])
            elif isinstance(img_tag['height'], str) and img_tag['height'].strip().endswith('px'):
                height_str = img_tag['height'].strip().rstrip('px')
                if height_str.isdigit():
                    height = int(height_str)
    except (ValueError, KeyError):
        pass

    # Check for dimensions in style attribute
    if (width == 0 or height == 0) and img_tag.get('style'):
        style = img_tag['style']
        width_match = re.search(r'width:\s*(\d+)px', style)
        if width_match:
            width = int(width_match.group(1))
        height_match = re.search(r'height:\s*(\d+)px', style)
        if height_match:
            height = int(height_match.group(1))

    return width, height

def process_candidate_images(candidate_images):
    """Process a list of candidate images and return the best one based on a refined scoring logic."""
    if not candidate_images:
        print("No candidate images available for processing.")
        return None

    # Normalize candidates and log each candidate's metadata.
    normalized_candidates = []
    for item in candidate_images:
        url = item[0]
        if isinstance(item[1], dict):
            normalized_candidates.append(item)
        elif isinstance(item[1], (int, float)):
            normalized_candidates.append((url, {'score': item[1], 'filesize': item[1]}))
        else:
            normalized_candidates.append((url, {'score': 1000}))
        if DEBUG_LOGGING:
            debug_print(f"Normalized candidate: {url} with metadata: {normalized_candidates[-1][1]}")
    candidate_images = normalized_candidates

    # First pass: filter out obviously bad candidates and categorize images
    meta_images = []
    content_images = []
    other_images = []
    
    for url, metadata in candidate_images:
        # Immediately exclude disqualified images
        if any(pattern in url.lower() for pattern in ['logo', 'icon', 'avatar', 'banner', 'emoji', 'advertisement']):
            debug_print(f"Skipping excluded pattern image: {url}")
            continue
            
        # Check file extension for common image types
        if re.search(r'\.(jpe?g|png|webp|gif|svg)([?#].*)?$', url.lower()):
            # Good - it's a known image type
            pass
        elif not re.search(r'\.(bmp|tiff?|avif|ico)([?#].*)?$', url.lower()):
            # Not a typical image extension, check if URL seems to be an API or script
            if re.search(r'(\.php|\.aspx?|\.cgi|\?|\=)', url.lower()):
                debug_print(f"Skipping potential non-image URL: {url}")
                continue
    
        # Categorize by priority
        if metadata.get('score', 0) > 500000:
            meta_images.append((url, metadata))
        elif metadata.get('width', 0) > 200 and metadata.get('height', 0) > 200:
            content_images.append((url, metadata))
        else:
            other_images.append((url, metadata))
    
    # If we have meta images, prioritize them
    if meta_images:
        debug_print(f"Using meta images priority: {len(meta_images)} candidates")
        top_candidates = meta_images
    else:
        # Combine remaining categories
        top_candidates = content_images + other_images
        
    if not top_candidates:
        print("No suitable images found after filtering.")
        return None
    
    # Second pass: get dimensions and calculate scores
    enhanced_candidates = []
    # Get top 5 for dimension fetching
    initial_top = sorted(top_candidates, key=lambda item: item[1].get('score', 0), reverse=True)[:5]
    
    for url, metadata in top_candidates:
        width = metadata.get('width', 0)
        height = metadata.get('height', 0)
        srcset_width = metadata.get('srcset_width', 0)

        # If it's a top candidate and we don't have dimensions, fetch them
        if (width == 0 or height == 0) and (url, metadata) in initial_top:
            actual_width, actual_height = get_actual_image_dimensions(url)
            if actual_width > 0 and actual_height > 0:
                metadata['width'] = actual_width
                metadata['height'] = actual_height
                width, height = actual_width, actual_height

        # Calculate final score with improved weighting
        base_score = metadata.get('score', 0)
        filesize = metadata.get('filesize', 0)
        
        # Calculate dimension score
        dimension_score = 0
        if width > 0 and height > 0:
            # Reward larger images but with diminishing returns
            area = width * height
            if area > 0:
                dimension_score = min(area / 1000, 5000)  # Cap at 5000 to avoid huge images dominating
                
                # Adjust for reasonable aspect ratios
                aspect = width / height
                if 0.5 <= aspect <= 2.5:  # Reasonable range for content images
                    dimension_score *= 1.3
                    
                # Penalize extreme aspect ratios
                elif aspect < 0.2 or aspect > 5:
                    dimension_score *= 0.5
        elif srcset_width > 0:
            # If we only have srcset width, estimate a score
            dimension_score = srcset_width * 2
            
        # Filesize can be an indicator of quality
        filesize_score = 0
        if filesize > 0:
            filesize_kb = filesize / 1024
            # Reward larger files up to a point (8MB)
            if filesize_kb < 8192:
                filesize_score = min(filesize_kb / 10, 500)
            else:
                # Penalize excessively large files
                filesize_score = 500 - min((filesize_kb - 8192) / 100, 400)
        
        # Combine scores with appropriate weights
        final_score = base_score
        if dimension_score > 0:
            final_score = max(final_score, dimension_score * 1.5)
        if filesize_score > 0:
            final_score += filesize_score
            
        # Small images don't provide value
        if width > 0 and height > 0 and width < 100 and height < 100:
            continue
            
        metadata['final_score'] = final_score
        debug_print(f"Final score for {url}: {final_score} (dimensions: {width}x{height})")
        enhanced_candidates.append((url, metadata))

    if not enhanced_candidates:
        print("No suitable images found after scoring.")
        return None

    # Sort by final score
    enhanced_candidates.sort(key=lambda item: item[1].get('final_score', 0), reverse=True)
    best_image_url = enhanced_candidates[0][0]
    print(f"Best image found: {best_image_url} with score {enhanced_candidates[0][1].get('final_score')}")
    
    if DEBUG_LOGGING and len(enhanced_candidates) > 1:
        debug_print(f"Runner-up: {enhanced_candidates[1][0]} with score {enhanced_candidates[1][1].get('final_score')}")
        
    return best_image_url

def parse_images_from_soup(soup, base_url):
    """Extract image candidates from HTML using BeautifulSoup with improved handling."""
    candidate_images = []
    
    # Track processed URLs to avoid duplicates
    processed_urls = set()

    # 1. Get meta tag images (high priority)
    meta_tags = [
        ('meta[property="og:image"]', 'content', 4000000),
        ('meta[name="twitter:image"]', 'content', 1500000),
        ('meta[name="twitter:image:src"]', 'content', 1500000),
        ('meta[property="og:image:secure_url"]', 'content', 4000000),
        ('meta[itemprop="image"]', 'content', 1000000),
    ]
    
    for selector, attr, score in meta_tags:
        for tag in soup.select(selector):
            if tag.get(attr):
                url = urljoin(base_url, tag[attr])
                if url not in processed_urls:
                    processed_urls.add(url)
                    candidate_images.append((url, {'score': score}))
                    print(f"Found meta image ({selector}): {url}")

    # 2. Check Schema.org image in JSON-LD
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                # Handle different schema formats
                image_candidates = []
                
                if 'image' in data:
                    if isinstance(data['image'], str):
                        image_candidates.append(data['image'])
                    elif isinstance(data['image'], list):
                        image_candidates.extend(data['image'])
                    elif isinstance(data['image'], dict) and 'url' in data['image']:
                        image_candidates.append(data['image']['url'])
                        
                # Handle nested images in Graph schemas        
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
                        if url not in processed_urls:
                            processed_urls.add(url)
                            candidate_images.append((url, {'score': 1000000}))
                            print(f"Found Schema.org image: {url}")
        except Exception as e:
            debug_print(f"Error parsing JSON-LD: {e}")

    # 3. Process <picture> elements
    for picture in soup.find_all('picture'):
        max_width = 0
        best_source = None

        # Check <source> elements
        for source in picture.find_all('source'):
            if source.get('srcset'):
                best_src, width = parse_best_srcset(source['srcset'])
                if best_src and width > max_width:
                    max_width = width
                    best_source = best_src
            # Also check src attribute
            elif source.get('src'):
                if max_width == 0:
                    best_source = source['src']

        # Check the <img> inside picture as fallback
        img = picture.find('img')
        if img:
            if img.get('srcset'):
                img_best_src, img_width = parse_best_srcset(img['srcset'])
                if img_best_src and img_width > max_width:
                    max_width = img_width
                    best_source = img_best_src
            elif img.get('src') and not best_source:
                best_source = img['src']
                width, height = get_image_dimensions_from_attributes(img)
                if width > 0:
                    max_width = width

        if best_source:
            absolute_url = urljoin(base_url, best_source)
            if absolute_url not in processed_urls:
                processed_urls.add(absolute_url)
                metadata = {'srcset_width': max_width, 'score': max_width * 2}
                candidate_images.append((absolute_url, metadata))

    # 4. Handle special data attributes for lazy-loaded images
    lazy_img_selectors = [
        ('img[data-src]', 'data-src'),
        ('img[data-lazy-src]', 'data-lazy-src'),
        ('img[data-lazy]', 'data-lazy'),
        ('img[data-original]', 'data-original'),
        ('img[data-srcset]', 'data-srcset'),
        ('img[loading="lazy"]', 'src'),
        ('img.lazyload', 'src')
    ]
    
    for selector, attr in lazy_img_selectors:
        for img in soup.select(selector):
            if img.get(attr):
                # For srcset, parse it to get the best URL
                if attr.endswith('srcset'):
                    best_src, width = parse_best_srcset(img[attr])
                    if best_src:
                        url = urljoin(base_url, best_src)
                        if url not in processed_urls:
                            processed_urls.add(url)
                            metadata = {'srcset_width': width}
                            width_attr, height_attr = get_image_dimensions_from_attributes(img)
                            if width_attr > 0:
                                metadata['width'] = width_attr
                            if height_attr > 0:
                                metadata['height'] = height_attr
                            candidate_images.append((url, metadata))
                else:
                    url = urljoin(base_url, img[attr])
                    if url not in processed_urls:
                        processed_urls.add(url)
                        width, height = get_image_dimensions_from_attributes(img)
                        metadata = {}
                        if width > 0:
                            metadata['width'] = width
                        if height > 0:
                            metadata['height'] = height
                        candidate_images.append((url, metadata))

    # 5. Process standard img tags
    for img in soup.find_all('img'):
        if img.get('src'):
            src = img['src']
            
            # Skip data URLs and very small images
            if src.startswith('data:'):
                continue
                
            # Check if image should be excluded based on classes or styling
            classes = img.get('class', [])
            if isinstance(classes, list) and any(c.lower() in ['logo', 'icon', 'avatar'] for c in classes):
                continue
                
            style = img.get('style', '')
            if 'display:none' in style or 'visibility:hidden' in style:
                continue

            # Check srcset first for better quality images
            srcset_url = None
            srcset_width = 0
            if img.get('srcset'):
                srcset_url, srcset_width = parse_best_srcset(img['srcset'])
            
            # Use srcset URL if available, otherwise fall back to src
            url = urljoin(base_url, srcset_url if srcset_url else src)
            if url in processed_urls:
                continue
                
            processed_urls.add(url)
            
            # Get dimensions and calculate score
            width, height = get_image_dimensions_from_attributes(img)
            alt_text = img.get('alt', '')
            
            metadata = {}
            if width > 0:
                metadata['width'] = width
            if height > 0:
                metadata['height'] = height
            if srcset_width > 0:
                metadata['srcset_width'] = srcset_width
                
            # Calculate initial score based on dimensions
            if width > 0 and height > 0:
                metadata['score'] = width * height
            elif srcset_width > 0:
                metadata['score'] = srcset_width * srcset_width
            else:
                # Default score for images without dimensions
                metadata['score'] = 640 * 480
                
            # Boost score for content images based on meaningful alt text
            if alt_text and len(alt_text) > 10:
                metadata['score'] = metadata['score'] * 1.2
                
            candidate_images.append((url, metadata))

    return candidate_images

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
        # Handle URLs that are already images
        if re.search(r'\.(jpe?g|png|webp|gif|svg)([?#].*)?$', url.lower()):
            print(f"URL appears to be an image: {url}")
            # Validate that it's actually an image
            response = requests.head(url, headers=HEADERS, timeout=5)
            content_type = response.headers.get('Content-Type', '').lower()
            if 'image/' in content_type:
                return url
        
        # Standard HTML page fetch
        response = get_final_response(url, HEADERS)
        if response is None:
            print("No response received.")
            return None
            
        # Check if the URL is a direct image
        content_type = response.headers.get('Content-Type', '').lower()
        if content_type.startswith('image/'):
            print(f"URL is an image: {url}")
            return url
            
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

            # Get natural dimensions as reported by the browser
            try:
                natural_width = driver.execute_script("return arguments[0].naturalWidth;", img)
                natural_height = driver.execute_script("return arguments[0].naturalHeight;", img)
            except:
                natural_width = natural_height = 0

            # Get display dimensions
            try:
                display_width = driver.execute_script("return arguments[0].clientWidth;", img)
                display_height = driver.execute_script("return arguments[0].clientHeight;", img)
            except:
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
                pass  # If we can't determine visibility, continue with the image

            # Don't skip images just because they're small - use dimensions for scoring later

            metadata = {
                'width': width,
                'height': height,
                'score': width * height if width > 0 and height > 0 else 640 * 480  # Default reasonable score
            }

            # Fetch image size for promising candidates
            if metadata['score'] > 10000 or (natural_width > 200 and natural_height > 200):
                file_size = evaluate_image_url(img_url)
                if file_size > 0:
                    metadata['filesize'] = file_size

            exclude_patterns = ['logo', 'icon', 'avatar', 'banner', 'emoji', 'advertisement']
            if not any(pattern in img_url.lower() for pattern in exclude_patterns):
                candidate_images.append((img_url, metadata))

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
