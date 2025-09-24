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

from typing import List, Optional, Tuple


from image_parser import custom_fetch_largest_image
from embeddings_dedup import (
    fetch_recent_articles, get_embedding, deduplicate_articles_with_exclusions,
    get_best_matching_article
)
from html_generation import (
    generate_headlines_html, refresh_images_only
)

from shared import (EXPIRE_DAY, EXPIRE_WEEK, TZ, Mode, g_c)
from LLMModelManager import LLMModelManager, FALLBACK_MODEL, MISTRAL_EXTRA_PARAMS
from Logging import _setup_logging, DEBUG

from enum import Enum  # Ensure this is included if not already

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
LOG_LEVEL = "INFO"  # Change to "DEBUG" for maximum verbosity
LOG_FILE = "auto_update.log"  # Single log file that gets appended to

# Set up custom logging for auto_update
logger = _setup_logging(LOG_FILE, LOG_LEVEL)

# =============================================================================
# ENUMERATIONS AND CONSTANTS
# =============================================================================

class PromptMode(Enum):
    O3 = 'o3'

# =============================================================================
# CORE CONFIGURATION CONSTANTS
# =============================================================================

# Prompt mode selection
PROMPT_MODE = PromptMode.O3  # Use O3 prompt mode by default

# Headlines and archive limits
MAX_PREVIOUS_HEADLINES = 200  # Number of headlines to remember and filter out to the AI
MAX_ARCHIVE_HEADLINES = 50    # Size of Headlines Archive page

# Title marker used to separate reasoning from selected headlines
TITLE_MARKER = "= HEADLINES ="

# Article processing limits
MAX_ARTICLES_PER_FEED_FOR_LLM = 5  # How many articles from each feed to consider for the LLM

# =============================================================================
# LLM/AI CONFIGURATION
# =============================================================================

# Global LLM/AI settings
MAX_TOKENS = 10000
TIMEOUT = 120


# AI Attribution configuration
SHOW_AI_ATTRIBUTION = True  # Set to False to hide AI model attribution in headlines

# Optional: include more article data (summary, etc) in LLM prompt
INCLUDE_ARTICLE_SUMMARY_FOR_LLM = False

# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

# Model selection behavior
USE_RANDOM_MODELS = True  # Set to True to always try random models, False to use cached working model

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

# O3-suggested alternate prompt for reasoning models
PROMPT_O3_SYSTEM = f"""
INSTRUCTIONS:
1. Write exactly ONE paragraph (40 words or less) explaining your choices
2. Write {TITLE_MARKER} on its own line.
3. List exactly 3 best titles for the listed audience from the list of titles below, one per line
4. Do NOT include any extra text on the title lines, put your comments and disclaimers above or below the list of titles.
5. IMPORTANT: You must select ONLY from the provided list of titles - do not make up new titles
6. Order the titles by importance - most important/interesting first
7. CRITICAL: Each selected title must cover a completely distinct topic - ensure there is no similarity in topics between your selections

The example below shows the structure, but you must write your own reasoning and select actual titles:

TEMPLATE START
[Reasoning paragraph above titles]

{TITLE_MARKER}
[Select and paste the MOST important/interesting title from the list]
[Select and paste the SECOND most important/interesting title from the list]
[Select and paste the THIRD most important/interesting title from the list]
TEMPLATE END
"""

PROMPT_O3_USER_TEMPLATE = """
<scratchpad>
Think step-by-step, de-duplicate, choose three best. Some headlines are irrelevant—discard them.
</scratchpad>

Find the top 3 articles most interesting to:
{mode_instructions}


INPUT TITLES:
"""

# =============================================================================
# PROVIDER CONFIGURATION
# =============================================================================

# Run mode configuration
RUN_MODE = "normal"  # options: "normal", "compare"

# Provider configuration
PROVIDER = "openrouter"

# Configuration for the primary provider/model
MODEL_1 = None

# Configuration for the secondary provider/model (for comparison mode)
MODEL_2 = None  # Will be set based on provider

# Add unified provider client cache (for normal mode)
provider_client_cache = None

# Global URL storage
ALL_URLS = {}  # Initialized here, passed to utils

# Create global model manager instance
model_manager = LLMModelManager()

# =============================================================================
# SIMPLIFIED PROVIDER FUNCTIONS
# =============================================================================

