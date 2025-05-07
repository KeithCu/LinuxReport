"""
Handle ZeroMQ message callbacks for various message types
"""
import os
import json
import datetime
import importlib.util
from html_generation import refresh_images_only
from shared import g_c, TZ, MODE, MODE_MAP, PATH, ABOVE_HTML_FILE

def handle_zmq_feed_update(url, feed_data):
    """Handle feed update notifications from ZMQ
    
    Args:
        url: The feed URL or special identifier (e.g., "headlines_update")
        feed_data: Additional data about the update
    """
    # Skip if we don't have data or action
    if not feed_data:
        return
    
    action = feed_data.get("action")
    
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
            
        # Check if we have this file locally
        if not os.path.exists(file):
            return
            
        # Refresh local images for headlines
        try:
            print(f"Received headline update from remote server for {mode}, refreshing images")
            # Just refresh images since the headlines themselves would've been updated
            # in a separate server step
            refresh_images_only(mode)
            
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
            
            # Log the update
            try:
                with open(f"{mode}_zmq_updates.log", "a") as log:
                    timestamp = datetime.datetime.now(TZ).isoformat()
                    log.write(f"{timestamp}: Received headline update from remote server\n")
                    titles = feed_data.get("titles", [])
                    for title in titles:
                        log.write(f"  - {title}\n")
            except Exception as e:
                print(f"Error writing to ZMQ update log: {e}")
        except Exception as e:
            print(f"Error handling headline update: {e}")
    
    # Handle other feed update types as needed
    # ...

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