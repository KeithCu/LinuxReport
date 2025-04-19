"""
Module: html_generation.py

This module provides functions for generating HTML content from article data,
including templates for rendering headlines and image content.
"""

import os
from jinja2 import Template

from article_deduplication import extract_articles_from_html
# Updated import path for custom_fetch_largest_image
from image_parser import custom_fetch_largest_image

# === Constants and Templates ===
headline_template = Template("""
<div class="linkclass">
<center>
<code>
<a href="{{ url }}" target="_blank">
<font size="5"><b>{{ title }}</b></font>
</a>
</code>
{% if image_url %}
<br/>
<a href="{{ url }}" target="_blank">
<img src="{{ image_url }}" width="500" alt="{{ title }}">
</a>
{% endif %}
</center>
</div>
<br/>
""")

def generate_headlines_html(top_articles, output_file):
    """
    Generate HTML content for headlines and write to a file.
    
    Args:
        top_articles: List of article dictionaries with at least 'url' and 'title' keys
        output_file: Path to the output HTML file
    """
    # Determine the first article that has an image to show one image only
    first_image_idx = None
    for idx, art in enumerate(top_articles[:3]):
        if art.get("image_url"):
            first_image_idx = idx
            break
    
    # Render HTML: only the first image is displayed
    html_parts = []
    for idx, art in enumerate(top_articles[:3]):
        rendered_html = headline_template.render(
            url=art["url"],
            title=art["title"],
            image_url=art.get("image_url") if idx == first_image_idx else None
        )
        html_parts.append(rendered_html)

    # Combine all headline HTML
    full_html = "\n".join(html_parts)

    # Write to the output file
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(full_html)
    
    print(f"Generated HTML with {len(html_parts)} headlines to {output_file}")

def refresh_images_only(mode):
    """
    Refresh only the images in the HTML file without changing the articles.
    
    Args:
        mode: The mode name used to construct the HTML filename
        
    Returns:
        bool: True if successful, False otherwise
    """
    
    html_file = f"{mode}reportabove.html"
    
    # Extract the articles from the HTML
    articles = extract_articles_from_html(html_file)
    
    if not articles:
        print(f"No articles found in existing HTML file {html_file}")
        return False
    
    print(f"Found {len(articles)} articles in {html_file}, refreshing images...")
    
    # Fetch images for articles
    for article in articles:
        article["image_url"] = custom_fetch_largest_image(article["url"])
    
    # Generate new HTML with fresh images
    generate_headlines_html(articles, html_file)
    print(f"Successfully refreshed images in {html_file}")
    return True