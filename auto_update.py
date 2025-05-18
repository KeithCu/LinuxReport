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
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
import enum  # New import for Enum

from image_parser import custom_fetch_largest_image
from article_deduplication import (
    fetch_recent_articles, get_embedding, deduplicate_articles_with_exclusions,
    get_best_matching_article
)
from html_generation import (
    generate_headlines_html, refresh_images_only
)

from shared import (EXPIRE_DAY, EXPIRE_WEEK, TZ, Mode, g_c)

from enum import Enum  # Ensure this is included if not already

class PromptMode(Enum):
    DEFAULT = 'default'
    O3 = 'o3'
    THIRTY_B = '30b'  # Represents '30b' prompt

# --- Configuration and Prompt Constants ---
MAX_PREVIOUS_HEADLINES = 200 # Number of headlines to remember and filter out to the AI

MAX_ARCHIVE_HEADLINES = 50 # Size of Headlines Archive page


# Title marker used to separate reasoning from selected headlines
TITLE_MARKER = "***"

# How many articles from each feed to consider for the LLM
MAX_ARTICLES_PER_FEED_FOR_LLM = 5

# === Global LLM/AI config ===
MAX_TOKENS = 5000
TIMEOUT = 60
MODEL_CACHE_DURATION = EXPIRE_DAY * 7

PROMPT_AI = f""" Rank these article titles by relevance to {{mode_instructions}}
    Please talk over the titles to decide which ones sound interesting.
    Some headlines will be irrelevant, those are easy to exclude.
    Do not select top 3 headlines that are similar; pick only distinct headlines/topics.
    When you are done discussing the titles, put {TITLE_MARKER} and then list the top 3, using only the titles.
    """


PROMPT_30B = f""" Prompt:
Given a list of news headlines, follow these steps:
Identify headlines relevant to {{mode_instructions}}. Exclude irrelevant ones.
Think carefully and consisely about relevance, interest, and topic distinction without repeating entire headlines in your reasoning.
From relevant headlines, pick the top 3 most interesting, each covering a completely distinct topic. Ensure they have no similarity in topics.
After reasoning, output {TITLE_MARKER} followed by only the top 3 headlines in this format, with no extra text:
1. [Title 1]
2. [Title 2]
3. [Title 3]
"""

#O3-suggested alternate prompt for reasoning models
PROMPT_O3_SYSTEM = """
FORMAT:
1. Exactly ONE paragraph (<= 40 words) explaining your choice.
2. {TITLE_MARKER} on its own line.
3. Best headline.
4. Second headline.
5. Third headline.
No other text.
""".format(TITLE_MARKER=TITLE_MARKER)

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

PROVIDER = "openrouter"

PROMPT_MODE = PromptMode.DEFAULT  # Default Enum instance

# Configuration for the primary provider/model
MODEL_1 = None

# Configuration for the secondary provider/model (for comparison mode)
MODEL_2 = None  # Will be set based on provider

MISTRAL_EXTRA_PARAMS = {
    "provider": {
        "order": ["Mistral"], # Try to send the request to Mistral first
        "allow_fallbacks": True
    }
}

# Add unified provider client cache (for normal mode)
provider_client_cache = None

# Optional: include more article data (summary, etc) in LLM prompt
INCLUDE_ARTICLE_SUMMARY_FOR_LLM = False


