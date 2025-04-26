#!/usr/bin/env python3
import argparse
import datetime
import importlib.util
import os
import re
import sys
from timeit import default_timer as timer
import json
import traceback
import time

from image_parser import custom_fetch_largest_image
from article_deduplication import (
    fetch_recent_articles, get_embedding, deduplicate_articles_with_exclusions,
    get_best_matching_article
)
from html_generation import (
    generate_headlines_html, refresh_images_only
)

from shared import (EXPIRE_DAY, EXPIRE_WEEK, MODE, TZ, Mode, g_c)

# --- Configuration and Prompt Constants ---
MAX_PREVIOUS_HEADLINES = 200

# How many articles from each feed to consider for the LLM
MAX_ARTICLES_PER_FEED_FOR_LLM = 5

# Provider configurations
PROVIDER_CONFIGS = {
    "together": {
        "api_key_env_var": "TOGETHER_API_KEY_LINUXREPORT",
        "base_url": "https://api.together.xyz/v1",
        "models": {
            "primary": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
            "fallback": "meta-llama/Llama-3.3-70B-Instruct-Turbo"
        }
    },
    "openrouter": {
        "api_key_env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "models": {
            "primary": "meta-llama/llama-3.3-70b-instruct:free",
            "fallback": "meta-llama/llama-3.3-70b-instruct:floor",
            "primary_compare": "x-ai/grok-3-mini-beta",
            "fallback_compare": "google/gemini-2.5-flash-preview"

        },
        "headers": {
            "HTTP-Referer": "https://linuxreport.net",
            "X-Title": "LinuxReport"
        }
    }
}

# Default to Together AI's primary model
PRIMARY_MODEL = PROVIDER_CONFIGS["together"]["models"]["primary"]
FALLBACK_MODEL = PROVIDER_CONFIGS["together"]["models"]["fallback"]

MODEL_CACHE_DURATION = EXPIRE_DAY * 7

# === Global LLM/AI config ===
MAX_TOKENS = 5000
TIMEOUT = 60

BASE = "/srv/http/"

MODE_TO_PATH = {
    "linux": BASE + "LinuxReport2",
    "ai": BASE + "aireport",
    "covid": BASE + "CovidReport2",
    "trump": BASE + "trumpreport",
    "solar": BASE + "pvreport",
}

#Simple schedule for when to do updates. Service calls hourly
MODE_TO_SCHEDULE = {
    "linux": [0, 8, 12, 16, 20],
    "ai": [7, 11, 15, 19, 23],
    "covid": [7, 11, 15, 19, 23],
    "trump": [0, 4, 8, 10, 12, 14, 16, 20],
    "solar": [6, 12, 18],
}

BANNED_WORDS = [
    "tmux",
    "redox",
    "java",
    "javascript",
    "mysql (mariadb is ok)",
]

modetoprompt2 = {
    Mode.LINUX_REPORT: f"""Arch and Debian Linux programmers and experienced users.
    Prefer major news especially about important codebases. 
    Avoid simple tutorials, error explanations, troubleshooting guides, or cheat sheets.
    Nothing about Ubuntu or any other distro. Anything non-distro-specific is fine, but nothing about 
    the following products:
    {', '.join(BANNED_WORDS)}.\n""",
    Mode.AI_REPORT : "AI Language Model and Robotic Researchers. Nothing about AI security.",
    Mode.COVID_REPORT : "COVID-19 researchers",
    Mode.TRUMP_REPORT : "Trump's biggest fans",
    Mode.SOLAR_REPORT: "Solar energy industry professionals and enthusiasts. Focus on major solar and battery technology, policy, and market news. Avoid basic installation guides, generic green energy content, or unrelated renewables."
}

modetoprompt = {
    "linux": modetoprompt2[Mode.LINUX_REPORT],
    "ai": modetoprompt2[Mode.AI_REPORT],
    "covid": modetoprompt2[Mode.COVID_REPORT],
    "trump": modetoprompt2[Mode.TRUMP_REPORT],
    "solar": modetoprompt2[Mode.SOLAR_REPORT],
}

PROMPT_AI = f""" Rank these article titles by relevance to {modetoprompt2[MODE]}
    Please talk over the titles to decide which ones sound interesting.
    Some headlines will be irrelevant, those are easy to exclude.
    Do not select headlines that are very similar or nearly duplicates; pick only distinct headlines/topics.
    When you are done discussing the titles, put *** and then list the top 3, using only the titles.
    """


