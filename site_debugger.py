#!/usr/bin/env python3
"""
Generalized site debugging module for analyzing problematic sites.

This module provides reusable debugging utilities for analyzing websites
using Selenium (for JavaScript-heavy sites) or requests/BeautifulSoup
(for static sites).

Usage:
    - Generic:
        from site_debugger import SiteDebugger, DebugConfig

        config = DebugConfig(
            url="https://example.com",
            site_name="example",
            user_agent="My Bot -- https://example.com",
            wait_time=5,
            post_selectors=[".post", "article"],
            title_selectors=["h1", "h2", ".title"],
            link_selectors=["a[href*='/20']"],
        )

        debugger = SiteDebugger(config)
        result = debugger.debug_selenium()


"""

import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

import requests
from bs4 import BeautifulSoup


@dataclass
class DebugConfig:
    """Configuration for site debugging."""
    url: str
    site_name: str
    user_agent: str = "Site Debugger Bot"
    wait_time: int = 5
    post_selectors: List[str] = field(default_factory=lambda: [".post-item", "article", ".post"])
    title_selectors: List[str] = field(default_factory=lambda: ["h1", "h2", "h3", ".title"])
    link_selectors: List[str] = field(default_factory=lambda: ["a[href*='/20']", "a"])
    error_selectors: List[str] = field(default_factory=lambda: [
        "[class*='error']", "[class*='Error']", 
        "[id*='error']", "[id*='Error']"
    ])
    loading_selectors: List[str] = field(default_factory=lambda: [
        "[class*='loading']", "[class*='Loading']",
        "[class*='spinner']", "[class*='Spinner']"
    ])
    save_js: bool = True
    save_console: bool = True
    save_html: bool = True
    save_report: bool = True
    custom_analysis: Optional[Callable] = None  # Function to perform custom analysis


