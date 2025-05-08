"""
example_storage_sync.py

Example showing how to use the object_storage_sync module to synchronize feed updates
across multiple servers using object storage instead of ZeroMQ.
"""
import time
import json
import sys
import os

# Import our storage sync module
import object_storage_sync as storage_sync

def feed_update_callback(url, feed_content, feed_data):
    """Callback function that gets called when a feed update is received"""
    print(f"\n--- Feed Update Received ---")
    print(f"URL: {url}")
    print(f"Content length: {len(feed_content) if feed_content else 0}")
    print(f"Feed data: {feed_data}")
    print(f"----------------------------\n")
    
    # In a real implementation, you would process the feed:
    # 1. Update your database
    # 2. Update any cache
    # 3. Possibly notify users, etc.

def main():
    # Register our callback function
    storage_sync.register_feed_update_callback(feed_update_callback)
    
    # Configure the storage sync module (with Linode Object Storage info)
    # In a real app, you'd get these from configuration or environment variables
    storage_sync.configure_storage(
        enabled=True,
        region='us-east-1',  # Adjust to your region
        bucket_name='feed-sync-example',
        access_key='YOUR_ACCESS_KEY',  # Replace with your access key
        secret_key='YOUR_SECRET_KEY',  # Replace with your secret key
        host='us-east-1.linodeobjects.com',  # Adjust for your region
        check_interval=30  # Check for updates every 30 seconds
    )
    
    # Optional: Start a file watcher to automatically publish updates when files change
    # Create a directory to watch
    watch_dir = os.path.join(os.getcwd(), 'feed_files')
    if not os.path.exists(watch_dir):
        os.makedirs(watch_dir)
        print(f"Created directory to watch: {watch_dir}")
    
    # Start the file watcher
    storage_sync.start_file_watcher(watch_dir)
    print(f"Watching directory {watch_dir} for .feed files")
    print("To test, create files like 'https___example.com_feed.xml.feed' in this directory")

    # Main interaction loop
    try:
        print("\nObject Storage Feed Sync Example")
        print("--------------------------------")
        print("1. Publish a feed update")
        print("2. Check for feed updates manually")
        print("3. Clean up old updates")
        print("q. Quit")
        
        while True:
            choice = input("\nEnter choice (1-3, or q to quit): ").strip().lower()
            
            if choice == 'q':
                break
                
            elif choice == '1':
                url = input("Enter feed URL: ").strip()
                
                # In a real app, you would fetch the feed content here
                # For this example, we'll just create some dummy content
                feed_content = {
                    "title": "Example Feed",
                    "entries": [
                        {"title": "Entry 1", "link": "https://example.com/1", "published": time.time()},
                        {"title": "Entry 2", "link": "https://example.com/2", "published": time.time()}
                    ]
                }
                
                feed_data = {
                    "last_updated": time.time(),
                    "status": "success"
                }
                
                # Publish the update
                obj = storage_sync.publish_feed_update(url, json.dumps(feed_content), feed_data)
                if obj:
                    print(f"Published update for {url}")
                    print(f"Object name: {obj.name}")
                else:
                    print(f"Failed to publish update for {url}")
                
            elif choice == '2':
                print("Checking for updates...")
                storage_sync.check_for_updates()
                print("Done checking.")
                
            elif choice == '3':
                max_age_hours = float(input("Enter maximum age in hours (default=24): ") or "24")
                print(f"Cleaning up updates older than {max_age_hours} hours...")
                storage_sync.cleanup_old_updates(max_age_hours=max_age_hours)
                print("Cleanup complete.")
                
            else:
                print("Invalid choice. Please try again.")
                
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        # Clean up
        storage_sync.stop_file_watcher()
        storage_sync.stop_storage_watcher()
        print("Stopped watchers. Goodbye!")

if __name__ == "__main__":
    main() 