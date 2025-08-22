\
"""
Module: image_utils.py

Contains core utility functions, constants, and image dimension logic
extracted from image_processing.py.
"""
import re
import requests
from io import BytesIO
from PIL import Image
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from shared import g_logger

# === Constants and Configuration ===
DEBUG_LOGGING = True
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0'}
EXCLUDED_PATTERNS = ['logo', 'icon', 'avatar', 'banner', 'emoji', 'css', 'advertisement', 'michaellarabel']
EXCLUDED_RE = re.compile(r"(?:" + r"|".join(re.escape(p) for p in EXCLUDED_PATTERNS) + r")", re.IGNORECASE)
IMAGE_EXT_RE = re.compile(r"\\.(jpe?g|png|webp|gif|svg)([?#].*)?$", re.IGNORECASE)

# === Utility Functions ===

def is_excluded(url):
    return bool(EXCLUDED_RE.search(url))

def parse_dimension(value):
    # Extract leading numeric value (int or float)
    m = re.match(r'^\s*(\d+(?:\.\d+)?)', str(value))
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
                    g_logger.debug(f"Skipping small image ({content_length} bytes): {img_url}")
                    return 0, 0
            except Exception:
                pass
        
        if 'svg' in content_type:
            g_logger.debug(f"SVG image detected for {img_url}, attempting to parse dimensions")
            try:
                svg = ET.fromstring(response.content)
                width = svg.attrib.get('width')
                height = svg.attrib.get('height')
                
                # Improved SVG dimension parsing with unit handling
                def parse_svgdimension(value):
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
                        except Exception:
                            pass
                            
                # More realistic fallback based on SVG content complexity
                fallback_dim = min(max(int(len(response.content) ** 0.4), 200), 800)
                g_logger.debug(f"Fallback SVG dimensions based on file size for {img_url}: {fallback_dim}x{fallback_dim}")
                return fallback_dim, fallback_dim
            except Exception as e:
                g_logger.debug(f"Error parsing SVG for {img_url}: {e}")
                return 640, 480  # Default fallback dimensions
        
        # More efficient image dimension detection using image header only
        try:
            with Image.open(BytesIO(response.content)) as img:
                width, height = img.size
                g_logger.debug(f"Got actual dimensions for {img_url}: {width}x{height}")
                return width, height
        except Image.UnidentifiedImageError:
            g_logger.debug(f"Could not identify image file: {img_url}")
            return 0, 0
        except Exception as e:
            g_logger.debug(f"Error reading image dimensions with PIL for {img_url}: {e}")
            return 0, 0
    except requests.exceptions.RequestException as e:
        g_logger.debug(f"Request error getting dimensions for {img_url}: {e}")
        return 0, 0
    except Exception as e:
        g_logger.debug(f"Generic error getting dimensions for {img_url}: {e}")
        return 0, 0


def extract_domain(url):
    parsed = urlparse(url)
    netloc = parsed.netloc
    if (netloc.startswith("www.")):
        return netloc[4:]
    return netloc

# === Srcset Parsing ===

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
                    # Approximate width based on pixel density descriptor
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

def score_image_candidate(width, height, alt_text=None):
    """Score an image candidate based on area and alt text."""
    area = width * height if width > 0 and height > 0 else 0
    score = area if area > 0 else 640 * 480  # Default to 640x480 if unknown
    if alt_text and len(alt_text) > 10:
        score *= 1.2
    return score
