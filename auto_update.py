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
from openai import APIError, APITimeoutError, RateLimitError
import requests

from typing import List, Optional, Tuple


from image_parser import custom_fetch_largest_image
from embeddings_dedup import (
    fetch_recent_articles, get_embeddings, deduplicate_articles_with_exclusions,
    get_best_matching_article
)
from html_generation import (
    generate_headlines_html, refresh_images_only,
    append_to_archive, clean_excess_headlines
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

# O3-style prompt for reasoning models selecting top headlines
PROMPT_O3_SYSTEM = f"""
You are selecting the top 3 headlines from a provided list for a specific target audience.
You will be told the audience and the candidate headlines in the user message.

Follow these rules EXACTLY:

1. Choose exactly 3 headlines from the provided list. Do NOT invent or rewrite headlines.
2. Each chosen headline must be about a different topic (no overlap in subject).
3. Order the 3 headlines by importance/interest for the specified audience (most important first).
4. Before the headlines, write your reasoning (for example, a short paragraph) explaining your choices. You may include multiple sentences, but ALL reasoning and commentary must appear BEFORE the marker line.
5. On a new line after all reasoning, write exactly: {TITLE_MARKER}
6. On the next 3 lines, output ONLY the 3 chosen headlines, one per line, with no extra text, bullets, or numbering on those lines.
7. After the {TITLE_MARKER} line, do not include any other text or lists. The 3 lines immediately following {TITLE_MARKER} are the ONLY lines that will be parsed as selected headlines.

Example of correct output format (use your own reasoning and real headlines):

Short explanation of why these 3 headlines were chosen for the audience.

{TITLE_MARKER}
First chosen headline from the provided list
Second chosen headline from the provided list
Third chosen headline from the provided list
"""

PROMPT_O3_USER_TEMPLATE = """
<scratchpad>
Think step-by-step. Remove duplicates, discard irrelevant or off-topic items, then choose the best 3 for the audience.
Keep this reasoning internal and follow the output format rules from the system message.
</scratchpad>

Audience:
{mode_instructions}

Candidate headlines:
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

def _extract_error_details(e):
    """
    Extracts a descriptive error message and the response body from various exception types.
    
    Args:
        e (Exception): The exception to analyze.
        
    Returns:
        tuple: (error_message, error_body)
    """
    error_body = None
    
    # Handle custom RuntimeError with multi-args (from _try_call_model)
    if isinstance(e, RuntimeError) and len(e.args) > 1:
        return e.args[0], e.args[1]
        
    # Handle OpenAI-style API errors
    if isinstance(e, APIError):
        try:
            status_code = getattr(e, 'status_code', 'N/A')
            body = getattr(e, 'body', 'N/A')
            error_body = body if body != 'N/A' else None
            
            details = []
            if status_code != 'N/A':
                details.append(f"HTTP {status_code}")
            
            if isinstance(body, dict):
                inner = body.get('error', {})
                if isinstance(inner, dict):
                    msg = inner.get('message')
                    code = inner_error_code = inner.get('code')
                    if msg: details.append(f"Msg: {msg}")
                    if code: details.append(f"Code: {code}")
                else:
                    details.append(f"Body: {json.dumps(body)}")
            elif body != 'N/A':
                details.append(f"Body: {body}")
                
            msg = f"APIError ({', '.join(details)})" if details else f"APIError: {str(e)}"
            return msg, error_body
        except Exception as inner_e:
            return f"APIError: {str(e)} (parsing failed: {inner_e})", getattr(e, 'body', None)
            
    # Fallback for other exceptions
    msg = f"{type(e).__name__}: {str(e)}"
    error_body = getattr(e, 'body', str(e))
    return msg, error_body


def _try_call_model(client, model, messages, max_tokens):
    max_retries = 1
    last_error = "Unknown error"
    last_error_body = None
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
        except (APITimeoutError, RateLimitError) as e:
            last_error, last_error_body = _extract_error_details(e)
            logger.warning(f"API Error on attempt {attempt} for model {model}: {last_error}. Retrying...")
            if attempt < max_retries:
                time.sleep(1)  # Wait before retrying
        except APIError as e:
            last_error, last_error_body = _extract_error_details(e)
            logger.error(f"API Error on attempt {attempt} for model {model}: {last_error}")
            break # Don't retry on other API errors
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            last_error, last_error_body = _extract_error_details(e)
            logger.error(f"Network or JSON error on attempt {attempt} for model {model}: {last_error}")
            break
        except Exception as e:
            last_error, last_error_body = _extract_error_details(e)
            logger.error(f"Unexpected error on attempt {attempt} for model {model}: {last_error}")
            break
    
    error_msg = f"Model call failed after {max_retries} attempts for model {model}. Last error: {last_error}"
    logger.error(error_msg)
    raise RuntimeError(error_msg, last_error_body)


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

def ask_ai_top_articles(articles, dry_run=False, forced_model=None):
    """Filters articles, constructs prompt, queries the primary AI, handles fallback (if applicable)."""
    logger.info(f"Starting AI article selection with {len(articles)} total articles")

    # Prepare articles
    result = _prepare_articles_for_ai(articles)
    if result is None:
        return "No new articles to rank.", [], None, []
    filtered_articles, previous_selections = result

    # Prepare messages
    messages = _prepare_messages(PROMPT_MODE, filtered_articles)
    logger.info(f"Constructed prompt for {PROMPT_MODE} mode with {len(filtered_articles)} articles")

    if logger.isEnabledFor(DEBUG):
        logger.debug("Prompt messages:")
        for i, msg in enumerate(messages):
            logger.debug(f"  Message {i+1} ({msg['role']}): {msg['content'][:200]}...")

    # Try AI selection with simplified logic
    response_text, top_articles, used_model, attempts = _try_ai_models(messages, filtered_articles, forced_model)
    
    # Check if we succeeded
    if not top_articles or len(top_articles) < 3:
        logger.error("Failed to get 3 articles after trying all available models")
        return "Failed to get 3 articles after trying all available models.", [], None, attempts

    # Update cache
    _update_selections_cache(top_articles, previous_selections, used_model, dry_run)
    
    return response_text, top_articles, used_model, attempts


def _try_ai_models(messages, filtered_articles, forced_model=None):
    """Simplified model selection logic."""
    logger.info("Starting AI model selection process")

    current_model = None
    attempts = []

    # Try up to 3 different models (including fallback)
    for attempt_idx in range(3):
        if attempt_idx == 2:  # 3rd attempt
            current_model = FALLBACK_MODEL
            logger.info(f"Using fallback model: {current_model}")
        else:
            # Only use forced_model on the first attempt; let the system pick a new model on retries
            model_to_force = forced_model if attempt_idx == 0 else None
            current_model = model_manager.get_available_model(current_model=current_model, forced_model=model_to_force)
            if current_model is None:
                logger.error("No available models found, skipping this attempt")
                attempt_record = {
                    "model": None,
                    "messages": messages,
                    "response": None,
                    "success": False,
                    "error": "No available models"
                }
                attempts.append(attempt_record)
                continue

        logger.info(f"Trying model: {current_model}")

        attempt_record = {
            "model": current_model,
            "messages": messages,
            "response": None,
            "success": False,
            "error": None
        }
        attempts.append(attempt_record)

        try:
            response_text, used_model = call_openrouter_model(current_model, messages, MAX_TOKENS, f"Attempt {attempt_idx+1}")
            attempt_record["response"] = response_text

            if not response_text:
                error_msg = "Empty response"
                logger.warning(f"Model {current_model} returned no response")
                model_manager.mark_failed(current_model, error_msg, response_text="")
                attempt_record["error"] = error_msg
                continue

            top_articles = _process_ai_response(response_text, filtered_articles, f"model {current_model}")
            if top_articles and len(top_articles) >= 3:
                logger.info(f"Successfully got {len(top_articles)} articles from model {current_model}")
                model_manager.mark_success(current_model)
                attempt_record["success"] = True
                return response_text, top_articles, current_model, attempts
            else:
                error_msg = "Insufficient articles returned"
                logger.warning(f"Model {current_model} failed to produce enough articles")
                model_manager.mark_failed(current_model, error_msg, response_text)
                attempt_record["error"] = error_msg

        except (RuntimeError, RateLimitError, APITimeoutError) as e:
            error_msg, response_body = _extract_error_details(e)
            logger.error(f"Model {current_model} failed: {error_msg}")
            
            # Use the captured response body if available
            response_text_for_failure = response_body if response_body else attempt_record.get("response", "")
            if isinstance(response_text_for_failure, (dict, list)):
                try:
                    response_text_for_failure = json.dumps(response_text_for_failure, indent=2)
                except Exception:
                    response_text_for_failure = str(response_text_for_failure)
            
            attempt_record["response"] = response_text_for_failure
            model_manager.mark_failed(current_model, error_msg, response_text_for_failure)
            attempt_record["error"] = error_msg

    logger.error("All model attempts failed")
    return None, [], None, attempts





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
    
    # Filter out old selections to keep only the most recent ones
    if len(previous_selections) > MAX_PREVIOUS_HEADLINES:
        previous_selections = previous_selections[-MAX_PREVIOUS_HEADLINES:]
        logger.info(f"Trimmed previous selections to {len(previous_selections)} entries (max: {MAX_PREVIOUS_HEADLINES})")
    
    # Compute embeddings in batch for efficiency
    previous_titles = [sel["title"] for sel in previous_selections]
    if previous_titles:
        previous_embeddings = get_embeddings(previous_titles)
    else:
        previous_embeddings = []
    previous_urls = [sel["url"] for sel in previous_selections]
    logger.info(f"Found {len(previous_selections)} previous selections to exclude")

    # Filter by URL to avoid duplicates
    articles_after_url_filter = [article for article in articles if article["url"] not in previous_urls]
    logger.info(f"After URL filtering: {len(articles)} -> {len(articles_after_url_filter)} articles")

    # Apply embedding-based deduplication
    filtered_articles = deduplicate_articles_with_exclusions(articles_after_url_filter, previous_embeddings)
    logger.info(f"After embedding deduplication: {len(articles_after_url_filter)} -> {len(filtered_articles)} articles")

    # Filter by title length (10-200 characters)
    filtered_articles = [
        article for article in filtered_articles
        if len(article['title']) >= 10 and len(article['title']) <= 200 and not article['title'].startswith(('http://', 'https://', 'www.'))
    ]
    logger.info(f"After title length filtering: {len(filtered_articles)} articles")

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
            
    except RuntimeError as e:
        logger.error(f"{label} failed with exception: {e}")




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
    except (ValueError, AttributeError) as e:
        logger.error(f"Configuration or data error in mode {mode}: {e}")
        traceback.print_exc()
        return 1


def _process_normal_mode(mode, articles, html_file, dry_run):
    """Process articles in normal mode with improved error handling."""
    logger.info("Running in normal mode")
    
    # Generate a single timestamp for this run
    run_timestamp = datetime.datetime.now(TZ).isoformat()
    
    # Get AI-selected articles
    full_response, top_3_articles_match, used_model, attempts = ask_ai_top_articles(articles, dry_run, MODEL_1)

    # Save LLM attempts to cache
    if attempts:
        cache_key = f"llm_attempts:{mode}:{run_timestamp}"
        logger.info(f"Saving {len(attempts)} LLM attempts to cache with key {cache_key}")
        g_c.put(cache_key, attempts, timeout=EXPIRE_WEEK * 2)

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
    generate_headlines_html(
        top_3_articles_match, 
        html_file, 
        model_name=used_model if SHOW_AI_ATTRIBUTION else None,
        attempts=attempts,
        timestamp=run_timestamp
    )
                
    logger.info(f"Appending to archive for mode: {mode}")
    append_to_archive(mode, top_3_articles_match, run_timestamp)
    
    logger.info("Normal mode processing completed successfully")
    return 0

def parse_arguments():
    """Parse command line arguments and return a config object."""
    parser = argparse.ArgumentParser(description='Generate report with optional force update')
    parser.add_argument('--mode', type=str, help='Force a specific mode (e.g., linux, trump, ai). If not provided, mode is detected from current working directory.')
    parser.add_argument('--force', action='store_true', help='Force update regardless of schedule')
    parser.add_argument('--forceimage', action='store_true', help='Only refresh images in the HTML file')
    parser.add_argument('--dry-run', action='store_true', help='Run AI analysis but do not update files')
    parser.add_argument('--compare', action='store_true', help='Run in comparison mode')
    parser.add_argument('--include-summary', action='store_true', help='Include article summary/html_content in LLM prompt')
    parser.add_argument('--prompt-mode', type=str, help='Set the prompt mode (e.g., o3)')
    parser.add_argument('--use-cached-model', action='store_true', help='Use cached working model instead of random selection')
    parser.add_argument('--force-model', type=str, help='Force the use of a specific model (overrides random/cached selection)')
    parser.add_argument('--clear-failed-models', action='store_true', help='Clear the list of failed models from cache')
    parser.add_argument('--clean-excess-headlines', action='store_true', help='Remove headlines created outside scheduled hours from archive and recent selections cache (use --dry-run to preview)')

    args = parser.parse_args()
    logger.info("Command line arguments parsed")
    
    return args

def detect_mode(forced_mode=None):
    """
    Detect the current mode based on working directory and settings files.
    
    Args:
        forced_mode (str, optional): If provided, force this mode instead of detecting from cwd.
    
    Returns:
        tuple: (mode_string, settings_module, settings_config)
    """
    # If mode is forced, use it directly
    if forced_mode:
        forced_mode = forced_mode.lower()
        logger.info(f"Forcing mode: {forced_mode}")
        
        # Validate that the forced mode is a valid Mode enum value
        valid_modes = [mode.value for mode in Mode]
        if forced_mode not in valid_modes:
            logger.error(f"Invalid mode '{forced_mode}'. Valid modes are: {', '.join(valid_modes)}")
            sys.exit(1)
        
        # Load the settings file for the forced mode
        settings_file = f"{forced_mode}_report_settings.py"
        if not os.path.isfile(settings_file):
            logger.error(f"Settings file not found for mode '{forced_mode}': {settings_file}")
            sys.exit(1)
        
        spec = importlib.util.spec_from_file_location("module_name", settings_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        logger.info(f"Loaded settings for forced mode '{forced_mode}' from {settings_file}")
        return forced_mode, module, module.CONFIG
    
    # Otherwise, use the original detection logic based on cwd
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
    logger.error("Use --mode <mode_name> to force a specific mode.")
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
    
    # Handle clear failed models case early
    if args.clear_failed_models:
        logger.info("Clearing failed models from cache...")
        success = model_manager.clear_failed_models()
        if success:
            logger.info("Failed models cache cleared successfully")
        else:
            logger.info("No failed models to clear")
        sys.exit(0)

    # Detect mode and load settings
    selected_mode_str, loaded_settings_module, loaded_settings_config = detect_mode(forced_mode=args.mode)

    # Handle clean excess headlines case early (needs mode detection)
    if args.clean_excess_headlines:
        logger.info("Cleaning excess headlines created outside scheduled hours...")
        clean_excess_headlines(selected_mode_str, loaded_settings_config, dry_run=args.dry_run)
        sys.exit(0)
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