def get_openrouter_client():
    """Get an OpenRouter API client with caching."""
    global provider_client_cache
    
    if provider_client_cache is not None:
        return provider_client_cache
    
    # Import here to avoid circular imports
    from openai import OpenAI
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1"
    )
    
    # Add OpenRouter-specific headers
    headers = {
        "HTTP-Referer": "https://linuxreport.net",
        "X-Title": "LinuxReport"
    }
    for header, value in headers.items():
        client._client.headers[header] = value
    
    provider_client_cache = client
    return client



def call_openrouter_model(model, messages, max_tokens, label=""):
    """Call OpenRouter model with retry logic, timeout, and logging."""
    client = get_openrouter_client()
    response_text = _try_call_model(client, model, messages, max_tokens)
    return response_text, model



# Provider registry - simplified to just track the provider name
PROVIDER_NAME = "openrouter"

def _try_call_model(client, model, messages, max_tokens):
    max_retries = 1
    for attempt in range(1, max_retries + 1):
        start = timer()
        logger.info(f"Calling model {model} (attempt {attempt}/{max_retries})")

        prepared_messages = list(messages) # Make a copy to potentially modify

        # If the model requires user-only instructions and the current message structure
        # is [system_prompt, user_prompt] (typical for O3 mode), combine them.
        if model_manager.is_user_only_instruction_model(model) and \
           len(prepared_messages) == 2 and \
           prepared_messages[0].get("role") == "system" and \
           prepared_messages[1].get("role") == "user":

            system_content = prepared_messages[0]["content"]
            user_content = prepared_messages[1]["content"]

            combined_user_content = f"{system_content}\n\n{user_content}"
            prepared_messages = [{"role": "user", "content": combined_user_content}]

        try:
            if 'mistral' in model.lower():
                extra_params = MISTRAL_EXTRA_PARAMS
            else:
                extra_params = {}

            response = client.chat.completions.create(
                model=model,
                messages=prepared_messages,
                max_tokens=max_tokens,
                timeout=TIMEOUT,
                extra_body=extra_params
            )
            end = timer()

            # Check if response has choices before accessing
            if not response.choices:
                raise RuntimeError(f"Model {model} returned empty choices")

            choice = response.choices[0]
            response_text = choice.message.content
            finish_reason = choice.finish_reason
            response_time = end - start

            logger.info(f"Model {model} responded in {response_time:.3f}s, finish_reason: {finish_reason}")
            logger.debug(f"Response length: {len(response_text)} characters")


            return response_text
        except Exception as e:
            error_msg = str(e)
            if "JSONDecodeError" in error_msg:
                logger.error(f"Model {model} returned malformed response: {error_msg}")
            else:
                logger.error(f"Error on attempt {attempt} for model {model}: {error_msg}")
            if attempt < max_retries:
                time.sleep(1)
    logger.error(f"Model call failed after {max_retries} attempts for model {model}")
    raise RuntimeError(f"Model call failed after {max_retries} attempts for model {model}")


def extract_top_titles_from_ai(text):
    """Extracts top titles from AI-generated text with multiple fallback strategies."""
    if not text:
        return []

    # Try to find the marker by looking for the marker word with any surrounding characters
    marker_index = text.rfind(TITLE_MARKER)
    if marker_index != -1:
        marker_length = len(TITLE_MARKER)
    else:
        # Extract only A-Za-z letters from the marker
        letters = ''.join(c for c in TITLE_MARKER if c.isalpha())
        if letters:
            marker_index = text.rfind(letters)
            if marker_index != -1:
                marker_length = len(letters)
        else:
            marker_index = -1
            marker_length = 0

    # Get lines to process - either after marker or reversed for bottom-up search
    if marker_index != -1:
        text = text[marker_index + marker_length:]
        lines = text.splitlines()
        should_reverse = False
        lines = lines[:10]  # Only look at first 10 lines after marker
    else:
        lines = text.splitlines()[-15:]  # For bottom-up search, look at last 15 lines
        should_reverse = True
        lines = list(reversed(lines))

    # Process the lines
    titles = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Clean up formatting - combine all regex operations into one
        line = re.sub(r'^\*+|\*+$|^["\']|["\']$|^[-–—]+|[-–—]+$|\*\*|^[-–—\s]+|^[#\s]+|^[•\s]+|^\d+\.?\s*', '', line)
        line = line.strip()

        # Use different regex patterns based on whether we're going forward or backward
        if should_reverse:
            match = re.match(r"^\d+[\.\)\-\s:,]+(.+)", line)
            if match:
                title = match.group(1)
            else:
                continue
        else:
            title = line

        titles.append(title)
        if len(titles) == 3:
            break

    if not titles:
        logger.warning("No valid titles found in response")
        return []

    # Reverse the titles if we were processing in reverse
    if should_reverse:
        titles = list(reversed(titles))

    logger.info(f"Successfully extracted {len(titles)} valid titles")
    return titles