# Provider class hierarchy
class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, name: str):
        self.name = name
        self._client = None
    
    @property
    @abstractmethod
    def api_key_env_var(self) -> str:
        """Get the environment variable name for the API key."""
        pass
    
    @property
    @abstractmethod
    def base_url(self) -> str:
        """Get the base URL for the API."""
        pass
    
    @property
    @abstractmethod
    def primary_model(self) -> str:
        """Get the primary model name."""
        pass
    
    @property
    @abstractmethod
    def fallback_model(self) -> str:
        """Get the fallback model name."""
        pass
    
    def get_comparison_models(self) -> Tuple[str, str]:
        """Get models for comparison mode (default to primary/fallback)."""
        return self.primary_model, self.fallback_model
    
    def get_api_key(self) -> str:
        """Get the API key from environment variables."""
        api_key = os.environ.get(self.api_key_env_var)
        if not api_key:
            raise ValueError(f"API key {self.api_key_env_var} not set for provider {self.name}")
        return api_key
    
    def get_client(self, use_cache: bool = True):
        """Get an API client for this provider."""
        global provider_client_cache
        
        # Use cached client if available and requested
        if use_cache and provider_client_cache is not None:
            return provider_client_cache
        
        # Import here to avoid circular imports
        from openai import OpenAI
        
        # Create new client
        client = OpenAI(
            api_key=self.get_api_key(),
            base_url=self.base_url
        )
        
        # Apply any provider-specific configuration
        self._configure_client(client)
        
        # Cache the client if requested
        if use_cache:
            provider_client_cache = client
        
        return client
    
    def _configure_client(self, client):
        """Configure the client with provider-specific settings."""
        pass  # Default implementation does nothing
    
    def call_model(self, model: str, messages: List[Dict[str, str]], max_tokens: int, label: str = "") -> str:
        """Call the model with retry logic, timeout, and logging."""
        client = self.get_client(use_cache=False)
        return _try_call_model(client, model, messages, max_tokens)
    
    def call_with_fallback(self, messages: List[Dict[str, str]], prompt_mode: str, label: str = "") -> Tuple[Optional[str], Optional[str]]:
        """Call the primary model with fallback to secondary if needed."""
        # Try primary model
        primary_model = self.primary_model
        print(f"\n--- LLM Call: {self.name} / {primary_model} / {prompt_mode} {label} ---")
        
        try:
            response_text = self.call_model(primary_model, messages, MAX_TOKENS, f"{label}")
            return response_text, primary_model
        except Exception as e:
            print(f"Error with model {primary_model} ({self.name}): {e}")
            traceback.print_exc()
            
            # Try fallback model
            try:
                fallback_model = self.fallback_model
                print(f"Trying fallback model: {fallback_model}")
                response_text = self.call_model(fallback_model, messages, MAX_TOKENS, f"Fallback {label}")
                return response_text, fallback_model
            except Exception as fallback_e:
                print(f"Fallback model {fallback_model} also failed: {fallback_e}")
                traceback.print_exc()
        
        return None, None
    
    def __str__(self) -> str:
        return f"{self.name} Provider (primary: {self.primary_model}, fallback: {self.fallback_model})"


class OpenRouterProvider(LLMProvider):
    """Provider implementation for OpenRouter."""
    
    def __init__(self):
        super().__init__("openrouter")
    
    @property
    def api_key_env_var(self) -> str:
        return "OPENROUTER_API_KEY"
    
    @property
    def base_url(self) -> str:
        return "https://openrouter.ai/api/v1"
    
    @property
    def primary_model(self) -> str:
        return "meta-llama/llama-3.3-70b-instruct:free"
    
    @property
    def fallback_model(self) -> str:
        return "meta-llama/llama-3.3-70b-instruct:floor"
    
    def get_comparison_models(self) -> Tuple[str, str]:
        """Get models specific for comparison mode."""
        return "google/gemma-3-27b-it", "mistralai/mistral-small-3.1-24b-instruct"
    
    def _configure_client(self, client):
        """Add OpenRouter-specific headers."""
        headers = {
            "HTTP-Referer": "https://linuxreport.net",
            "X-Title": "LinuxReport"
        }
        for header, value in headers.items():
            client._client.headers[header] = value
        print(f"[OpenRouter] Using headers: {headers}")


# Provider registry
PROVIDERS = {
    "openrouter": OpenRouterProvider()
}

