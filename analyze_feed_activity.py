#!/usr/bin/env python3
"""
Feed Activity Analyzer

This script analyzes feed history data to determine the optimal order
for RSS feeds based on their activity levels. It calculates scores based on:
1. Average bucket values (activity probabilities)
2. Recent activity from the 'recent' field
3. Whether the feed is in initial phase (less reliable data)
"""

import json
import statistics
from typing import Dict, List, Tuple
from pathlib import Path


def load_feed_history(file_path: str) -> Dict:
    """Load feed history data from JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def calculate_activity_score(feed_data: Dict) -> float:
    """
    Calculate an activity score for a feed based on multiple factors.
    
    Args:
        feed_data: Dictionary containing feed statistics
        
    Returns:
        float: Activity score (higher = more active)
    """
    buckets = feed_data.get('buckets', {})
    recent = feed_data.get('recent', [])
    in_initial_phase = feed_data.get('in_initial_phase', False)
    
    # Calculate average bucket value (activity probability)
    bucket_values = list(buckets.values())
    avg_bucket = statistics.mean(bucket_values) if bucket_values else 0.0
    
    # Calculate recent activity (sum of recent article counts)
    recent_activity = sum(entry[1] for entry in recent) if recent else 0
    
    # Normalize recent activity (assuming 5 recent entries is typical)
    normalized_recent = min(recent_activity / 5.0, 1.0) if recent else 0.0
    
    # Penalty for feeds in initial phase (less reliable data)
    initial_phase_penalty = 0.8 if in_initial_phase else 1.0
    
    # Weighted score: 70% bucket activity, 30% recent activity
    score = (0.7 * avg_bucket + 0.3 * normalized_recent) * initial_phase_penalty
    
    return score


def analyze_feed_activity(feed_history: Dict) -> List[Tuple[str, float, Dict]]:
    """
    Analyze feed activity and return sorted list of (url, score, details).
    
    Args:
        feed_history: Dictionary of feed history data
        
    Returns:
        List of tuples: (url, score, details)
    """
    results = []
    
    for url, feed_data in feed_history.items():
        score = calculate_activity_score(feed_data)
        
        # Extract additional details for reporting
        buckets = feed_data.get('buckets', {})
        recent = feed_data.get('recent', [])
        in_initial_phase = feed_data.get('in_initial_phase', False)
        
        avg_bucket = statistics.mean(list(buckets.values())) if buckets else 0.0
        recent_activity = sum(entry[1] for entry in recent) if recent else 0
        
        details = {
            'avg_bucket': avg_bucket,
            'recent_activity': recent_activity,
            'in_initial_phase': in_initial_phase,
            'total_buckets': len(buckets),
            'recent_entries': len(recent)
        }
        
        results.append((url, score, details))
    
    # Sort by score (highest first)
    results.sort(key=lambda x: x[1], reverse=True)
    
    return results


def generate_optimal_url_order(results: List[Tuple[str, float, Dict]]) -> List[str]:
    """Generate the optimal URL order for ALL_URLS configuration."""
    return [url for url, score, details in results]


def print_analysis_report(results: List[Tuple[str, float, Dict]], title: str = "Feed Activity Analysis"):
    """Print a detailed analysis report."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    
    print(f"\n{'Rank':<4} {'Score':<8} {'URL':<50} {'Avg Bucket':<12} {'Recent':<8} {'Phase'}")
    print("-" * 100)
    
    for i, (url, score, details) in enumerate(results, 1):
        # Truncate URL for display
        display_url = url[:47] + "..." if len(url) > 50 else url
        
        phase_indicator = "INIT" if details['in_initial_phase'] else "STABLE"
        
        print(f"{i:<4} {score:<8.4f} {display_url:<50} {details['avg_bucket']:<12.4f} "
              f"{details['recent_activity']:<8} {phase_indicator}")
    
    print(f"\n{'='*60}")
    print("RECOMMENDED ALL_URLS ORDER:")
    print(f"{'='*60}")
    
    for i, (url, score, details) in enumerate(results, 1):
        print(f"{i:2d}. {url}")
    
    print(f"\n{'='*60}")
    print("PYTHON CONFIGURATION:")
    print(f"{'='*60}")
    
    print("SITE_URLS = [")
    for url, score, details in results:
        print(f'    "{url}",')
    print("]")
    
    print(f"\n{'='*60}")


def main():
    """Main function to analyze PV feed history and generate optimized config."""
    feed_file = "feed_history-pv.json"
    
    if not Path(feed_file).exists():
        print(f"Error: {feed_file} not found!")
        print("Please ensure the feed history file exists in the current directory.")
        return
    
    try:
        print(f"Analyzing {feed_file}...")
        feed_history = load_feed_history(feed_file)
        results = analyze_feed_activity(feed_history)
        
        # Print detailed analysis report
        print_analysis_report(results, "PV Report Feed Activity Analysis")
        
        # Generate optimized configuration for pv_report_settings.py
        print(f"\n{'='*80}")
        print("OPTIMIZED SITE_URLS CONFIGURATION FOR pv_report_settings.py:")
        print(f"{'='*80}")
        
        print("    SITE_URLS=[")
        for url, score, details in results:
            print(f'        "{url}",')
        print("    ],")
        
        print(f"\n{'='*80}")
        print("RECOMMENDATIONS:")
        print(f"{'='*80}")
        
        print("1. Most Active Feeds (High Priority):")
        for i, (url, score, details) in enumerate(results[:3], 1):
            print(f"   {i}. {url}")
        
        print("\n2. Medium Activity Feeds (Medium Priority):")
        for i, (url, score, details) in enumerate(results[3:6], 4):
            print(f"   {i}. {url}")
        
        print("\n3. Low Activity Feeds (Consider Removal):")
        for i, (url, score, details) in enumerate(results[6:], 7):
            if details['recent_activity'] == 0 and details['avg_bucket'] < 0.1:
                print(f"   {i}. {url} (INACTIVE - Consider removing)")
            else:
                print(f"   {i}. {url}")
        
        print(f"\n{'='*80}")
        
    except (json.JSONDecodeError, IOError, OSError) as e:
        print(f"Error analyzing {feed_file}: {e}")


if __name__ == "__main__":
    main() 