#O3-suggested alternate prompt for reasoning models
PROMPT_O3_SYSTEM = """
FORMAT:
1. Exactly ONE paragraph (<= 40 words) explaining your choice.
2. *** on its own line.
3. Best headline.
4. Second headline.
5. Third headline.
No other text.
"""

PROMPT_O3_USER_TEMPLATE = """
<scratchpad>
Think step-by-step, de-duplicate, choose three best. Some headlines are irrelevant—discard them.
</scratchpad>

Find the top 3 articles most interesting to:
{mode_instructions}


INPUT TITLES:
"""


# --- Global Variables ---
cache = g_c

ALL_URLS = {} # Initialized here, passed to utils

# --- Global Configuration (Replaces Environment Variables except API Keys) ---
RUN_MODE = "normal"  # options: "normal", "compare"

# Configuration for the primary provider/model
CHAT_PROVIDER_1 = "openrouter"  # options: "together", "openrouter"
PROMPT_MODE_1 = "default"     # options: "default", "o3"
MODEL_1 = None

# Configuration for the secondary provider/model (for comparison mode)
CHAT_PROVIDER_2 = "openrouter" # options: "together", "openrouter"
PROMPT_MODE_2 = "default"      # options: "default", "o3"
MODEL_2 = PROVIDER_CONFIGS["openrouter"]["models"]["primary"] # Model for provider 2

# Add unified provider client cache (for normal mode)
provider_client_cache = None

# Optional: include more article data (summary, etc) in LLM prompt
INCLUDE_ARTICLE_SUMMARY_FOR_LLM = False

# Helper: Map model name to provider info
def get_provider_info_from_model(model_name):
    """Get provider configuration based on model name or provider name."""
    # First try to find provider by model name
    for provider, config in PROVIDER_CONFIGS.items():
        if any(model_name == model for model in config["models"].values()):
            return {
                "provider": provider,
                "api_key_env_var": config["api_key_env_var"],
                "base_url": config["base_url"]
            }
    
    # If not found by model name, try by provider name
    if model_name in PROVIDER_CONFIGS:
        config = PROVIDER_CONFIGS[model_name]
        return {
            "provider": model_name,
            "api_key_env_var": config["api_key_env_var"],
            "base_url": config["base_url"]
        }
    
    # Default to Together AI if no match found
    return {
        "provider": "together",
        "api_key_env_var": PROVIDER_CONFIGS["together"]["api_key_env_var"],
        "base_url": PROVIDER_CONFIGS["together"]["base_url"]
    }

def get_current_model():
    """Get the current working model, with fallback mechanism."""
    # Check if we have a cached working model
    cached_model = g_c.get("working_llm_model")
    if cached_model:
        return cached_model
    
    # Get the current provider's primary model
    provider_config = PROVIDER_CONFIGS.get(CHAT_PROVIDER_1, PROVIDER_CONFIGS["together"])
    return provider_config["models"]["primary"]

def update_model_cache(model):
    """Update the cache with the currently working model if it's different."""
    current_model = g_c.get("working_llm_model")
    if current_model == model:
        return
    g_c.put("working_llm_model", model, timeout=MODEL_CACHE_DURATION)

def get_provider_client(model=None, use_cache=True):
    """Get a client for the specified model or provider."""
    global provider_client_cache
    
    if model is None:
        model = get_current_model()
    
    info = get_provider_info_from_model(model)
    from openai import OpenAI
    
    # Get API key from environment
    api_key = os.environ.get(info["api_key_env_var"])
    if not api_key:
        raise ValueError(f"API key {info['api_key_env_var']} not set for provider {info['provider']}")
    
    # If using cache and we have a cached client for this provider
    if use_cache and provider_client_cache is not None:
        return provider_client_cache
    
    # Create new client with provider-specific configuration
    client = OpenAI(
        api_key=api_key,
        base_url=info["base_url"]
    )
    
    # Add OpenRouter-specific headers if needed
    if info["provider"] == "openrouter" and "headers" in PROVIDER_CONFIGS["openrouter"]:
        for header, value in PROVIDER_CONFIGS["openrouter"]["headers"].items():
            client._client.headers[header] = value
        print(f"[OpenRouter] Using headers: {PROVIDER_CONFIGS['openrouter']['headers']}")
    
    print(f"[get_provider_client] Provider: {info['provider']}, Model: {model}, Base URL: {info['base_url']}")
    
    # Cache the client if requested
    if use_cache:
        provider_client_cache = client
    
    return client

