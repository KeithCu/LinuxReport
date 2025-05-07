"""
Handle ZeroMQ message callbacks for various message types
"""
import os
import json
import datetime
import importlib.util
from html_generation import refresh_images_only
from shared import g_c, TZ, MODE, MODE_MAP, PATH, ABOVE_HTML_FILE

def handle_zmq_feed_update(url, feed_content=None, feed_data=None):
    """Handle feed update notifications from ZMQ
    
    Args:
        url: The feed URL or special identifier (e.g., "headlines_update")
        feed_content: The actual feed content that was fetched (complete feed data)
        feed_data: Additional metadata about the update
    """
    # Skip if we don't have any data to process
    if not feed_content and not feed_data:
        return
    
    action = feed_data.get("action") if feed_data else None
    
    # Special handling for headline updates from auto_update.py
    if url == "headlines_update" and action == "auto_update_headlines":
        # Get mode from feed_data
        mode = feed_data.get("mode")
        if not mode:
            return
            
        current_mode = MODE_MAP.get(MODE)
        if mode != current_mode:
            # This headline update is for a different mode/site, ignore it
            return
            
        # Get the HTML file name
        file = feed_data.get("file")
        if not file:
            return
            
        # Process received HTML file content
        if feed_content and isinstance(feed_content, str) and feed_data.get("content_type") == "html":
            try:
                print(f"Received HTML file for {mode}, writing directly to {file}")
                
                # Write the received content directly to the file
                with open(file, "w", encoding="utf-8") as f:
                    f.write(feed_content)
                print(f"Updated HTML file {file} with received content")
                
                # Clear the file cache for the headlines file
                try:
                    from shared import _file_cache
                    above_html_path = os.path.join(PATH, ABOVE_HTML_FILE)
                    if above_html_path in _file_cache:
                        del _file_cache[above_html_path]
                        print(f"Cleared file cache for {above_html_path}")
                except (ImportError, AttributeError) as e:
                    print(f"Warning: Could not clear file cache: {e}")
                
                # Invalidate template caches for faster refresh
                try:
                    from routes import clear_page_caches
                    clear_page_caches()
                    print("Cleared page caches")
                except ImportError:
                    # If routes isn't available, continue without clearing caches
                    print("Warning: Could not clear page caches - routes module not available")
                
                # Log update to file
                with open(f"{mode}_zmq_updates.log", "a") as log:
                    timestamp = datetime.datetime.now(TZ).isoformat()
                    log.write(f"{timestamp}: Received and saved HTML file for {mode}\n")
                
            except Exception as e:
                print(f"Error processing HTML content: {e}")
                # Fall back to refreshing images only as a last resort
                try:
                    refresh_images_only(mode)
                    print(f"Fallback: Refreshed images for {mode}")
                except Exception as img_err:
                    print(f"Error in fallback image refresh: {img_err}")
        else:
            print(f"Received headline update without HTML content for {mode}, cannot process")
    
    # Handle regular feed updates with their content
    elif feed_content and url and url.startswith(("http:", "https:")):
        try:
            # Process feed content directly without refetching
            print(f"Processing feed content for {url}")
            
            # Implementation will depend on your feed processing system
            # Example placeholder for feed processor implementation:
            # feed_processor.update_from_content(url, feed_content)
            
        except Exception as e:
            print(f"Error processing feed content for {url}: {e}")

# Register the handler function when this module is imported
try:
    # Check if ZeroMQ is available
    zmq_spec = importlib.util.find_spec("zmq")
    if zmq_spec is not None:
        # Only import if ZeroMQ is installed
        from zmq_feed_sync import register_feed_update_callback, ZMQ_ENABLED
        if ZMQ_ENABLED:
            register_feed_update_callback(handle_zmq_feed_update)
            print("Registered ZMQ handler for feed updates")
        else:
            print("ZMQ is installed but disabled, skipping handler registration")
    else:
        print("ZeroMQ library not installed, skipping handler registration")
except Exception as e:
    print(f"Error registering ZMQ handler (continuing without ZMQ support): {e}") 