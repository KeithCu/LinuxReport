#!/usr/bin/env python3
import subprocess
import re
import sys
import os
import platform
import argparse
from pathlib import Path
from typing import List, Set

# Cache duration configuration (in seconds)
# 1 week = 604800, 2 weeks = 1209600, 4 weeks = 2419200, 1 year = 31536000
CACHE_DURATION = 1209600  # 2 weeks

def detect_environment():
    """Detect and display the current environment information."""
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {platform.python_version()}")
    
    # Check for MSYS2
    msystem = os.environ.get('MSYSTEM')
    if msystem:
        print(f"MSYS2 Environment: {msystem}")
    else:
        print("Standard environment")
    
    # Check for s3cmd using the same shell logic as run_command
    try:
        # Detect MSYS2 environment
        is_msys2 = os.environ.get('MSYSTEM') is not None
        
        # For MSYS2, try a simpler approach
        if is_msys2:
            print("Testing s3cmd in MSYS2 environment...")
            
            # Try to find the MSYS2 bash executable
            msys2_root = os.environ.get('MSYS2_ROOT', 'C:/tools/msys64')
            bash_path = Path(msys2_root) / 'usr' / 'bin' / 'bash.exe'
            
            if os.path.exists(bash_path):
                print(f"Using MSYS2 bash: {bash_path}")
                # Use bash with -c to run the command
                result = subprocess.run([bash_path, '-c', 's3cmd --version'], 
                                      capture_output=True, text=True, shell=False)
            else:
                # Fallback to shell=True
                print("MSYS2 bash not found, trying shell=True...")
                result = subprocess.run('s3cmd --version', 
                                      capture_output=True, text=True, shell=True)
        else:
            # Use shell=True for Unix/Linux, shell=False for Windows
            use_shell = os.name != 'nt'
            print(f"Testing s3cmd with shell={use_shell}")
            result = subprocess.run(['s3cmd', '--version'], 
                                  capture_output=True, text=True, shell=use_shell)
            
        print(f"s3cmd return code: {result.returncode}")
        if result.stdout:
            print(f"s3cmd stdout: {result.stdout.strip()}")
        if result.stderr:
            print(f"s3cmd stderr: {result.stderr.strip()}")
            
        if result.returncode == 0:
            print(f"s3cmd available: {result.stdout.strip()}")
            return True
        else:
            print("s3cmd not found or not working properly")
            return False
    except FileNotFoundError:
        print("s3cmd not found in PATH")
        return False

def run_command(command: str) -> str:
    """Run a shell command and return its output."""
    try:
        # Detect MSYS2 environment
        is_msys2 = os.environ.get('MSYSTEM') is not None
        
        # For MSYS2, use bash directly
        if is_msys2:
            # Try to find the MSYS2 bash executable
            msys2_root = os.environ.get('MSYS2_ROOT', 'C:/tools/msys64')
            bash_path = Path(msys2_root) / 'usr' / 'bin' / 'bash.exe'

            if bash_path.exists():
                # Use bash with -c to run the command
                result = subprocess.run([bash_path, '-c', command], 
                                      check=True, capture_output=True, text=True)
            else:
                # Fallback to shell=True
                result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        else:
            # Use shell=True for Unix/Linux, shell=False for Windows
            use_shell = os.name != 'nt'
            result = subprocess.run(command, shell=use_shell, check=True, capture_output=True, text=True)
        
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        print(f"Error output: {e.stderr}")
        print(f"Return code: {e.returncode}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Command not found: {command}")
        print("Please ensure s3cmd is installed and available in your PATH")
        print("For MSYS2: pacman -S s3cmd")
        print("For other systems: pip install s3cmd")
        sys.exit(1)

def extract_changed_files(sync_output: str) -> Set[str]:
    """Extract filenames of changed files from s3cmd sync output."""
    changed_files = set()
    # Pattern to match file paths in s3cmd sync output
    pattern = r's3://linuxreportstatic/([^\s\'"]+)'
    
    for line in sync_output.split('\n'):
        if '->' in line:  # Only process lines that indicate file transfers
            matches = re.findall(pattern, line)
            if matches:
                # Clean up any trailing quotes or extra characters
                for match in matches:
                    clean_match = match.rstrip("'\"")
                    if clean_match:
                        changed_files.add(clean_match)
    
    return changed_files

