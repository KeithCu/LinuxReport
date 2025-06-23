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
    if text in embedding_cache:
        return embedding_cache[text]
        
    if embedder is None:
        # Lazy initialization of SentenceTransformer since it takes 5 seconds.
        embedder = SentenceTransformer(EMBEDDER_MODEL_NAME)
        st_util = util
    
    embedding = embedder.encode(text, convert_to_tensor=True)
    embedding_cache[text] = embedding
    return embedding

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
    unique_articles = []
    do_not_select_similar = excluded_embeddings.copy()  # Start with embeddings of previous selections

    print("\nFiltering articles by embedding similarity:")
    for article in articles:
        title = article["title"]
        current_emb = get_embedding(title)  # Compute embedding for the article's title
        
        is_similar = any(st_util.cos_sim(current_emb, emb).item() >= threshold for emb in do_not_select_similar)
        
        if not is_similar:
            unique_articles.append(article)
            do_not_select_similar.append(current_emb)  # Add to the list to avoid similar articles later
        else:
            print(f"Filtered by embedding similarity: {title}")

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
    target_emb = get_embedding(target_title)
    best_match = None
    best_score = 0.0
    
    for article in articles:
        score = st_util.cos_sim(target_emb, get_embedding(article["title"])).item()
        if score > best_score:
            best_match = article
            if score == 1.0:
                return best_match
            best_score = score
    
    if best_score < THRESHOLD:
        print(f"\nNo match found above threshold {THRESHOLD}. Scores:")
        for article in articles:
            score = st_util.cos_sim(target_emb, get_embedding(article["title"])).item()
            print(f"Score for '{article['title']}': {score}")
            
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