def _try_call_model(client, model, messages, max_tokens, provider_label=""):
    """Helper to call a model with retry logic, timeout, and logging."""
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        start = timer()
        print(f"[_try_call_model] Attempt {attempt}/{max_retries} for model: {model} ({provider_label})")
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                timeout=TIMEOUT
            )
            end = timer()
            choice = response.choices[0]
            response_text = choice.message.content
            finish_reason = choice.finish_reason
            print(f"[_try_call_model] Response from {provider_label} ({model}) in {end - start:.3f}s, finish_reason: {finish_reason}")
            if finish_reason != "stop":
                print(f"Warning: Response finish_reason is {finish_reason}")
            print(f"[_try_call_model] Model response (Attempt {attempt}):\n{response_text}\n{'-'*40}")
            return response_text
        except Exception as e:
            print(f"Error on attempt {attempt} for model {model} ({provider_label}): {e}")
            traceback.print_exc()
            if attempt < max_retries:
                time.sleep(1)
    raise RuntimeError(f"Model call failed after {max_retries} attempts for model {model} ({provider_label})")

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


def _prepare_messages(prompt_mode, filtered_articles):
    """Prepares the message list based on the prompt mode."""
    if INCLUDE_ARTICLE_SUMMARY_FOR_LLM:
        def article_line(i, article):
            summary = article.get('summary') or article.get('html_content') or ''
            if summary:
                return f"{i}. {article['title']}\n    Summary: {summary.strip()}"
            else:
                return f"{i}. {article['title']}"
    else:
        def article_line(i, article):
            return f"{i}. {article['title']}"

    if prompt_mode == "o3":
        user_list = "\n".join(article_line(i, article) for i, article in enumerate(filtered_articles, 1))
        messages = [
            {"role": "system", "content": PROMPT_O3_SYSTEM},
            {"role": "user",   "content": PROMPT_O3_USER_TEMPLATE.format(mode_instructions=modetoprompt2[MODE]) + user_list},
        ]
    else: # Default mode
        prompt = PROMPT_AI + "\n" + "\n".join(article_line(i, article) for i, article in enumerate(filtered_articles, 1))
        messages = [{"role": "user", "content": prompt}]
    return messages


def ask_ai_top_articles(articles):
    """Filters articles, constructs prompt, queries the primary AI, handles fallback (if applicable)."""
    # --- Deduplication (remains the same) ---
    previous_selections = g_c.get("previously_selected_selections_2")
    if previous_selections is None:
        previous_selections = []

    previous_embeddings = [get_embedding(sel["title"]) for sel in previous_selections]
    previous_urls = [sel["url"] for sel in previous_selections]

    articles = [article for article in articles if article["url"] not in previous_urls]
    # Pass threshold to deduplicate function
    filtered_articles = deduplicate_articles_with_exclusions(articles, previous_embeddings)

    if not filtered_articles:
        print("No new articles available after deduplication.")
        return "No new articles to rank.", [], previous_selections

    # --- Prepare Messages ---
    messages = _prepare_messages(PROMPT_MODE_1, filtered_articles)
    print(f"Constructed Prompt (Mode: {PROMPT_MODE_1}):")
    print(messages)

    # --- Call Primary LLM ---
    current_provider = CHAT_PROVIDER_1
    current_model = get_current_model()
    provider_config = PROVIDER_CONFIGS[current_provider]
    response_text = None

    try:
        # Only use models for the selected provider
        provider_config = PROVIDER_CONFIGS[CHAT_PROVIDER_1]
        current_model = provider_config["models"]["primary"]
        primary_client = get_provider_client(model=current_model, use_cache=True)
        response_text = _try_call_model(primary_client, current_model, messages, MAX_TOKENS, f"Primary ({CHAT_PROVIDER_1})")
        update_model_cache(current_model)
    except Exception as e:
        print(f"Error with model {current_model} ({CHAT_PROVIDER_1}): {e}")
        traceback.print_exc()
        # Try fallback model for the same provider only
        try:
            fallback_model = provider_config["models"]["fallback"]
            fallback_client = get_provider_client(model=fallback_model, use_cache=False)
            print(f"Trying fallback model: {fallback_model}")
            response_text = _try_call_model(fallback_client, fallback_model, messages, MAX_TOKENS, f"Fallback ({CHAT_PROVIDER_1})")
            update_model_cache(fallback_model)
        except Exception as fallback_e:
            print(f"Fallback model {fallback_model} also failed: {fallback_e}")
            traceback.print_exc()
            return "LLM models failed due to error (all models for selected provider).", filtered_articles, previous_selections

    if not response_text or response_text.startswith("LLM models are currently unavailable"):
        return "No response from LLM models.", filtered_articles, previous_selections

    # --- Process Response and Update Selections (remains the same) ---
    top_titles = extract_top_titles_from_ai(response_text)
    top_articles = []
    for title in top_titles:
        best_match = get_best_matching_article(title, filtered_articles)
        if (best_match):
            top_articles.append(best_match)

    new_selections = [{"url": art["url"], "title": art["title"]}
                      for art in top_articles if art]
    updated_selections = previous_selections + new_selections
    if len(updated_selections) > MAX_PREVIOUS_HEADLINES:
        updated_selections = updated_selections[-MAX_PREVIOUS_HEADLINES:]

    return response_text, top_articles, updated_selections