# Helper function to get provider
def get_provider(name: str) -> LLMProvider:
    """Get a provider by name."""
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider: {name}")
    return PROVIDERS[name]

def get_current_model():
    """Get the current working model, with fallback mechanism."""
    # Check if we have a cached working model
    cached_model = g_c.get("working_llm_model")
    if cached_model:
        return cached_model
    
    # Get the current provider's primary model
    return get_provider(PROVIDER)

def update_model_cache(model):
    """Update the cache with the currently working model if it's different."""
    current_model = g_c.get("working_llm_model")
    if current_model == model:
        return
    g_c.put("working_llm_model", model, timeout=MODEL_CACHE_DURATION)

def _try_call_model(client, model, messages, max_tokens):
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        start = timer()
        print(f"[_try_call_model] Attempt {attempt}/{max_retries} for model: {model}")
        try:
            if 'mistral' in model.lower():
                extra_params = MISTRAL_EXTRA_PARAMS
            else:
                extra_params = {}
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                timeout=TIMEOUT,
                extra_body=extra_params
            )
            end = timer()
            choice = response.choices[0]
            response_text = choice.message.content
            finish_reason = choice.finish_reason
            print(f"[_try_call_model] Response in {end - start:.3f}s, finish_reason: {finish_reason}")
            print(f"[_try_call_model] Model response (Attempt {attempt}):\n{response_text}\n{'-'*40}")
            return response_text
        except Exception as e:
            print(f"Error on attempt {attempt} for model {model}: {e}")
            traceback.print_exc()
            if attempt < max_retries:
                time.sleep(1)
    raise RuntimeError(f"Model call failed after {max_retries} attempts for model {model}")

