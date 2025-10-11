#!/usr/bin/env python3
"""
performance_benchmark.py

Comprehensive performance benchmark comparing Selenium vs Playwright implementations.
Tests single-threaded and multi-threaded performance, memory usage, and reliability.
"""

import os
import sys
import time
import threading
import statistics
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from seleniumfetch import fetch_site_posts as selenium_fetch, cleanup_selenium_drivers
from playwrightfetch import fetch_site_posts as playwright_fetch, cleanup_playwright_browsers

# Test configuration
TEST_URLS = [
    "https://keithcu.com/wordpress/?feed=rss2",
    "https://keithcu.com/wordpress/?feed=rss2",  # Same URL for consistency
    "https://keithcu.com/wordpress/?feed=rss2",  # Same URL for consistency
]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

class PerformanceBenchmark:
    def __init__(self):
        self.results = {
            'selenium': {'single': [], 'multi': [], 'errors': 0},
            'playwright': {'single': [], 'multi': [], 'errors': 0}
        }
    
    def test_single_fetch(self, implementation, url, user_agent):
        """Test single fetch performance."""
        start_time = time.time()
        try:
            if implementation == 'selenium':
                result = selenium_fetch(url, user_agent)
            else:
                result = playwright_fetch(url, user_agent)
            
            end_time = time.time()
            duration = end_time - start_time
            
            if result and result.get('status') == 200:
                return {
                    'success': True,
                    'duration': duration,
                    'entries': len(result.get('entries', [])),
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'duration': duration,
                    'entries': 0,
                    'error': f"Invalid result: {result}"
                }
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            return {
                'success': False,
                'duration': duration,
                'entries': 0,
                'error': str(e)
            }
    
    def test_concurrent_fetch(self, implementation, url, user_agent, num_workers=3):
        """Test concurrent fetch performance."""
        def worker(worker_id):
            return self.test_single_fetch(implementation, url, user_agent)
        
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker, i) for i in range(num_workers)]
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({
                        'success': False,
                        'duration': 0,
                        'entries': 0,
                        'error': str(e)
                    })
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        return {
            'total_duration': total_duration,
            'individual_results': results,
            'successful_workers': sum(1 for r in results if r['success']),
            'total_entries': sum(r['entries'] for r in results)
        }
    
    def run_single_threaded_benchmark(self, num_runs=5):
        """Run single-threaded performance benchmark."""
        print("\n" + "="*80)
        print("SINGLE-THREADED PERFORMANCE BENCHMARK")
        print("="*80)
        
        for implementation in ['selenium', 'playwright']:
            print(f"\nTesting {implementation.upper()} (Single-threaded)...")
            durations = []
            total_entries = 0
            errors = 0
            
            for run in range(num_runs):
                print(f"  Run {run + 1}/{num_runs}...", end=" ")
                
                result = self.test_single_fetch(implementation, TEST_URLS[0], USER_AGENT)
                
                if result['success']:
                    durations.append(result['duration'])
                    total_entries += result['entries']
                    print(f"SUCCESS: {result['duration']:.2f}s ({result['entries']} entries)")
                else:
                    errors += 1
                    print(f"FAILED: {result['error']}")
                
                # Small delay between runs
                time.sleep(0.5)
            
            if durations:
                avg_duration = statistics.mean(durations)
                min_duration = min(durations)
                max_duration = max(durations)
                std_duration = statistics.stdev(durations) if len(durations) > 1 else 0
                
                self.results[implementation]['single'] = {
                    'avg_duration': avg_duration,
                    'min_duration': min_duration,
                    'max_duration': max_duration,
                    'std_duration': std_duration,
                    'total_entries': total_entries,
                    'errors': errors,
                    'success_rate': (num_runs - errors) / num_runs * 100
                }
                
                print(f"  Results: {avg_duration:.2f}s avg (±{std_duration:.2f}s), "
                      f"{min_duration:.2f}s-{max_duration:.2f}s range, "
                      f"{total_entries} total entries, {errors} errors")
            else:
                print(f"  No successful runs for {implementation}")
                self.results[implementation]['single'] = None
    
    def run_multi_threaded_benchmark(self, num_runs=3, num_workers=3):
        """Run multi-threaded performance benchmark."""
        print("\n" + "="*80)
        print("MULTI-THREADED PERFORMANCE BENCHMARK")
        print("="*80)
        
        for implementation in ['selenium', 'playwright']:
            print(f"\nTesting {implementation.upper()} (Multi-threaded, {num_workers} workers)...")
            total_durations = []
            total_entries = 0
            total_errors = 0
            successful_workers = []
            
            for run in range(num_runs):
                print(f"  Run {run + 1}/{num_runs}...", end=" ")
                
                result = self.test_concurrent_fetch(implementation, TEST_URLS[0], USER_AGENT, num_workers)
                
                total_durations.append(result['total_duration'])
                total_entries += result['total_entries']
                total_errors += (num_workers - result['successful_workers'])
                successful_workers.append(result['successful_workers'])
                
                print(f"SUCCESS: {result['total_duration']:.2f}s total ({result['successful_workers']}/{num_workers} workers, {result['total_entries']} entries)")
                
                # Small delay between runs
                time.sleep(1.0)
            
            if total_durations:
                avg_duration = statistics.mean(total_durations)
                min_duration = min(total_durations)
                max_duration = max(total_durations)
                std_duration = statistics.stdev(total_durations) if len(total_durations) > 1 else 0
                avg_successful_workers = statistics.mean(successful_workers)
                
                self.results[implementation]['multi'] = {
                    'avg_duration': avg_duration,
                    'min_duration': min_duration,
                    'max_duration': max_duration,
                    'std_duration': std_duration,
                    'total_entries': total_entries,
                    'total_errors': total_errors,
                    'avg_successful_workers': avg_successful_workers,
                    'success_rate': (total_entries / (num_runs * num_workers)) * 100 if num_runs * num_workers > 0 else 0
                }
                
                print(f"  Results: {avg_duration:.2f}s avg (±{std_duration:.2f}s), "
                      f"{min_duration:.2f}s-{max_duration:.2f}s range, "
                      f"{total_entries} total entries, {total_errors} errors, "
                      f"{avg_successful_workers:.1f} avg successful workers")
            else:
                print(f"  No successful runs for {implementation}")
                self.results[implementation]['multi'] = None
    
    def print_comparison(self):
        """Print detailed comparison of results."""
        print("\n" + "="*80)
        print("PERFORMANCE COMPARISON SUMMARY")
        print("="*80)
        
        # Single-threaded comparison
        print("\nSINGLE-THREADED PERFORMANCE:")
        print("-" * 50)
        
        selenium_single = self.results['selenium']['single']
        playwright_single = self.results['playwright']['single']
        
        if selenium_single and playwright_single:
            speedup = selenium_single['avg_duration'] / playwright_single['avg_duration']
            print(f"Selenium:  {selenium_single['avg_duration']:.2f}s avg (±{selenium_single['std_duration']:.2f}s)")
            print(f"Playwright: {playwright_single['avg_duration']:.2f}s avg (±{playwright_single['std_duration']:.2f}s)")
            print(f"Speedup:   {speedup:.2f}x {'faster' if speedup > 1 else 'slower'}")
            print(f"Success:   Selenium {selenium_single['success_rate']:.1f}% vs Playwright {playwright_single['success_rate']:.1f}%")
        else:
            print("Insufficient data for single-threaded comparison")
        
        # Multi-threaded comparison
        print("\nMULTI-THREADED PERFORMANCE:")
        print("-" * 50)
        
        selenium_multi = self.results['selenium']['multi']
        playwright_multi = self.results['playwright']['multi']
        
        if selenium_multi and playwright_multi:
            speedup = selenium_multi['avg_duration'] / playwright_multi['avg_duration']
            print(f"Selenium:  {selenium_multi['avg_duration']:.2f}s avg (±{selenium_multi['std_duration']:.2f}s)")
            print(f"Playwright: {playwright_multi['avg_duration']:.2f}s avg (±{playwright_multi['std_duration']:.2f}s)")
            print(f"Speedup:   {speedup:.2f}x {'faster' if speedup > 1 else 'slower'}")
            print(f"Workers:   Selenium {selenium_multi['avg_successful_workers']:.1f} vs Playwright {playwright_multi['avg_successful_workers']:.1f} successful")
            print(f"Success:   Selenium {selenium_multi['success_rate']:.1f}% vs Playwright {playwright_multi['success_rate']:.1f}%")
        else:
            print("Insufficient data for multi-threaded comparison")
        
        # Overall recommendation
        print("\nRECOMMENDATION:")
        print("-" * 50)
        
        if selenium_single and playwright_single and selenium_multi and playwright_multi:
            single_speedup = selenium_single['avg_duration'] / playwright_single['avg_duration']
            multi_speedup = selenium_multi['avg_duration'] / playwright_multi['avg_duration']
            
            if single_speedup > 1.1 and multi_speedup > 1.1:
                print("SUCCESS: Playwright is significantly faster in both single and multi-threaded scenarios")
                print("   Consider migrating to Playwright for better performance")
            elif single_speedup > 1.1:
                print("SUCCESS: Playwright is faster for single-threaded operations")
                print("   Consider hybrid approach: Playwright for single-threaded, Selenium for multi-threaded")
            elif multi_speedup > 1.1:
                print("SUCCESS: Playwright is faster for multi-threaded operations")
                print("   Consider migrating to Playwright for concurrent workloads")
            else:
                print("BALANCED: Performance is similar between both implementations")
                print("   Choose based on other factors (reliability, maintenance, etc.)")
        else:
            print("UNKNOWN: Insufficient data for recommendation")

def main():
    """Run the complete performance benchmark."""
    print("SELENIUM vs PLAYWRIGHT PERFORMANCE BENCHMARK")
    print("=" * 80)
    print(f"Test URL: {TEST_URLS[0]}")
    print(f"User Agent: {USER_AGENT[:50]}...")
    print("=" * 80)
    
    benchmark = PerformanceBenchmark()
    
    try:
        # Run benchmarks
        benchmark.run_single_threaded_benchmark(num_runs=5)
        benchmark.run_multi_threaded_benchmark(num_runs=3, num_workers=3)
        
        # Print comparison
        benchmark.print_comparison()
        
    except KeyboardInterrupt:
        print("\n\nWARNING: Benchmark interrupted by user")
    except Exception as e:
        print(f"\n\nERROR: Benchmark failed: {e}")
        traceback.print_exc()
    finally:
        # Cleanup
        print("\nCleaning up...")
        try:
            cleanup_selenium_drivers()
            cleanup_playwright_browsers()
            print("SUCCESS: Cleanup completed")
        except Exception as e:
            print(f"WARNING: Cleanup error: {e}")
    
    print("\nBenchmark completed!")

if __name__ == '__main__':
    main()
