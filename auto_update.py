#!/usr/bin/env python3
import os
import sys
from openai import OpenAI
from pathlib import Path
import argparse
import importlib.util
import diskcache

from add_image import fetch_largest_image, save_as_webp, update_html_file
from shared import FeedHistory, RssFeed, TZ
import feedparser
from app import DiskCacheWrapper, PATH

# Initialize Together AI client
client = OpenAI(
    api_key=os.environ.get("TOGETHER_API_KEY_LINUXREPORT"),
    base_url="https://api.together.xyz/v1",
)

modetoprompt = {
    "linux": "Linux programmers and enthusiasts",
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

PATH = f"C:\\run\\linuxreport" #FIXME: TEMPORARY OVERRIDE

cache = DiskCacheWrapper(PATH)

dc = diskcache.Cache(".")

def disk_cache(expiration_seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}_{args}_{kwargs}"
            if cache_key in dc:
                try:
                    return dc[cache_key]
                except KeyError:
                    pass
            result = func(*args, **kwargs)
            dc.set(cache_key, result, expire=expiration_seconds)
            return result
        return wrapper
    return decorator

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
        for entry in feed.entries:  # Top 3 from each feed
            articles.append({"title": entry["title"], "url": entry["link"]})
            count += 1
            if count >= 3:
                break

    return articles

@disk_cache(86400*300)
def select_top_articles(articles, prompt, model):
    """Use Together AI's LLM to select the top 3 articles based on the prompt."""
    prompt_full = prompt + "\n" + "\n".join(f"{i}. {article['title']}" for i, article in enumerate(articles, 1))
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt_full}],
        max_tokens=100,
    )

    print(response.choices[0].message.content)
    return response.choices[0].message.content


def main(mode):
    global ALL_URLS
    prompt = modetoprompt[mode]

    # FIXME: TEMPORARY OVERRIDE
    module_path = f"C:\\users\\keith\\OneDrive\\Desktop\\LinuxReport2\\LinuxReport\\{mode}_report_settings.py"

    # module = __import__(module_path)

    # Check if the file exists (optional but recommended)
    if not os.path.isfile(module_path):
        raise FileNotFoundError(f"Module file not found: {module_path}")

    # Create a module specification from the file path
    spec = importlib.util.spec_from_file_location("module_name", module_path)

    # Load the module
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    ALL_URLS = module.ALL_URLS

    base_path = PATH
    mode_dir = os.path.join(base_path, modetopath[mode])
    html_file = os.path.join(mode_dir, "reportabove.html")
    prompt = f"Rank these article titles by relevance to {prompt} (Feel free to talk the titles over which ones sound interesting and when you have decided then list the top 3 as 1. 2. 3."
    model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"

    try:
        articles = fetch_recent_articles()
        if not articles:
            print(f"No articles found for mode: {mode}")
            sys.exit(1)

        full_response = select_top_articles(articles, prompt, model)

        lines = full_response.split('\n')
        #top_articles = [line.strip() for line in lines if line.strip().startswith(('1.', '2.', '3.'))]
        #
        # Update the HTML file with selected articles and images
        for article in selected_articles:
            image_content = fetch_largest_image(article["url"])
            image_filename = save_as_webp(image_content)
            update_html_file(html_file, article["title"], image_filename, article["url"])
            print(f"Updated {html_file} with {article['title']}")
    except Exception as e:
        print(f"Error in mode {mode}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["linux", "ai", "covid", "trump"])
    
    # Simulate command line input
    args = parser.parse_args(['--mode', 'trump'])  # Pass simulated args as list
    main(args.mode)
