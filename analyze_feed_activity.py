#!/usr/bin/env python3
"""
Analyze feed history JSON file and suggest sort order based on activity.

Usage:
    python analyze_feed_activity.py [feed_history_file.json] [settings_file.py]
    
    The settings file is AUTO-DETECTED from the feed history filename:
    - feed_history-robot.json -> robot_report_settings.py
    - feed_history-space.json -> space_report_settings.py
    - etc.
    
    If no files are provided, defaults to feed_history-robot.json and 
    auto-detects robot_report_settings.py.
    
    The settings file should contain a SITE_URLS list, which is used as the
    official list of active feeds. URLs in feed_history but not in SITE_URLS
    are filtered out as old/unused domains.
    
    You can optionally specify both files explicitly if needed.
"""

import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def calculate_activity_score(feed_data: Dict) -> Dict:
    """Calculate various activity metrics for a feed."""
    buckets = feed_data.get('buckets', {})
    recent = feed_data.get('recent', [])
    
    # Extract bucket values
    bucket_values = [v for v in buckets.values() if v > 0]
    
    # Calculate metrics
    max_bucket = max(bucket_values) if bucket_values else 0
    avg_bucket = sum(bucket_values) / len(bucket_values) if bucket_values else 0
    sum_buckets = sum(bucket_values)
    non_zero_count = len(bucket_values)
    
    # Recent activity metrics
    recent_sum = sum(r[1] for r in recent if isinstance(r, list) and len(r) >= 2)
    recent_non_zero = sum(1 for r in recent if isinstance(r, list) and len(r) >= 2 and r[1] > 0)
    
    # Combined activity score (weighted)
    # Higher weight on max bucket (peak activity) and recent activity
    score = (
        max_bucket * 0.4 +           # Peak activity weight
        avg_bucket * 0.2 +            # Average activity weight
        sum_buckets * 0.1 +           # Total activity weight
        recent_sum * 0.2 +            # Recent items weight
        non_zero_count * 0.1         # Frequency weight
    )
    
    return {
        'max_bucket': max_bucket,
        'avg_bucket': avg_bucket,
        'sum_buckets': sum_buckets,
        'non_zero_count': non_zero_count,
        'recent_sum': recent_sum,
        'recent_non_zero': recent_non_zero,
        'score': score
    }


def extract_site_urls(settings_file: Path) -> List[str]:
    """Extract SITE_URLS list from Python settings file."""
    if not settings_file.exists():
        print(f"Warning: Settings file not found: {settings_file}", file=sys.stderr)
        return []
    
    try:
        with open(settings_file, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading settings file: {e}", file=sys.stderr)
        return []
    
    # Try to find SITE_URLS using regex (more robust than ast parsing)
    # Look for SITE_URLS=[...] pattern
    pattern = r'SITE_URLS\s*=\s*\[(.*?)\]'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        # Extract the list content
        list_content = match.group(1)
        # Parse string literals from the list
        urls = []
        # Match quoted strings (both single and double quotes)
        url_pattern = r'["\']([^"\']+)["\']'
        for url_match in re.finditer(url_pattern, list_content):
            urls.append(url_match.group(1))
        return urls
    
    # Fallback: try AST parsing
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'SITE_URLS':
                        if isinstance(node.value, ast.List):
                            urls = []
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant):
                                    urls.append(elt.value)
                                elif isinstance(elt, ast.Str):  # Python < 3.8
                                    urls.append(elt.s)
                            return urls
    except Exception as e:
        print(f"Warning: Could not parse settings file with AST: {e}", file=sys.stderr)
    
    print(f"Warning: Could not extract SITE_URLS from {settings_file}", file=sys.stderr)
    return []


def guess_settings_filename(json_file: Path) -> Path:
    """Guess settings filename from feed history filename."""
    # feed_history-robot.json -> robot_report_settings.py
    # feed_history-space.json -> space_report_settings.py
    filename = json_file.stem  # e.g., "feed_history-robot"
    
    if filename.startswith("feed_history-"):
        domain = filename.replace("feed_history-", "")
        return Path(f"{domain}_report_settings.py")
    
    return Path("")


