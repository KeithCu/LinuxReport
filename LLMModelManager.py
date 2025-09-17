import time
import random
import logging
from shared import g_c

# =============================================================================
# MODEL CONFIGURATION CONSTANTS
# =============================================================================

# List of free models to try
FREE_MODELS = [
    "agentica-org/deepcoder-14b-preview:free",
    "arliai/qwq-32b-arliai-rpr-v1:free",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
    "cognitivecomputations/dolphin3.0-mistral-24b:free",
    "cognitivecomputations/dolphin3.0-r1-mistral-24b:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "deepseek/deepseek-chat-v3.1:free",
    # "deepseek/deepseek-chat:free", # Removed by openrouter.ai on: 2025-08-01
    "deepseek/deepseek-r1-0528-qwen3-8b:free",
    "deepseek/deepseek-r1-0528:free",
    "deepseek/deepseek-r1-distill-llama-70b:free",
    "deepseek/deepseek-r1-distill-qwen-14b:free",
    # "deepseek/deepseek-r1-distill-qwen-32b:free", # Removed by openrouter.ai on: 2025-08-01
    "deepseek/deepseek-r1:free",
    # "deepseek/deepseek-v3-base:free", # Removed by openrouter.ai on: 2025-08-01
    # "featherless/qwerky-72b:free", # Removed by openrouter.ai on: 2025-09-07
    "google/gemini-2.0-flash-exp:free",
    "google/gemini-2.5-pro-exp-03-25",
    "google/gemma-2-9b-it:free",
    "google/gemma-3-12b-it:free",
    "google/gemma-3-27b-it:free",
    "google/gemma-3-4b-it:free",
    "google/gemma-3n-e2b-it:free",
    "google/gemma-3n-e4b-it:free",
    "meta-llama/llama-3.1-405b-instruct:free",
    # "meta-llama/llama-3.2-11b-vision-instruct:free", # Removed by openrouter.ai on: 2025-09-07
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    # "meta-llama/llama-3.3-8b-instruct:free", # Removed by openrouter.ai on: 2025-08-01
    # "meta-llama/llama-4-maverick:free", # Removed by openrouter.ai on: 2025-08-01
    # "meta-llama/llama-4-scout:free", # Removed by openrouter.ai on: 2025-08-01
    "microsoft/mai-ds-r1:free",
  #  "microsoft/phi-4-reasoning-plus:free", very long answers, often fails to follow instructions
  #  "microsoft/phi-4-reasoning:free", 
    "mistralai/devstral-small-2505:free",
    # "mistralai/devstral-small:free", # Removed by openrouter.ai on: 2025-08-01
    "mistralai/mistral-7b-instruct:free",
    "mistralai/mistral-nemo:free",
    "mistralai/mistral-small-24b-instruct-2501:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "mistralai/mistral-small-3.2-24b-instruct:free",
    "moonshotai/kimi-dev-72b:free",
    "moonshotai/kimi-k2:free",
    "moonshotai/kimi-vl-a3b-thinking:free",
    # "moonshotai/moonlight-16b-a3b-instruct:free", # Removed by openrouter.ai on: 2025-08-01
    "nousresearch/deephermes-3-llama-3-8b-preview:free",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1:free",
    # "nvidia/llama-3.3-nemotron-super-49b-v1:free", # Removed by openrouter.ai on: 2025-08-01
   # "open-r1/olympiccoder-32b:free", Generates too many tokens
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    # "opengvlab/internvl3-14b:free", # Removed by openrouter.ai on: 2025-08-01
    # "openrouter/cypher-alpha:free", # Removed by openrouter.ai on: 2025-08-01
    # "openrouter/horizon-alpha", # Removed by openrouter.ai on: 2025-08-10
    "openrouter/sonoma-dusk-alpha",
    "openrouter/sonoma-sky-alpha",
    "qwen/qwen-2.5-72b-instruct:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "qwen/qwen2.5-vl-32b-instruct:free",
    "qwen/qwen2.5-vl-72b-instruct:free",
    "qwen/qwen3-14b:free",
    "qwen/qwen3-235b-a22b:free",
    "qwen/qwen3-30b-a3b:free",
    # "qwen/qwen3-32b:free", # Removed by openrouter.ai on: 2025-08-01
    "qwen/qwen3-4b:free",
    "qwen/qwen3-8b:free",
    "qwen/qwen3-coder:free",
    "qwen/qwq-32b:free",
    "rekaai/reka-flash-3:free",
    # "sarvamai/sarvam-m:free", # Removed by openrouter.ai on: 2025-09-07
    "shisa-ai/shisa-v2-llama3.3-70b:free",
    "tencent/hunyuan-a13b-instruct:free",
    # "thudm/glm-4-32b:free", # Removed by openrouter.ai on: 2025-08-10
    # "thudm/glm-z1-32b:free", # Removed by openrouter.ai on: 2025-09-07
    "tngtech/deepseek-r1t-chimera:free",
    "tngtech/deepseek-r1t2-chimera:free",
    "z-ai/glm-4.5-air:free",
]

