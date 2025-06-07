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
import enum
import random

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
    O3 = 'o3'
    THIRTY_B = '30b'  # Represents '30b' prompt

# Randomly select between O3 and 30B prompts by default
#PROMPT_MODE = random.choice([PromptMode.O3, PromptMode.THIRTY_B])

# Use O3 prompt mode by default for a while to try it out
PROMPT_MODE = PromptMode.O3


# --- Configuration and Prompt Constants ---
MAX_PREVIOUS_HEADLINES = 200 # Number of headlines to remember and filter out to the AI

MAX_ARCHIVE_HEADLINES = 50 # Size of Headlines Archive page


# Title marker used to separate reasoning from selected headlines
TITLE_MARKER = "= HEADLINES ="

# How many articles from each feed to consider for the LLM
MAX_ARTICLES_PER_FEED_FOR_LLM = 5

# === Global LLM/AI config ===
MAX_TOKENS = 10000
TIMEOUT = 120
MODEL_CACHE_DURATION = EXPIRE_DAY * 7

# Global logging configuration
GLOBAL_LOGGING_ENABLED = True
API_RESPONSE_LOG = "api_responses.jsonl"

# AI Attribution configuration
SHOW_AI_ATTRIBUTION = True  # Set to False to hide AI model attribution in headlines
# List of free models to try
FREE_MODELS = [
    "agentica-org/deepcoder-14b-preview:free",
    "arliai/qwq-32b-arliai-rpr-v1:free",
    "cognitivecomputations/dolphin3.0-r1-mistral-24b:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "deepseek/deepseek-r1-0528-qwen3-8b:free",
    "deepseek/deepseek-r1-0528:free",
    "deepseek/deepseek-r1-distill-qwen-14b:free",
    "deepseek/deepseek-r1-distill-qwen-32b:free",
    "google/gemma-3-12b-it:free",
    "google/gemma-3n-e4b-it:free",
    "meta-llama/llama-3.3-8b-instruct:free",
    "meta-llama/llama-4-scout:free",
    "meta-llama/llama-4-maverick:free",
    "meta-llama/llama-3.2-11b-vision-instruct:free",
  #  "microsoft/phi-4-reasoning-plus:free", very long answers, often fails to follow instructions
  #  "microsoft/phi-4-reasoning:free", 
    "microsoft/mai-ds-r1:free",
    "mistralai/devstral-small:free",
    "mistralai/mistral-7b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "moonshotai/moonlight-16b-a3b-instruct:free",
    "nousresearch/deephermes-3-llama-3-8b-preview:free",
    "nousresearch/deephermes-3-mistral-24b-preview:free",
    "nvidia/llama-3.3-nemotron-super-49b-v1:free",
    "opengvlab/internvl3-14b:free",
   # "open-r1/olympiccoder-32b:free", Generates too many tokens
    "qwen/qwen-2.5-72b-instruct:free",
    "qwen/qwen3-8b:free",
    "qwen/qwen3-14b:free",
    "qwen/qwen3-32b:free",
    "qwen/qwen3-30b-a3b:free",
    "qwen/qwen3-235b-a22b:free",
    "rekaai/reka-flash-3:free",
    "shisa-ai/shisa-v2-llama3.3-70b:free",
    "thudm/glm-z1-32b:free",
    "thudm/glm-4-32b:free",
    "tngtech/deepseek-r1t-chimera:free",
]

# Fallback model to use if all free models fail
FALLBACK_MODEL = "mistralai/mistral-small-3.1-24b-instruct"

# Set to True to always try random models, False to use cached working model
USE_RANDOM_MODELS = True

PROMPT_30B = f""" Prompt:
Given this list of news headlines, follow these steps:
Identify headlines relevant to {{mode_instructions}}. Exclude irrelevant ones.
Think carefully and consisely about relevance, interest, and topic distinction.
From relevant headlines, pick the top 3 most interesting, each covering a completely distinct topic. Ensure they have no similarity in topics.
After reasoning, output {TITLE_MARKER} followed by the top 3 headlines in this format, with no extra text but title:

{TITLE_MARKER}
Best headline
Second Best headline
Third Best headline
"""

