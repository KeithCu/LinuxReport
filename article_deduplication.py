"""
Module: article_deduplication.py

This module provides functionality for article fetching, deduplication using
sentence embeddings, and finding similar articles based on their titles.
"""

import os
import re
from sentence_transformers import SentenceTransformer, util

# === Constants and Configuration ===
EMBEDDER_MODEL_NAME = 'all-MiniLM-L6-v2'
THRESHOLD = 0.75  # Similarity threshold for deduplication

# === Embedding Model Globals ===
embedder = None
st_util = None

def get_embedding(text):
    """Get the embedding vector for a piece of text using SentenceTransformer."""
    global embedder, st_util
    if embedder is None:
        # Lazy initialization of SentenceTransformer since it takes 5 seconds.
        embedder = SentenceTransformer(EMBEDDER_MODEL_NAME)
        st_util = util
    return embedder.encode(text, convert_to_tensor=True)

def deduplicate_articles_with_exclusions(articles, excluded_embeddings, threshold=THRESHOLD):
    """Deduplicate articles based on their embeddings, excluding similar ones."""
    unique_articles = []
    do_not_select_similar = excluded_embeddings.copy()  # Start with embeddings of previous selections

    for article in articles:
        title = article["title"]
        current_emb = get_embedding(title)  # Compute embedding for the article's title
        
        is_similar = any(st_util.cos_sim(current_emb, emb).item() >= threshold for emb in do_not_select_similar)
        
        if not is_similar:
            unique_articles.append(article)
            do_not_select_similar.append(current_emb)  # Add to the list to avoid similar articles later
        else:
            print(f"Filtered duplicate (embeddings): {title}")

    return unique_articles

def get_best_matching_article(target_title, articles):
    """Finds the article with the highest similarity score to the target title."""
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
    return best_match

def extract_articles_from_html(html_file):
    """Extract article URLs and titles from the HTML file."""
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

def fetch_recent_articles(all_urls, cache):
    """Fetch recent articles from RSS feeds stored in cache."""
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