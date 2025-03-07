#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from timeit import default_timer as timer
import argparse
import importlib.util
import string
import datetime
from jinja2 import Template
import requests
from urllib.parse import urljoin

from rapidfuzz import process, fuzz

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

from shared import FeedHistory, RssFeed, TZ, Mode, MODE, ask_ai_top_articles, extract_top_titles_from_ai, modetoprompt, normalize, get_article_for_title
import feedparser
from shared import DiskCacheWrapper, PATH
from seleniumfetch import create_driver



base = "/srv/http/"

MODE_TO_PATH = {
    "linux": base + "LinuxReport2",
    "ai": base + "aireport",
    "covid": base + "CovidReport2",
    "trump": base + "trumpreport",
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

def fetch_largest_image(url):
    try:    #A better user agent increases chance of success
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0'}
        response = get_final_response(url, headers)
        if response is None:
            return None
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content']
        else:
            exclude_text = "Linux_opengraph"  # Define the chunk of text to exclude
            images = soup.find_all('img', {
                'src': lambda x: x is not None and exclude_text not in x,
                'width': True,
                'height': True
            })
            if not images:
                print("No suitable image found with dimensions.")
                return None
            largest_image = max(images, key=lambda img: int(img['width']) * int(img['height']))
            image_url = largest_image['src']

        absolute_image_url = urljoin(url, image_url)
        print (f"largest image found {absolute_image_url}")
        return absolute_image_url  # Return the URL instead of content

    except Exception as e:
        print(f"Error fetching image: {e}")
        return None

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
            return (None, 0)

        images = driver.find_elements(By.TAG_NAME, 'img')
        
        if not images:
            print("No images found on the page.")
            driver.quit()
            return (None, 0)

        largest_image_url = None
        largest_size = 0

        for img in images:
            try:
                img_url = img.get_attribute('src')
                if not img_url or 'data:' in img_url:  # Skip data URLs or invalid URLs
                    continue

                try:
                    with urllib.request.urlopen(img_url) as response:
                        image_data = response.read()
                    
                    image_size = len(image_data)
                    
                    # Update if this image is larger than the current largest
                    if image_size > largest_size:
                        largest_size = image_size
                        largest_image_url = img_url

                except Exception as e:
                    print(f"Error downloading or measuring {img_url}: {e}")
                    continue

            except Exception as e:
                print(f"Error processing image element: {e}")
                continue

        driver.quit()  # Close the browser

        if largest_image_url:
            print(f"Largest image URL: {largest_image_url}")
            print(f"Size: {largest_size} bytes")
            return (largest_image_url, largest_size)
        else:
            print("No valid images found.")
            return (None, 0)

    except Exception as e:
        print(f"Error accessing the webpage or processing images: {e}")
        driver.quit()
        return (None, 0)


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
        potential_image_url = fetch_largest_image(article["url"])
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

