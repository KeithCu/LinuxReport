#!/usr/bin/env python3
import os
import sys
from openai import OpenAI
from pathlib import Path
import argparse
import importlib.util
import re
from rapidfuzz import process, fuzz
import string
import datetime
from jinja2 import Template
import requests
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from shared import FeedHistory, RssFeed, TZ
import feedparser
from app import DiskCacheWrapper, PATH

from timeit import default_timer as timer

# Initialize Together AI client
client = OpenAI(
    api_key=os.environ.get("TOGETHER_API_KEY_LINUXREPORT"),
    base_url="https://api.together.xyz/v1",
)

BANNED_WORDS = [
    "tmux",
    "redox",
]
modetoprompt = {
    "linux": f"""Arch Linux programmers and enthusiasts. Nothing about Ubuntu or any other
    distro. Of course anything non-distro-specific is fine, but nothing about the 
    following topics: {', '.join(BANNED_WORDS)}.\n""",
    "ai": "AI Language Model Researchers. Nothing about AI security.",
    "covid": "COVID-19 researchers",
    "trump": "Trump's biggest fans",
}

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

def fetch_largest_image(url):
    """Fetch the URL of the largest image from the given URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content']
        else:
            images = soup.find_all('img', {'src': True, 'width': True, 'height': True})
            if not images:
                print("No suitable image found with dimensions.")
                return None
            largest_image = max(images, key=lambda img: int(img['width']) * int(img['height']))
            image_url = largest_image['src']

        absolute_image_url = urljoin(url, image_url)
        return absolute_image_url  # Return the URL instead of content

    except requests.RequestException as e:
        print(f"Error fetching image: {e}")
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

def ask_ai_top_articles(articles, prompt, model):
    prompt_full = prompt + "\n" + "\n".join(f"{i}. {article['title']}" for i, article in enumerate(articles, 1))
    print (prompt_full)
    start = timer()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt_full}],
        max_tokens=3000,
    )

    end = timer()
    print(f"LLM Response: {response.choices[0].message.content} in {end - start:f}.")
    return response.choices[0].message.content

def extract_top_titles_from_ai(text):
    # Split the text into individual lines
    lines = text.splitlines()
    titles = []
    
    # Iterate through each line
    for line in lines:
        # Check if the line starts with a number followed by a period and space (e.g., "1. ")
        match = re.match(r"^\d+\.\s+(.+)$", line)
        if match:
            # Extract the title (everything after the number and period) and clean it
            title = match.group(1).strip("*").strip()
            titles.append(title)
            # Stop after collecting 3 titles
            if len(titles) == 3:
                break
    
    return titles

def normalize(text):
    return text.lower().translate(str.maketrans("", "", string.punctuation)).strip()

# Function to find the closest matching article
def get_article_for_title(target_title, articles):
    # Extract the list of article titles
    titles = [article["title"] for article in articles]
    # Find the best match using fuzzy matching with normalization
    best_title, score, index = process.extractOne(target_title, titles, processor=normalize, scorer=fuzz.ratio)
    # Return the corresponding article
    return articles[index]


# Define the Jinja2 template for a single headline
headline_template = Template("""
<center>
<code>
<a href="{{ url }}" target="_blank">
<font size="5"><b>{{ title }}</b></font>
</a>
</code>
{% if loop_index == 0 and image_url %}
<br/>
<a href="{{ url }}" target="_blank">
<img src="{{ image_url }}" width="500" alt="{{ title }}">
</a>
{% endif %}
</center>
<br/>
""")

# Replace the generate_headlines_html function in auto_update.py around line 332
def generate_headlines_html(top_articles, output_file):
    html_parts = []
    for i, article in enumerate(top_articles[:3]):  # Take up to three articles
        image_url = None
        if i == 0:  # Only fetch image for the first article
            image_url = fetch_largest_image(article["url"])
        
        rendered_html = headline_template.render(
            url=article["url"],
            title=article["title"],
            image_url=image_url,
            loop_index=i  # Pass the index for the template to use
        )
        html_parts.append(rendered_html)
    
    full_html = "\n".join(html_parts)
    
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
    prompt_ai = f""" Rank these article titles by relevance to {prompt} 
    Please talk over the the titles to decide which ones sound interesting.
    Some headlines will be irrelevant, those are easy to exclude.
    When you are done discussing the titles, put *** and then list the top 3.
    """
    model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"

    try:
        articles = fetch_recent_articles()
        if not articles:
            print(f"No articles found for mode: {mode}")
            sys.exit(1)

        full_response = ask_ai_top_articles(articles, prompt_ai, model)
        top_3 = extract_top_titles_from_ai(full_response)
        top_3_articles = [get_article_for_title(title, articles) for title in top_3]
        generate_headlines_html(top_3_articles, html_file)
    except Exception as e:
        print(f"Error in mode {mode}: {e}")
        sys.exit(1)

if __name__ == "__main__":

    cwd = os.getcwd()
    for mode in MODE_TO_PATH.keys():
        if mode in cwd:
            hours = MODE_TO_SCHEDULE[mode]
            current_hour = datetime.datetime.now(TZ).hour
            if current_hour in hours:
                main(mode)
                break

