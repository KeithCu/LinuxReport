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
import random
import logging

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

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Logging configuration
# LOG_LEVEL options: DEBUG, INFO, WARNING, ERROR, CRITICAL
# - DEBUG: Most verbose - shows everything including full AI responses, article lists, etc.
# - INFO: Default level - shows main process steps, counts, success/failure messages
# - WARNING: Shows warnings and errors only
# - ERROR: Shows only errors
# - CRITICAL: Shows only critical errors
# Note: Each level includes all levels above it (INFO includes WARNING, ERROR, CRITICAL)
LOG_LEVEL = "INFO"  # Change to "DEBUG" for maximum verbosity
LOG_FILE = "auto_update.log"  # Single log file that gets appended to

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a'),  # 'a' for append mode
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Log startup information
logger.info(f"Starting auto_update.py with LOG_LEVEL={LOG_LEVEL}")
logger.info(f"Log file: {LOG_FILE}")

# =============================================================================
# ENUMERATIONS AND CONSTANTS
# =============================================================================

class PromptMode(Enum):
    O3 = 'o3'
    THIRTY_B = '30b'  # Represents '30b' prompt

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
MODEL_CACHE_DURATION = EXPIRE_DAY * 7

# Global logging configuration
GLOBAL_LOGGING_ENABLED = True
API_RESPONSE_LOG = "api_responses.jsonl"

# AI Attribution configuration
SHOW_AI_ATTRIBUTION = True  # Set to False to hide AI model attribution in headlines

# Optional: include more article data (summary, etc) in LLM prompt
INCLUDE_ARTICLE_SUMMARY_FOR_LLM = False

# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