#O3-suggested alternate prompt for reasoning models
PROMPT_O3_SYSTEM = f"""
INSTRUCTIONS:
1. Write exactly ONE paragraph (40 words or less) explaining your choices
2. Write {TITLE_MARKER} on its own line
3. List exactly 3 titles from the list of titles below, one per line
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


# --- Global Variables ---
cache = g_c

ALL_URLS = {} # Initialized here, passed to utils

# Track failed models globally
FAILED_MODELS = set()

# --- Global Configuration (Replaces Environment Variables except API Keys) ---
RUN_MODE = "normal"  # options: "normal", "compare"

PROVIDER = "openrouter"

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

# Models that don't support system instructions properly and need user-only instructions
USER_ONLY_INSTRUCTION_MODELS = [
    "google/gemma-3-27b-it:free",
    "qwen/qwen3-8b:free",  # Added due to issues with system prompts
]

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
        # Try the selected model first
        current_model = self.primary_model
        print(f"\n--- LLM Call: {self.name} / {current_model} / {prompt_mode} {label} (Primary Model) ---")
        
        try:
            response_text = self.call_model(current_model, messages, MAX_TOKENS, f"{label}")
            return response_text, current_model
        except Exception as e:
            print(f"Primary model {current_model} failed: {str(e)}")
            FAILED_MODELS.add(current_model)
        
        # Let ModelSelector handle all model selection logic
        current_model = self.model_selector.get_next_model(current_model)
        if current_model:
            print(f"\n--- LLM Call: {self.name} / {current_model} / {prompt_mode} {label} (Fallback) ---")
            try:
                response_text = self.call_model(current_model, messages, MAX_TOKENS, f"{label}")
                return response_text, current_model
            except Exception as e:
                print(f"Fallback model {current_model} failed: {str(e)}")
                FAILED_MODELS.add(current_model)
        
        return None, None
    
    def __str__(self) -> str:
        return f"{self.name} Provider (primary: {self.primary_model}, fallback: {self.fallback_model})"


def update_model_cache(model):
    """Update the cache with the currently working model if it's different."""
    current_model = g_c.get("working_llm_model")
    if current_model == model:
        return
    g_c.put("working_llm_model", model, timeout=MODEL_CACHE_DURATION)
    print(f"Updated cached working model to: {model}")

class ModelSelector:
    """Simple model selection and fallback logic."""
    
    def __init__(self, use_random=True, forced_model=None):
        self.use_random = use_random
        self.forced_model = forced_model
        self.failed_models = set()
        self.cache = g_c
        
    def get_next_model(self, current_model=None):
        """Get the next model to try."""
        # 1. Forced model takes precedence
        if self.forced_model:
            return self.forced_model
            
        # 2. Try cached model if not using random selection
        if not self.use_random:
            cached_model = self.cache.get("working_llm_model")
            if cached_model and cached_model not in self.failed_models:
                return cached_model
                
        # 3. Try random available model
        available_models = [m for m in FREE_MODELS if m not in self.failed_models and m != current_model]
        if available_models:
            return random.choice(available_models)
            
        # 4. Final fallback
        return FALLBACK_MODEL if FALLBACK_MODEL not in self.failed_models else None
        
    def mark_failed(self, model):
        """Mark a model as failed."""
        self.failed_models.add(model)
        
    def mark_success(self, model):
        """Mark a model as successful and update cache."""
        if model != self.forced_model:  # Don't cache forced models
            self.cache.put("working_llm_model", model, timeout=MODEL_CACHE_DURATION)

class OpenRouterProvider(LLMProvider):
    """Provider implementation for OpenRouter."""
    
    def __init__(self, forced_model=None):
        super().__init__("openrouter")
        self.model_selector = ModelSelector(use_random=USE_RANDOM_MODELS, forced_model=forced_model)
        self._selected_model = self.model_selector.get_next_model()
        print(f"Selected model: {self._selected_model}")
    
    @property
    def api_key_env_var(self) -> str:
        return "OPENROUTER_API_KEY"
    
    @property
    def base_url(self) -> str:
        return "https://openrouter.ai/api/v1"
    
    @property
    def primary_model(self) -> str:
        return self._selected_model
    
    @property
    def fallback_model(self) -> str:
        return FALLBACK_MODEL
    
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
        
    def call_with_fallback(self, messages: List[Dict[str, str]], prompt_mode: str, label: str = "") -> Tuple[Optional[str], Optional[str]]:
        """Call models with fallback strategy."""
        current_model = self.primary_model
        max_attempts = 3  # Try up to 3 different models
        
        for attempt in range(max_attempts):
            print(f"\n--- LLM Call: {self.name} / {current_model} / {prompt_mode} {label} (Attempt {attempt + 1}/{max_attempts}) ---")
            
            try:
                response_text = self.call_model(current_model, messages, MAX_TOKENS, f"{label}")
                if response_text:
                    self.model_selector.mark_success(current_model)
                    return response_text, current_model
            except Exception as e:
                print(f"Model {current_model} failed: {str(e)}")
                self.model_selector.mark_failed(current_model)
            
            # Let ModelSelector handle all model selection logic
            current_model = self.model_selector.get_next_model(current_model)
            if not current_model:
                print("No more models available to try")
                break
                
        return None, None

