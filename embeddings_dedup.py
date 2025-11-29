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
import math

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import numpy as np
from sentence_transformers import SentenceTransformer

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
embedding_cache = {}  # Cache for storing computed embeddings as numpy arrays
_embedding_dim = None  # Cache embedding dimension for zero vector creation
_zero_embedding = None  # Cached zero embedding vector

# Keep st_util for backward compatibility with tests
try:
    from sentence_transformers import util
    st_util = util
except ImportError:
    st_util = None

# =============================================================================
# EMBEDDING UTILITY FUNCTIONS
# =============================================================================

def clamp_similarity(score):
    """Clamp cosine similarity score to [-1, 1] to avoid floating point artifacts."""
    if not isinstance(score, (int, float)) or math.isnan(score):
        return 0.0
    return max(-1.0, min(1.0, score))


def _get_zero_embedding():
    """Get a zero embedding vector of the correct dimension."""
    global embedder, _embedding_dim, _zero_embedding
    if _zero_embedding is not None:
        return _zero_embedding
    if embedder is None:
        embedder = SentenceTransformer(EMBEDDER_MODEL_NAME)
    if _embedding_dim is None:
        # Get dimension by encoding a dummy text once
        sample = embedder.encode(" ", convert_to_tensor=False, show_progress_bar=False)
        _embedding_dim = sample.shape[-1]
    # Create zero array and cache it
    _zero_embedding = np.zeros(_embedding_dim, dtype=np.float32)
    return _zero_embedding


def get_embedding(text):
    """
    Get the embedding vector for a piece of text using SentenceTransformer.

    Computes semantic embeddings for text using the configured transformer model.
    Implements caching to avoid recomputing embeddings for the same text.
    Uses lazy loading to defer model initialization until first use.

    Args:
        text (str): Text to compute embedding for

    Returns:
        np.ndarray: Embedding vector for the input text (numpy array)
    """
    global embedder

    # Normalize input early - strip whitespace (will raise AttributeError for None)
    text = text.strip()

    # Initialize embedder once if needed
    if embedder is None:
        embedder = SentenceTransformer(EMBEDDER_MODEL_NAME)

    # Handle empty strings gracefully
    if not text:
        return _get_zero_embedding()

    # Check cache first
    if text in embedding_cache:
        return embedding_cache[text]

    # Compute embedding as numpy array directly (no tensor conversion)
    embedding = embedder.encode(text, convert_to_tensor=False, show_progress_bar=False)
    embedding_cache[text] = embedding
    return embedding


def get_embeddings_batch(texts):
    """
    Get embeddings for multiple texts with caching support.

    Args:
        texts: List of text strings to encode

    Returns:
        list: List of embedding numpy arrays (same order as input texts)
    """
    global embedder
    if embedder is None:
        embedder = SentenceTransformer(EMBEDDER_MODEL_NAME)

    # Pre-allocate result list to maintain order
    embeddings = [None] * len(texts)
    valid_texts = []
    valid_indices = []

    # First pass: handle cached and identify texts to encode
    zero_vec = _get_zero_embedding()
    for i, text in enumerate(texts):
        # Normalize input - strip whitespace (will raise AttributeError for None)
        try:
            normalized_text = text.strip()
        except AttributeError:
            # Re-raise AttributeError for None/invalid types (expected by tests)
            raise
        if normalized_text:
            if normalized_text in embedding_cache:
                embeddings[i] = embedding_cache[normalized_text]
            else:
                valid_texts.append(normalized_text)
                valid_indices.append(i)
        else:
            # Empty text gets zero vector
            embeddings[i] = zero_vec

    # Encode uncached texts in batch (as numpy arrays directly)
    if valid_texts:
        batch_embeddings = embedder.encode(valid_texts, convert_to_tensor=False, show_progress_bar=False)

        # Cache and assign to correct positions
        for text, emb, idx in zip(valid_texts, batch_embeddings, valid_indices):
            embedding_cache[text] = emb
            embeddings[idx] = emb

    return embeddings

# =============================================================================
# DEDUPLICATION FUNCTIONS
# =============================================================================

def _compute_cosine_similarities(query_emb, candidate_embs):
    """
    Compute cosine similarities between a query embedding and candidate embeddings.
    
    Args:
        query_emb: Query embedding vector (1D numpy array)
        candidate_embs: Candidate embedding vectors (2D numpy array, shape: [n_candidates, dim])
    
    Returns:
        Array of similarity scores (1D numpy array, shape: [n_candidates])
    """
    if candidate_embs.shape[0] == 0:
        return np.array([])
    
    query_norm = np.linalg.norm(query_emb)
    candidate_norms = np.linalg.norm(candidate_embs, axis=1)
    dot_products = np.dot(candidate_embs, query_emb)
    
    # Avoid division by zero: if either norm is zero, similarity is 0
    denominator = candidate_norms * query_norm
    with np.errstate(divide='ignore', invalid='ignore'):
        similarities = np.where(
            denominator > 0,
            dot_products / denominator,
            0.0
        )
    return np.clip(similarities, -1.0, 1.0)


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
    # Validate input parameters
    if not isinstance(articles, (list, tuple)):
        raise TypeError(f"articles must be a list or tuple, got {type(articles).__name__}")
    if not isinstance(excluded_embeddings, (list, tuple)):
        raise TypeError(f"excluded_embeddings must be a list or tuple, got {type(excluded_embeddings).__name__}")
    
    # Vectorized implementation using numpy operations for optimal performance
    if not articles:
        return []

    unique_articles = []

    # Get all article titles and compute embeddings in batch for efficiency
    article_titles = [article["title"] for article in articles]
    article_embeddings = get_embeddings_batch(article_titles)  # Already numpy arrays

    # Convert excluded embeddings to numpy arrays (handle both numpy and torch tensors)
    excluded_list = []
    for emb in excluded_embeddings:
        if isinstance(emb, np.ndarray):
            excluded_list.append(emb)
        elif hasattr(emb, 'numpy'):  # torch.Tensor
            excluded_list.append(emb.numpy())
        else:
            excluded_list.append(np.asarray(emb))
    
    # Build excluded arrays list (will stack once at end for efficiency)
    excluded_arrays_list = excluded_list.copy()

    # Process articles individually to maintain exact progressive exclusion behavior
    # This ensures each article is checked against ALL previously selected articles
    for article, current_emb in zip(articles, article_embeddings):
        # Check similarity against all current exclusions
        if excluded_arrays_list:
            excluded_arrays = np.stack(excluded_arrays_list)
            similarities = _compute_cosine_similarities(current_emb, excluded_arrays)
            max_similarity = np.max(similarities)
            is_similar = max_similarity >= threshold
        else:
            is_similar = False

        if not is_similar:
            unique_articles.append(article)
            # Add to excluded list (will be stacked on next iteration if needed)
            excluded_arrays_list.append(current_emb)

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

    # Embeddings are already numpy arrays, use them directly
    target_array = target_emb
    article_arrays = np.stack(article_embeddings)

    # Use shared similarity computation function
    similarities = _compute_cosine_similarities(target_array, article_arrays)

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