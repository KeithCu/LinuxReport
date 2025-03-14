#!/usr/bin/env python3
import os
import sys
from timeit import default_timer as timer
import re
import argparse
import importlib.util
import datetime

from jinja2 import Template

from shared import TZ, Mode, MODE, g_c, DiskCacheWrapper, EXPIRE_WEEK
from auto_update_utils import custom_fetch_largest_image

MAX_PREVIOUS_HEADLINES = 200

# Similarity threshold for deduplication
THRESHOLD = 0.75

# Initialize Together AI client
openai_client = None
def get_openai_client():
    global openai_client
    if openai_client is None:
        from openai import OpenAI
        openai_client = OpenAI(
            api_key=os.environ.get("TOGETHER_API_KEY_LINUXREPORT"),
            base_url="https://api.together.xyz/v1",
        )
    return openai_client

MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"

BASE = "/srv/http/"

MODE_TO_PATH = {
    "linux": BASE + "LinuxReport2",
    "ai": BASE + "aireport",
    "covid": BASE + "CovidReport2",
    "trump": BASE + "trumpreport",
}

#Simple schedule for when to do updates. Service calls hourly
MODE_TO_SCHEDULE = {
    "linux": [0, 8, 12, 16, 20],
    "ai": [8, 16, 20],
    "covid": [8, 16, 20],
    "trump": [4, 8, 10, 12, 14, 16, 20, 23],
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


def extract_top_titles_from_ai(text):
    """Extracts top titles from AI-generated text after the first '***' marker."""
    marker_index = text.find('***')
    if (marker_index != -1):
        # Use the content after the first '***'
        text = text[marker_index + 3:]
    lines = text.splitlines()
    titles = []

    for line in lines:
        match = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if match:
            title = match.group(1).strip("*").strip()
            titles.append(title)
            if len(titles) == 3:
                break

    return titles


BANNED_WORDS = [
    "tmux",
    "redox",
]

modetoprompt2 = {
    Mode.LINUX_REPORT: f"""Arch Linux programmers and experienced users. Nothing about Ubuntu or any other
    distro. Of course anything non-distro-specific is fine, but nothing about the following topics:
    {', '.join(BANNED_WORDS)}.\n""",
    Mode.AI_REPORT : "AI Language Model and Robotic Researchers. Nothing about AI security.",
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

# Load the SentenceTransformer model once - lazy initialization variables
EMBEDDER_MODEL_NAME = 'all-MiniLM-L6-v2'
embedder = None  # Lazy initialization
st_util = None   # Lazy load for sentence_transformers.util

def get_embedding(text):
    global embedder, st_util
    if embedder is None:
        from sentence_transformers import SentenceTransformer, util
        embedder = SentenceTransformer(EMBEDDER_MODEL_NAME)
        st_util = util
    return embedder.encode(text, convert_to_tensor=True)

def deduplicate_articles_with_exclusions(articles, excluded_embeddings, threshold=THRESHOLD):
    """Deduplicate articles based on their embeddings, excluding similar ones."""
    unique_articles = []
    do_not_select_similar = excluded_embeddings.copy()  # Start with embeddings of previous selections

    for article in articles:
        title = article["title"]
        current_emb = get_embedding(title)  # Compute embedding for the article's title
        
        # Use lazy-loaded st_util for cosine similarity
        is_similar = any(st_util.cos_sim(current_emb, emb).item() >= threshold for emb in do_not_select_similar)
        
        if not is_similar:
            unique_articles.append(article)
            do_not_select_similar.append(current_emb)  # Add to the list to avoid similar articles later
        else:
            print(f"Filtered duplicate (embeddings): {title}")

    return unique_articles

def get_best_matching_article(target_title, articles):
    """Finds the article with the highest similarity score to the target title."""
    target_emb = get_embedding(target_title)
    best_match = None
    best_score = 0.0
    for article in articles:
        score = st_util.cos_sim(target_emb, get_embedding(article["title"])).item()
#        print (f"Score for {target_title} to {article['title']}: {score}")
        if score > best_score:
            best_match = article
            best_score = score
    return best_match

# --- Modified ask_ai_top_articles using embeddings for deduplication ---
def ask_ai_top_articles(articles):
    """Filters out articles whose headlines are semantically similar (using embeddings)
    Then, constructs the prompt and queries the AI ranking system.
    """
    previous_selections = g_c.get("previously_selected_selections_2")
    if previous_selections is None:
        previous_selections = []

    previous_embeddings = [get_embedding(sel["title"]) for sel in previous_selections]
    previous_urls = [sel["url"] for sel in previous_selections]

    articles = [article for article in articles if article["url"] not in previous_urls]

    filtered_articles = deduplicate_articles_with_exclusions(articles, previous_embeddings)

    if not filtered_articles:
        print("No new articles available after deduplication.")
        return "No new articles to rank."
    
    # Build the prompt for the AI ranking system.
    prompt = PROMPT_AI + "\n" + "\n".join(f"{i}. {article['title']}" for i, article in enumerate(filtered_articles, 1))
    print("Constructed Prompt:")
    print(prompt)

    start = timer()
    response = get_openai_client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=3000,
    )
    end = timer()
    print(f"LLM Response in {end - start:.3f} seconds:")
    response_text = response.choices[0].message.content
    print(response_text)

    top_titles = extract_top_titles_from_ai(response_text)
    top_articles = []
    for title in top_titles:
        best_match = get_best_matching_article(title, filtered_articles)
        if best_match:
            top_articles.append(best_match)

    # Update previous selections for future deduplication.
    new_selections = [{"url": art["url"], "title": art["title"]}
                      for art in top_articles if art]
    updated_selections = previous_selections + new_selections
    if len(updated_selections) > MAX_PREVIOUS_HEADLINES:
        updated_selections = updated_selections[-MAX_PREVIOUS_HEADLINES:]
    g_c.put("previously_selected_selections_2", updated_selections, timeout=EXPIRE_WEEK)

    return response_text

# --- Integration into the main pipeline ---
def main(mode):
    global ALL_URLS

    module_path = f"{mode}_report_settings.py"
    if not os.path.isfile(module_path):
        raise FileNotFoundError(f"Module file not found: {module_path}")

    spec = importlib.util.spec_from_file_location("module_name", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ALL_URLS = module.ALL_URLS

    html_file = f"{mode}reportabove.html"

    try:
        articles = fetch_recent_articles()
        if not articles:
            print(f"No articles found for mode: {mode}")
            sys.exit(1)

        full_response = ask_ai_top_articles(articles)
        top_3 = extract_top_titles_from_ai(full_response)
        top_3_articles = []
        for title in top_3:
            print (title)
            best_match = get_best_matching_article(title, articles)
            print (f"Best match for {title}: {best_match}")
            if best_match:
                top_3_articles.append(best_match)
        generate_headlines_html(top_3_articles, html_file)
    except Exception as e:
        print(f"Error in mode {mode}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate report with optional force update')
    parser.add_argument('--force', action='store_true', help='Force update regardless of schedule')
    args = parser.parse_args()

    cwd = os.getcwd()
    for mode in MODE_TO_PATH.keys():
        if mode.lower() in cwd.lower():
            hours = MODE_TO_SCHEDULE[mode]
            current_hour = datetime.datetime.now(TZ).hour
            if args.force or current_hour in hours:
                main(mode)
                break