class SiteDebugger:
    """Generalized site debugging utility.

    Key behavior:

    - Each run that fetches from the network (Selenium or requests) MUST:
      - Save the HTML it received to disk (if save_html is True).
      - Return the paths of all generated artifacts in `result["files"]`.
    - All subsequent parsing / selector experiments for that snapshot MUST:
      - Operate ONLY on the saved HTML file (no additional network calls).
      - Be driven via the `debug_from_html()` helper below.

    This ensures:
    - Repeatable debugging against a frozen DOM snapshot.
    - No accidental hammering of source sites when iterating on selectors.
    """

    def __init__(self, config: DebugConfig):
        self.config = config
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.files_created: List[str] = []

    def _get_file_prefix(self) -> str:
        """Generate file prefix from site name and timestamp."""
        safe_name = self.config.site_name.lower().replace('.', '_').replace('/', '_')
        return f"{safe_name}_debug_{self.timestamp}"

    def debug_from_html(self, html_path: str, is_selenium: bool = False) -> Optional[Dict[str, Any]]:
        """
        Run analysis and reports using an existing HTML file on disk.

        This is the canonical way to iterate on selectors/parsing logic without
        performing additional network fetches.

        Args:
            html_path: Path to a previously saved HTML file (typically from
                       debug_selenium() or debug_requests()).
            is_selenium: If True, run Selenium-style DOM/selector analysis
                         semantics where applicable; otherwise use the
                         requests/BeautifulSoup analysis.

        Returns:
            Result dict (same shape as debug_* methods) or None on error.
        """
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                html = f.read()
        except Exception as e:
            print(f"Error reading HTML from {html_path}: {e}")
            return None

        # Common result scaffold
        result: Dict[str, Any] = {
            "url": self.config.url,
            "title": "N/A (from file)",
            "current_url": self.config.url,
            "html_length": len(html),
            "files": {"html": html_path},
        }

        # For Selenium-style analysis, we rely on BeautifulSoup plus the
        # same selector logic patterns used in _analyze_requests_page.
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.text:
            result["title"] = soup.title.text.strip()

        if is_selenium:
            # Reuse the BeautifulSoup-based analysis but label appropriately.
            analysis = self._analyze_requests_page(soup)
            result.update(analysis)
            console_logs: List[Any] = []
            if self.config.save_report:
                report_filename = self._save_requests_report(result, soup)
                result["files"]["report"] = report_filename
                self.files_created.append(report_filename)
        else:
            analysis = self._analyze_requests_page(soup)
            result.update(analysis)
            if self.config.custom_analysis:
                try:
                    custom_result = self.config.custom_analysis(soup)
                    result["custom_analysis"] = custom_result
                except Exception as e:
                    print(f"Custom analysis error (from HTML): {e}")
                    result["custom_analysis_error"] = str(e)
            if self.config.save_report:
                report_filename = self._save_requests_report(result, soup)
                result["files"]["report"] = report_filename
                self.files_created.append(report_filename)

        return result
    
    def debug_selenium(self) -> Optional[Dict[str, Any]]:
        """
        Debug a site using Selenium (for JavaScript-heavy sites).
        
        Returns dict with debug results and file paths, or None on error.
        """
        print(f"Starting Selenium debug for {self.config.url}...")
        
        # Setup Chrome options
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-agent={self.config.user_agent}")
        options.add_argument("--enable-logging")
        options.add_argument("--v=1")
        
        # Create driver
        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        driver = webdriver.Chrome(service=service, options=options)
        
        try:
            print(f"Loading {self.config.url}...")
            driver.get(self.config.url)
            
            print(f"Waiting {self.config.wait_time} seconds for page to load...")
            time.sleep(self.config.wait_time)
            
            # Get page source
            html_content = driver.page_source
            
            result = {
                'url': self.config.url,
                'title': driver.title,
                'current_url': driver.current_url,
                'html_length': len(html_content),
                'files': {}
            }
            
            # Save HTML
            if self.config.save_html:
                html_filename = f"{self._get_file_prefix()}.html"
                with open(html_filename, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"HTML saved to: {html_filename}")
                result['files']['html'] = html_filename
                self.files_created.append(html_filename)
            
            # Get console logs
            console_logs = []
            if self.config.save_console:
                try:
                    console_logs = driver.get_log('browser')
                    if console_logs:
                        console_filename = f"{self._get_file_prefix()}_console.log"
                        with open(console_filename, 'w', encoding='utf-8') as f:
                            for log in console_logs:
                                f.write(f"{log['timestamp']}: {log['level']} - {log['message']}\n")
                        print(f"Console logs saved to: {console_filename}")
                        result['files']['console'] = console_filename
                        self.files_created.append(console_filename)
                    else:
                        print("No console logs found")
                except Exception as e:
                    print(f"Could not get console logs: {e}")
            
            # Extract and save JavaScript
            js_content = []
            script_count = 0
            if self.config.save_js:
                try:
                    js_files = driver.find_elements(By.TAG_NAME, "script")
                    script_count = len(js_files)
                    
                    for i, script in enumerate(js_files):
                        src = script.get_attribute('src')
                        if src:
                            js_content.append(f"// External script {i+1}: {src}")
                        else:
                            inline_js = script.get_attribute('innerHTML')
                            if inline_js:
                                js_content.append(f"// Inline script {i+1}:")
                                js_content.append(inline_js)
                                js_content.append("// " + "="*50)
                    
                    if js_content:
                        js_filename = f"{self._get_file_prefix()}.js"
                        with open(js_filename, 'w', encoding='utf-8') as f:
                            f.write('\n'.join(js_content))
                        print(f"JavaScript content saved to: {js_filename}")
                        result['files']['javascript'] = js_filename
                        self.files_created.append(js_filename)
                except Exception as e:
                    print(f"Error extracting JavaScript: {e}")
            
            # Analyze page elements
            analysis = self._analyze_selenium_page(driver)
            result.update(analysis)
            result['script_count'] = script_count
            result['console_log_count'] = len(console_logs)
            
            # Custom analysis
            if self.config.custom_analysis:
                try:
                    custom_result = self.config.custom_analysis(driver)
                    result['custom_analysis'] = custom_result
                except Exception as e:
                    print(f"Custom analysis error: {e}")
                    result['custom_analysis_error'] = str(e)
            
            # Save report
            if self.config.save_report:
                report_filename = self._save_selenium_report(result, console_logs)
                result['files']['report'] = report_filename
                self.files_created.append(report_filename)
            
            return result
            
        except Exception as e:
            print(f"Error during Selenium fetch: {e}")
            import traceback
            traceback.print_exc()
            return None
            
        finally:
            driver.quit()
            print("Driver closed")
    
    def _analyze_selenium_page(self, driver) -> Dict[str, Any]:
        """Analyze page elements using Selenium."""
        analysis = {
            'post_items': [],
            'error_elements': [],
            'loading_elements': [],
            'candidate_articles': []
        }
        
        # Try different post selectors
        for selector in self.config.post_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    analysis['post_items'].append({
                        'selector': selector,
                        'count': len(elements),
                        'sample_texts': [e.text[:100] for e in elements[:3]]
                    })
                    print(f"Found {len(elements)} elements with selector: {selector}")
            except Exception as e:
                print(f"Error with selector {selector}: {e}")
        
        # Check for errors
        for selector in self.config.error_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    analysis['error_elements'].append({
                        'selector': selector,
                        'count': len(elements),
                        'sample': [{
                            'class': e.get_attribute('class'),
                            'id': e.get_attribute('id'),
                            'text': e.text[:200]
                        } for e in elements[:5]]
                    })
            except Exception:
                pass
        
        # Check for loading states
        for selector in self.config.loading_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    analysis['loading_elements'].append({
                        'selector': selector,
                        'count': len(elements)
                    })
            except Exception:
                pass
        
        # Find candidate articles using link selectors
        for selector in self.config.link_selectors:
            try:
                anchors = driver.find_elements(By.CSS_SELECTOR, selector)
                candidates = []
                for el in anchors[:30]:
                    try:
                        text = el.text.strip()
                        href = el.get_attribute('href')
                        if text and href:
                            # Filter out navigation/menu links
                            if any(skip in href.lower() for skip in ['/category/', '/tag/', '/author/', '#', 'javascript:']):
                                continue
                            candidates.append({'text': text, 'href': href})
                    except Exception:
                        continue
                if candidates:
                    analysis['candidate_articles'].append({
                        'selector': selector,
                        'count': len(candidates),
                        'samples': candidates[:10]
                    })
            except Exception as e:
                print(f"Error with link selector {selector}: {e}")
        
        return analysis
    
    def _save_selenium_report(self, result: Dict[str, Any], console_logs: List) -> str:
        """Save a comprehensive debug report."""
        report_filename = f"{self._get_file_prefix()}_report.txt"
        
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(f"{self.config.site_name} Debug Report - {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            f.write(f"URL: {self.config.url}\n")
            f.write(f"Page Title: {result.get('title', 'N/A')}\n")
            f.write(f"Current URL: {result.get('current_url', 'N/A')}\n")
            f.write(f"HTML Length: {result.get('html_length', 0)} characters\n")
            f.write(f"Script Tags: {result.get('script_count', 0)}\n")
            f.write(f"Console Logs: {result.get('console_log_count', 0)}\n\n")
            
            # Post items
            if result.get('post_items'):
                f.write("Post Items Found:\n")
                f.write("-"*20 + "\n")
                for item in result['post_items']:
                    f.write(f"  Selector: {item['selector']}\n")
                    f.write(f"  Count: {item['count']}\n")
                    if item.get('sample_texts'):
                        for text in item['sample_texts']:
                            f.write(f"    - {text[:100]}...\n")
                    f.write("\n")
            
            # Candidate articles
            if result.get('candidate_articles'):
                f.write("Candidate Articles:\n")
                f.write("-"*20 + "\n")
                for item in result['candidate_articles']:
                    f.write(f"  Selector: {item['selector']}\n")
                    f.write(f"  Count: {item['count']}\n")
                    for sample in item.get('samples', [])[:5]:
                        f.write(f"    - {sample['text'][:80]}... -> {sample['href']}\n")
                    f.write("\n")
            
            # Errors
            if result.get('error_elements'):
                f.write("Error Elements:\n")
                f.write("-"*20 + "\n")
                for item in result['error_elements']:
                    f.write(f"  Selector: {item['selector']}\n")
                    f.write(f"  Count: {item['count']}\n")
                    for sample in item.get('sample', [])[:3]:
                        f.write(f"    Class: {sample.get('class')}\n")
                        f.write(f"    ID: {sample.get('id')}\n")
                        f.write(f"    Text: {sample.get('text', '')[:150]}...\n")
                        f.write("-"*10 + "\n")
                    f.write("\n")
            
            # Loading elements
            if result.get('loading_elements'):
                f.write("Loading Elements:\n")
                f.write("-"*20 + "\n")
                for item in result['loading_elements']:
                    f.write(f"  Selector: {item['selector']} - Count: {item['count']}\n")
                f.write("\n")
            
            # Console logs
            if console_logs:
                f.write("Console Logs:\n")
                f.write("-"*20 + "\n")
                for log in console_logs:
                    f.write(f"{log['timestamp']}: {log['level']} - {log['message']}\n")
                f.write("\n")
            
            # Custom analysis
            if result.get('custom_analysis'):
                f.write("Custom Analysis:\n")
                f.write("-"*20 + "\n")
                f.write(f"{json.dumps(result['custom_analysis'], indent=2)}\n")
        
        print(f"Debug report saved to: {report_filename}")
        return report_filename
    
    def debug_requests(self) -> Optional[Dict[str, Any]]:
        """
        Debug a site using requests/BeautifulSoup (for static sites).
        
        Returns dict with debug results and file paths, or None on error.
        """
        print(f"Starting requests debug for {self.config.url}...")
        
        try:
            headers = {
                'User-Agent': self.config.user_agent
            }
            
            print(f"Fetching {self.config.url}...")
            response = requests.get(self.config.url, timeout=10, headers=headers)
            print(f"Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"Failed to fetch page: {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            result = {
                'url': self.config.url,
                'status_code': response.status_code,
                'title': soup.title.text if soup.title else 'No title',
                'html_length': len(response.text),
                'files': {}
            }
            
            # Save HTML
            if self.config.save_html:
                html_filename = f"{self._get_file_prefix()}.html"
                with open(html_filename, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"HTML saved to: {html_filename}")
                result['files']['html'] = html_filename
                self.files_created.append(html_filename)
            
            # Analyze page
            analysis = self._analyze_requests_page(soup)
            result.update(analysis)
            
            # Custom analysis
            if self.config.custom_analysis:
                try:
                    custom_result = self.config.custom_analysis(soup)
                    result['custom_analysis'] = custom_result
                except Exception as e:
                    print(f"Custom analysis error: {e}")
                    result['custom_analysis_error'] = str(e)
            
            # Save report
            if self.config.save_report:
                report_filename = self._save_requests_report(result, soup)
                result['files']['report'] = report_filename
                self.files_created.append(report_filename)
            
            return result
            
        except Exception as e:
            print(f"Error during requests fetch: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _analyze_requests_page(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze page elements using BeautifulSoup."""
        analysis = {
            'articles': [],
            'article_containers': [],
            'candidate_links': []
        }
        
        # Look for article elements
        articles = soup.find_all('article')
        if articles:
            article_data = []
            for i, article in enumerate(articles[:10]):
                article_info = {
                    'index': i,
                    'classes': article.get('class', []),
                }
                
                # Find title
                for title_tag in ['h1', 'h2', 'h3', 'h4']:
                    title_elem = article.find(title_tag)
                    if title_elem:
                        article_info['title'] = title_elem.text.strip()
                        article_info['title_tag'] = title_elem.name
                        break
                
                # Find link
                link_elem = article.find('a')
                if link_elem and link_elem.get('href'):
                    article_info['link'] = link_elem['href']
                
                # Find date/time
                time_elem = article.find(['time', 'span'], 
                                         class_=lambda x: x and ('date' in str(x).lower() or 'time' in str(x).lower()))
                if time_elem:
                    article_info['time_text'] = time_elem.text.strip()
                
                article_data.append(article_info)
            
            analysis['articles'] = article_data
        
        # Check for other common containers
        containers = [
            ('div', {'class': 'post'}),
            ('div', {'class': 'entry'}),
            ('div', {'class': 'article'}),
            ('section', {'class': 'post'}),
            ('li', {'class': 'post'}),
        ]
        
        for tag, attrs in containers:
            elements = soup.find_all(tag, attrs)
            if elements:
                analysis['article_containers'].append({
                    'tag': tag,
                    'attrs': attrs,
                    'count': len(elements)
                })
        
        # Find candidate links (anchors with year in URL)
        anchors = soup.find_all('a', href=lambda x: x and '/20' in x)
        candidates = []
        for anchor in anchors[:30]:
            href = anchor.get('href', '')
            text = anchor.text.strip()
            if text and href and not any(skip in href.lower() for skip in ['/category/', '/tag/', '/author/']):
                candidates.append({'text': text, 'href': href})
        
        if candidates:
            analysis['candidate_links'] = candidates[:20]
        
        return analysis
    
    def _save_requests_report(self, result: Dict[str, Any], soup: BeautifulSoup) -> str:
        """Save a comprehensive debug report for requests-based analysis."""
        report_filename = f"{self._get_file_prefix()}_report.txt"
        
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(f"{self.config.site_name} Debug Report (Requests) - {datetime.now()}\n")
            f.write("="*50 + "\n\n")
            f.write(f"URL: {self.config.url}\n")
            f.write(f"Status Code: {result.get('status_code', 'N/A')}\n")
            f.write(f"Page Title: {result.get('title', 'N/A')}\n")
            f.write(f"HTML Length: {result.get('html_length', 0)} characters\n\n")
            
            # Articles
            if result.get('articles'):
                f.write("Articles Found:\n")
                f.write("-"*20 + "\n")
                for article in result['articles'][:5]:
                    f.write(f"Article {article.get('index', '?')}:\n")
                    if article.get('title'):
                        f.write(f"  Title: {article['title'][:100]}\n")
                    if article.get('link'):
                        f.write(f"  Link: {article['link']}\n")
                    if article.get('time_text'):
                        f.write(f"  Time: {article['time_text']}\n")
                    if article.get('classes'):
                        f.write(f"  Classes: {article['classes']}\n")
                    f.write("\n")
            
            # Other containers
            if result.get('article_containers'):
                f.write("Other Article Containers:\n")
                f.write("-"*20 + "\n")
                for container in result['article_containers']:
                    f.write(f"  {container['tag']} with {container['attrs']}: {container['count']}\n")
                f.write("\n")
            
            # Candidate links
            if result.get('candidate_links'):
                f.write("Candidate Article Links:\n")
                f.write("-"*20 + "\n")
                for link in result['candidate_links'][:10]:
                    f.write(f"  - {link['text'][:80]}... -> {link['href']}\n")
                f.write("\n")
            
            # Custom analysis
            if result.get('custom_analysis'):
                f.write("Custom Analysis:\n")
                f.write("-"*20 + "\n")
                f.write(f"{json.dumps(result['custom_analysis'], indent=2)}\n")
        
        print(f"Debug report saved to: {report_filename}")
        return report_filename
    
    def test_fetch_config(self, fetch_config_class, fetch_function) -> bool:
        """
        Test a fetch configuration using the site's fetch function.
        
        Args:
            fetch_config_class: The fetch config class to test
            fetch_function: The fetch function (e.g., fetch_site_posts)
        
        Returns:
            True if successful, False otherwise
        """
        print(f"Testing fetch configuration for {self.config.site_name}...")
        
        try:
            config = fetch_config_class()
            print(f"Configuration: {config}")
            
            print(f"Fetching posts from {self.config.url}...")
            result = fetch_function(self.config.url, self.config.user_agent)
            
            if result and 'entries' in result:
                entries = result['entries']
                print(f"Successfully fetched {len(entries)} posts")
                
                # Show first few entries
                for i, entry in enumerate(entries[:3]):
                    print(f"\nPost {i+1}:")
                    print(f"  Title: {entry.get('title', 'N/A')[:100]}...")
                    print(f"  Link: {entry.get('link', 'N/A')}")
                    print(f"  Published: {entry.get('published', 'N/A')}")
                
                return True
            else:
                print("No entries found in result")
                print(f"Result keys: {result.keys() if result else 'None'}")
                return False
                
        except Exception as e:
            print(f"Error during fetch: {e}")
            import traceback
            traceback.print_exc()
            return False

