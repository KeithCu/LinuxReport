#!/usr/bin/env python3
import os
import sys
from urllib.parse import urlparse
from pathlib import Path
from timeit import default_timer as timer
import argparse
import importlib.util
import string
import datetime
from jinja2 import Template
import requests
from urllib.parse import urljoin
import re
from rapidfuzz import process, fuzz
import json

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import urllib.request
import os
from PIL import Image
import io

from shared import FeedHistory, RssFeed, TZ, Mode, MODE, g_c
import feedparser
from shared import DiskCacheWrapper, PATH
from seleniumfetch import create_driver
from openai import OpenAI

# Initialize Together AI client
client = OpenAI(
    api_key=os.environ.get("TOGETHER_API_KEY_LINUXREPORT"),
    base_url="https://api.together.xyz/v1",
)

BASE = "/srv/http/"

MODE_TO_PATH = {
    "linux": BASE + "LinuxReport2",
    "ai": BASE + "aireport",
    "covid": BASE + "CovidReport2",
    "trump": BASE + "trumpreport",
}

#Simple schedule for when to do updates. Service calls hourly
MODE_TO_SCHEDULE = {
    "linux": [8, 12, 16],
    "ai": [8, 16],
    "covid": [8, 16],
    "trump": [4, 8, 10, 12, 14, 16, 20],
}

cache = DiskCacheWrapper(".")
ALL_URLS = {}
custom_hacks = {}

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
                target_url = part.strip()[4:].strip()  # Extract the URL after 'url='
                break

        if target_url:
            url = urljoin(url, target_url)
            continue
        else:
            return response

    print("Error: Too many meta refresh redirects")
    return None

def parse_images_from_soup(soup, base_url):
    candidate_images = []

    # 1. Check meta tags first (typically highest quality for sharing)
    meta_image_url = get_meta_image(soup)
    if meta_image_url:
        absolute_meta_url = urljoin(base_url, meta_image_url)
        candidate_images.append((absolute_meta_url, 1000000))  # Give high priority to meta images
        print(f"Found meta image: {absolute_meta_url}")
    
    # 2. Check for picture elements with srcset
    for picture in soup.find_all('picture'):
        # Find the highest resolution source
        max_width = 0
        best_source = None
        
        for source in picture.find_all('source'):
            if source.get('srcset'):
                best_src, width = parse_best_srcset(source['srcset'])
                if width > max_width:
                    max_width = width
                    best_source = best_src
        
        # Also check for img inside picture as fallback
        img = picture.find('img')
        if img:
            if img.get('srcset'):
                img_best_src, img_width = parse_best_srcset(img['srcset'])
                if img_width > max_width:
                    max_width = img_width
                    best_source = img_best_src
            elif img.get('src'):
                best_source = img['src']
                # Estimate size based on any width attributes
                if img.get('width'):
                    try:
                        max_width = int(img['width'])
                    except ValueError:
                        max_width = 500  # Default estimate
        
        if best_source:
            absolute_url = urljoin(base_url, best_source)
            candidate_images.append((absolute_url, max_width * max_width))  # Square for comparison
    
    # 3. Process all img tags (both standard and lazy-loaded)
    for img in soup.find_all('img'):
        # Check various attributes for image source
        src = None
        for attr in ['src', 'data-src', 'data-lazy-src', 'data-original', 'data-srcset']:
            if img.get(attr):
                src = img[attr]
                break
        
        if not src:
            continue
            
        # Handle srcset if available
        if attr == 'data-srcset' or attr == 'srcset' or 'srcset' in img.attrs:
            srcset = img.get('srcset', img.get('data-srcset', ''))
            best_src, _ = parse_best_srcset(srcset)
            if best_src:
                src = best_src
        
        # Calculate image importance score
        width = height = 100  # Default estimates
        
        # Try to get dimensions
        try:
            if img.get('width') and not img['width'] == 'auto':
                width = int(img['width']) if img['width'].isdigit() else width
            if img.get('height') and not img['height'] == 'auto':
                height = int(img['height']) if img['height'].isdigit() else height
        except (ValueError, KeyError):
            pass
            
        # Check if image is hidden or very small
        style = img.get('style', '')
        if 'display:none' in style or 'visibility:hidden' in style:
            continue
            
        # Check for very small images or icons to exclude
        if (width < 50 or height < 50) and ('icon' in src.lower() or 'logo' in src.lower()):
            continue
            
        # Calculate score based on size and position in the document
        score = width * height
        absolute_url = urljoin(base_url, src)
        
        # Exclude common patterns for site logos, icons, etc.
        exclude_patterns = ['logo', 'icon', 'avatar', 'banner', 'Linux_opengraph']
        if not any(pattern in absolute_url.lower() for pattern in exclude_patterns):
            candidate_images.append((absolute_url, score))
    
    return candidate_images

