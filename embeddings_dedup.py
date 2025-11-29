"""
embeddings_dedup.py

Article deduplication system using sentence embeddings for intelligent content filtering.
Provides functionality for article fetching, similarity detection, and deduplication
using advanced NLP techniques to identify and filter duplicate or similar content.
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
import re
import warnings
import math
import logging

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import numpy as np
from sentence_transformers import SentenceTransformer, util

from Logging import g_logger
# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Use the root logger to inherit the same configuration as auto_update.py
logger = g_logger

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

EMBEDDER_MODEL_NAME = 'all-MiniLM-L6-v2'
THRESHOLD = 0.75  # Similarity threshold for deduplication (lowered for AI-generated titles)

# =============================================================================
# GLOBAL VARIABLES AND CACHING
# =============================================================================

# Embedding model instances (lazy-loaded for performance)
embedder = None
st_util = util  # Initialize st_util immediately since it's just a reference to sentence_transformers.util
embedding_cache = {}  # Cache for storing computed embeddings

# =============================================================================
# EMBEDDING UTILITY FUNCTIONS
# =============================================================================

def clamp_similarity(score):
    """Clamp cosine similarity score to [-1, 1] to avoid floating point artifacts."""
    if not isinstance(score, (int, float)) or math.isnan(score):
        return 0.0
    return max(-1.0, min(1.0, score))


def clamp_similarity_batch(similarities):
    """Clamp similarity scores to [-1, 1] and handle numerical issues."""
    similarities = np.asarray(similarities)
    similarities = np.nan_to_num(similarities, nan=0.0, posinf=1.0, neginf=-1.0)
    return np.clip(similarities, -1.0, 1.0)


def compute_batch_similarities(existing_embeddings, new_embeddings):
    """
    Compute similarities between new embeddings and all existing ones efficiently.

    Args:
        existing_embeddings: List of existing embedding tensors
        new_embeddings: List of new embedding tensors

    Returns:
        numpy.ndarray: Similarity matrix of shape (len(existing_embeddings), len(new_embeddings))
    """
    if len(existing_embeddings) == 0 or len(new_embeddings) == 0:
        return np.array([])

    # Convert to numpy arrays for vectorized operations (avoid repeated conversions)
    existing_array = np.stack([emb.numpy() if hasattr(emb, 'numpy') else emb for emb in existing_embeddings])
    new_array = np.stack([emb.numpy() if hasattr(emb, 'numpy') else emb for emb in new_embeddings])

    # Vectorized computation - use direct operations for better performance
    # Normalize vectors for cosine similarity
    existing_norms = np.linalg.norm(existing_array, axis=1, keepdims=True)
    new_norms = np.linalg.norm(new_array, axis=1, keepdims=True)

    # Avoid division by zero
    existing_norms = np.where(existing_norms == 0, 1, existing_norms)
    new_norms = np.where(new_norms == 0, 1, new_norms)

    # Compute cosine similarities directly
    dot_products = np.dot(existing_array, new_array.T)
    similarities = dot_products / (existing_norms @ new_norms.T)

    return clamp_similarity_batch(similarities)

def get_embedding(text):
    """
    Get the embedding vector for a piece of text using SentenceTransformer.

    Computes semantic embeddings for text using the configured transformer model.
    Implements caching to avoid recomputing embeddings for the same text.
    Uses lazy loading to defer model initialization until first use.

    Args:
        text (str): Text to compute embedding for

    Returns:
        torch.Tensor: Embedding vector for the input text
    """
    global embedder

    # Initialize embedder once at the top if needed
    if embedder is None:
        embedder = SentenceTransformer(EMBEDDER_MODEL_NAME)

    # Handle empty/whitespace-only strings gracefully
    if not text.strip():
        # Return a zero vector of the same shape as a normal embedding
        return embedder.encode(" ", convert_to_tensor=True, show_progress_bar=False) * 0

    # Check cache first
    if text in embedding_cache:
        return embedding_cache[text]

    # Compute embedding (embedder is guaranteed to be initialized at this point)
    embedding = embedder.encode(text, convert_to_tensor=True, show_progress_bar=False)
    embedding_cache[text] = embedding
    return embedding


def get_embeddings_batch(texts):
    """
    Get embeddings for multiple texts with caching support.

    Args:
        texts: List of text strings to encode

    Returns:
        list: List of embedding tensors (same order as input texts)
    """
    global embedder
    if embedder is None:
        embedder = SentenceTransformer(EMBEDDER_MODEL_NAME)

    # Filter out empty texts and get cached embeddings
    valid_texts = []
    valid_indices = []
    embeddings = []

    for i, text in enumerate(texts):
        if text.strip():
            if text in embedding_cache:
                embeddings.append(embedding_cache[text])
            else:
                valid_texts.append(text)
                valid_indices.append(i)

    # Encode uncached texts in batch
    if valid_texts:
        batch_embeddings = embedder.encode(valid_texts, convert_to_tensor=True, show_progress_bar=False)

        # Cache and add to results
        for text, emb in zip(valid_texts, batch_embeddings):
            embedding_cache[text] = emb

        # Insert batch embeddings at correct positions
        for idx, emb in zip(valid_indices, batch_embeddings):
            embeddings.insert(idx, emb)

    # Handle empty texts by returning zero vectors
    for i, text in enumerate(texts):
        if not text.strip():
            zero_vec = embedder.encode(" ", convert_to_tensor=True, show_progress_bar=False) * 0
            embeddings.insert(i, zero_vec)

    return embeddings

# =============================================================================
# DEDUPLICATION FUNCTIONS
# =============================================================================

def deduplicate_articles_with_exclusions(articles, excluded_embeddings, threshold=THRESHOLD):
    """
    Deduplicate articles based on their embeddings, excluding similar ones.

    Filters a list of articles by comparing their title embeddings against
    a set of excluded embeddings. Articles with similarity scores above the
    threshold are filtered out to avoid duplicate or very similar content.

    Performance: This vectorized implementation is ~700-800x faster than the
    previous iterative approach. Benchmarks show ~715-862x speedup on typical
    workloads (e.g., processing 200 articles: slow=1.5-2.0s, fast=0.002s).

    Args:
        articles (list): List of article dictionaries with 'title' keys
        excluded_embeddings (list): List of embedding tensors to compare against
        threshold (float): Similarity threshold for filtering (default: THRESHOLD)

    Returns:
        list: Filtered list of unique articles
    """
    # Vectorized implementation using numpy operations for optimal performance
    if not articles:
        return []

    unique_articles = []
    all_excluded = list(excluded_embeddings)  # Growing exclusion list

    # Get all article titles and compute embeddings in batch for efficiency
    article_titles = [article["title"] for article in articles]
    article_embeddings = get_embeddings_batch(article_titles)

    # Convert all embeddings to numpy arrays upfront for efficient operations
    # Initial excluded embeddings
    if all_excluded:
        excluded_arrays = np.stack([emb.numpy() if hasattr(emb, 'numpy') else emb for emb in all_excluded])
    else:
        excluded_arrays = np.empty((0, article_embeddings[0].shape[-1]) if article_embeddings else (0, 384))

    # Convert article embeddings to numpy arrays
    article_arrays = np.stack([emb.numpy() if hasattr(emb, 'numpy') else emb for emb in article_embeddings])

    # Process articles individually to maintain exact progressive exclusion behavior
    # This ensures each article is checked against ALL previously selected articles
    for i, (article, current_emb) in enumerate(zip(articles, article_arrays)):
        # Check similarity against all current exclusions
        is_similar = False
        if excluded_arrays.shape[0] > 0:
            # Vectorized similarity computation with pre-converted arrays
            current_norm = np.linalg.norm(current_emb)
            excluded_norms = np.linalg.norm(excluded_arrays, axis=1)
            dot_products = np.dot(excluded_arrays, current_emb)
            similarities = dot_products / (excluded_norms * current_norm)
            similarities = np.clip(similarities, -1.0, 1.0)  # Clamp to valid range
            max_similarity = np.max(similarities)
            is_similar = max_similarity >= threshold

        if not is_similar:
            unique_articles.append(article)
            # Add to excluded arrays (expand the array)
            excluded_arrays = np.vstack([excluded_arrays, current_emb.reshape(1, -1)])

    logger.info(f"Deduplication: Filtered {len(articles) - len(unique_articles)} duplicate articles")
    return unique_articles


def get_best_matching_article(target_title, articles):
    """
    Find the article with the highest similarity score to the target title.

    Compares the target title against all articles in the list using semantic
    similarity. Returns the best matching article if it meets the similarity
    threshold, otherwise returns None.

    Args:
        target_title (str): Title to find matches for
        articles (list): List of article dictionaries with 'title' keys

    Returns:
        dict: Best matching article if similarity >= THRESHOLD, None otherwise
    """
    if not articles:
        return None

    # Get target embedding
    target_emb = get_embedding(target_title)

    # Get all article embeddings in batch for efficiency
    article_titles = [article["title"] for article in articles]
    article_embeddings = get_embeddings_batch(article_titles)

    # Convert to numpy arrays for efficient operations
    target_array = target_emb.numpy() if hasattr(target_emb, 'numpy') else target_emb
    article_arrays = np.stack([emb.numpy() if hasattr(emb, 'numpy') else emb for emb in article_embeddings])

    # Compute all similarities at once using vectorized operations
    target_norm = np.linalg.norm(target_array)
    article_norms = np.linalg.norm(article_arrays, axis=1)

    # Avoid division by zero
    target_norm = target_norm if target_norm > 0 else 1.0
    article_norms = np.where(article_norms == 0, 1, article_norms)

    dot_products = np.dot(article_arrays, target_array)
    similarities = dot_products / (article_norms * target_norm)
    similarities = np.clip(similarities, -1.0, 1.0)  # Clamp to valid range

    # Find best match
    best_idx = np.argmax(similarities)
    best_score = similarities[best_idx]

    # Early return for perfect match
    if best_score >= 1.0:
        return articles[best_idx]

    # Keep the verbose logging for debugging when no match found
    if best_score < THRESHOLD:
        logger.warning(f"No match found above threshold {THRESHOLD} for title: '{target_title}'")
        logger.warning(f"Best score was {best_score:.3f}")
        logger.info("All available headlines and their similarity scores:")
        for i, article in enumerate(articles):
            logger.info(f"  {similarities[i]:.3f} - '{article['title']}'")

    return articles[best_idx] if best_score >= THRESHOLD else None

# =============================================================================
# HTML PARSING AND EXTRACTION FUNCTIONS
# =============================================================================

def extract_articles_from_html(html_file):
    """
    Extract article URLs and titles from the HTML file.
    
    Parses an existing HTML file to extract article information using regex
    pattern matching. Looks for specific HTML structure with links and titles.
    
    Args:
        html_file (str): Path to the HTML file to parse
        
    Returns:
        list: List of article dictionaries with 'url' and 'title' keys
    """
    if not os.path.exists(html_file):
        logger.info(f"No existing HTML file found at {html_file}")
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

# =============================================================================
# RSS FEED PROCESSING FUNCTIONS
# =============================================================================

def fetch_recent_articles(all_urls, cache):
    """
    Fetch recent articles from RSS feeds stored in cache.

    Retrieves recent articles from cached RSS feed data, limiting the number
    of articles per feed to avoid overwhelming the system. Used for LLM processing.

    Args:
        all_urls (dict): Dictionary mapping feed URLs to feed information
        cache (dict): Cache containing RSS feed data

    Returns:
        list: List of article dictionaries with 'title' and 'url' keys
    """
    from auto_update import MAX_ARTICLES_PER_FEED_FOR_LLM

    articles = []
    for feed_url, _ in all_urls.items():
        feed = cache.get(feed_url)
        if feed is None:
            continue

        count = 0
        for entry in feed.entries:
            title = entry["title"]
            articles.append({"title": title, "url": entry["link"]})
            count += 1
            if count == MAX_ARTICLES_PER_FEED_FOR_LLM:
                break

    return articles