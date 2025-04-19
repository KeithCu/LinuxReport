from urllib.parse import urljoin
import json
from image_utils import is_excluded, extract_dimensions_from_tag_or_style, debug_print, parse_best_srcset

def extract_img_url_from_tag(img_tag, base_url):
    """Extract the best image URL from an <img> tag, considering src, srcset, and data-* attributes."""
    srcset = img_tag.get('srcset')
    if srcset:
        # Use imported parse_best_srcset from image_utils
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
            debug_print(f"Error parsing JSON-LD: {e}")

    # 3. All <img> tags, robust lazy-load and data-* handling
    for img in soup.find_all('img'):
        url = extract_img_url_from_tag(img, base_url)
        if not url or is_excluded(url):
            continue
        # Use imported extract_dimensions_from_tag_or_style
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
        add_candidate(candidate_images, processed_urls, url, metadata)

    return candidate_images
