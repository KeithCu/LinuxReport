"""
article_deduplication.py

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

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
from sentence_transformers import SentenceTransformer, util

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

EMBEDDER_MODEL_NAME = 'all-MiniLM-L6-v2'
THRESHOLD = 0.75  # Similarity threshold for deduplication

# =============================================================================
# GLOBAL VARIABLES AND CACHING
# =============================================================================

# Embedding model instances (lazy-loaded for performance)
embedder = None
st_util = None
embedding_cache = {}  # Cache for storing computed embeddings

# =============================================================================
# EMBEDDING UTILITY FUNCTIONS
# =============================================================================

def clamp_similarity(score):
    """Clamp cosine similarity score to [-1, 1] to avoid floating point artifacts."""
    if not isinstance(score, (int, float)) or math.isnan(score):
        warnings.warn(f"Non-numeric or NaN similarity score: {score}, type: {type(score)}")
        return 0.0
    return max(-1.0, min(1.0, score))

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
    global embedder, st_util
    
    # Input validation
    if text is None:
        warnings.warn("get_embedding called with None text")
        text = ""
    
    if not isinstance(text, str):
        warnings.warn(f"get_embedding called with non-string text: {type(text)}")
        text = str(text)
    
    # Handle empty/whitespace-only strings gracefully
    if not text.strip():
        if embedder is None:
            try:
                embedder = SentenceTransformer(EMBEDDER_MODEL_NAME)
                st_util = util
            except Exception as e:
                warnings.warn(f"Failed to initialize SentenceTransformer: {e}")
                return None
        # Return a zero vector of the same shape as a normal embedding
        try:
            return embedder.encode(" ", convert_to_tensor=True) * 0
        except Exception as e:
            warnings.warn(f"Failed to create zero embedding: {e}")
            return None
    
    # Check cache first
    if text in embedding_cache:
        return embedding_cache[text]
    
    # Initialize model if needed
    if embedder is None:
        try:
            embedder = SentenceTransformer(EMBEDDER_MODEL_NAME)
            st_util = util
        except Exception as e:
            warnings.warn(f"Failed to initialize SentenceTransformer: {e}")
            return None
    
    # Compute embedding
    try:
        embedding = embedder.encode(text, convert_to_tensor=True)
        embedding_cache[text] = embedding
        return embedding
    except Exception as e:
        warnings.warn(f"Failed to compute embedding for text '{text[:50]}...': {e}")
        return None

# =============================================================================
# DEDUPLICATION FUNCTIONS
# =============================================================================

def deduplicate_articles_with_exclusions(articles, excluded_embeddings, threshold=THRESHOLD):
    """
    Deduplicate articles based on their embeddings, excluding similar ones.
    
    Filters a list of articles by comparing their title embeddings against
    a set of excluded embeddings. Articles with similarity scores above the
    threshold are filtered out to avoid duplicate or very similar content.
    
    Args:
        articles (list): List of article dictionaries with 'title' keys
        excluded_embeddings (list): List of embedding tensors to compare against
        threshold (float): Similarity threshold for filtering (default: THRESHOLD)
        
    Returns:
        list: Filtered list of unique articles
    """
    # Input validation
    if not isinstance(articles, list):
        warnings.warn(f"articles must be a list, got {type(articles)}")
        return []
    
    if not isinstance(excluded_embeddings, list):
        warnings.warn(f"excluded_embeddings must be a list, got {type(excluded_embeddings)}")
        excluded_embeddings = []
    
    if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
        warnings.warn(f"threshold must be a number between 0 and 1, got {threshold}")
        threshold = THRESHOLD
    
    unique_articles = []
    do_not_select_similar = excluded_embeddings.copy()  # Start with embeddings of previous selections
    
    # Track statistics
    processed_count = 0
    filtered_count = 0
    error_count = 0

    print("\nFiltering articles by embedding similarity:")
    for i, article in enumerate(articles):
        # Validate article structure
        if not isinstance(article, dict):
            warnings.warn(f"Article {i} is not a dictionary: {type(article)}")
            error_count += 1
            continue
        
        if "title" not in article:
            warnings.warn(f"Article {i} missing 'title' key: {article}")
            error_count += 1
            continue
        
        title = article["title"]
        # Skip empty/whitespace-only or non-string titles
        if not isinstance(title, str) or not title.strip():
            warnings.warn(f"Skipping article with invalid or empty title: {title}")
            error_count += 1
            continue
        
        processed_count += 1
        
        # Get embedding with error handling
        current_emb = get_embedding(title)
        if current_emb is None:
            warnings.warn(f"Failed to get embedding for title: {title}")
            error_count += 1
            continue
        
        # Check similarity against excluded embeddings
        try:
            is_similar = False
            for emb in do_not_select_similar:
                if emb is None:
                    continue
                similarity = clamp_similarity(st_util.cos_sim(current_emb, emb).item())
                if similarity >= threshold:
                    is_similar = True
                    break
            
            if not is_similar:
                unique_articles.append(article)
                do_not_select_similar.append(current_emb)  # Add to the list to avoid similar articles later
            else:
                print(f"Filtered by embedding similarity: {title}")
                filtered_count += 1
                
        except Exception as e:
            warnings.warn(f"Error computing similarity for '{title}': {e}")
            error_count += 1
            continue

    # Print summary statistics
    print(f"\nDeduplication summary:")
    print(f"  Processed: {processed_count} articles")
    print(f"  Filtered: {filtered_count} articles")
    print(f"  Errors: {error_count} articles")
    print(f"  Remaining: {len(unique_articles)} articles")
    
    if error_count > 0:
        warnings.warn(f"Encountered {error_count} errors during deduplication")
    
    if len(unique_articles) == 0 and len(articles) > 0:
        warnings.warn("All articles were filtered out - threshold may be too low")

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
    # Input validation
    if not isinstance(target_title, str):
        warnings.warn(f"target_title must be a string, got {type(target_title)}")
        return None
    
    if not isinstance(articles, list):
        warnings.warn(f"articles must be a list, got {type(articles)}")
        return None
    
    if not target_title.strip():
        warnings.warn("target_title is empty or whitespace-only")
        return None
    
    # Get target embedding
    target_emb = get_embedding(target_title)
    if target_emb is None:
        warnings.warn(f"Failed to get embedding for target title: {target_title}")
        return None
    
    best_match = None
    best_score = 0.0
    valid_articles = 0
    
    for i, article in enumerate(articles):
        # Validate article structure
        if not isinstance(article, dict) or "title" not in article:
            warnings.warn(f"Article {i} is invalid: {article}")
            continue
        
        article_title = article["title"]
        valid_articles += 1
        
        # Get article embedding
        article_emb = get_embedding(article_title)
        if article_emb is None:
            warnings.warn(f"Failed to get embedding for article title: {article_title}")
            continue
        
        # Compute similarity
        try:
            score = clamp_similarity(st_util.cos_sim(target_emb, article_emb).item())
            if score > best_score:
                best_match = article
                if score == 1.0:
                    return best_match
                best_score = score
        except Exception as e:
            warnings.warn(f"Error computing similarity for '{article_title}': {e}")
            continue
    
    if valid_articles == 0:
        warnings.warn("No valid articles found in the list")
        return None
    
    if best_score < THRESHOLD:
        print(f"\nNo match found above threshold {THRESHOLD}. Scores:")
        for article in articles:
            if not isinstance(article, dict) or "title" not in article:
                continue
            try:
                article_emb = get_embedding(article["title"])
                if article_emb is not None:
                    score = clamp_similarity(st_util.cos_sim(target_emb, article_emb).item())
                    print(f"Score for '{article['title']}': {score}")
            except Exception as e:
                print(f"Error computing score for '{article['title']}': {e}")
            
    return best_match if best_score >= THRESHOLD else None

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
            print(f"No data found for {feed_url}")
            continue

        count = 0
        for entry in feed.entries:
            title = entry["title"]
            articles.append({"title": title, "url": entry["link"]})
            count += 1
            if count == MAX_ARTICLES_PER_FEED_FOR_LLM:
                break

    return articles