def _prepare_messages(prompt_mode, filtered_articles):
    """Prepares the message list based on the prompt mode."""
    # Default empty messages list
    messages = []
    
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
    else:
        # Default case if prompt_mode is not recognized
        logger.warning(f"Unhandled prompt_mode: {prompt_mode}. Using default O3 prompt.")
        user_list = "\n".join(article_line(i, article) for i, article in enumerate(filtered_articles, 1))
        messages = [
            {"role": "system", "content": PROMPT_O3_SYSTEM},
            {"role": "user",   "content": PROMPT_O3_USER_TEMPLATE.format(mode_instructions=mode_instructions) + user_list},
        ]
    return messages

def ask_ai_top_articles(articles, dry_run=False):
    """Filters articles, constructs prompt, queries the primary AI, handles fallback (if applicable)."""
    logger.info(f"Starting AI article selection with {len(articles)} total articles")
    
    # Prepare articles
    result = _prepare_articles_for_ai(articles)
    if result is None:
        return "No new articles to rank.", [], None
    filtered_articles, previous_selections = result

    # Prepare messages
    messages = _prepare_messages(PROMPT_MODE, filtered_articles)
    logger.info(f"Constructed prompt for {PROMPT_MODE} mode with {len(filtered_articles)} articles")
    
    if logger.isEnabledFor(DEBUG):
        logger.debug("Prompt messages:")
        for i, msg in enumerate(messages):
            logger.debug(f"  Message {i+1} ({msg['role']}): {msg['content'][:200]}...")

    # Try AI selection with simplified logic
    response_text, top_articles, used_model = _try_ai_models(messages, filtered_articles)
    
    # Check if we succeeded
    if not top_articles or len(top_articles) < 3:
        logger.error("Failed to get 3 articles after trying all available models")
        return "Failed to get 3 articles after trying all available models.", [], None

    # Update cache
    _update_selections_cache(top_articles, previous_selections, used_model, dry_run)
    
    return response_text, top_articles, used_model


def _try_ai_models(messages, filtered_articles):
    """Simplified model selection logic."""
    logger.info("Starting AI model selection process")

    current_model = None

    # Try up to 3 different models (including fallback)
    for attempt in range(3):
        if attempt == 2:  # 3rd attempt
            current_model = FALLBACK_MODEL
            logger.info(f"Using fallback model: {current_model}")
        else:
            current_model = model_manager.get_available_model(current_model=current_model)

        logger.info(f"Trying model: {current_model}")

        try:
            response_text, used_model = call_openrouter_model(current_model, messages, MAX_TOKENS, f"Attempt {attempt+1}")

            if not response_text:
                logger.warning(f"Model {current_model} returned no response")
                model_manager.mark_failed(current_model)
                continue

            top_articles = _process_ai_response(response_text, filtered_articles, f"model {current_model}")
            if top_articles and len(top_articles) >= 3:
                logger.info(f"Successfully got {len(top_articles)} articles from model {current_model}")
                model_manager.mark_success(current_model)
                return response_text, top_articles, current_model
            else:
                logger.warning(f"Model {current_model} failed to produce enough articles")
                model_manager.mark_failed(current_model)

        except Exception as e:
            logger.error(f"Model {current_model} failed: {str(e)}")
            model_manager.mark_failed(current_model)

    logger.error("All model attempts failed")
    return None, [], None





def _process_ai_response(response_text, filtered_articles, model_context):
    """Process AI response and extract matching articles."""
    logger.info(f"Processing AI response from {model_context}")
    logger.info(f"Response text: {response_text}")
    
    # Extract titles from response
    top_titles = extract_top_titles_from_ai(response_text)
    logger.info(f"Extracted {len(top_titles)} titles from AI response")
    
    if logger.isEnabledFor(DEBUG):
        logger.debug("Extracted titles:")
        for i, title in enumerate(top_titles, 1):
            logger.debug(f"  {i}. {title}")
    
    if not top_titles:
        logger.warning(f"No headlines extracted from {model_context}")
        return []
    
    # Match titles to articles
    logger.info("Matching extracted titles to articles")
    top_articles = []
    for i, title in enumerate(top_titles, 1):
        logger.debug(f"Matching title {i}: {title}")
        best_match = get_best_matching_article(title, filtered_articles)
        if best_match:
            top_articles.append(best_match)
            logger.info(f"Selected article {i}: {best_match['title']} ({best_match['url']})")
        else:
            logger.warning(f"Failed to find match for title: {title}")

    logger.info(f"Successfully matched {len(top_articles)} articles out of {len(top_titles)} titles")
    return top_articles