# Fallback model to use if all free models fail
FALLBACK_MODEL = "mistralai/mistral-small-3.2-24b-instruct"

# Models that don't support system instructions properly and need user-only instructions
USER_ONLY_INSTRUCTION_MODELS = [
    "google/gemma-2-9b-it:free",  # Google Gemma models don't support system instructions
    "google/gemma-3-12b-it:free",  # Google Gemma models don't support system instructions
    "google/gemma-3-27b-it:free",
    "google/gemma-3-4b-it:free",  # Added due to "Developer instruction is not enabled" error
    "google/gemma-3n-e4b-it:free",  # Google Gemma models don't support system instructions
    "qwen/qwen3-8b:free",  # Added due to issues with system prompts
]

# Global tracking with persistence
FAILED_MODELS_CACHE_KEY = "failed_llm_models"

# Cache duration (30 days)
MODEL_CACHE_DURATION = 30 * 24 * 60 * 60  # 30 days in seconds

# Mistral-specific configuration
MISTRAL_EXTRA_PARAMS = {
    "provider": {
        "order": ["Mistral"], # Try to send the request to Mistral first
        "allow_fallbacks": True
    }
}

# Set up logger
logger = logging.getLogger(__name__)

class LLMModelManager:
    """Manages model selection, caching, and failure tracking.
    
    This class consolidates all model management logic including:
    - Model selection (random, cached, forced, fallback)
    - Failure tracking and blacklisting
    - Success caching
    - Model-specific behavior detection
    
    All model-related operations should go through this class to ensure
    consistent behavior and proper caching.
    """
    
    def __init__(self, cache_duration=None):
        """Initialize the model manager.
        
        Args:
            cache_duration: Duration in seconds for caching. Defaults to MODEL_CACHE_DURATION.
        """
        self.cache_duration = cache_duration or MODEL_CACHE_DURATION
        self.failed_models_cache_key = FAILED_MODELS_CACHE_KEY
        self.working_model_cache_key = "working_llm_model"
        
    def get_failed_models(self):
        """Get the set of currently failed models."""
        failed_models_data = g_c.get(self.failed_models_cache_key) or {}
        current_time = time.time()
        
        # Filter out models that have been failed for too long
        failed_models = {
            model for model, fail_time in failed_models_data.items()
            if current_time - fail_time < self.cache_duration
        }
        
        logger.debug(f"Loaded {len(failed_models)} failed models from cache")
        return failed_models
    
    def mark_failed(self, model):
        """Mark a model as failed with timestamp."""
        if model not in FREE_MODELS:
            logger.warning(f"Attempted to mark unknown model as failed: {model}")
            return
            
        failed_models_data = g_c.get(self.failed_models_cache_key) or {}
        failed_models_data[model] = time.time()
        g_c.put(self.failed_models_cache_key, failed_models_data, timeout=self.cache_duration)
        logger.info(f"Marked model as failed: {model}")
    
    def mark_success(self, model, forced_model=None):
        """Mark a model as successful and update cache."""
        if model not in FREE_MODELS:
            logger.warning(f"Attempted to mark unknown model as successful: {model}")
            return
            
        if model != forced_model:  # Don't cache forced models
            g_c.put(self.working_model_cache_key, model, timeout=self.cache_duration)
            logger.info(f"Cached working model: {model}")
    
    def get_available_model(self, use_random=True, forced_model=None, current_model=None):
        """Get the next available model to try.
        
        Args:
            use_random: Whether to use random selection or cached model
            forced_model: Specific model to use (takes precedence)
            current_model: Current model to avoid selecting again
            
        Returns:
            Model name or None if no models available
        """
        failed_models = self.get_failed_models()
        
        # 1. Forced model takes precedence
        if forced_model:
            logger.debug(f"Using forced model: {forced_model}")
            return forced_model
            
        # 2. Try cached model if not using random selection
        if not use_random:
            cached_model = g_c.get(self.working_model_cache_key)
            if cached_model and cached_model not in failed_models:
                logger.debug(f"Using cached model: {cached_model}")
                return cached_model
                
        # 3. Try random available model
        available_models = [m for m in FREE_MODELS if m not in failed_models and m != current_model]
        if available_models:
            selected_model = random.choice(available_models)
            logger.debug(f"Selected random model: {selected_model} from {len(available_models)} available")
            return selected_model
    
    def get_comparison_models(self):
        """Get models for comparison mode."""
        return "google/gemma-3-27b-it", "mistralai/mistral-small-3.1-24b-instruct"
    
    def is_user_only_instruction_model(self, model):
        """Check if a model requires user-only instructions."""
        return model in USER_ONLY_INSTRUCTION_MODELS