def extract_top_titles_from_ai(text):
    """Extracts top titles from AI-generated text after the first '{TITLE_MARKER}' marker."""
    marker_index = text.find(TITLE_MARKER)
    if (marker_index != -1):
        # Use the content after the first '{TITLE_MARKER}'
        text = text[marker_index + len(TITLE_MARKER):]
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

    # Get the mode instructions from the global REPORT_PROMPT
    mode_instructions = REPORT_PROMPT

    if prompt_mode == PromptMode.O3:
        user_list = "\n".join(article_line(i, article) for i, article in enumerate(filtered_articles, 1))
        messages = [
            {"role": "system", "content": PROMPT_O3_SYSTEM},
            {"role": "user",   "content": PROMPT_O3_USER_TEMPLATE.format(mode_instructions=mode_instructions) + user_list},
        ]
    elif prompt_mode == PromptMode.THIRTY_B:
        mode_instructions = REPORT_PROMPT
        user_list = "\n".join(article_line(i, article) for i, article in enumerate(filtered_articles, 1))
        messages = [
            {"role": "user", "content": PROMPT_30B.format(mode_instructions=mode_instructions) + "\n" + user_list}
        ]
    else: # Default mode
        prompt = PROMPT_AI.format(mode_instructions=mode_instructions) + "\n" + "\n".join(article_line(i, article) for i, article in enumerate(filtered_articles, 1))
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
    messages = _prepare_messages(PROMPT_MODE, filtered_articles)
    print(f"Constructed Prompt (Mode: {PROMPT_MODE}):")
    print(messages)

    # --- Call Primary LLM using the provider class ---
    provider1 = get_provider(PROVIDER)
    response_text, used_model = provider1.call_with_fallback(
        messages, 
        PROMPT_MODE,
        "Primary"
    )
    
    # Update model cache if we got a valid response
    if response_text and used_model:
        update_model_cache(used_model)
    else:
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
    provider = get_provider(PROVIDER)
    model1, model2 = provider.get_comparison_models()
    messages1 = _prepare_messages(PROMPT_MODE, filtered_articles)
    response_text1 = provider.call_model(model1, messages1, MAX_TOKENS, 'Comparison 1')
    
    if not response_text1:
        print(f"Comparison 1 failed for {PROVIDER}")

    # --- Config 2 ---
    messages2 = _prepare_messages(PROMPT_MODE, filtered_articles)
    response_text2 = provider.call_model(model2, messages2, MAX_TOKENS, 'Comparison 2')
    
    if not response_text2:
        print(f"Comparison 2 failed for {PROVIDER}")

    print("\n--- Comparison Mode Finished ---")


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
def main(mode, settings_module, settings_config, dry_run=False): # Add dry_run parameter
    global ALL_URLS, REPORT_PROMPT
    ALL_URLS = settings_config.ALL_URLS
    REPORT_PROMPT = settings_config.REPORT_PROMPT
    SITE_PATH = settings_config.PATH  # Get the site's path from its config

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
    parser.add_argument('--compare', action='store_true', help='Run in comparison mode')
    parser.add_argument('--include-summary', action='store_true', help='Include article summary/html_content in LLM prompt')
    parser.add_argument('--prompt-mode', type=str, help='Set the prompt mode (e.g., default, o3)')
    args = parser.parse_args()

    # Configure primary provider from CLI
    # Set MODEL_1 based on selected provider
    provider = get_provider(PROVIDER)
    MODEL_1 = provider.primary_model
    
    # Set MODEL_2 for comparison mode
    MODEL_2 = provider.fallback_model

    # Set RUN_MODE to 'compare' if --compare is specified
    if args.compare:
        RUN_MODE = "compare"
        # In compare mode, use openrouter for both, but with dedicated comparison models
        

    # Set INCLUDE_ARTICLE_SUMMARY_FOR_LLM from CLI flag
    if args.include_summary:
        INCLUDE_ARTICLE_SUMMARY_FOR_LLM = True

    # Revert to CWD-based mode detection
    cwd = os.getcwd()
    selected_mode_enum = None
    selected_mode_str = None

    # Try to find a matching settings file in the current directory
    for mode_enum_val in Mode: # Renamed to avoid conflict with outer 'mode' variable
        settings_file = f"{mode_enum_val.value}_report_settings.py"
        if os.path.isfile(settings_file):
            # Load the settings file to get its path
            spec = importlib.util.spec_from_file_location("module_name", settings_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Check if the current directory matches the configured path
            if cwd == module.CONFIG.PATH:
                selected_mode_enum = mode_enum_val
                selected_mode_str = mode_enum_val.value
                # Store the loaded module and config
                loaded_settings_module = module
                loaded_settings_config = module.CONFIG
                break

    if selected_mode_enum is None:
        print(f"Error: Could not determine mode from current directory: {cwd}")
        print("Expected to find a settings file with a matching PATH in the current directory.")
        sys.exit(1)

    print(f"Detected mode '{selected_mode_str}' based on current directory.")

    if args.forceimage:
        refresh_images_only(selected_mode_str) # Pass string mode
    else:
        # Check schedule using the config's SCHEDULE field
        current_hour = datetime.datetime.now(TZ).hour
        # Ensure dry-run/compare always run if specified, otherwise check schedule or force flag
        should_run = args.force or (loaded_settings_config.SCHEDULE and current_hour in loaded_settings_config.SCHEDULE) or args.dry_run or RUN_MODE == "compare"
        if should_run:
            if args.prompt_mode:
                try:
                    prompt_mode_enum = PromptMode(args.prompt_mode.upper())
                    PROMPT_MODE = prompt_mode_enum
                except ValueError:
                    print(f"Invalid prompt mode specified: {args.prompt_mode}. Using default.")
                    PROMPT_MODE = PromptMode.DEFAULT
            main(selected_mode_str, loaded_settings_module, loaded_settings_config, dry_run=args.dry_run) # Pass string mode, loaded module and config
        else:
            print(f"Skipping update for mode '{selected_mode_str}' based on schedule (Current hour: {current_hour}, Scheduled: {loaded_settings_config.SCHEDULE}). Use --force to override.")


