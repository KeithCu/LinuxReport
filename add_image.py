import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from PIL import Image
import io
import os
import time
import random

# Mapping of mode to corresponding HTML file
MODE_TO_FILE = {
    'trump': 'trumpreportabove.html',
    'techno': 'technoreportabove.html',
    'ai': 'aireportabove.html',
    'python': 'pythonreportabove.html',
    'covid': 'covidreportabove.html',
    'linux': 'linuxreportabove.html'
}

def fetch_largest_image(url):
    """Fetch the largest image from the given URL."""
    try:
        # Fetch the webpage
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html_content = response.text

        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Try to find Open Graph image first (often the main image)
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content']
        else:
            # Find all <img> tags with width and height attributes
            images = soup.find_all('img', {'src': True, 'width': True, 'height': True})
            if not images:
                print("No suitable image found with dimensions.")
                sys.exit(1)

            # Calculate area and select the largest image
            largest_image = max(images, key=lambda img: int(img['width']) * int(img['height']))
            image_url = largest_image['src']

        # Resolve relative URL to absolute
        absolute_image_url = urljoin(url, image_url)

        # Download the image
        image_response = requests.get(absolute_image_url, headers=headers, timeout=10)
        image_response.raise_for_status()
        return image_response.content

    except requests.RequestException as e:
        print(f"Error fetching image: {e}")
        sys.exit(1)

def save_as_webp(image_content):
    """Save the image as WebP in static/images with a unique filename."""
    # Ensure the directory exists
    os.makedirs('static/images', exist_ok=True)

    # Generate a unique filename
    timestamp = int(time.time() * 1000)
    random_num = random.randint(0, 999)
    filename = f"image_{timestamp}_{random_num}.webp"
    filepath = os.path.join('static/images', filename)

    # Convert to WebP using Pillow
    image = Image.open(io.BytesIO(image_content))
    image.save(filepath, 'WEBP')

    return filename

def update_html_file(html_file, title, image_filename, article_url):
    """Update the HTML file with a new entry, keeping only the latest two."""
    # Read existing content or initialize empty
    try:
        with open(html_file, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        content = ''

    # Parse the existing HTML
    soup = BeautifulSoup(content, 'html.parser')

    # Create the new center element
    new_center = soup.new_tag('center')

    # Title as a clickable link
    code = soup.new_tag('code')
    font = soup.new_tag('font', size='6')
    b = soup.new_tag('b')
    a_title = soup.new_tag('a', href=article_url, target='_blank')
    a_title.string = title
    b.append(a_title)
    font.append(b)
    code.append(font)
    new_center.append(code)

    # Line break
    br = soup.new_tag('br')
    new_center.append(br)

    # Image as a clickable link
    a_img = soup.new_tag('a', href=article_url, target='_blank')
    img = soup.new_tag('img', src=f'/static/images/{image_filename}', width='500', alt=title)
    a_img.append(img)
    new_center.append(a_img)

    # Insert the new entry at the beginning
    soup.insert(0, new_center)

    # Keep only the first two <center> elements
    centers = soup.find_all('center')
    for center in centers[2:]:
        center.decompose()

    # Write back the updated content
    with open(html_file, 'w') as f:
        f.write(str(soup))

def main():
    # Check command-line arguments
    if len(sys.argv) != 4:
        print("Usage: python add_image.py <URL> <TITLE> <MODE>")
        print("Modes:", ', '.join(MODE_TO_FILE.keys()))
        sys.exit(1)

    url = sys.argv[1]
    title = sys.argv[2]
    mode = sys.argv[3].lower()

    # Validate mode
    if mode not in MODE_TO_FILE:
        print(f"Invalid mode '{mode}'. Available modes: {', '.join(MODE_TO_FILE.keys())}")
        sys.exit(1)

    html_file = MODE_TO_FILE[mode]

    # Fetch the largest image
    image_content = fetch_largest_image(url)

    # Save as WebP and get the filename
    image_filename = save_as_webp(image_content)

    # Update the HTML file
    update_html_file(html_file, title, image_filename, url)

    print(f"Added image to {html_file} with title '{title}'")

if __name__ == "__main__":
    main()