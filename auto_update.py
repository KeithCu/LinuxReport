#!/usr/bin/env python3
import os
import sys
from timeit import default_timer as timer
import re
import argparse
import importlib.util
import string
import datetime

from jinja2 import Template
from rapidfuzz import process, fuzz
from openai import OpenAI

from shared import TZ, Mode, MODE, g_c
from shared import DiskCacheWrapper, PATH

from auto_update_utils import custom_fetch_largest_image

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

MAX_PREVIOUS_HEADLINES = 30

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

def fetch_recent_articles():
    articles = []
    for url, _ in ALL_URLS.items():
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

def main(mode):
    global ALL_URLS

    module_path = f"{mode}_report_settings.py"

    if not os.path.isfile(module_path):
        raise FileNotFoundError(f"Module file not found: {module_path}")

    spec = importlib.util.spec_from_file_location("module_name", module_path)

    # Load the module
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    ALL_URLS = module.ALL_URLS

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

