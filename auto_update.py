#!/usr/bin/env python3
import argparse
import datetime
import importlib.util
import os
import re
import sys
from timeit import default_timer as timer
import json

from jinja2 import Template

from auto_update_utils import custom_fetch_largest_image
from shared import (EXPIRE_DAY, EXPIRE_WEEK, MODE, TZ, DiskCacheWrapper, Mode,
                    g_c)

# --- Configuration and Prompt Constants ---

BANNED_WORDS = [
    "tmux",
    "redox",
    "java",
]

MAX_PREVIOUS_HEADLINES = 200

# Similarity threshold for deduplication
THRESHOLD = 0.75

# Model configuration with primary and fallback options
PRIMARY_MODEL  = "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"
FALLBACK_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
EMBEDDER_MODEL_NAME = 'all-MiniLM-L6-v2'

MODEL_CACHE_DURATION = EXPIRE_DAY * 7

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
    "ai": [7, 11, 15, 19, 23],
    "covid": [7, 11, 15, 19, 23],
    "trump": [0, 4, 8, 10, 12, 14, 16, 20],
}

modetoprompt2 = {
    Mode.LINUX_REPORT: f"""Arch and Debian Linux programmers and experienced users. Nothing about Ubuntu or any other
    distro. Anything non-distro-specific is fine, but nothing about the following topics:
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
    Do not select headlines that are very similar or nearly duplicates; pick only distinct headlines.
    When you are done discussing the titles, put *** and then list the top 3, using only the titles.
    """

# --- End Configuration and Prompt Constants ---

# --- Global Variables ---
openai_client = None
cache = DiskCacheWrapper(".")
ALL_URLS = {}
embedder = None  # Lazy initialization
st_util = None
headline_template = Template("""
<div class="linkclass">
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
</div>
<br/>
""")

# Initialize the https://together.ai/ client only if needed because it takes 2 seconds.
def get_openai_client():
    global openai_client
    if (openai_client is None):
        from openai import OpenAI
        openai_client = OpenAI(
            api_key=os.environ.get("TOGETHER_API_KEY_LINUXREPORT"),
            base_url="https://api.together.xyz/v1",
        )
    return openai_client

def get_current_model():
    """Get the current working model, with fallback mechanism."""
    # Check if we have a cached working model
    cached_model = g_c.get("working_llm_model")
    if cached_model:
        return cached_model
    
    # Default to PRIMARY_MODEL if no cached info
    return PRIMARY_MODEL

def update_model_cache(model):
    """Update the cache with the currently working model if it's different."""
    current_model = g_c.get("working_llm_model")
    if current_model == model:
        return
    g_c.put("working_llm_model", model, timeout=MODEL_CACHE_DURATION)

def _try_call_model(model, prompt, max_tokens):
    """Helper function to call a specific model and return its response."""
    start = timer()
    response = get_openai_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    end = timer()
    response_text = response.choices[0].message.content
    print(f"LLM Response with {model} in {end - start:.3f} seconds:")
    print(response_text)
    return response_text


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
    # Determine the first article that has an image to show one image only
    first_image_idx = None
    for idx, art in enumerate(top_articles[:3]):
        if art.get("image_url"):
            first_image_idx = idx
            break
    # Render HTML: only the first image is displayed
    html_parts = []
    for idx, art in enumerate(top_articles[:3]):
        rendered_html = headline_template.render(
            url=art["url"],
            title=art["title"],
            image_url=art.get("image_url") if idx == first_image_idx else None
        )
        html_parts.append(rendered_html)

    # Combine all headline HTML
    full_html = "\n".join(html_parts)

    # Step 3: Write to the output file
    output_dir = os.path.dirname(output_file)
    if (output_dir):
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

def get_embedding(text):
    global embedder, st_util
    if embedder is None:
        # Lazy initialization of SentenceTransformer since it takes 5 seconds.
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
            if score == 1.0:
                return best_match
            best_score = score
    return best_match

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

    # Get current model and implement fallback mechanism
    current_model = get_current_model()
    response_text = None
    
    try:
        # Try the current model first
        response_text = _try_call_model(current_model, prompt, 3000)
        
    except Exception as e:
        print(f"Error with model {current_model}: {str(e)}")        
        print(f"Primary model failed. Trying fallback model: {FALLBACK_MODEL}")
        try:
            response_text = _try_call_model(FALLBACK_MODEL, prompt, 3000)
            
            # Update the model cache to use the fallback model
            update_model_cache(FALLBACK_MODEL)
            
        except Exception as fallback_error:
            print(f"Fallback model also failed: {str(fallback_error)}")
            return "LLM models are currently unavailable."
    
    if response_text is None or response_text.startswith("LLM models are currently unavailable"):
        return "No response from LLM models."

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

def extract_articles_from_html(html_file):
    """Extract article URLs and titles from the HTML file."""
    if not os.path.exists(html_file):
        print(f"No existing HTML file found at {html_file}")
        return []
        
    # Read the existing file
    with open(html_file, "r", encoding="utf-8") as f:
        current_html = f.read()
    
    articles = []
    pattern = r'<a\s+[^>]*href="([^"]+)"[^>]*>\s*<font[^>]*>\s*<b[^>]*>([^<]+)</b>'
    matches = re.finditer(pattern, current_html)
    
    for match in matches:
        url, title = match.groups()
        articles.append({"url": url, "title": title})
    
    return articles

def refresh_images_only(mode):
    """Refresh only the images in the HTML file without changing the articles."""
    html_file = f"{mode}reportabove.html"
    
    # Extract the articles from the HTML
    articles = extract_articles_from_html(html_file)
    
    if not articles:
        print(f"No articles found in existing HTML file {html_file}")
        return False
    
    print(f"Found {len(articles)} articles in {html_file}, refreshing images...")
    
    # Now generate a new HTML with fresh images
    generate_headlines_html(articles, html_file)
    print(f"Successfully refreshed images in {html_file}")
    return True

MAX_ARCHIVE_HEADLINES = 50

def repair_archive_entries_if_needed(archive_file, old_entries):
    """One-time repair: fill in missing image_url fields in the loaded archive entries list."""
    repair_flag_key = f"archive_repair_done:{archive_file}"
    if g_c.get(repair_flag_key):
        return False  # Already repaired
    changed = False
    for entry in old_entries:
        if not entry.get("image_url"):
            url = entry["url"]
            cache_key = f"image_url:{url}"
            cached_img = g_c.get(cache_key)
            if cached_img:
                entry["image_url"] = cached_img
            else:
                img_url = custom_fetch_largest_image(url)
                entry["image_url"] = img_url
                if img_url:
                    g_c.put(cache_key, img_url, timeout=60*60*24*30)  # 30 days
            changed = True
    if changed:
        with open(archive_file, "w", encoding="utf-8") as f:
            for entry in old_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"Archive {archive_file} updated with missing images.")
    else:
        print(f"No missing images found in {archive_file}.")
    g_c.put(repair_flag_key, True, timeout=60*60*24*365)  # Mark as done for 1 year
    return changed