# Provider registry
PROVIDERS = {
    "openrouter": OpenRouterProvider  # Store the class, not an instance
}

# Global provider instance
_provider_instance = None

def get_provider(name: str, forced_model=None) -> LLMProvider:
    """Get a provider by name."""
    global _provider_instance
    if _provider_instance is None:
        if name not in PROVIDERS:
            raise ValueError(f"Unknown provider: {name}")
        _provider_instance = PROVIDERS[name](forced_model=forced_model)  # Pass forced_model to provider
    return _provider_instance

def _try_call_model(client, model, messages, max_tokens):
    max_retries = 1
    for attempt in range(1, max_retries + 1):
        start = timer()
        print(f"[_try_call_model] Attempt {attempt}/{max_retries} for model: {model}")
        
        prepared_messages = list(messages) # Make a copy to potentially modify

        # If the model requires user-only instructions and the current message structure
        # is [system_prompt, user_prompt] (typical for O3 mode), combine them.
        if model in USER_ONLY_INSTRUCTION_MODELS and \
           len(prepared_messages) == 2 and \
           prepared_messages[0].get("role") == "system" and \
           prepared_messages[1].get("role") == "user":
            
            print(f"Model {model} is in USER_ONLY_INSTRUCTION_MODELS. Combining system and user prompts into a single user prompt.")
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
                messages=prepared_messages, # Use potentially modified messages
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
            
            # Log the API response only if global logging is enabled
            if GLOBAL_LOGGING_ENABLED:
                try:
                    log_entry = {
                        "timestamp": datetime.datetime.now(TZ).isoformat(),
                        "model": model,
                        "response": response_text,
                        "finish_reason": finish_reason,
                        "response_time": end - start,
                        "messages": prepared_messages # Log potentially modified messages
                    }
                    with open(API_RESPONSE_LOG, "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_entry, ensure_ascii=False, indent=2) + "\n")
                except Exception as log_error:
                    print(f"Warning: Failed to log API response: {str(log_error)}")
                    # Continue execution even if logging fails
            
            return response_text
        except Exception as e:
            error_msg = str(e)
            if "JSONDecodeError" in error_msg:
                print(f"Model {model} returned malformed response: {error_msg}")
            else:
                print(f"Error on attempt {attempt} for model {model}: {error_msg}")
            # Add failed model to global set
            FAILED_MODELS.add(model)
            if attempt < max_retries:
                time.sleep(1)
    raise RuntimeError(f"Model call failed after {max_retries} attempts for model {model}")


def extract_top_titles_from_ai(text):
    """Extracts top titles from AI-generated text with multiple fallback strategies."""
    if not text:
        print("Warning: Empty text provided")
        return []
        
    # Try to find the marker by looking for the marker word with any surrounding characters
    marker_index = text.rfind(TITLE_MARKER)
    if marker_index != -1:
        marker_length = len(TITLE_MARKER)
    else:
        # Extract only A-Za-z letters from the marker
        letters = ''.join(c for c in TITLE_MARKER if c.isalpha())
        if letters:
            # If we have letters, look for those words
            marker_index = text.rfind(letters)
            if marker_index != -1:
                marker_length = len(letters)
        else:
            marker_index = -1
            marker_length = 0
    
    # Get lines to process - either after marker or reversed for bottom-up search
    if marker_index != -1:
        # When marker is found, trust the model's formatting and only look at lines immediately after
        text = text[marker_index + marker_length:]
        lines = text.splitlines()
        should_reverse = False
        # Only look at first 10 lines after marker to avoid false positives
        lines = lines[:10]
    else:
        # For bottom-up search, only look at last 15 lines
        lines = text.splitlines()[-15:]
        should_reverse = True
        lines = list(reversed(lines))
    
    # Process the lines
    titles = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Clean up formatting first - combine all regex operations into one
        line = re.sub(r'^\*+|\*+$|^["\']|["\']$|^[-–—]+|[-–—]+$|\*\*|^[-–—\s]+|^[#\s]+|^[•\s]+', '', line)
        line = line.strip()
            
        # Use different regex patterns based on whether we're going forward or backward
        if should_reverse:
            # For bottom-up search, just find numbered lines
            # Pattern explanation:
            # ^ - Start of line
            # \d+ - One or more digits
            # [\.\)\-\s:,]+ - One or more separators (period, parenthesis, dash, space, colon, comma)
            # (.+) - Capture the rest of the line
            match = re.match(r"^\d+[\.\)\-\s:,]+(.+)", line)
            if match:
                title = match.group(1)
            else:
                continue  # Skip unnumbered lines in bottom-up search
        else:
            # When going forward after marker, accept any non-empty line as a potential title
            title = line
                
        # Validate title length and content
        if len(title) >= 10 and len(title) <= 200 and not title.startswith(('http://', 'https://', 'www.')):
            titles.append(title)
            if len(titles) == 3:
                break
    
    if not titles:
        print("Warning: No valid titles found in response")
        return []
        
    # Reverse the titles if we were processing in reverse
    if should_reverse:
        titles = list(reversed(titles))
        
    print(f"Found {len(titles)} valid titles in response")
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
    else: # THIRTY_B mode
        mode_instructions = REPORT_PROMPT
        user_list = "\n".join(article_line(i, article) for i, article in enumerate(filtered_articles, 1))
        messages = [
            {"role": "user", "content": PROMPT_30B.format(mode_instructions=mode_instructions) + "\n" + user_list}
        ]
    return messages

def ask_ai_top_articles(articles):
    """Filters articles, constructs prompt, queries the primary AI, handles fallback (if applicable)."""
    # --- Deduplication (remains the same) ---
    previous_selections = g_c.get("previously_selected_selections_2")
    print(f"Retrieved previous_selections from cache: {len(previous_selections) if previous_selections else 0} entries")
    if previous_selections is None:
        previous_selections = []
        print("No previous selections found in cache")

    previous_embeddings = [get_embedding(sel["title"]) for sel in previous_selections]
    previous_urls = [sel["url"] for sel in previous_selections]
    print(f"Previous URLs in cache: {len(previous_urls)} total")
    if previous_urls:
        print("Most recent URLs in cache:")
        for url in previous_urls[-3:]:  # Show last 3 as examples
            print(f"  - {url}")

    # Log articles being filtered by URL
    print("\nFiltering articles by URL:")
    for article in articles:
        if article["url"] in previous_urls:
            print(f"Filtered by URL match: {article['title']} ({article['url']})")

    articles = [article for article in articles if article["url"] not in previous_urls]
    print(f"\nRemaining articles after URL filtering: {len(articles)}")
    
    # Pass threshold to deduplicate function
    filtered_articles = deduplicate_articles_with_exclusions(articles, previous_embeddings)
    print(f"Remaining articles after embedding filtering: {len(filtered_articles)}")

    if not filtered_articles:
        print("No new articles available after deduplication.")
        return "No new articles to rank.", [], previous_selections, None

    # --- Prepare Messages ---
    messages = _prepare_messages(PROMPT_MODE, filtered_articles)
    print(f"Constructed Prompt (Mode: {PROMPT_MODE}):")
    print(messages)

    # --- Call Primary LLM using the provider class ---
    provider1 = get_provider(PROVIDER, forced_model=None)
    response_text, used_model = provider1.call_with_fallback(
        messages, 
        PROMPT_MODE,
        "Primary"
    )
    
    if not response_text or response_text.startswith("LLM models are currently unavailable"):
        return "No response from LLM models.", [], previous_selections, None

    # --- Process Response and Update Selections (remains the same) ---
    top_titles = extract_top_titles_from_ai(response_text)
    
    # If no headlines extracted, try fallback model
    if not top_titles:
        print("No headlines extracted from primary model, trying fallback model...")
        fallback_model = provider1.fallback_model
        if fallback_model not in FAILED_MODELS:
            try:
                response_text = provider1.call_model(fallback_model, messages, MAX_TOKENS, "Fallback (headline retry)")
                if response_text:
                    top_titles = extract_top_titles_from_ai(response_text)
                    if top_titles:
                        used_model = fallback_model
                        print(f"Successfully extracted headlines using fallback model: {fallback_model}")
                    else:
                        print("Fallback model also failed to extract headlines")
                        FAILED_MODELS.add(fallback_model)
                        return "No headlines could be extracted from AI response.", [], previous_selections, None
            except Exception as e:
                print(f"Fallback model failed during headline retry: {e}")
                traceback.print_exc()
                FAILED_MODELS.add(fallback_model)
                return "Fallback model failed to process headlines.", [], previous_selections, None
        else:
            print(f"Fallback model {fallback_model} was already tried and failed")
            return "No headlines could be extracted from AI response.", [], previous_selections, None
    
    # Only update model cache if we successfully extracted headlines
    if top_titles and used_model:
        update_model_cache(used_model)
    
    top_articles = []
    for title in top_titles:
        best_match = get_best_matching_article(title, filtered_articles)
        if (best_match):
            top_articles.append(best_match)
            print(f"Selected article: {best_match['title']} ({best_match['url']})")
        else:
            print(f"Failed to find match for title: {title}")

    new_selections = [{"url": art["url"], "title": art["title"]}
                      for art in top_articles if art]
    updated_selections = previous_selections + new_selections
    if len(updated_selections) > MAX_PREVIOUS_HEADLINES:
        updated_selections = updated_selections[-MAX_PREVIOUS_HEADLINES:]
        print(f"Trimmed selections to {len(updated_selections)} entries")

    print(f"Updating cache with {len(updated_selections)} selections")
    return response_text, top_articles, updated_selections, used_model


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
    provider = get_provider(PROVIDER, forced_model=None)
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
            "image_url": article.get("image_url"),
            "alt_text": f"headline: {article['title'][:50]}" if article.get("image_url") else None
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
            full_response, top_3_articles_match, updated_selections, used_model = ask_ai_top_articles(articles)

            # Check if AI call failed or returned no usable response
            if not top_3_articles_match and not full_response.startswith("No new articles"):
                print(f"AI processing failed or returned no headlines.")
                # Decide if we should exit or continue without update
                sys.exit(1) # Exit if AI failed critically

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
            generate_headlines_html(top_3_articles_match, html_file, model_name=used_model if SHOW_AI_ATTRIBUTION else None)
                        
            print(f"Appending to archive for mode: {mode}")
            append_to_archive(mode, top_3_articles_match)
            # Update selections cache only on successful normal run completion
            print(f"About to update cache with {len(updated_selections)} selections")
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
    parser.add_argument('--prompt-mode', type=str, help='Set the prompt mode (e.g., o3)')
    parser.add_argument('--use-cached-model', action='store_true', help='Use cached working model instead of random selection')
    parser.add_argument('--force-model', type=str, help='Force the use of a specific model (overrides random/cached selection)')
    args = parser.parse_args()

    # Set USE_RANDOM_MODELS based on command line argument
    USE_RANDOM_MODELS = not args.use_cached_model

    # Revert to CWD-based mode detection
    cwd = os.getcwd()
    selected_mode_enum = None
    selected_mode_str = None

    # Try to find a matching settings file in the current directory
    for mode_enum_val in Mode:
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

    # Handle forceimage case early
    if args.forceimage:
        refresh_images_only(selected_mode_str, None)
        sys.exit(0)

    # Check schedule using the config's SCHEDULE field
    current_hour = datetime.datetime.now(TZ).hour
    should_run = args.force or (loaded_settings_config.SCHEDULE and current_hour in loaded_settings_config.SCHEDULE) or args.dry_run or args.compare

    if not should_run:
        print(f"Skipping update for mode '{selected_mode_str}' based on schedule (Current hour: {current_hour}, Scheduled: {loaded_settings_config.SCHEDULE}). Use --force to override.")
        sys.exit(0)

    # Set RUN_MODE to 'compare' if --compare is specified
    if args.compare:
        RUN_MODE = "compare"

    # Set INCLUDE_ARTICLE_SUMMARY_FOR_LLM from CLI flag
    if args.include_summary:
        INCLUDE_ARTICLE_SUMMARY_FOR_LLM = True

    # Configure primary provider from CLI - only if we're actually going to run
    provider = get_provider(PROVIDER, forced_model=args.force_model)
    MODEL_1 = provider.primary_model
    MODEL_2 = provider.fallback_model

    if args.prompt_mode:
        try:
            prompt_mode_enum = PromptMode(args.prompt_mode.upper())
            PROMPT_MODE = prompt_mode_enum
        except ValueError:
            print(f"Invalid prompt mode specified: {args.prompt_mode}. Using 30B mode.")
            PROMPT_MODE = PromptMode.THIRTY_B

    main(selected_mode_str, loaded_settings_module, loaded_settings_config, dry_run=args.dry_run)


