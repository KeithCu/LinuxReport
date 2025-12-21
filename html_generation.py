'''
html_generation.py

Provides functions for generating and updating the HTML content for the AI-powered headlines.
This includes rendering articles with Jinja2 templates and refreshing images.
'''

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
from shared import g_logger, g_c

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
from jinja2 import Template

# =============================================================================
# LOCAL IMPORTS
# =============================================================================
from embeddings_dedup import extract_articles_from_html
from image_parser import custom_fetch_largest_image

# =============================================================================
# CONSTANTS AND TEMPLATES
# =============================================================================

# Jinja2 template for rendering a single headline with an optional image.
HEADLINE_TEMPLATE = Template("""
<div class="linkclass">
<center>
<a href="{{ url }}" target="_blank">
<span class="main-headline">{{ title }}</span>
</a>
{% if image_url %}
<br/>
<a href="{{ url }}" target="_blank">
<img src="{{ image_url }}" width="500" alt="headline: {{ title[:50] }}" loading="lazy" onerror="this.style.display='none'">
</a>
{% endif %}
</center>
</div>
<br/>
""")

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def sanitize_timestamp_for_id(timestamp):
    """
    Sanitize a timestamp string for use as an HTML ID attribute.
    
    Args:
        timestamp (str): ISO timestamp string
    
    Returns:
        str: Sanitized string safe for use in HTML IDs
    """
    return timestamp.replace(':', '-').replace('.', '-').replace('+', '-').replace('/', '-').replace('T', '-').replace('Z', '')

# =============================================================================
# HTML GENERATION FUNCTIONS
# =============================================================================

def build_llm_process_viewer_html(attempts, timestamp):
    """
    Build HTML for LLM process viewer popup.
    
    Note: JavaScript initialization is handled by the shared ai-process.js file
    which is included via Flask-Assets bundle. No inline JavaScript needed.
    
    Args:
        attempts (list): List of LLM attempt dictionaries
        timestamp (str): ISO timestamp for this headline generation
    
    Returns:
        str: HTML string containing popup HTML (no JavaScript)
    """
    if not attempts:
        return ""
    
    # Sanitize timestamp for use as HTML ID
    sanitized_id = sanitize_timestamp_for_id(timestamp)
    
    # Build popup HTML using base class names (no -main suffix)
    popup_html = f"""
<div class="ai-process-overlay" id="overlay-{sanitized_id}"></div>
<div class="ai-process-popup" id="popup-{sanitized_id}">
    <span class="ai-process-close" data-target="popup-{sanitized_id}">&times;</span>
    <h3>LLM Process</h3>"""
    
    for attempt in attempts:
        success_class = "ai-success" if attempt.get('success') else "ai-failed"
        status_text = "Success" if attempt.get('success') else "Failed"
        error_text = f" ({attempt.get('error', '')})" if attempt.get('error') else ""
        
        popup_html += f"""
    <div class="ai-attempt">
        <div class="ai-attempt-header">
            Model: {attempt.get('model', 'Unknown')} | 
            Status: <span class="{success_class}">{status_text}{error_text}</span>
        </div>
        <div class="ai-attempt-header">Prompt:</div>
        <div class="ai-attempt-body">"""
        
        for msg in attempt.get('messages', []):
            popup_html += f"[{msg.get('role', 'unknown')}]: {msg.get('content', '')}\n"
        
        popup_html += """</div>"""
        
        if attempt.get('response'):
            popup_html += f"""
        <div class="ai-attempt-header">Response:</div>
        <div class="ai-attempt-body">{attempt.get('response')}</div>"""
        
        popup_html += """
    </div>"""
    
    popup_html += """
</div>"""
    
    return popup_html

