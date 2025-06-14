#!/usr/bin/env python3
import subprocess
import re
import sys
import os
from typing import List, Set

def run_command(command: str) -> str:
    """Run a shell command and return its output."""
    try:
        # Use shell=False on Windows to avoid shell interpretation issues
        use_shell = os.name != 'nt'
        result = subprocess.run(command, shell=use_shell, check=True, capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        print(f"Error output: {e.stderr}")
        sys.exit(1)

def extract_changed_files(sync_output: str) -> Set[str]:
    """Extract filenames of changed files from s3cmd sync output."""
    changed_files = set()
    # Pattern to match file paths in s3cmd sync output
    pattern = r's3://linuxreportstatic/([^\s]+)'
    
    for line in sync_output.split('\n'):
        if '->' in line:  # Only process lines that indicate file transfers
            matches = re.findall(pattern, line)
            if matches:
                changed_files.update(matches)
    
    return changed_files

def set_file_permissions(files: Set[str]):
    """Set ACL and cache headers for each file."""
    for file_path in files:
        # Set ACL to public
        acl_command = f's3cmd setacl s3://linuxreportstatic/{file_path} --acl-public'
        run_command(acl_command)
        
        # Set cache control header
        cache_command = f's3cmd modify --add-header="Cache-Control: max-age=31536000" s3://linuxreportstatic/{file_path}'
        run_command(cache_command)
        
        print(f"Processed: {file_path}")

def main():
    # Run the sync command
    print("Running s3cmd sync...")
    # Use os.path.join for cross-platform path handling
    static_path = os.path.join('static', 'images')
    sync_command = f's3cmd sync {static_path} s3://linuxreportstatic/ --delete-removed'
    sync_output = run_command(sync_command)
    
    # Extract changed files
    changed_files = extract_changed_files(sync_output)
    
    if not changed_files:
        print("No files were changed.")
        return
    
    print(f"\nFound {len(changed_files)} changed files:")
    for file in changed_files:
        print(f"- {file}")
    
    # Set permissions and cache headers for changed files
    print("\nSetting permissions and cache headers...")
    set_file_permissions(changed_files)
    
    print("\nSync and file processing completed successfully!")

if __name__ == "__main__":
    main() 