def _prepare_articles_for_ai(articles):
    """Prepare articles by deduplicating and filtering."""
    logger.info(f"Preparing {len(articles)} articles for AI selection")

    # Get previous selections for deduplication
    previous_selections = g_c.get("previously_selected_selections_2") or []
    previous_embeddings = [get_embedding(sel["title"]) for sel in previous_selections]
    previous_urls = [sel["url"] for sel in previous_selections]

    # Filter by URL to avoid duplicates
    articles = [article for article in articles if article["url"] not in previous_urls]

    # Apply embedding-based deduplication
    filtered_articles = deduplicate_articles_with_exclusions(articles, previous_embeddings)

    # Filter by title length (10-200 characters)
    filtered_articles = [
        article for article in filtered_articles
        if len(article['title']) >= 10 and len(article['title']) <= 200 and not article['title'].startswith(('http://', 'https://', 'www.'))
    ]

    logger.info(f"Filtered articles: {len(articles)} -> {len(filtered_articles)} articles")

    if not filtered_articles:
        logger.warning("No new articles available after all filtering.")
        return None, previous_selections

    return filtered_articles, previous_selections


def _update_selections_cache(top_articles, previous_selections, used_model, dry_run=False):
    """Update the selections cache with new articles."""
    if dry_run:
        logger.info("DRY RUN: Skipping cache updates")
        return

    new_selections = [{"url": art["url"], "title": art["title"]}
                      for art in top_articles if art]
    updated_selections = previous_selections + new_selections
    if len(updated_selections) > MAX_PREVIOUS_HEADLINES:
        updated_selections = updated_selections[-MAX_PREVIOUS_HEADLINES:]
        logger.info(f"Trimmed selections to {len(updated_selections)} entries")

    logger.info(f"Updating cache with {len(updated_selections)} selections")
    g_c.put("previously_selected_selections_2", updated_selections, timeout=EXPIRE_WEEK)
    logger.info(f"Cache update status: {g_c.get('previously_selected_selections_2') is not None}")


def run_comparison(articles):
    """Runs two LLM calls with different configurations for comparison."""
    logger.info("--- Running Comparison Mode ---")

    # Use the same deduplication logic as ask_ai_top_articles
    result = _prepare_articles_for_ai(articles)
    if result is None:
        logger.warning("No new articles available after deduplication for comparison.")
        return
    filtered_articles, _ = result

    logger.info(f"Comparison mode: {len(filtered_articles)} articles after deduplication")

    # Get comparison models and run them
    model1, model2 = model_manager.get_comparison_models()
    logger.info(f"Comparison model 1: {model1}")
    logger.info(f"Comparison model 2: {model2}")
    
    # Run both models
    _run_comparison_model(model1, filtered_articles, "Comparison 1")
    _run_comparison_model(model2, filtered_articles, "Comparison 2")

    logger.info("--- Comparison Mode Finished ---")


def _run_comparison_model(model, filtered_articles, label):
    """Helper function to run a single comparison model."""
    try:
        messages = _prepare_messages(PROMPT_MODE, filtered_articles)
        response_text, used_model = call_openrouter_model(model, messages, MAX_TOKENS, label)
        
        if not response_text:
            logger.error(f"{label} returned no response")
            return
        
        logger.info(f"{label} completed successfully")
        # Process and log the results
        top_articles = _process_ai_response(response_text, filtered_articles, f"{label} ({model})")
        if top_articles:
            logger.info(f"{label} selected {len(top_articles)} articles")
        else:
            logger.warning(f"{label} failed to produce articles")
            
    except Exception as e:
        logger.error(f"{label} failed with exception: {e}")