def run_comparison(articles):
    """Runs two LLM calls with different configurations for comparison."""
    print("\n--- Running Comparison Mode ---")

    # --- Deduplication (same as ask_ai_top_articles) ---
    previous_selections = g_c.get("previously_selected_selections_2") or []
    previous_embeddings = [get_embedding(sel["title"]) for sel in previous_selections]
    previous_urls = [sel["url"] for sel in previous_selections]
    articles = [article for article in articles if article["url"] not in previous_urls]
    filtered_articles = deduplicate_articles_with_exclusions(articles, previous_embeddings)

    if not filtered_articles:
        print("No new articles available after deduplication for comparison.")
        return

    # --- Config 1 ---
    print("\n--- Configuration 1 ---")
    print(f"Provider: {CHAT_PROVIDER_1}, Model: {MODEL_1}, Prompt Mode: {PROMPT_MODE_1}")
    messages1 = _prepare_messages(PROMPT_MODE_1, filtered_articles)
    print("Messages 1:")
    # Corrected get_provider_client call: infer provider from model name
    try:
        client1 = get_provider_client(model=MODEL_1, use_cache=False) # Use renamed parameter
        _try_call_model(client1, MODEL_1, messages1, MAX_TOKENS, f"Comparison ({CHAT_PROVIDER_1})")
    except Exception as e: # Keep general
        print(f"Error during Comparison Call 1 ({CHAT_PROVIDER_1} / {MODEL_1}): {e}")


    # --- Config 2 ---
    print("\n--- Configuration 2 ---")
    print(f"Provider: {CHAT_PROVIDER_2}, Model: {MODEL_2}, Prompt Mode: {PROMPT_MODE_2}")
    messages2 = _prepare_messages(PROMPT_MODE_2, filtered_articles)
    print("Messages 2:")
    # Corrected get_provider_client call: infer provider from model name
    try:
        client2 = get_provider_client(model=MODEL_2, use_cache=False) # Use renamed parameter
        _try_call_model(client2, MODEL_2, messages2, MAX_TOKENS, f"Comparison ({CHAT_PROVIDER_2})")
    except Exception as e: # Keep general
        print(f"Error during Comparison Call 2 ({CHAT_PROVIDER_2} / {MODEL_2}): {e}")

    print("\n--- Comparison Mode Finished ---")


MAX_ARCHIVE_HEADLINES = 50

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

    all_entries = new_entries + old_entries
    all_entries = all_entries[:MAX_ARCHIVE_HEADLINES]
    with open(archive_file, "w", encoding="utf-8") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# --- Integration into the main pipeline ---
