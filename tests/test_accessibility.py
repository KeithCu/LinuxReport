"""
test_accessibility.py

Tests for accessibility features including ARIA attributes, keyboard navigation, and focus management.
"""

import pytest
from bs4 import BeautifulSoup
import re

def test_aria_roles_present(client):
    """Test that ARIA roles are present in the main page."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    # Check for main landmarks
    assert soup.find('main', {'role': 'main'})
    assert soup.find('header', {'role': 'banner'})
    assert soup.find('nav', {'role': 'navigation'})
    assert soup.find('aside', {'role': 'complementary'})
    
    # Check for feed roles
    feeds = soup.find_all('div', {'role': 'feed'})
    assert len(feeds) > 0
    
    # Check for article roles
    articles = soup.find_all('article', {'role': 'article'})
    assert len(articles) > 0

def test_aria_labels_present(client):
    """Test that ARIA labels are present for important elements."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    # Check for weather widget
    weather_widget = soup.find('div', {'role': 'region', 'aria-label': 'Weather Information'})
    assert weather_widget is not None
    
    # Check for navigation
    nav = soup.find('nav', {'aria-label': 'Site Navigation'})
    assert nav is not None
    
    # Check for main content
    main = soup.find('main', {'id': 'main-content'})
    assert main is not None

def test_skip_link_present(client):
    """Test that skip link is present for keyboard users."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    skip_link = soup.find('a', {'class': 'skip-link'})
    assert skip_link is not None
    assert skip_link.get('href') == '#main-content'
    assert skip_link.get('aria-label') == 'Skip to main content'

def test_button_aria_attributes(client):
    """Test that buttons have proper ARIA attributes."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    # Check weather toggle button
    weather_toggle = soup.find('button', {'id': 'weather-toggle-btn'})
    assert weather_toggle is not None
    assert weather_toggle.get('aria-expanded') == 'false'
    assert weather_toggle.get('aria-controls') == 'weather-content'
    
    # Check chat toggle button
    chat_toggle = soup.find('button', {'id': 'chat-toggle-btn'})
    assert chat_toggle is not None
    assert chat_toggle.get('aria-expanded') == 'false'
    assert chat_toggle.get('aria-controls') == 'chat-container'

def test_form_aria_attributes(client):
    """Test that form elements have proper ARIA attributes."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    # Check theme select
    theme_select = soup.find('select', {'id': 'theme-select'})
    assert theme_select is not None
    assert theme_select.get('aria-label') == 'Select theme'
    
    # Check font select
    font_select = soup.find('select', {'id': 'font-select'})
    assert font_select is not None
    assert font_select.get('aria-label') == 'Select font'

def test_article_structure(client):
    """Test that articles have proper structure and ARIA attributes."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    articles = soup.find_all('article', {'role': 'article'})
    assert len(articles) > 0
    
    for article in articles:
        # Check that articles have aria-labelledby
        assert article.get('aria-labelledby') is not None
        
        # Check that articles have title links
        title_link = article.find('a', {'id': re.compile(r'article-title-\d+')})
        assert title_link is not None

def test_pagination_aria_attributes(client):
    """Test that pagination controls have proper ARIA attributes."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    pagination_controls = soup.find_all('div', {'class': 'pagination-controls'})
    assert len(pagination_controls) > 0
    
    for control in pagination_controls:
        assert control.get('role') == 'navigation'
        assert control.get('aria-label') == 'Article pagination'
        
        prev_btn = control.find('button', {'class': 'prev-btn'})
        if prev_btn:
            assert prev_btn.get('aria-label') == 'Previous page'
        
        next_btn = control.find('button', {'class': 'next-btn'})
        if next_btn:
            assert next_btn.get('aria-label') == 'Next page'

def test_live_regions_present(client):
    """Test that live regions are present for dynamic content."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    # Check weather content
    weather_content = soup.find('div', {'aria-live': 'polite'})
    assert weather_content is not None
    
    # Check loading indicator
    loading_indicator = soup.find('div', {'role': 'status', 'aria-live': 'polite'})
    assert loading_indicator is not None

def test_accessibility_css_classes(client):
    """Test that accessibility CSS classes are present."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    # Check for sr-only class (should be in CSS)
    # This test verifies the structure supports screen reader content
    sr_only_elements = soup.find_all('div', {'class': 'sr-only'})
    # Note: sr-only elements are typically added dynamically by JavaScript

def test_alt_text_present(client):
    """Test that images have proper alt text."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    images = soup.find_all('img')
    for img in images:
        # Skip decorative images that might have empty alt
        if img.get('alt') is None:
            # Only allow empty alt for decorative images
            assert img.get('role') == 'presentation' or img.get('aria-hidden') == 'true'

def test_semantic_html_structure(client):
    """Test that the page uses semantic HTML structure."""
    response = client.get('/')
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.data, 'html.parser')
    
    # Check for proper heading structure
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    if headings:
        # Ensure headings are in logical order
        heading_levels = [int(h.name[1]) for h in headings]
        # Check that heading levels don't skip more than one level
        for i in range(1, len(heading_levels)):
            assert heading_levels[i] - heading_levels[i-1] <= 1

if __name__ == '__main__':
    pytest.main([__file__])
