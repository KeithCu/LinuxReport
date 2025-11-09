#!/usr/bin/env python3
"""
Unified test script for debugging problematic sites.

This script consolidates all the individual debug scripts into a single
generalized test file that can handle various site formats.

Usage:
    python test_site_debug.py --site patriots
    python test_site_debug.py --site uniteai
    python test_site_debug.py --site venturebeat
    python test_site_debug.py --site all
    python test_site_debug.py --site custom --url https://example.com --name example
"""

import sys
import os
import argparse
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from site_debugger import SiteDebugger, DebugConfig


def test_patriots_selenium():
    """Test patriots.win using Selenium debugging."""
    config = DebugConfig(
        url="https://patriots.win",
        site_name="patriots.win",
        user_agent="Trump Report -- https://trumpreport.info",
        wait_time=5,
        post_selectors=[".post-item", "a[href^='/p/']"],
        link_selectors=["a[href^='/p/']"],
    )
    
    debugger = SiteDebugger(config)
    result = debugger.debug_selenium()
    
    if result:
        print(f"\n[SUCCESS] Patriots.win debug completed!")
        print(f"Files created: {', '.join(result.get('files', {}).values())}")
        print(f"\nSummary:")
        if result.get('post_items'):
            for item in result['post_items']:
                print(f"  - {item['selector']}: {item['count']} items")
        return True
    else:
        print("\n[FAILED] Patriots.win debug failed!")
        return False


def test_patriots_fetch_config():
    """Test patriots.win fetch configuration."""
    try:
        from trump_report_settings import PatriotsWinFetchConfig
        from seleniumfetch import fetch_site_posts
    except ImportError as e:
        print(f"Could not import required modules: {e}")
        return False
    
    config = DebugConfig(
        url="https://patriots.win",
        site_name="patriots.win",
        user_agent="Trump Report -- https://trumpreport.info",
    )
    
    debugger = SiteDebugger(config)
    return debugger.test_fetch_config(PatriotsWinFetchConfig, fetch_site_posts)


def test_uniteai_selenium():
    """Test Unite.AI Robotics using Selenium debugging."""
    
    def custom_analysis(driver):
        """Custom analysis for Unite.AI - verify post structure matches config."""
        from selenium.webdriver.common.by import By
        # Check for post containers matching the config
        post_containers = driver.find_elements(By.CSS_SELECTOR, "li.mvp-blog-story-wrap")
        articles = []
        for container in post_containers[:10]:
            try:
                # Find title
                title_elem = container.find_element(By.CSS_SELECTOR, "h2")
                title = title_elem.text.strip() if title_elem else None
                
                # Find link using the actual config selector
                link_elem = container.find_element(By.CSS_SELECTOR, ".mvp-blog-story-text a[rel='bookmark']")
                link = link_elem.get_attribute('href') if link_elem else None
                
                # Find published date
                date_elem = container.find_element(By.CSS_SELECTOR, "span.mvp-cd-date")
                date = date_elem.text.strip() if date_elem else None
                
                if title and link:
                    articles.append({
                        'title': title,
                        'link': link,
                        'date': date
                    })
            except Exception as e:
                continue
        return {'found_articles': articles, 'total_containers': len(post_containers)}
    
    config = DebugConfig(
        url="https://www.unite.ai/",
        site_name="uniteai_main",
        user_agent="Robot Report -- https://robotreport.keithcu.com",
        wait_time=5,
        post_selectors=["li.mvp-blog-story-wrap"],
        title_selectors=["h2"],
        link_selectors=[".mvp-blog-story-text a[rel='bookmark']"],
        custom_analysis=custom_analysis,
    )
    
    debugger = SiteDebugger(config)
    result = debugger.debug_selenium()
    
    if result:
        print(f"\n[SUCCESS] Unite.AI debug completed!")
        print(f"Files created: {', '.join(result.get('files', {}).values())}")
        
        # Show post items found
        if result.get('post_items'):
            print(f"\nPost containers found:")
            for item in result['post_items']:
                print(f"  - {item['selector']}: {item['count']} items")
        
        # Show custom analysis results
        if result.get('custom_analysis'):
            analysis = result['custom_analysis']
            total = analysis.get('total_containers', 0)
            articles = analysis.get('found_articles', [])
            print(f"\nCustom analysis results:")
            print(f"  - Total post containers: {total}")
            print(f"  - Successfully parsed articles: {len(articles)}")
            if articles:
                print(f"\nFirst 5 articles:")
                for i, article in enumerate(articles[:5]):
                    print(f"    {i+1}. {article['title'][:60]}...")
                    print(f"       Link: {article['link']}")
                    print(f"       Date: {article['date']}")
        
        return True
    else:
        print("\n[FAILED] Unite.AI debug failed!")
        return False