def fetch_largest_image(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0'}
        response = get_final_response(url, headers)
        if response is None:
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
            
        # Sort by score (higher is better) and return the best image URL
        return process_candidate_images(candidate_images)

    except Exception as e:
        print(f"Error fetching image: {e}")
        return None

def get_meta_image(soup):
    """Extract image URL from various meta tags"""
    # Check OpenGraph image (highest priority)
    og_image = soup.find('meta', property='og:image')
    if og_image and og_image.get('content'):
        return og_image['content']
        
    # Check Twitter card
    twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
    if twitter_image and twitter_image.get('content'):
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

def parse_best_srcset(srcset):
    """Parse srcset attribute and return the best (largest) image URL"""
    if not srcset:
        return None, 0
        
    best_width = 0
    best_url = None
    
    # Handle space-separated srcset format
    parts = srcset.strip().split(',')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        # Split URL and descriptor
        subparts = part.split(' ')
        url = subparts[0].strip()
        
        if len(subparts) > 1:
            # Try to extract width descriptor (e.g., "800w")
            width_match = re.search(r'(\d+)w', part)
            if width_match:
                width = int(width_match.group(1))
                if width > best_width:
                    best_width = width
                    best_url = url
                    continue
            
            # Try to extract pixel density descriptor (e.g., "2x")
            density_match = re.search(r'(\d+(\.\d+)?)x', part)
            if density_match:
                density = float(density_match.group(1))
                # Convert density to an approximate width score
                approx_width = 1000 * density  # Rough estimate
                if approx_width > best_width:
                    best_width = approx_width
                    best_url = url
        else:
            # If no descriptor, just use the URL
            if best_url is None:
                best_url = url
                best_width = 1
    
    return best_url, best_width

def custom_fetch_largest_image(url):
    domain = extract_domain(url)
    if domain in custom_hacks:
        print(f"Using custom hack for {domain}")
        return custom_hacks[domain](url)
    else:
        return fetch_largest_image(url)

def extract_underlying_url(url, selector_func):
    """Common function to extract an underlying URL from a webpage."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0'}
        response = requests.get(url, headers=headers, timeout=10)
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

def extract_domain(url):
    parsed = urlparse(url)
    return parsed.netloc

custom_hacks["linuxtoday.com"] =  linuxtoday_custom_fetch
custom_hacks["citizenfreepress.com"] = citizenfreepress_custom_fetch

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

def process_candidate_images(candidate_images):
    """Process a list of candidate images and return the best one."""
    if not candidate_images:
        print("No suitable images found.")
        return None
    
    # Sort by score (higher is better) and return the best image URL
    candidate_images.sort(key=lambda x: x[1], reverse=True)
    best_image_url = candidate_images[0][0]
    
    print(f"Best image found: {best_image_url} with score {candidate_images[0][1]}")
    return best_image_url

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

def fetch_recent_articles():
    global cache    
    articles = []
    for url, rss_info in ALL_URLS.items():
        feed = cache.get(url)
        if feed is None:
            print (f"No data found for {url}")
            continue

        count = 0
        for entry in feed.entries:
            title = entry["title"]
            articles.append({"title": title, "url": entry["link"]})
            count += 1
            if count == 5:
                break

    return articles



# Define the Jinja2 template for a single headline
headline_template = Template("""
<center>
<code>
<a href="{{ url }}" target="_blank">
<font size="5"><b>{{ title }}</b></font>
</a>
</code>
{% if image_url %}
<br/>
<a href="{{ url }}" target="_blank">
<img src="{{ image_url }}" width="500" alt="{{ title }}">
</a>
{% endif %}
</center>
<br/>
""")

def generate_headlines_html(top_articles, output_file):
    # Step 1: Find the first article with an available image
    image_article_index = None
    image_url = None
    for i, article in enumerate(top_articles[:3]):
        potential_image_url = custom_fetch_largest_image(article["url"])
        if potential_image_url:
            image_article_index = i
            image_url = potential_image_url
            break  # Stop at the first article with an image

    # Step 2: Generate HTML for each of the three headlines
    html_parts = []
    for i, article in enumerate(top_articles[:3]):
        # Only pass image_url if this article is the one with the image
        current_image_url = image_url if i == image_article_index else None
        rendered_html = headline_template.render(
            url=article["url"],
            title=article["title"],
            image_url=current_image_url
        )
        html_parts.append(rendered_html)

    # Combine all headline HTML
    full_html = "\n".join(html_parts)

    # Step 3: Write to the output file
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(full_html)

BANNED_WORDS = [
    "tmux",
    "redox",
]

modetoprompt2 = {
    Mode.LINUX_REPORT: f"""Arch Linux programmers and experienced users. Nothing about Ubuntu or any other
    distro. Of course anything non-distro-specific is fine, but nothing about the 
    following topics: {', '.join(BANNED_WORDS)}.\n""",
    Mode.AI_REPORT : "AI Language Model Researchers. Nothing about AI security.",
    Mode.COVID_REPORT : "COVID-19 researchers",
    Mode.TRUMP_REPORT : "Trump's biggest fans",
}

modetoprompt = {
    "linux": modetoprompt2[Mode.LINUX_REPORT],
    "ai": modetoprompt2[Mode.AI_REPORT],
    "covid": modetoprompt2[Mode.COVID_REPORT],
    "trump": modetoprompt2[Mode.TRUMP_REPORT],
}

PROMPT_AI = f""" Rank these article titles by relevance to {modetoprompt2[MODE]} 
    Please talk over the titles to decide which ones sound interesting.
    Some headlines will be irrelevant, those are easy to exclude.
    When you are done discussing the titles, put *** and then list the top 3, using only the titles.
    """

MAX_PREVIOUS_HEADLINES = 9  # Example: Remember the last 9 headlines (configurable)


def get_article_for_title(target_title, articles):

    titles = [article["title"] for article in articles]

    best_title, score, index = process.extractOne(target_title, titles, processor=normalize, scorer=fuzz.ratio)
    return articles[index]

def ask_ai_top_articles(articles, model):
    previous_urls = g_c.get("previously_selected_urls")
    if not isinstance(previous_urls, list):
        previous_urls = []

    print (f"Previous URLs: {previous_urls}")
    filtered_articles = [article for article in articles if article["url"] not in previous_urls]
    
    if not filtered_articles:
        print("No new articles available after filtering previously selected ones.")
        return "No new articles to rank."

    prompt_full = PROMPT_AI + "\n" + "\n".join(f"{i}. {article['title']}" for i, article in enumerate(filtered_articles, 1))
    print(prompt_full)
    
    # Get AI response
    start = timer()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt_full}],
        max_tokens=3000,
    )
    end = timer()

    print(f"LLM Response: {response.choices[0].message.content} in {end - start:f}.")
    response_text = response.choices[0].message.content
    
    top_titles = extract_top_titles_from_ai(response_text)
    top_articles = [get_article_for_title(title, filtered_articles) for title in top_titles]
    
    new_urls = [article["url"] for article in top_articles if article]
    updated_urls = previous_urls + new_urls  # Append new selections
    
    if len(updated_urls) > MAX_PREVIOUS_HEADLINES:
        updated_urls = updated_urls[-MAX_PREVIOUS_HEADLINES:]

    print (f"Updated URLs: {updated_urls}")
    g_c.put("previously_selected_urls", updated_urls)
    
    return response_text
    
def extract_top_titles_from_ai(text):
    lines = text.splitlines()
    titles = []
    
    for line in lines:
        match = re.match(r"^\d+\.\s+(.+)$", line)
        if match:
            title = match.group(1).strip("*").strip()
            titles.append(title)
            if len(titles) == 3:
                break
    
    return titles

def normalize(text):
    return text.lower().translate(str.maketrans("", "", string.punctuation)).strip()


def main(mode):
    global ALL_URLS
    prompt = modetoprompt[mode]

    module_path = f"{mode}_report_settings.py"

    if not os.path.isfile(module_path):
        raise FileNotFoundError(f"Module file not found: {module_path}")

    spec = importlib.util.spec_from_file_location("module_name", module_path)

    # Load the module
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    ALL_URLS = module.ALL_URLS

    base_path = PATH
    mode_dir = os.path.join(base_path, MODE_TO_PATH[mode])
    html_file = f"{mode}reportabove.html"

    model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"

    try:
        articles = fetch_recent_articles()
        if not articles:
            print(f"No articles found for mode: {mode}")
            sys.exit(1)

        full_response = ask_ai_top_articles(articles, model)
        top_3 = extract_top_titles_from_ai(full_response)
        top_3_articles = [get_article_for_title(title, articles) for title in top_3]
        generate_headlines_html(top_3_articles, html_file)
    except Exception as e:
        print(f"Error in mode {mode}: {e}")
        sys.exit(1)

if __name__ == "__main__":

    cwd = os.getcwd()
    for mode in MODE_TO_PATH.keys():
        if mode.lower() in cwd.lower():
            hours = MODE_TO_SCHEDULE[mode]
            current_hour = datetime.datetime.now(TZ).hour
            if current_hour in hours:
                main(mode)
                break