def append_to_archive(mode, top_articles):
    """Append the current top articles to the archive file with timestamp and image. Limit archive to MAX_ARCHIVE_HEADLINES."""
    archive_file = f"{mode}report_archive.jsonl"
    timestamp = datetime.datetime.now(TZ).isoformat()
    # Build entries directly from pre-fetched image URLs
    new_entries = []
    for article in top_articles[:3]:
        new_entries.append({
            "title": article["title"],
            "url": article["url"],
            "timestamp": timestamp,
            "image_url": article.get("image_url")
        })
    # Read old entries, append new, and trim to limit
    try:
        with open(archive_file, "r", encoding="utf-8") as f:
            old_entries = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        old_entries = []

    # One-time repair: fill in missing image_url fields in the loaded entries
    repair_archive_entries_if_needed(archive_file, old_entries)

    all_entries = new_entries + old_entries
    all_entries = all_entries[:MAX_ARCHIVE_HEADLINES]
    with open(archive_file, "w", encoding="utf-8") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# --- Integration into the main pipeline ---
def main(mode):
    global ALL_URLS

    module_path = f"{mode}_report_settings.py"
    if not os.path.isfile(module_path):
        raise FileNotFoundError(f"Module file not found: {module_path}")

    spec = importlib.util.spec_from_file_location("module_name", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ALL_URLS = module.CONFIG.ALL_URLS

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
            print(f"Best match for {title}: {best_match}")
            if best_match:
                top_3_articles.append(best_match)
        # Fetch largest images in-line for each headline
        for art in top_3_articles:
            art['image_url'] = custom_fetch_largest_image(
                art['url'], underlying_link=art.get('underlying_link'), html_content=art.get('html_content')
            )
        # Render HTML and archive with images
        generate_headlines_html(top_3_articles, html_file)
        append_to_archive(mode, top_3_articles)  # <-- Archive the headlines
    except Exception as e:
        print(f"Error in mode {mode}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate report with optional force update')
    parser.add_argument('--force', action='store_true', help='Force update regardless of schedule')
    parser.add_argument('--forceimage', action='store_true', help='Only refresh images in the HTML file')
    args = parser.parse_args()

    cwd = os.getcwd()
    for mode in MODE_TO_PATH.keys():
        if mode.lower() in cwd.lower():
            if args.forceimage:
                refresh_images_only(mode)
            else:
                hours = MODE_TO_SCHEDULE[mode]
                current_hour = datetime.datetime.now(TZ).hour
                if args.force or current_hour in hours:
                    main(mode)
            break