def append_to_archive(mode, top_articles):
    """Append the current top articles to the archive file with timestamp and image. Limit archive to MAX_ARCHIVE_HEADLINES."""
    archive_file = f"{mode}report_archive.jsonl"
    timestamp = datetime.datetime.now(TZ).isoformat()
    
    logger.info(f"Appending {len(top_articles)} articles to archive: {archive_file}")
    
    # Build entries directly from pre-fetched image URLs
    new_entries = []
    for i, article in enumerate(top_articles[:3], 1):
        entry = {
            "title": article["title"],
            "url": article["url"],
            "timestamp": timestamp,
            "image_url": article.get("image_url"),
            "alt_text": f"headline: {article['title'][:50]}" if article.get("image_url") else None
        }
        new_entries.append(entry)
        logger.debug(f"Archive entry {i}: {article['title']} ({article['url']})")
    
    # Read old entries, append new, and trim to limit
    try:
        with open(archive_file, "r", encoding="utf-8") as f:
            old_entries = [json.loads(line) for line in f if line.strip()]
        logger.debug(f"Read {len(old_entries)} existing entries from archive")
    except FileNotFoundError:
        old_entries = []
        logger.info(f"Archive file {archive_file} not found, creating new archive")

    all_entries = new_entries + old_entries
    original_count = len(all_entries)
    all_entries = all_entries[:MAX_ARCHIVE_HEADLINES]
    final_count = len(all_entries)
    
    logger.info(f"Archive: {original_count} -> {final_count} entries (trimmed to {MAX_ARCHIVE_HEADLINES} max)")
    
    with open(archive_file, "w", encoding="utf-8") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    logger.info(f"Successfully updated archive file: {archive_file}")

# --- Integration into the main pipeline ---
def main(mode, settings_module, settings_config, dry_run=False):
    """Main processing function with improved error handling and dry run logic."""
    global ALL_URLS, REPORT_PROMPT
    
    
    # For other modes, set up the configuration
    ALL_URLS = settings_config.ALL_URLS
    REPORT_PROMPT = settings_config.REPORT_PROMPT
    SITE_PATH = settings_config.PATH

    logger.info(f"Starting main processing for mode: {mode}")
    logger.info(f"Site path: {SITE_PATH}")
    logger.info(f"Report prompt: {REPORT_PROMPT}")
    logger.info(f"Number of URLs configured: {len(ALL_URLS)}")
    logger.info(f"Dry run mode: {dry_run}")

    html_file = f"{mode}reportabove.html"

    try:
        # Fetch articles
        logger.info("Fetching recent articles from configured URLs")
        articles = fetch_recent_articles(ALL_URLS, g_c)
        if not articles:
            logger.error(f"No articles found for mode: {mode}")
            return 1

        logger.info(f"Fetched {len(articles)} articles from {len(ALL_URLS)} URLs")

        # Handle different run modes
        if RUN_MODE == "compare":
            logger.info("Running in comparison mode")
            run_comparison(articles)
            return 0
        elif RUN_MODE == "normal":
            return _process_normal_mode(mode, articles, html_file, dry_run)
        else:
            logger.error(f"Unknown RUN_MODE: {RUN_MODE}")
            return 1

    except (FileNotFoundError, ImportError) as e:
        logger.error(f"Configuration error for mode {mode}: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error in mode {mode}: {e}")
        traceback.print_exc()
        return 1


def _process_normal_mode(mode, articles, html_file, dry_run):
    """Process articles in normal mode with improved error handling."""
    logger.info("Running in normal mode")
    
    # Get AI-selected articles
    full_response, top_3_articles_match, used_model = ask_ai_top_articles(articles, dry_run)

    # Handle AI processing results
    if not top_3_articles_match:
        if full_response.startswith("No new articles"):
            logger.info("No new articles to process")
            return 0
        else:
            logger.error("AI processing failed or returned no headlines")
            return 1

    # Handle dry run mode
    if dry_run:
        logger.info("--- Dry Run Mode: Skipping file generation and archive update ---")
        logger.info(f"Would have selected {len(top_3_articles_match)} articles:")
        for i, article in enumerate(top_3_articles_match, 1):
            logger.info(f"  {i}. {article['title']} ({article['url']})")
        return 0

    # Normal processing: fetch images and generate files
    logger.info("Fetching images for top articles...")
    for i, art in enumerate(top_3_articles_match, 1):
        logger.debug(f"Fetching image for article {i}: {art['title']}")
        art['image_url'] = custom_fetch_largest_image(
            art['url'], underlying_link=art.get('underlying_link'), html_content=art.get('html_content')
        )
        if art['image_url']:
            logger.debug(f"Found image for article {i}: {art['image_url']}")
        else:
            logger.debug(f"No image found for article {i}")
            
    # Generate HTML and archive
    logger.info(f"Generating HTML file: {html_file}")
    generate_headlines_html(top_3_articles_match, html_file, model_name=used_model if SHOW_AI_ATTRIBUTION else None)
                
    logger.info(f"Appending to archive for mode: {mode}")
    append_to_archive(mode, top_3_articles_match)
    
    logger.info("Normal mode processing completed successfully")
    return 0

