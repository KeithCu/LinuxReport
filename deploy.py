#!/usr/bin/env python3
"""
deploy.py - Python version of deploy.sh
Performs the same operations: chown, restart Apache, wake up sites
"""

import os
import subprocess
import time
import sys
import urllib.request
import urllib.error
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# =============================================================================
# CONFIGURATION - Edit these values as needed
# =============================================================================

# Web server service name (change this if using nginx, gunicorn, etc.)
WEB_SERVER_SERVICE = "httpd"

# URLs for each service
URLS = {
    "LinuxReport2": "https://linuxreport.net",
    "CovidReport2": "https://covidreport.org",
    "aireport": "https://aireport.keithcu.com",
    "trumpreport": "https://trumpreport.info",
    "pvreport": "https://pvreport.org",
    "spacereport": "https://news.spaceelevatorwiki.com"
}

# =============================================================================
# FUNCTIONS
# =============================================================================

def run_command(cmd, check=True):
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if check:
            print(f"Error running command: {cmd}")
            print(f"Error: {e}")
            sys.exit(1)
        return None

def chown_directory(dir_name):
    """Change ownership for a directory"""
    print(f"Changing ownership for {dir_name}...")
    run_command(f"cd {dir_name} && sudo chown -R http:http * && cd ..")

def wake_up_site(dir_name, url):
    """Wake up a site with HTTP request"""
    site_name = dir_name.replace("Report2", "Report").replace("report", "Report")
    start_time = time.time()
    
    # Print when this task starts
    print(f"🔄 {site_name:<15} | Starting at {start_time:.3f}s")
    
    max_attempts = 5
    attempt = 1
    
    while attempt <= max_attempts:
        # Make the HTTP request
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Deploy-Script/1.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                http_status = response.getcode()
                response_content = response.read().decode('utf-8')
                
                # Get line 9 (index 8) for title
                content_lines = response_content.strip().split('\n')
                if len(content_lines) >= 9:
                    response_preview = content_lines[8].strip()
                else:
                    response_preview = ""
        except urllib.error.HTTPError as e:
            http_status = e.code
            response_preview = ""
        except urllib.error.URLError as e:
            http_status = "000"
            response_preview = ""
        except Exception as e:
            http_status = "000"
            response_preview = ""
        
        # Check if we got a successful response with content
        if response_preview.strip():
            status_icon = "✅"
            status_text = "SUCCESS"
            break
        elif http_status == "000":
            status_icon = "❌"
            status_text = "CONNECTION FAILED"
        else:
            status_icon = "⚠️"
            status_text = "EMPTY RESPONSE"
        
        if attempt < max_attempts:
            attempt += 1
            time.sleep(3)  # Wait between attempts
        else:
            status_icon = "💥"
            status_text = "FAILED"
            break
    
    # Format the output in columns
    title = response_preview.replace("<title>", "").replace("</title>", "").strip()
    if not title:
        title = "No title found"
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"{status_icon} {site_name:<15} | {http_status:<3} | {title:<40} | {duration:.2f}s")
    
    return status_text == "SUCCESS"

def wake_up_sites_round(round_name, round_number):
    """Wake up all sites concurrently for a specific round"""
    print(f"Step {round_number}: {round_name}...")
    print("=" * 100)
    print(f"{'Site':<15} | {'Status':<3} | {'Title':<40} | {'Duration'}")
    print("-" * 100)
    
    start_time = time.time()
    
    # Use a thread pool to run all sites concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit tasks with small delays to reduce thread contention
        futures = []
        for dir_name, url in URLS.items():
            future = executor.submit(wake_up_site, dir_name, url)
            futures.append(future)
            time.sleep(0.05)  # 50ms delay between submissions
        
        # Wait for all to complete
        success_count = 0
        for future in futures:
            if future.result():
                success_count += 1
    
    end_time = time.time()
    duration = end_time - start_time
    
    print("-" * 100)
    print(f"✅ {success_count}/{len(URLS)} sites deployed successfully!")
    print(f"⏱️  Total time: {duration:.2f} seconds")
    print("=" * 100)
    
    return success_count, duration

def wake_up_all_sites_concurrent():
    """Wake up all sites concurrently using ThreadPoolExecutor"""
    # First round
    success_count, duration = wake_up_sites_round("Waking up all sites", 3)
    
    # Wait 1 second after initial warm-up
    print("\n⏳ Waiting 1 second before second round...")
    time.sleep(1)
    
    # Second round
    second_success_count, second_duration = wake_up_sites_round("Second round - waking up all sites again", 4)

def warm_up_sites_only():
    """Just warm up all sites without chown or restart"""
    print("🔥 Warming up all sites only...")
    print("=" * 100)
    
    # Single round of warm-up
    success_count, duration = wake_up_sites_round("Warming up all sites", 1)
    
    print(f"🔥 Warm-up complete! {success_count}/{len(URLS)} sites warmed up in {duration:.2f} seconds")

def main():
    # =============================================================================
    # ARGUMENT PARSING
    # =============================================================================
    
    parser = argparse.ArgumentParser(description='Deploy and warm up sites')
    parser.add_argument('--warmup-only', action='store_true', 
                       help='Only warm up sites without chown or restart')
    
    args = parser.parse_args()
    
    # =============================================================================
    # MAIN EXECUTION
    # =============================================================================
    
    if args.warmup_only:
        # Just warm up sites
        warm_up_sites_only()
    else:
        # Full deployment
        overall_start = time.time()
        
        # Step 1: Change ownership for all directories
        print("Step 1: Changing ownership for all directories...")
        for dir_name in URLS.keys():
            chown_directory(dir_name)
        
        # Step 2: Restart web server
        print("Step 2: Restarting web server...")
        run_command(f"sudo systemctl restart {WEB_SERVER_SERVICE}")
        time.sleep(0.25)
        
        # Step 3: Wake up all sites concurrently
        wake_up_all_sites_concurrent()
        
        overall_end = time.time()
        total_duration = overall_end - overall_start
        
        print(f"🚀 Deployment complete! Total time: {total_duration:.2f} seconds")

if __name__ == "__main__":
    main() 