def list_s3_files() -> List[str]:
    """List all files in the S3 bucket."""
    command = "s3cmd ls s3://linuxreportstatic/ --recursive"
    output = run_command(command)
    
    files = []
    for line in output.split('\n'):
        if line.strip():
            # Extract filename from s3cmd ls output
            parts = line.split()
            if len(parts) >= 4:
                # Remove the bucket prefix to get just the filename
                file_path = parts[3].replace('s3://linuxreportstatic/', '')
                # Clean up any trailing quotes or extra characters
                file_path = file_path.rstrip("'\"")
                if file_path:  # Skip empty paths
                    files.append(file_path)
    
    return files

def set_file_permissions(files: Set[str]):
    """Set ACL and cache headers for each file."""
    for file_path in files:
        # Set ACL to public
        acl_command = f's3cmd setacl s3://linuxreportstatic/{file_path} --acl-public'
        run_command(acl_command)
        
        # Set cache control header with configurable duration
        cache_command = f's3cmd modify --add-header="Cache-Control: max-age={CACHE_DURATION}" s3://linuxreportstatic/{file_path}'
        run_command(cache_command)
        
        print(f"Processed: {file_path}")

def set_all_file_permissions():
    """Set ACL and cache headers for all files using recursive s3cmd commands."""
    print("Setting ACL to public for all files...")
    acl_command = f's3cmd setacl s3://linuxreportstatic/ --acl-public --recursive'
    run_command(acl_command)
    
    print(f"Setting cache headers (max-age={CACHE_DURATION}) for all files...")
    cache_command = f's3cmd modify --add-header="Cache-Control: max-age={CACHE_DURATION}" --recursive s3://linuxreportstatic/'
    run_command(cache_command)
    
    print("All files processed with recursive commands.")

def main():
    global CACHE_DURATION
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Sync static files to S3 and set cache headers')
    parser.add_argument('--all-files', action='store_true', 
                       help='Update cache duration on all files in S3, not just changed ones')
    parser.add_argument('--cache-duration', type=int, default=CACHE_DURATION,
                       help=f'Cache duration in seconds (default: {CACHE_DURATION})')
    args = parser.parse_args()
    
    # Update cache duration if specified
    if args.cache_duration != CACHE_DURATION:
        CACHE_DURATION = args.cache_duration
        print(f"Using custom cache duration: {CACHE_DURATION} seconds ({CACHE_DURATION // 86400} days)")
    
    print("=== Environment Detection ===")
    if not detect_environment():
        print("\nError: s3cmd is required but not available.")
        print("Please install s3cmd and ensure it's in your PATH.")
        print("For MSYS2: pacman -S s3cmd")
        print("For other systems: pip install s3cmd")
        sys.exit(1)
    
    print("\n=== Running S3 Sync ===")
    # Use pathlib for cross-platform path handling
    static_path = Path('static') / 'images'
    sync_command = f's3cmd sync {static_path} s3://linuxreportstatic/ --delete-removed'
    sync_output = run_command(sync_command)
    
    # Extract changed files
    changed_files = extract_changed_files(sync_output)
    
    if args.all_files:
        # Update cache duration on all files using recursive commands
        print("\n=== Updating Cache Duration on All Files ===")
        print("Using recursive s3cmd commands for faster processing...")
        set_all_file_permissions()
    else:
        # Only update changed files (default behavior)
        if not changed_files:
            print("No files were changed.")
            return
        
        print(f"\nFound {len(changed_files)} changed files:")
        for file in changed_files:
            print(f"- {file}")
        
        print("\nSetting permissions and cache headers on changed files...")
        set_file_permissions(changed_files)
    
    print("\nSync and file processing completed successfully!")

if __name__ == "__main__":
    main() 