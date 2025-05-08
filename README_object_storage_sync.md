# Object Storage Feed Synchronization

This package provides an alternative to the ZeroMQ-based feed synchronization system, using object storage (like Linode Object Storage or AWS S3) instead of a message queue to distribute feed updates across multiple servers.

## Overview

When running a feed aggregator across multiple servers, each server needs to know when another server has updated a feed to avoid duplicate work. The traditional approach uses ZeroMQ for real-time messaging between servers, but this requires direct network connections between all servers.

This object storage-based alternative provides a few advantages:

1. **No direct connections needed**: Servers only need to connect to the object storage service, not to each other
2. **Persistence**: Updates are stored and can be retrieved even if a server was offline when the update happened
3. **Simplicity**: No need to maintain ZeroMQ infrastructure, just use standard S3-compatible storage
4. **Scalability**: Works the same with 2 or 100 servers

## How It Works

### Basic Architecture

1. When a server fetches or updates a feed, it creates a JSON object in the object storage bucket
2. Each server periodically checks the bucket for new updates from other servers
3. When an update is found, the server downloads it and processes it using registered callbacks

### Key Components

- **Publisher**: Uploads feed updates to object storage with metadata
- **Watcher**: Periodically checks object storage for new updates
- **Callbacks**: Process the updates when they're received
- **File Watcher** (optional): Monitors local files for changes to automatically trigger updates

## Requirements

- Python 3.6+
- `apache-libcloud` for object storage access
- `watchdog` (optional) for file change monitoring
- Access to an S3-compatible object storage service (Linode, AWS, etc.)

## Installation

```bash
pip install apache-libcloud watchdog
```

## Usage

### Basic Configuration

```python
import object_storage_sync as storage_sync

# Configure the connection to your object storage
storage_sync.configure_storage(
    enabled=True,
    region='us-east-1',  # Your region
    bucket_name='feed-sync',
    access_key='YOUR_ACCESS_KEY',
    secret_key='YOUR_SECRET_KEY',
    host='us-east-1.linodeobjects.com',  # Adjust for your provider
    check_interval=30  # Check for updates every 30 seconds
)

# Register a callback function to handle feed updates
def my_feed_callback(url, feed_content, feed_data):
    print(f"Received update for feed: {url}")
    # Process the feed content and metadata
    
storage_sync.register_feed_update_callback(my_feed_callback)

# Start the watcher thread
storage_sync.start_storage_watcher()
```

### Publishing Feed Updates

When your application updates a feed, publish the update:

```python
# After fetching/updating a feed
feed_url = "https://example.com/feed.xml"
feed_content = {...}  # The parsed feed content
feed_metadata = {"last_updated": time.time(), "status": "success"}

storage_sync.publish_feed_update(feed_url, feed_content, feed_metadata)
```

### File-based Updates (Optional)

You can also set up a file watcher to automatically publish updates when files are modified:

```python
# Watch a directory for .feed files
storage_sync.start_file_watcher("/path/to/feed/files")

# When a file like "https___example.com_feed.xml.feed" is modified,
# it will automatically trigger a publish
```

### Cleaning Up Old Updates

To prevent the storage bucket from growing indefinitely:

```python
# Clean up updates older than 24 hours
storage_sync.cleanup_old_updates(max_age_hours=24)
```

## Comparison to ZeroMQ Approach

| Feature | Object Storage Sync | ZeroMQ Sync |
|---------|-------------------|------------|
| Real-time updates | Near real-time (polling) | True real-time |
| Persistence | Yes (updates stored) | No (messages lost if server down) |
| Direct connections | No (only to storage) | Yes (servers must be reachable) |
| Network requirements | Standard HTTPS | Special ports open |
| Cost | Storage costs | No additional costs |
| Complexity | Simple | More complex setup |

## Complete Example

See `example_storage_sync.py` for a complete example of how to use this package.

## Known Limitations

1. Updates are not truly real-time - there's a delay based on the polling interval
2. Some storage costs will be incurred (though typically minimal)
3. No built-in encryption for feed content (consider this for sensitive feeds)

## Future Improvements

- Add support for notification systems (webhooks, SQS, etc.) to eliminate polling
- Implement client-side encryption for sensitive feeds
- Add compression for large feed contents
- Add support for more authentication methods 