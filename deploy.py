#!/usr/bin/env python3
"""
deploy.py - Python version of deploy.sh
Performs the same operations: chown, restart Apache, wake up sites

NEW FEATURES:
- Deploy specific files from LinuxReport2 to all other directories
- Automatically add deployed files to git in all directories
- Handle git conflicts by providing a clean deployment workflow

USAGE EXAMPLES:
  python deploy.py                                    # Full deployment
  python deploy.py --warmup-only                      # Just warm up sites
  python deploy.py --files Tor.py config.yaml         # Deploy specific files only (no warmup)
  python deploy.py --files shared.py app.py           # Deploy multiple files only (no warmup)
"""

import os
import subprocess
import time
import sys
import urllib.request
import urllib.error
import socket
import argparse
import shutil
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
            # Use Googlebot user agent to prevent triggering refreshes/background updates
            # This ensures deploy requests don't trigger background refreshes when starting the app
            req = urllib.request.Request(url, headers={'User-Agent': 'LinuxReportDeployBot'})
            with urllib.request.urlopen(req, timeout=10) as response:
                http_status = response.getcode()
                response_content = response.read().decode('utf-8')
                
                # Search for title in the top 15 lines
                content_lines = response_content.strip().split('\n')
                response_preview = ""
                
                # Look for title tag in the first 15 lines
                for i in range(min(15, len(content_lines))):
                    line = content_lines[i].strip()
                    if '<title>' in line and '</title>' in line:
                        response_preview = line
                        break
                
                # If no title found in first 15 lines, use the first non-empty line as fallback
                if not response_preview:
                    for i in range(min(15, len(content_lines))):
                        line = content_lines[i].strip()
                        if line and not line.startswith('<!') and not line.startswith('<html'):
                            response_preview = line
                            break
        except urllib.error.HTTPError as e:
            http_status = e.code
            response_preview = ""
        except urllib.error.URLError as e:
            http_status = "000"
            response_preview = ""
        except (socket.timeout, ConnectionResetError) as e:
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

def copy_files_to_directories(files, target_dirs):
    """Copy specified files from LinuxReport2 to other directories"""
    print(f"📋 Copying {len(files)} file(s) to {len(target_dirs)} directories...")

    linux_report_dir = None
    for dir_name in URLS.keys():
        if "LinuxReport2" in dir_name:
            linux_report_dir = dir_name
            break

    if not linux_report_dir:
        print("❌ Could not find LinuxReport2 directory in URLS")
        return False

    if not os.path.exists(linux_report_dir):
        print(f"❌ Source directory {linux_report_dir} does not exist")
        return False

    success_count = 0
    for target_dir in target_dirs:
        if target_dir == linux_report_dir:
            continue  # Skip copying to itself

        if not os.path.exists(target_dir):
            print(f"⚠️  Target directory {target_dir} does not exist, skipping")
            continue

        print(f"  📂 Copying to {target_dir}...")

        for file_path in files:
            source_file = os.path.join(linux_report_dir, file_path)
            target_file = os.path.join(target_dir, file_path)

            if not os.path.exists(source_file):
                print(f"    ❌ Source file {source_file} does not exist")
                continue

            try:
                # Create target directory if it doesn't exist
                os.makedirs(os.path.dirname(target_file), exist_ok=True)

                # Copy the file
                shutil.copy2(source_file, target_file)
                print(f"    ✅ {file_path} -> {target_dir}")
                success_count += 1

            except (IOError, OSError) as e:
                print(f"    ❌ Error copying {file_path} to {target_dir}: {e}")

    print(f"📋 File copying complete! {success_count} files copied successfully")
    return success_count > 0

def add_files_to_git(files, directories):
    """Add specified files to git in the given directories"""
    print(f"🔧 Adding {len(files)} file(s) to git in {len(directories)} directories...")

    success_count = 0
    for directory in directories:
        if not os.path.exists(directory):
            print(f"⚠️  Directory {directory} does not exist, skipping")
            continue

        print(f"  📂 Adding files to git in {directory}...")

        try:
            # Change to the target directory
            original_dir = os.getcwd()
            os.chdir(directory)

            # Add files to git
            for file_path in files:
                if os.path.exists(file_path):
                    result = run_command(f"git add {file_path}", check=False)
                    if result is not None:
                        print(f"    ✅ Added {file_path} to git")
                        success_count += 1
                    else:
                        print(f"    ❌ Failed to add {file_path} to git")
                else:
                    print(f"    ⚠️  File {file_path} does not exist in {directory}")

            # Go back to original directory
            os.chdir(original_dir)

        except (subprocess.CalledProcessError, OSError) as e:
            print(f"    ❌ Error in {directory}: {e}")

    print(f"🔧 Git add complete! {success_count} files added to git successfully")
    return success_count > 0

def deploy_files_to_all_directories(files):
    """Deploy files from LinuxReport2 to all other directories and add to git"""
    print(f"🚀 Deploying {len(files)} file(s) to all directories...")

    # Get all target directories except LinuxReport2
    linux_report_dir = None
    target_dirs = []

    for dir_name in URLS.keys():
        if "LinuxReport2" in dir_name:
            linux_report_dir = dir_name
        else:
            target_dirs.append(dir_name)

    if not linux_report_dir:
        print("❌ Could not find LinuxReport2 directory in URLS")
        return False

    # Step 1: Copy files to all directories
    copy_success = copy_files_to_directories(files, target_dirs)

    # Step 2: Add files to git in all directories (including source)
    all_dirs = [linux_report_dir] + target_dirs
    git_success = add_files_to_git(files, all_dirs)

    return copy_success and git_success

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
    parser.add_argument('--files', nargs='+',
                       help='Deploy specific files from LinuxReport2 to all other directories and add to git')
    
    args = parser.parse_args()
    
    # =============================================================================
    # MAIN EXECUTION
    # =============================================================================
    
    if args.files:
        # Deploy specific files only (no warmup)
        deploy_files_to_all_directories(args.files)
        print("🚀 File deployment complete!")

    elif args.warmup_only:
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