def analyze_feed_history(json_file: Path, site_urls: Optional[List[str]] = None) -> List[Tuple[str, Dict]]:
    """Analyze feed history JSON and return sorted list of URLs by activity.
    
    Args:
        json_file: Path to feed history JSON file
        site_urls: Optional list of URLs to filter by (only analyze these URLs)
    
    Returns:
        List of (url, metrics) tuples sorted by activity score
    """
    if not json_file.exists():
        print(f"Error: File not found: {json_file}", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Filter by SITE_URLS if provided
    if site_urls:
        site_urls_set = set(site_urls)
        filtered_data = {url: data[url] for url in site_urls_set if url in data}
        # Also include URLs from SITE_URLS that aren't in feed_history (with zero metrics)
        missing_urls = site_urls_set - set(data.keys())
        if missing_urls:
            print(f"Note: {len(missing_urls)} URL(s) in SITE_URLS but not in feed_history (will show with zero activity)", file=sys.stderr)
        data = filtered_data
    
    results = []
    
    # Process URLs from feed_history
    for url, feed_data in data.items():
        metrics = calculate_activity_score(feed_data)
        results.append((url, metrics))
    
    # Add URLs from SITE_URLS that aren't in feed_history (with zero metrics)
    if site_urls:
        site_urls_set = set(site_urls)
        existing_urls = set(data.keys())
        missing_urls = site_urls_set - existing_urls
        
        for url in missing_urls:
            # Create zero metrics for missing URLs
            zero_metrics = {
                'max_bucket': 0.0,
                'avg_bucket': 0.0,
                'sum_buckets': 0.0,
                'non_zero_count': 0,
                'recent_sum': 0,
                'recent_non_zero': 0,
                'score': 0.0
            }
            results.append((url, zero_metrics))
    
    # Sort by score descending
    results.sort(key=lambda x: x[1]['score'], reverse=True)
    
    return results


def print_analysis(results: List[Tuple[str, Dict]], show_detailed: bool = True):
    """Print analysis results."""
    print("\n" + "=" * 80)
    print("Feed Activity Analysis - Ranked by Activity Score (most active first)")
    print("=" * 80)
    
    for i, (url, metrics) in enumerate(results, 1):
        print(f"\n{i:2d}. {url}")
        if show_detailed:
            print(f"    Score: {metrics['score']:.4f}")
            print(f"    Max Bucket: {metrics['max_bucket']:.4f}")
            print(f"    Avg Bucket: {metrics['avg_bucket']:.4f}")
            print(f"    Recent Items: {metrics['recent_sum']}")
            print(f"    Active Buckets: {metrics['non_zero_count']}")
        else:
            print(f"    Score: {metrics['score']:.4f} | Recent: {metrics['recent_sum']} | Active Buckets: {metrics['non_zero_count']}")
    
    print("\n" + "=" * 80)


def print_sorted_urls(results: List[Tuple[str, Dict]], format_type: str = "python"):
    """Print sorted URLs in a format suitable for copying into settings file."""
    print("\n" + "=" * 80)
    print("Sorted URLs (for copying into settings file)")
    print("=" * 80)
    
    if format_type == "python":
        print("\nSITE_URLS=[")
        for url, _ in results:
            print(f'        "{url}",')
        print("    ],")
    elif format_type == "json":
        urls = [url for url, _ in results]
        print(json.dumps(urls, indent=4))
    else:  # plain list
        for url, _ in results:
            print(url)


def main():
    """Main function."""
    # Get input files
    if len(sys.argv) > 1:
        json_file = Path(sys.argv[1])
    else:
        # Default to feed_history-robot.json in current directory
        json_file = Path("feed_history-robot.json")
        if not json_file.exists():
            print("Usage: python analyze_feed_activity.py [feed_history_file.json] [settings_file.py]", file=sys.stderr)
            print(f"Error: Default file not found: {json_file}", file=sys.stderr)
            sys.exit(1)
    
    # Get settings file (auto-detect from feed history filename if not provided)
    if len(sys.argv) > 2:
        settings_file = Path(sys.argv[2])
        print(f"Using specified settings file: {settings_file}")
    else:
        # Auto-detect settings filename from feed history filename
        settings_file = guess_settings_filename(json_file)
        if settings_file and settings_file.exists():
            print(f"Auto-detected settings file: {settings_file}")
        elif settings_file:
            print(f"Auto-detected settings file: {settings_file} (not found)")
    
    # Extract SITE_URLS from settings file
    site_urls = None
    if settings_file.exists():
        site_urls = extract_site_urls(settings_file)
        if site_urls:
            print(f"Found {len(site_urls)} URLs in SITE_URLS")
        else:
            print("Warning: Could not extract SITE_URLS, analyzing all feeds in history", file=sys.stderr)
    else:
        print("Warning: Settings file not found - analyzing all feeds in feed_history (no filtering)", file=sys.stderr)
    
    # Analyze
    results = analyze_feed_history(json_file, site_urls)
    
    # Print results
    print_analysis(results, show_detailed=True)
    
    # Print sorted URLs for easy copying
    print_sorted_urls(results, format_type="python")
    
    # Summary statistics
    print("\n" + "=" * 80)
    print("Summary Statistics")
    print("=" * 80)
    total_feeds = len(results)
    active_feeds = sum(1 for _, m in results if m['score'] > 0.5)
    very_active_feeds = sum(1 for _, m in results if m['score'] > 2.0)
    inactive_feeds = sum(1 for _, m in results if m['score'] == 0.0)
    
    print(f"Total feeds: {total_feeds}")
    print(f"Very active (score > 2.0): {very_active_feeds}")
    print(f"Active (score > 0.5): {active_feeds}")
    print(f"Inactive (score = 0.0): {inactive_feeds}")
    
    # Show filtered out URLs if using SITE_URLS filter
    if site_urls:
        try:
            with open(json_file, 'r') as f:
                all_data = json.load(f)
            filtered_out = set(all_data.keys()) - set(site_urls)
            if filtered_out:
                print(f"\nFiltered out {len(filtered_out)} old/unused domain(s) not in SITE_URLS:")
                for url in sorted(filtered_out):
                    print(f"  - {url}")
        except Exception:
            pass
    
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