def main(mode, dry_run=False): # Add dry_run parameter
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
        # Pass ALL_URLS and cache to fetch_recent_articles
        articles = fetch_recent_articles(ALL_URLS, cache)
        if not articles:
            print(f"No articles found for mode: {mode}")
            sys.exit(1) # Keep exit for no articles

        # --- Handle Run Modes ---
        if RUN_MODE == "compare":
            run_comparison(articles)
            # Comparison mode implies dry-run, so we exit here
            print("Exiting after comparison run.")
            sys.exit(0)
        elif RUN_MODE == "normal":
            full_response, top_3_articles_match, updated_selections = ask_ai_top_articles(articles)

            # Check if AI call failed or returned no usable response
            if not top_3_articles_match and not full_response.startswith("No new articles"):
                print(f"AI processing failed or returned no headlines: {full_response}")
                # Decide if we should exit or continue without update
                sys.exit(1) # Exit if AI failed critically

            print("\n--- Extracted Top Titles (from AI response) ---")
            # Extract again here just for printing in dry-run or normal mode
            top_titles_print = extract_top_titles_from_ai(full_response)
            for title in top_titles_print:
                print(title)
            print("--- Matched Articles (used for update) ---")
            for art in top_3_articles_match:
                print(f"- {art['title']} ({art['url']})")


            if dry_run:
                print("\n--- Dry Run Mode: Skipping file generation and archive update. ---")
                sys.exit(0) # Exit after dry run

            # --- Normal Run: Generate HTML and Archive ---
            if not top_3_articles_match:
                print("No top articles identified by AI. Skipping update.")
                sys.exit(0) # Exit gracefully if AI didn't pick articles

            # Fetch largest images in-line for each headline
            print("\nFetching images for top articles...")
            for art in top_3_articles_match:
                art['image_url'] = custom_fetch_largest_image(
                    art['url'], underlying_link=art.get('underlying_link'), html_content=art.get('html_content')
                )
            # Render HTML and archive with images
            print(f"Generating HTML file: {html_file}")
            # Pass headline_template to generate_headlines_html
            generate_headlines_html(top_3_articles_match, html_file)
            print(f"Appending to archive for mode: {mode}")
            append_to_archive(mode, top_3_articles_match)
            # Update selections cache only on successful normal run completion
            g_c.put("previously_selected_selections_2", updated_selections, timeout=EXPIRE_WEEK)
            print("Successfully updated headlines and archive.")

        else:
            print(f"Unknown RUN_MODE: {RUN_MODE}. Exiting.")
            sys.exit(1)

    except FileNotFoundError as e: # Specific error
        print(f"Configuration file error for mode {mode}: {e}")
        sys.exit(1)
    except ImportError as e: # Specific error
        print(f"Error importing settings for mode {mode}: {e}")
        sys.exit(1)
    except Exception as e: # Keep general for other unexpected errors during main execution
        print(f"Error in mode {mode}: {e}")
        traceback.print_exc() # Print traceback for debugging
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate report with optional force update')
    parser.add_argument('--force', action='store_true', help='Force update regardless of schedule')
    parser.add_argument('--forceimage', action='store_true', help='Only refresh images in the HTML file')
    parser.add_argument('--dry-run', action='store_true', help='Run AI analysis but do not update files')
    parser.add_argument('--provider', choices=['together','openrouter'], default='openrouter', help='Primary chat provider: together or openrouter')
    parser.add_argument('--compare', action='store_true', help='Run in comparison mode (compare two providers/models)')
    parser.add_argument('--include-summary', action='store_true', help='Include article summary/html_content in LLM prompt')
    args = parser.parse_args()

    # Configure primary provider from CLI
    CHAT_PROVIDER_1 = args.provider
    # Set MODEL_1 dynamically based on selected provider
    MODEL_1 = PROVIDER_CONFIGS[CHAT_PROVIDER_1]["models"]["primary"]

    # Set MODEL_2 dynamically to fallback model for selected provider (for comparison mode)
    MODEL_2 = PROVIDER_CONFIGS[CHAT_PROVIDER_1]["models"].get("fallback", MODEL_1)

    # Set RUN_MODE to 'compare' if --compare is specified
    if args.compare:
        RUN_MODE = "compare"
        # In compare mode, use openrouter for both, but with dedicated comparison models
        CHAT_PROVIDER_1 = "openrouter"
        MODEL_1 = PROVIDER_CONFIGS["openrouter"]["models"]["primary_compare"]
        CHAT_PROVIDER_2 = "openrouter"
        MODEL_2 = PROVIDER_CONFIGS["openrouter"]["models"]["fallback_compare"]

    # Set INCLUDE_ARTICLE_SUMMARY_FOR_LLM from CLI flag
    if args.include_summary:
        INCLUDE_ARTICLE_SUMMARY_FOR_LLM = True

    cwd = os.getcwd()
    for mode_key in MODE_TO_PATH.keys(): # Use mode_key to avoid conflict
        if mode_key.lower() in cwd.lower():
            if args.forceimage:
                refresh_images_only(mode_key)
            else:
                hours = MODE_TO_SCHEDULE[mode_key]
                current_hour = datetime.datetime.now(TZ).hour
                if args.force or current_hour in hours or args.dry_run or RUN_MODE == "compare": # Ensure dry-run/compare always run if specified
                    main(mode_key, dry_run=args.dry_run) # Pass dry_run flag
            break