def generate_headlines_html(top_articles, output_file, model_name=None, attempts=None, timestamp=None):
    """
    Generates the complete HTML for the headlines section and writes it to a file.

    This function takes a list of articles, renders them using the HEADLINE_TEMPLATE,
    and ensures that only the first article with a valid image displays that image.
    It can also add an attribution link for the AI model used and an LLM process viewer.

    Args:
        top_articles (list[dict]): A list of article dictionaries. Each dictionary
                                   must have 'url' and 'title' keys. 'image_url'
                                   is optional.
        output_file (str): The absolute path to the output HTML file.
        model_name (str, optional): The name of the AI model used for generation.
                                    If provided, an attribution link is added.
                                    Defaults to None.
        attempts (list, optional): List of LLM attempt dictionaries for process viewer.
                                    Defaults to None.
        timestamp (str, optional): ISO timestamp for this headline generation.
                                   Required if attempts are provided.
                                    Defaults to None.
    """
    html_parts = []
    image_shown = False

    # Render the top 3 articles, showing an image only for the first one that has it.
    for art in top_articles[:3]:
        image_url_to_render = None
        if not image_shown and art.get("image_url"):
            image_url_to_render = art.get("image_url")
            image_shown = True
        
        rendered_html = HEADLINE_TEMPLATE.render(
            url=art["url"],
            title=art["title"],
            image_url=image_url_to_render
        )
        html_parts.append(rendered_html)

    # Add AI model attribution and LLM process viewer if a model name is provided.
    if model_name:
        attribution_html = f"""
<div style="text-align: right; font-size: 8px; color: var(--link); margin-top: 0.5em;">
<a href="https://openrouter.ai/{model_name}" target="_blank" style="text-decoration: none; color: inherit;">Generated by {model_name}</a>"""
        
        # Add LLM process viewer link if attempts are available
        if attempts and timestamp:
            sanitized_id = sanitize_timestamp_for_id(timestamp)
            attribution_html += f""" | <span class="ai-process-link" data-target="popup-{sanitized_id}" style="cursor: pointer; text-decoration: underline;">View LLM Process</span>"""
        
        attribution_html += "</div>"
        html_parts.append(attribution_html)
        
        # Add LLM process viewer popup if attempts are available
        if attempts and timestamp:
            popup_html = build_llm_process_viewer_html(attempts, timestamp)
            html_parts.append(popup_html)

    full_html = "\n".join(html_parts)

    # Ensure the output directory exists and write the file.
    try:
        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(full_html)
        g_logger.info(f"Generated HTML with {len(top_articles[:3])} headlines to {output_file}")
    except IOError as e:
        g_logger.error(f"Error writing to output file {output_file}: {e}")

def refresh_images_only(mode, model_name=None):
    """
    Refreshes only the images in an existing headline HTML file.

    This function reads a report's HTML file, extracts the articles from it,
    fetches a new primary image for each article, and then regenerates the
    HTML file with the updated images.

    Args:
        mode (str): The report mode (e.g., 'linux', 'ai') used to determine
                    the filename (e.g., 'linuxreportabove.html').
        model_name (str, optional): The name of the AI model to attribute in the
                                    regenerated file. Defaults to None.

    Returns:
        bool: True if the refresh was successful, False otherwise.
    """
    html_file = f"{mode}reportabove.html"
    
    if not os.path.exists(html_file):
        g_logger.error(f"Cannot refresh images: HTML file {html_file} not found.")
        return False

    # Extract existing articles from the HTML file.
    articles = extract_articles_from_html(html_file)

    if not articles:
        g_logger.error(f"No articles found in existing HTML file {html_file}. Cannot refresh images.")
        return False

    g_logger.info(f"Found {len(articles)} articles in {html_file}, refreshing images...")

    # Fetch a new largest image for each article.
    for article in articles:
        article["image_url"] = custom_fetch_largest_image(article["url"])

    # Regenerate the HTML with the newly fetched images.
    generate_headlines_html(articles, html_file, model_name)
    g_logger.info(f"Successfully refreshed images in {html_file}")
    return True
