from datetime import datetime, timedelta, timezone
import os
import pickle
import json
import re
import diskcache
from enum import Enum

import string
from timeit import default_timer as timer
from pathlib import Path
import threading
import time
from typing import Dict, List, Optional
import zoneinfo
from openai import OpenAI
from rapidfuzz import process, fuzz


from FeedHistory import FeedHistory

# Initialize Together AI client
client = OpenAI(
    api_key=os.environ.get("TOGETHER_API_KEY_LINUXREPORT"),
    base_url="https://api.together.xyz/v1",
)

TZ = zoneinfo.ZoneInfo("US/Eastern")

class RssFeed:
    def __init__(self, entries, top_articles=None):
        self.entries = entries
        self.top_articles = top_articles if top_articles else []
        self.__post_init__()

    def __post_init__(self):
        if not hasattr(self, 'top_articles'):
            object.__setattr__(self, 'top_articles', [])

    def __setstate__(self, state):
        object.__setattr__(self, '__dict__', state)
        self.__post_init__()


class RssInfo:
    def __init__(self, logo_url, logo_alt, site_url):
        self.logo_url = logo_url
        self.logo_alt = logo_alt
        self.site_url = site_url

PATH = '/run/linuxreport'


class Mode(Enum):
    LINUX_REPORT = 1
    COVID_REPORT = 2
    TECHNO_REPORT = 3
    AI_REPORT = 4
    PYTHON_REPORT = 5
    TRUMP_REPORT = 6

EXPIRE_MINUTES = 60 * 5
EXPIRE_HOUR = 3600
EXPIRE_DAY = 3600 * 12
EXPIRE_WEEK = 86400 * 7
EXPIRE_YEARS = 86400 * 365 * 2

MODE = Mode.LINUX_REPORT

history = FeedHistory(data_file = f"{PATH}/feed_history{str(MODE)}.pickle")


class DiskCacheWrapper:
    def __init__(self, cache_dir):
        self.cache = diskcache.Cache(cache_dir)

    def has(self, key):
        return key in self.cache

    def get(self, key):
        return self.cache.get(key)

    def put(self, key, value, timeout=None):
        self.cache.set(key, value, expire=timeout)

    def delete(self, key):
        self.cache.delete(key)

    def has_feed_expired(self, url):
        last_fetch = self.get(url + ":last_fetch")
        if last_fetch is None:
            return True
        return history.has_expired(url, last_fetch)

g_c = DiskCacheWrapper(PATH)

BANNED_WORDS = [
    "tmux",
    "redox",
]

modetoprompt2 = {
    Mode.LINUX_REPORT: f"""Arch Linux programmers and enthusiasts. Nothing about Ubuntu or any other
    distro. Of course anything non-distro-specific is fine, but nothing about the 
    following topics: {', '.join(BANNED_WORDS)}.\n""",
    Mode.AI_REPORT : "AI Language Model Researchers. Nothing about AI security.",
    Mode.COVID_REPORT : "COVID-19 researchers",
    Mode.TRUMP_REPORT : "Trump's biggest fans",
}

modetoprompt = {
    "linux": f"""Arch Linux programmers and enthusiasts. Nothing about Ubuntu or any other
    distro. Of course anything non-distro-specific is fine, but nothing about the 
    following topics: {', '.join(BANNED_WORDS)}.\n""",
    "ai": "AI Language Model Researchers. Nothing about AI security.",
    "covid": "COVID-19 researchers",
    "trump": "Trump's biggest fans",
}

PROMPT_AI = f""" Rank these article titles by relevance to {modetoprompt2[MODE]} 
    Please talk over the titles to decide which ones sound interesting.
    Some headlines will be irrelevant, those are easy to exclude.
    When you are done discussing the titles, put *** and then list the top 3.
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