def test_venturebeat_requests():
    """
    Test VentureBeat using requests/BeautifulSoup debugging.

    Behavior:
    - On first run (no existing saved HTML), fetch from network via debug_requests(),
      save the HTML snapshot, and report.
    - On subsequent runs, if the saved HTML exists, re-run analysis ONLY against
      the saved file via debug_from_html() with no additional network calls.
    """
    def custom_analysis(soup):
        """Custom analysis for VentureBeat - analyze article structure."""
        articles = soup.find_all('article')
        article_data = []

        for i, article in enumerate(articles[:5]):
            article_info = {
                'index': i,
                'classes': article.get('class', []),
            }

            for title_tag in ['h1', 'h2', 'h3', 'h4']:
                title_elem = article.find(title_tag)
                if title_elem:
                    article_info['title'] = title_elem.text.strip()
                    article_info['title_tag'] = title_elem.name
                    article_info['title_classes'] = title_elem.get('class', [])
                    break

            link_elem = article.find('a')
            if link_elem and link_elem.get('href'):
                article_info['link'] = link_elem['href']

            time_elem = article.find(
                ['time', 'span'],
                class_=lambda x: x and ('date' in str(x).lower() or 'time' in str(x).lower())
            )
            if time_elem:
                article_info['time_text'] = time_elem.text.strip()
                article_info['time_attrs'] = dict(time_elem.attrs)

            article_data.append(article_info)

        return {'article_analysis': article_data}

    config = DebugConfig(
        url="https://venturebeat.com/category/ai/",
        site_name="venturebeat_ai",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        ),
        custom_analysis=custom_analysis,
    )

    debugger = SiteDebugger(config)

    # Determine expected HTML snapshot path used by debug_requests()
    html_path = f"{config.site_name.lower().replace('.', '_').replace('/', '_')}_debug_{debugger.timestamp}.html"

    if os.path.exists(html_path):
        print(f"Re-using existing HTML snapshot for VentureBeat: {html_path}")
        result = debugger.debug_from_html(html_path, is_selenium=False)
    else:
        print("No existing HTML snapshot found for VentureBeat; fetching once via debug_requests()")
        result = debugger.debug_requests()
        if result and 'html' in result.get('files', {}):
            html_path = result['files']['html']
            print(f"Saved HTML snapshot for future runs: {html_path}")

    if result:
        print(f"\n[SUCCESS] VentureBeat debug completed!")
        print(f"Files created: {', '.join(result.get('files', {}).values())}")
        if result.get('articles'):
            print(f"\nFound {len(result['articles'])} articles")
            for article in result['articles'][:3]:
                if article.get('title'):
                    print(f"  - {article['title'][:80]}...")
        return True
    else:
        print("\n[FAILED] VentureBeat debug failed!")
        return False


def run_custom_site(url: str, name: str, use_selenium: bool = True) -> bool:
    """
    Helper to debug a custom site.

    Note:
    - This is an executable helper, not a pytest test.
    - It is intentionally NOT named like `test_*` to avoid pytest treating
      `url` / `name` as fixtures.
    """
    print(f"Testing custom site: {name} at {url}")

    config = DebugConfig(
        url=url,
        site_name=name,
        user_agent="Site Debugger Bot",
        wait_time=5,
    )

    debugger = SiteDebugger(config)

    if use_selenium:
        result = debugger.debug_selenium()
    else:
        result = debugger.debug_requests()

    if result:
        print(f"\n[SUCCESS] Custom site debug completed!")
        print(f"Files created: {', '.join(result.get('files', {}).values())}")
        return True
    else:
        print("\n[FAILED] Custom site debug failed!")
        return False


def main():
    parser = argparse.ArgumentParser(description='Test site debugging utilities')
    parser.add_argument('--site', type=str, required=True,
                       choices=['patriots', 'patriots-config', 'uniteai', 'venturebeat', 'all', 'custom'],
                       help='Site to test')
    parser.add_argument('--url', type=str, help='Custom URL (required for --site custom)')
    parser.add_argument('--name', type=str, help='Custom site name (required for --site custom)')
    parser.add_argument('--selenium', action='store_true', default=True,
                       help='Use Selenium for custom sites (default: True)')
    parser.add_argument('--requests', action='store_true',
                       help='Use requests/BeautifulSoup instead of Selenium for custom sites')
    
    args = parser.parse_args()
    
    if args.site == 'custom':
        if not args.url or not args.name:
            print("ERROR: --url and --name are required for custom sites")
            sys.exit(1)
        use_selenium = not args.requests
        success = test_custom_site(args.url, args.name, use_selenium)
    elif args.site == 'patriots':
        success = test_patriots_selenium()
    elif args.site == 'patriots-config':
        success = test_patriots_fetch_config()
    elif args.site == 'uniteai':
        success = test_uniteai_selenium()
    elif args.site == 'venturebeat':
        success = test_venturebeat_requests()
    elif args.site == 'all':
        print("Running all tests...\n")
        results = []
        
        print("\n" + "="*60)
        print("TEST 1: Patriots.win (Selenium)")
        print("="*60)
        results.append(('Patriots (Selenium)', test_patriots_selenium()))
        
        print("\n" + "="*60)
        print("TEST 2: Patriots.win (Fetch Config)")
        print("="*60)
        results.append(('Patriots (Config)', test_patriots_fetch_config()))
        
        print("\n" + "="*60)
        print("TEST 3: Unite.AI (Selenium)")
        print("="*60)
        results.append(('Unite.AI', test_uniteai_selenium()))
        
        print("\n" + "="*60)
        print("TEST 4: VentureBeat (Requests)")
        print("="*60)
        results.append(('VentureBeat', test_venturebeat_requests()))
        
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for test_name, result in results:
            status = "PASS" if result else "FAIL"
            print(f"{test_name}: {status}")
        
        success = all(result for _, result in results)
    else:
        print(f"Unknown site: {args.site}")
        sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