def parse_arguments():
    """Parse command line arguments and return a config object."""
    parser = argparse.ArgumentParser(description='Generate report with optional force update')
    parser.add_argument('--force', action='store_true', help='Force update regardless of schedule')
    parser.add_argument('--forceimage', action='store_true', help='Only refresh images in the HTML file')
    parser.add_argument('--dry-run', action='store_true', help='Run AI analysis but do not update files')
    parser.add_argument('--compare', action='store_true', help='Run in comparison mode')
    parser.add_argument('--include-summary', action='store_true', help='Include article summary/html_content in LLM prompt')
    parser.add_argument('--prompt-mode', type=str, help='Set the prompt mode (e.g., o3)')
    parser.add_argument('--use-cached-model', action='store_true', help='Use cached working model instead of random selection')
    parser.add_argument('--force-model', type=str, help='Force the use of a specific model (overrides random/cached selection)')
    
    args = parser.parse_args()
    logger.info("Command line arguments parsed")
    
    return args

def detect_mode():
    """Detect the current mode based on working directory and settings files."""
    cwd = os.getcwd()
    logger.info(f"Current working directory: {cwd}")
    
    for mode_enum_val in Mode:
        settings_file = f"{mode_enum_val.value}_report_settings.py"
        if os.path.isfile(settings_file):
            spec = importlib.util.spec_from_file_location("module_name", settings_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if cwd == module.CONFIG.PATH:
                logger.info(f"Matched mode '{mode_enum_val.value}' with path {module.CONFIG.PATH}")
                return mode_enum_val.value, module, module.CONFIG
    
    logger.error(f"Could not determine mode from current directory: {cwd}")
    logger.error("Expected to find a settings file with a matching PATH in the current directory.")
    sys.exit(1)

def should_run_update(args, settings_config):
    """Determine if the update should run based on schedule and arguments."""
    if args.force or args.dry_run or args.compare:
        return True
    
    current_hour = datetime.datetime.now(TZ).hour
    scheduled = settings_config.SCHEDULE and current_hour in settings_config.SCHEDULE
    
    logger.info(f"Schedule check: current_hour={current_hour}, scheduled_hours={settings_config.SCHEDULE}, should_run={scheduled}")
    
    if not scheduled:
        logger.info(f"Skipping update based on schedule (Current hour: {current_hour}, Scheduled: {settings_config.SCHEDULE}). Use --force to override.")
    
    return scheduled

def configure_global_settings(args):
    """Configure global settings based on command line arguments."""
    global USE_RANDOM_MODELS, RUN_MODE, INCLUDE_ARTICLE_SUMMARY_FOR_LLM, PROMPT_MODE, MODEL_1, MODEL_2


    # Set model selection behavior
    USE_RANDOM_MODELS = not args.use_cached_model

    # Set comparison mode
    if args.compare:
        RUN_MODE = "compare"

    # Set summary inclusion
    if args.include_summary:
        INCLUDE_ARTICLE_SUMMARY_FOR_LLM = True

    # Configure models
    MODEL_1 = model_manager.get_available_model(use_random=USE_RANDOM_MODELS, forced_model=args.force_model)
    MODEL_2 = FALLBACK_MODEL

    # Set prompt mode
    if args.prompt_mode:
        try:
            PROMPT_MODE = PromptMode(args.prompt_mode.upper())
        except ValueError:
            logger.warning(f"Invalid prompt mode specified: {args.prompt_mode}. Using default O3 mode.")
            PROMPT_MODE = PromptMode.O3

if __name__ == "__main__":
    args = parse_arguments()
    
    
    # Detect mode and load settings
    selected_mode_str, loaded_settings_module, loaded_settings_config = detect_mode()
    logger.info(f"Detected mode '{selected_mode_str}' based on current directory.")
    
    # Handle forceimage case early
    if args.forceimage:
        logger.info("Running in forceimage mode - only refreshing images")
        refresh_images_only(selected_mode_str, None)
        sys.exit(0)
    
    # Check if we should run
    if not should_run_update(args, loaded_settings_config):
        sys.exit(0)
    
    # Configure global settings
    configure_global_settings(args)
    
    logger.info("Starting main processing...")
    exit_code = main(selected_mode_str, loaded_settings_module, loaded_settings_config, dry_run=args.dry_run)
    sys.exit(exit_code)


