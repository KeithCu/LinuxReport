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

from jinja2 import Template

from add_image import fetch_largest_image, save_as_webp, update_html_file
from shared import FeedHistory, RssFeed, TZ
import feedparser
from app import DiskCacheWrapper, PATH

# Initialize Together AI client
client = OpenAI(
    api_key=os.environ.get("TOGETHER_API_KEY_LINUXREPORT"),
    base_url="https://api.together.xyz/v1",
)

banned_words = [
    "tmux",
]
modetoprompt = {
    "linux": f"Arch Linux programmers and enthusiasts. Nothing about Ubuntu or any other distro. Of course anything non-distro-specific is fine, but nothing about the following topics: {', '.join(banned_words)}.\n",
    "ai": "AI Language Model Researchers",
    "covid": "COVID-19 researchers",
    "trump": "Trump's biggest fans",
}

base = "/srv/http/"

modetopath = {
    "linux": base + "LinuxReport2",
    "ai": base + "aireport",
    "covid": base + "CovidReport2",
    "trump": base + "trumpreport",
}

cache = DiskCacheWrapper(".")

ALL_URLS = {}

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
            if count >= 8:
                break

    return articles

def ask_ai_top_articles(articles, prompt, model):
    prompt_full = prompt + "\n" + "\n".join(f"{i}. {article['title']}" for i, article in enumerate(articles, 1))
    print (prompt_full)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt_full}],
        max_tokens=3000,
    )

    print(response.choices[0].message.content)
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
<a href="{{ url }}">
<font size="6"><b>{{ title }}</b></font>
</a>
</code>
</center>
<br/>
""")

def generate_headlines_html(top_articles, output_file):
    html_parts = []
    for article in top_articles[:3]:  # Take up to three articles
        rendered_html = headline_template.render(
            url=article["url"],
            title=article["title"]
        )
        html_parts.append(rendered_html)
    
    full_html = "\n".join(html_parts)
    
    output_dir = os.path.dirname(output_file)
    if output_dir:  # If there's a directory in the path
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
    mode_dir = os.path.join(base_path, modetopath[mode])
    html_file = f"{mode}reportabove.html"
    prompt_ai = f""" Rank these article titles by relevance to {prompt} 
    Please talk over the the titles over which ones sound interesting.
    Some headlines will be irrelevant, those are easy to exclude.
    When you are done discussing the titles, put *** and then list the tope 3.
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["linux", "ai", "covid", "trump"])


    #main("linux")
    #main("ai")
    #main("trump")
    