# List of free models to try
FREE_MODELS = [
    "agentica-org/deepcoder-14b-preview:free",
    "arliai/qwq-32b-arliai-rpr-v1:free",
    "cognitivecomputations/dolphin3.0-r1-mistral-24b:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "deepseek/deepseek-r1-0528:free",
    "deepseek/deepseek-r1-0528-qwen3-8b:free",
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

# Model selection behavior
USE_RANDOM_MODELS = True  # Set to True to always try random models, False to use cached working model

# Models that don't support system instructions properly and need user-only instructions
USER_ONLY_INSTRUCTION_MODELS = [
    "google/gemma-3-27b-it:free",
    "qwen/qwen3-8b:free",  # Added due to issues with system prompts
]

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

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

# O3-suggested alternate prompt for reasoning models
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

# =============================================================================
# PROVIDER CONFIGURATION
# =============================================================================

# Global tracking with persistence
FAILED_MODELS_CACHE_KEY = "failed_llm_models"
FAILED_MODELS_RETRY_HOURS = 24  # Retry failed models after 24 hours

# Run mode configuration
RUN_MODE = "normal"  # options: "normal", "compare"

# Provider configuration
PROVIDER = "openrouter"

# Configuration for the primary provider/model
MODEL_1 = None

# Configuration for the secondary provider/model (for comparison mode)
MODEL_2 = None  # Will be set based on provider

# Mistral-specific configuration
MISTRAL_EXTRA_PARAMS = {
    "provider": {
        "order": ["Mistral"], # Try to send the request to Mistral first
        "allow_fallbacks": True
    }
}

# Add unified provider client cache (for normal mode)
provider_client_cache = None

# Global URL storage
ALL_URLS = {}  # Initialized here, passed to utils

# =============================================================================
# PROVIDER CLASS HIERARCHY
# =============================================================================

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
            self.model_selector.mark_failed(current_model)
        
        # Let ModelSelector handle all model selection logic
        current_model = self.model_selector.get_next_model(current_model)
        if current_model:
            print(f"\n--- LLM Call: {self.name} / {current_model} / {prompt_mode} {label} (Fallback) ---")
            try:
                response_text = self.call_model(current_model, messages, MAX_TOKENS, f"{label}")
                return response_text, current_model
            except Exception as e:
                print(f"Fallback model {current_model} failed: {str(e)}")
                self.model_selector.mark_failed(current_model)
        
        return None, None
    
    def __str__(self) -> str:
        return f"{self.name} Provider (primary: {self.primary_model}, fallback: {self.fallback_model})"


def update_model_cache(model):
    """Update the cache with the currently working model if it's different."""
    current_model = g_c.get("working_llm_model")
    if current_model == model:
        logger.debug(f"Model {model} already cached, no update needed")
        return
    g_c.put("working_llm_model", model, timeout=MODEL_CACHE_DURATION)
    logger.info(f"Updated cached working model from {current_model} to: {model}")

class ModelSelector:
    """Simple model selection and fallback logic."""
    
    def __init__(self, use_random=True, forced_model=None):
        self.use_random = use_random
        self.forced_model = forced_model
        self.cache = g_c
        self._load_failed_models()
        logger.info(f"ModelSelector initialized: use_random={use_random}, forced_model={forced_model}")
        
    def _load_failed_models(self):
        """Load failed models from cache with timestamp."""
        failed_models_data = self.cache.get(FAILED_MODELS_CACHE_KEY) or {}
        current_time = time.time()
        
        # Filter out models that have been failed for too long
        self.failed_models = {
            model for model, fail_time in failed_models_data.items()
            if current_time - fail_time < FAILED_MODELS_RETRY_HOURS * 3600
        }
        
        logger.debug(f"Loaded {len(self.failed_models)} failed models from cache")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Failed models: {list(self.failed_models)}")
        
    def mark_failed(self, model):
        """Mark a model as failed with timestamp."""
        if model not in FREE_MODELS:
            logger.warning(f"Attempted to mark unknown model as failed: {model}")
            return
            
        failed_models_data = self.cache.get(FAILED_MODELS_CACHE_KEY) or {}
        failed_models_data[model] = time.time()
        self.cache.put(FAILED_MODELS_CACHE_KEY, failed_models_data, timeout=EXPIRE_WEEK)
        self.failed_models.add(model)
        logger.info(f"Marked model as failed: {model}")
        
    def mark_success(self, model):
        """Mark a model as successful and update cache."""
        if model not in FREE_MODELS:
            logger.warning(f"Attempted to mark unknown model as successful: {model}")
            return
            
        if model != self.forced_model:  # Don't cache forced models
            self.cache.put("working_llm_model", model, timeout=MODEL_CACHE_DURATION)
            logger.info(f"Cached working model: {model}")
            
        # Remove from failed models if it was there
        if model in self.failed_models:
            self.failed_models.remove(model)
            failed_models_data = self.cache.get(FAILED_MODELS_CACHE_KEY) or {}
            if model in failed_models_data:
                del failed_models_data[model]
                self.cache.put(FAILED_MODELS_CACHE_KEY, failed_models_data, timeout=EXPIRE_WEEK)
            logger.info(f"Removed model from failed list: {model}")
            
    def get_next_model(self, current_model=None):
        """Get the next model to try."""
        # Reload failed models to check for retry eligibility
        self._load_failed_models()
        
        # 1. Forced model takes precedence
        if self.forced_model:
            logger.debug(f"Using forced model: {self.forced_model}")
            return self.forced_model
            
        # 2. Try cached model if not using random selection
        if not self.use_random:
            cached_model = self.cache.get("working_llm_model")
            if cached_model and cached_model not in self.failed_models:
                logger.debug(f"Using cached model: {cached_model}")
                return cached_model
                
        # 3. Try random available model
        available_models = [m for m in FREE_MODELS if m not in self.failed_models and m != current_model]
        if available_models:
            selected_model = random.choice(available_models)
            logger.debug(f"Selected random model: {selected_model} from {len(available_models)} available")
            return selected_model
            
        # 4. Final fallback
        if FALLBACK_MODEL not in self.failed_models:
            logger.debug(f"Using fallback model: {FALLBACK_MODEL}")
            return FALLBACK_MODEL
        else:
            logger.error("No models available - all models have failed")
            return None
        
    def get_model_status(self):
        """Get current status of all models."""
        self._load_failed_models()  # Refresh status
        status = {
            "forced_model": self.forced_model,
            "use_random": self.use_random,
            "failed_models": list(self.failed_models),
            "cached_model": self.cache.get("working_llm_model"),
            "available_models": [m for m in FREE_MODELS if m not in self.failed_models]
        }
        logger.debug(f"Model status: {status}")
        return status

class OpenRouterProvider(LLMProvider):
    """Provider implementation for OpenRouter."""
    
    def __init__(self, forced_model=None):
        super().__init__("openrouter")
        self.model_selector = ModelSelector(use_random=USE_RANDOM_MODELS, forced_model=forced_model)
        self._selected_model = self.model_selector.get_next_model()
        logger.info(f"OpenRouterProvider initialized with selected model: {self._selected_model}")
    
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
        logger.debug(f"OpenRouter headers configured: {headers}")
        
    def call_with_fallback(self, messages: List[Dict[str, str]], prompt_mode: str, label: str = "") -> Tuple[Optional[str], Optional[str]]:
        """Call models with fallback strategy."""
        current_model = self.primary_model
        max_attempts = 3  # Try up to 3 different models
        
        logger.info(f"Starting model calls with fallback strategy (max attempts: {max_attempts})")
        
        for attempt in range(max_attempts):
            logger.info(f"Attempt {attempt + 1}/{max_attempts}: {self.name} / {current_model} / {prompt_mode} {label}")
            
            try:
                response_text = self.call_model(current_model, messages, MAX_TOKENS, f"{label}")
                if response_text:
                    self.model_selector.mark_success(current_model)
                    logger.info(f"Successfully got response from {current_model}")
                    return response_text, current_model
            except Exception as e:
                logger.error(f"Model {current_model} failed: {str(e)}")
                self.model_selector.mark_failed(current_model)
            
            # Let ModelSelector handle all model selection logic
            current_model = self.model_selector.get_next_model(current_model)
            if not current_model:
                logger.error("No more models available to try")
                break
                
        logger.error("All model attempts failed")
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
        logger.info(f"Calling model {model} (attempt {attempt}/{max_retries})")
        
        prepared_messages = list(messages) # Make a copy to potentially modify

        # If the model requires user-only instructions and the current message structure
        # is [system_prompt, user_prompt] (typical for O3 mode), combine them.
        if model in USER_ONLY_INSTRUCTION_MODELS and \
           len(prepared_messages) == 2 and \
           prepared_messages[0].get("role") == "system" and \
           prepared_messages[1].get("role") == "user":
            
            logger.debug(f"Model {model} requires user-only instructions. Combining system and user prompts.")
            system_content = prepared_messages[0]["content"]
            user_content = prepared_messages[1]["content"]
            
            combined_user_content = f"{system_content}\n\n{user_content}"
            prepared_messages = [{"role": "user", "content": combined_user_content}]
            logger.debug(f"Combined message length: {len(combined_user_content)} characters")

        try:
            if 'mistral' in model.lower():
                extra_params = MISTRAL_EXTRA_PARAMS
                logger.debug(f"Using Mistral extra params: {extra_params}")
            else:
                extra_params = {}
                
            logger.debug(f"Making API call to {model} with {len(prepared_messages)} messages, max_tokens={max_tokens}")
            
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
            response_time = end - start
            
            logger.info(f"Model {model} responded in {response_time:.3f}s, finish_reason: {finish_reason}")
            logger.debug(f"Response length: {len(response_text)} characters")
            
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Full response from {model}:\n{response_text}")
            
            # Log the API response only if global logging is enabled
            if GLOBAL_LOGGING_ENABLED:
                try:
                    log_entry = {
                        "timestamp": datetime.datetime.now(TZ).isoformat(),
                        "model": model,
                        "response": response_text,
                        "finish_reason": finish_reason,
                        "response_time": response_time,
                        "messages": prepared_messages # Log potentially modified messages
                    }
                    with open(API_RESPONSE_LOG, "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_entry, ensure_ascii=False, indent=2) + "\n")
                    logger.debug(f"Logged API response to {API_RESPONSE_LOG}")
                except Exception as log_error:
                    logger.warning(f"Failed to log API response: {str(log_error)}")
                    # Continue execution even if logging fails
            
            return response_text
        except Exception as e:
            error_msg = str(e)
            if "JSONDecodeError" in error_msg:
                logger.error(f"Model {model} returned malformed response: {error_msg}")
            else:
                logger.error(f"Error on attempt {attempt} for model {model}: {error_msg}")
            # Add failed model to global set
            if attempt < max_retries:
                logger.debug(f"Waiting 1 second before retry...")
                time.sleep(1)
    logger.error(f"Model call failed after {max_retries} attempts for model {model}")
    raise RuntimeError(f"Model call failed after {max_retries} attempts for model {model}")


def extract_top_titles_from_ai(text):
    """Extracts top titles from AI-generated text with multiple fallback strategies."""
    if not text:
        logger.warning("Empty text provided to extract_top_titles_from_ai")
        return []
    
    logger.debug(f"Extracting titles from AI response (length: {len(text)})")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Full AI response:\n{text}")
        
    # Try to find the marker by looking for the marker word with any surrounding characters
    marker_index = text.rfind(TITLE_MARKER)
    if marker_index != -1:
        marker_length = len(TITLE_MARKER)
        logger.debug(f"Found title marker '{TITLE_MARKER}' at position {marker_index}")
    else:
        # Extract only A-Za-z letters from the marker
        letters = ''.join(c for c in TITLE_MARKER if c.isalpha())
        if letters:
            # If we have letters, look for those words
            marker_index = text.rfind(letters)
            if marker_index != -1:
                marker_length = len(letters)
                logger.debug(f"Found partial marker '{letters}' at position {marker_index}")
        else:
            marker_index = -1
            marker_length = 0
            logger.debug("No title marker found")
    
    # Get lines to process - either after marker or reversed for bottom-up search
    if marker_index != -1:
        # When marker is found, trust the model's formatting and only look at lines immediately after
        text = text[marker_index + marker_length:]
        lines = text.splitlines()
        should_reverse = False
        # Only look at first 10 lines after marker to avoid false positives
        lines = lines[:10]
        logger.debug(f"Processing {len(lines)} lines after marker (forward search)")
    else:
        # For bottom-up search, only look at last 15 lines
        lines = text.splitlines()[-15:]
        should_reverse = True
        lines = list(reversed(lines))
        logger.debug(f"Processing {len(lines)} lines from end (reverse search)")
    
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Lines to process:")
        for i, line in enumerate(lines):
            logger.debug(f"  Line {i+1}: '{line}'")
    
    # Process the lines
    titles = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            logger.debug(f"  Skipping empty line {i+1}")
            continue

        # Clean up formatting first - combine all regex operations into one
        # Remove: asterisks, quotes, dashes, bullets, numbers with periods, extra whitespace
        original_line = line
        line = re.sub(r'^\*+|\*+$|^["\']|["\']$|^[-–—]+|[-–—]+$|\*\*|^[-–—\s]+|^[#\s]+|^[•\s]+|^\d+\.?\s*', '', line)
        line = line.strip()
        
        logger.debug(f"  Line {i+1} cleanup: '{original_line}' -> '{line}'")
            
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
                logger.debug(f"  Line {i+1} matched numbered pattern: '{title}'")
            else:
                logger.debug(f"  Line {i+1} did not match numbered pattern, skipping")
                continue  # Skip unnumbered lines in bottom-up search
        else:
            # When going forward after marker, accept any non-empty line as a potential title
            title = line
            logger.debug(f"  Line {i+1} accepted as potential title: '{title}'")
                
        # Validate title length and content
        if len(title) >= 10 and len(title) <= 200 and not title.startswith(('http://', 'https://', 'www.')):
            titles.append(title)
            logger.debug(f"  Line {i+1} validated and added: '{title}'")
            if len(titles) == 3:
                logger.debug(f"  Reached 3 titles, stopping extraction")
                break
        else:
            logger.debug(f"  Line {i+1} failed validation (length: {len(title)}, starts with URL: {title.startswith(('http://', 'https://', 'www.'))}): '{title}'")
    
    if not titles:
        logger.warning("No valid titles found in response")
        return []
        
    # Reverse the titles if we were processing in reverse
    if should_reverse:
        titles = list(reversed(titles))
        logger.debug("Reversed titles order due to reverse processing")
        
    logger.info(f"Successfully extracted {len(titles)} valid titles")
    if logger.isEnabledFor(logging.DEBUG):
        for i, title in enumerate(titles, 1):
            logger.debug(f"  Final title {i}: '{title}'")
    
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

def _try_fallback_model(provider1, messages, filtered_articles, reason):
    """Try fallback model and return (success, top_articles, used_model)"""
    fallback_model = provider1.fallback_model
    logger.info(f"Attempting fallback model '{fallback_model}' due to: {reason}")
    
    if fallback_model not in provider1.model_selector.failed_models:
        try:
            response_text = provider1.call_model(fallback_model, messages, MAX_TOKENS, f"Fallback ({reason})")
            if response_text:
                logger.info("Fallback model returned response, extracting titles")
                top_titles = extract_top_titles_from_ai(response_text)
                if top_titles:
                    logger.info(f"Successfully extracted {len(top_titles)} headlines using fallback model: {fallback_model}")
                    # Process articles with new titles
                    top_articles = []
                    for i, title in enumerate(top_titles, 1):
                        logger.debug(f"Fallback matching title {i}: {title}")
                        best_match = get_best_matching_article(title, filtered_articles)
                        if (best_match):
                            top_articles.append(best_match)
                            logger.info(f"Fallback selected article {i}: {best_match['title']} ({best_match['url']})")
                        else:
                            logger.warning(f"Fallback failed to find match for title: {title}")
                    return True, top_articles, fallback_model
                else:
                    logger.warning("Fallback model also failed to extract headlines")
                    provider1.model_selector.mark_failed(fallback_model)
            return False, [], None
        except Exception as e:
            logger.error(f"Fallback model failed during {reason}: {e}")
            traceback.print_exc()
            provider1.model_selector.mark_failed(fallback_model)
            return False, [], None
    else:
        logger.warning(f"Fallback model {fallback_model} was already tried and failed")
        return False, [], None

def ask_ai_top_articles(articles):
    """Filters articles, constructs prompt, queries the primary AI, handles fallback (if applicable)."""
    logger.info(f"Starting AI article selection with {len(articles)} total articles")
    
    # --- Deduplication (remains the same) ---
    previous_selections = g_c.get("previously_selected_selections_2")
    logger.info(f"Retrieved previous_selections from cache: {len(previous_selections) if previous_selections else 0} entries")
    if previous_selections is None:
        previous_selections = []
        logger.info("No previous selections found in cache")

    previous_embeddings = [get_embedding(sel["title"]) for sel in previous_selections]
    previous_urls = [sel["url"] for sel in previous_selections]
    
    logger.debug(f"Previous URLs for filtering: {previous_urls}")

    # Log articles being filtered by URL
    logger.info("Filtering articles by URL to avoid duplicates")
    original_count = len(articles)
    articles = [article for article in articles if article["url"] not in previous_urls]
    filtered_count = len(articles)
    logger.info(f"URL filtering: {original_count} -> {filtered_count} articles (removed {original_count - filtered_count})")
    
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Articles after URL filtering:")
        for i, article in enumerate(articles, 1):
            logger.debug(f"  {i}. {article['title']} ({article['url']})")
    
    # Pass threshold to deduplicate function
    logger.info("Applying embedding-based deduplication")
    filtered_articles = deduplicate_articles_with_exclusions(articles, previous_embeddings)
    logger.info(f"Embedding filtering: {filtered_count} -> {len(filtered_articles)} articles (removed {filtered_count - len(filtered_articles)})")
    
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Articles after embedding filtering:")
        for i, article in enumerate(filtered_articles, 1):
            logger.debug(f"  {i}. {article['title']} ({article['url']})")

    if not filtered_articles:
        logger.warning("No new articles available after deduplication.")
        return "No new articles to rank.", [], previous_selections, None

    # --- Prepare Messages ---
    messages = _prepare_messages(PROMPT_MODE, filtered_articles)
    logger.info(f"Constructed prompt for {PROMPT_MODE} mode with {len(filtered_articles)} articles")
    
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Prompt messages:")
        for i, msg in enumerate(messages):
            logger.debug(f"  Message {i+1} ({msg['role']}): {msg['content'][:200]}...")

    # --- Call Primary LLM using the provider class ---
    provider1 = get_provider(PROVIDER, forced_model=None)
    response_text, used_model = provider1.call_with_fallback(
        messages, 
        PROMPT_MODE,
        "Primary"
    )
    
    if not response_text or response_text.startswith("LLM models are currently unavailable"):
        logger.error("No response from LLM models")
        return "No response from LLM models.", [], previous_selections, None

    # --- Process Response and Update Selections (remains the same) ---
    logger.info("Extracting top titles from AI response")
    top_titles = extract_top_titles_from_ai(response_text)
    logger.info(f"Extracted {len(top_titles)} titles from AI response")
    
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Extracted titles:")
        for i, title in enumerate(top_titles, 1):
            logger.debug(f"  {i}. {title}")
    
    # If no headlines extracted, try fallback model
    if not top_titles:
        logger.warning("No headlines extracted from primary model, trying fallback model...")
        success, top_articles, used_model = _try_fallback_model(provider1, messages, filtered_articles, "headline retry")
        if success:
            return response_text, top_articles, previous_selections, used_model
        else:
            logger.error("No headlines could be extracted from AI response")
            return "No headlines could be extracted from AI response.", [], previous_selections, None
    
    logger.info("Matching extracted titles to articles")
    top_articles = []
    for i, title in enumerate(top_titles, 1):
        logger.debug(f"Matching title {i}: {title}")
        best_match = get_best_matching_article(title, filtered_articles)
        if (best_match):
            top_articles.append(best_match)
            logger.info(f"Selected article {i}: {best_match['title']} ({best_match['url']})")
        else:
            logger.warning(f"Failed to find match for title: {title}")

    logger.info(f"Successfully matched {len(top_articles)} articles out of {len(top_titles)} titles")

    # If fewer than 3 articles found, try fallback model
    if len(top_articles) < 3:
        logger.warning(f"Only {len(top_articles)} articles found, trying fallback model...")
        success, top_articles, used_model = _try_fallback_model(provider1, messages, filtered_articles, "article count retry")
        if success:
            return response_text, top_articles, previous_selections, used_model
        else:
            logger.error("No headlines could be extracted from AI response")
            return "No headlines could be extracted from AI response.", [], previous_selections, None

    # Only update model cache if we successfully got 3 articles
    if len(top_articles) >= 3 and used_model:
        update_model_cache(used_model)

    # Check for duplicate URLs in selected articles
    selected_urls = [art["url"] for art in top_articles if art]
    unique_urls = set(selected_urls)
    if len(selected_urls) != len(unique_urls):
        logger.error(f"DUPLICATE DETECTED: {len(selected_urls)} selected URLs but only {len(unique_urls)} unique URLs")
        logger.error(f"Selected URLs: {selected_urls}")
        logger.error(f"Unique URLs: {list(unique_urls)}")
        # Find the duplicates
        from collections import Counter
        url_counts = Counter(selected_urls)
        duplicates = [url for url, count in url_counts.items() if count > 1]
        logger.error(f"Duplicate URLs: {duplicates}")
        
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Full article details for debugging:")
            for i, article in enumerate(top_articles):
                logger.debug(f"  Article {i+1}: {article['title']} ({article['url']})")
    else:
        logger.info(f"All {len(top_articles)} selected articles have unique URLs")

    new_selections = [{"url": art["url"], "title": art["title"]}
                      for art in top_articles if art]
    updated_selections = previous_selections + new_selections
    if len(updated_selections) > MAX_PREVIOUS_HEADLINES:
        updated_selections = updated_selections[-MAX_PREVIOUS_HEADLINES:]
        logger.info(f"Trimmed selections to {len(updated_selections)} entries")

    logger.info(f"Updating cache with {len(updated_selections)} selections")
    g_c.put("previously_selected_selections_2", updated_selections, timeout=EXPIRE_WEEK)
    logger.info(f"Cache update status: {g_c.get('previously_selected_selections_2') is not None}")
    return response_text, top_articles, updated_selections, used_model


def run_comparison(articles):
    """Runs two LLM calls with different configurations for comparison."""
    logger.info("--- Running Comparison Mode ---")

    # --- Deduplication (same as ask_ai_top_articles) ---
    previous_selections = g_c.get("previously_selected_selections_2") or []
    previous_embeddings = [get_embedding(sel["title"]) for sel in previous_selections]
    previous_urls = [sel["url"] for sel in previous_selections]
    articles = [article for article in articles if article["url"] not in previous_urls]
    filtered_articles = deduplicate_articles_with_exclusions(articles, previous_embeddings)

    logger.info(f"Comparison mode: {len(articles)} articles after deduplication")

    if not filtered_articles:
        logger.warning("No new articles available after deduplication for comparison.")
        return

    # --- Config 1 ---
    provider = get_provider(PROVIDER, forced_model=None)
    model1, model2 = provider.get_comparison_models()
    logger.info(f"Comparison model 1: {model1}")
    logger.info(f"Comparison model 2: {model2}")
    
    messages1 = _prepare_messages(PROMPT_MODE, filtered_articles)
    response_text1 = provider.call_model(model1, messages1, MAX_TOKENS, 'Comparison 1')
    
    if not response_text1:
        logger.error(f"Comparison 1 failed for {PROVIDER}")

    # --- Config 2 ---
    messages2 = _prepare_messages(PROMPT_MODE, filtered_articles)
    response_text2 = provider.call_model(model2, messages2, MAX_TOKENS, 'Comparison 2')
    
    if not response_text2:
        logger.error(f"Comparison 2 failed for {PROVIDER}")

    logger.info("--- Comparison Mode Finished ---")


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
def main(mode, settings_module, settings_config, dry_run=False): # Add dry_run parameter
    global ALL_URLS, REPORT_PROMPT
    ALL_URLS = settings_config.ALL_URLS
    REPORT_PROMPT = settings_config.REPORT_PROMPT
    SITE_PATH = settings_config.PATH  # Get the site's path from its config

    logger.info(f"Starting main processing for mode: {mode}")
    logger.info(f"Site path: {SITE_PATH}")
    logger.info(f"Report prompt: {REPORT_PROMPT}")
    logger.info(f"Number of URLs configured: {len(ALL_URLS)}")
    
    if dry_run:
        logger.info("Running in DRY RUN mode - no files will be updated")

    html_file = f"{mode}reportabove.html"

    try:
        # Pass ALL_URLS and cache to fetch_recent_articles
        logger.info("Fetching recent articles from configured URLs")
        articles = fetch_recent_articles(ALL_URLS, g_c)
        if not articles:
            logger.error(f"No articles found for mode: {mode}")
            sys.exit(1) # Keep exit for no articles

        logger.info(f"Fetched {len(articles)} articles from {len(ALL_URLS)} URLs")

        # --- Handle Run Modes ---
        if RUN_MODE == "compare":
            logger.info("Running in comparison mode")
            run_comparison(articles)
            # Comparison mode implies dry-run, so we exit here
            logger.info("Exiting after comparison run.")
            sys.exit(0)
        elif RUN_MODE == "normal":
            logger.info("Running in normal mode")
            full_response, top_3_articles_match, updated_selections, used_model = ask_ai_top_articles(articles)

            # Check if AI call failed or returned no usable response
            if not top_3_articles_match and not full_response.startswith("No new articles"):
                logger.error("AI processing failed or returned no headlines.")
                # Decide if we should exit or continue without update
                sys.exit(1) # Exit if AI failed critically

            if dry_run:
                logger.info("--- Dry Run Mode: Skipping file generation and archive update. ---")
                sys.exit(0) # Exit after dry run

            # --- Normal Run: Generate HTML and Archive ---
            if not top_3_articles_match:
                logger.warning("No top articles identified by AI. Skipping update.")
                sys.exit(0) # Exit gracefully if AI didn't pick articles

            # Fetch largest images in-line for each headline
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
                    
            # Render HTML and archive with images
            logger.info(f"Generating HTML file: {html_file}")
            # Pass headline_template to generate_headlines_html
            generate_headlines_html(top_3_articles_match, html_file, model_name=used_model if SHOW_AI_ATTRIBUTION else None)
                        
            logger.info(f"Appending to archive for mode: {mode}")
            append_to_archive(mode, top_3_articles_match)
            # Update selections cache only on successful normal run completion
            logger.info(f"About to update cache with {len(updated_selections)} selections")
            g_c.put("previously_selected_selections_2", updated_selections, timeout=EXPIRE_WEEK)
            logger.info("Successfully updated headlines and archive.")

        else:
            logger.error(f"Unknown RUN_MODE: {RUN_MODE}. Exiting.")
            sys.exit(1)

    except FileNotFoundError as e: # Specific error
        logger.error(f"Configuration file error for mode {mode}: {e}")
        sys.exit(1)
    except ImportError as e: # Specific error
        logger.error(f"Error importing settings for mode {mode}: {e}")
        sys.exit(1)
    except Exception as e: # Keep general for other unexpected errors during main execution
        logger.error(f"Error in mode {mode}: {e}")
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

    logger.info("Command line arguments parsed")
    logger.info(f"Arguments: force={args.force}, forceimage={args.forceimage}, dry_run={args.dry_run}, compare={args.compare}, include_summary={args.include_summary}, prompt_mode={args.prompt_mode}, use_cached_model={args.use_cached_model}, force_model={args.force_model}")

    # Set USE_RANDOM_MODELS based on command line argument
    USE_RANDOM_MODELS = not args.use_cached_model
    logger.info(f"USE_RANDOM_MODELS set to: {USE_RANDOM_MODELS}")

    # Revert to CWD-based mode detection
    cwd = os.getcwd()
    logger.info(f"Current working directory: {cwd}")
    selected_mode_enum = None
    selected_mode_str = None

    # Try to find a matching settings file in the current directory
    for mode_enum_val in Mode:
        settings_file = f"{mode_enum_val.value}_report_settings.py"
        if os.path.isfile(settings_file):
            logger.debug(f"Found settings file: {settings_file}")
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
                logger.info(f"Matched mode '{selected_mode_str}' with path {module.CONFIG.PATH}")
                break
            else:
                logger.debug(f"Settings file {settings_file} path mismatch: {module.CONFIG.PATH} != {cwd}")

    if selected_mode_enum is None:
        logger.error(f"Could not determine mode from current directory: {cwd}")
        logger.error("Expected to find a settings file with a matching PATH in the current directory.")
        sys.exit(1)

    logger.info(f"Detected mode '{selected_mode_str}' based on current directory.")

    # Handle forceimage case early
    if args.forceimage:
        logger.info("Running in forceimage mode - only refreshing images")
        refresh_images_only(selected_mode_str, None)
        sys.exit(0)

    # Check schedule using the config's SCHEDULE field
    current_hour = datetime.datetime.now(TZ).hour
    should_run = args.force or (loaded_settings_config.SCHEDULE and current_hour in loaded_settings_config.SCHEDULE) or args.dry_run or args.compare

    logger.info(f"Schedule check: current_hour={current_hour}, scheduled_hours={loaded_settings_config.SCHEDULE}, should_run={should_run}")

    if not should_run:
        logger.info(f"Skipping update for mode '{selected_mode_str}' based on schedule (Current hour: {current_hour}, Scheduled: {loaded_settings_config.SCHEDULE}). Use --force to override.")
        sys.exit(0)

    # Set RUN_MODE to 'compare' if --compare is specified
    if args.compare:
        RUN_MODE = "compare"
        logger.info("Set RUN_MODE to 'compare'")

    # Set INCLUDE_ARTICLE_SUMMARY_FOR_LLM from CLI flag
    if args.include_summary:
        INCLUDE_ARTICLE_SUMMARY_FOR_LLM = True
        logger.info("Set INCLUDE_ARTICLE_SUMMARY_FOR_LLM to True")

    # Configure primary provider from CLI - only if we're actually going to run
    provider = get_provider(PROVIDER, forced_model=args.force_model)
    MODEL_1 = provider.primary_model
    MODEL_2 = provider.fallback_model
    logger.info(f"Configured provider: {PROVIDER}, MODEL_1={MODEL_1}, MODEL_2={MODEL_2}")

    if args.prompt_mode:
        try:
            prompt_mode_enum = PromptMode(args.prompt_mode.upper())
            PROMPT_MODE = prompt_mode_enum
            logger.info(f"Set PROMPT_MODE to {PROMPT_MODE}")
        except ValueError:
            logger.warning(f"Invalid prompt mode specified: {args.prompt_mode}. Using 30B mode.")
            PROMPT_MODE = PromptMode.THIRTY_B

    logger.info("Starting main processing...")
    main(selected_mode_str, loaded_settings_module, loaded_settings_config, dry_run=args.dry_run)


