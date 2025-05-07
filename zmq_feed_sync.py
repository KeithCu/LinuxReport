"""
zmq_feed_sync.py

ZeroMQ-based publisher/subscriber for feed updates. Used to synchronize feed updates across multiple servers.
"""
import threading
import time
import json
import os
from urllib.parse import urlparse

# Check if ZeroMQ is available
ZMQ_AVAILABLE = False
try:
    import zmq
    ZMQ_AVAILABLE = True
except ImportError:
    # Create a placeholder zmq module with NOBLOCK constant to avoid attribute errors
    class PlaceholderZMQ:
        NOBLOCK = 0
        PUB = 0
        SUB = 0
        LINGER = 0
        SNDHWM = 0
        RCVHWM = 0
        SUBSCRIBE = 0
    
    zmq = PlaceholderZMQ()
    print("Warning: pyzmq is not installed. ZeroMQ feed synchronization will be disabled.")

# ZeroMQ configuration
ZMQ_ENABLED = False  # Global switch to enable/disable ZMQ functionality
ZMQ_FEED_PORT = 5556  # Default port for feed sync
ZMQ_FEED_ADDR = "tcp://*:5556"  # Publisher binds here
ZMQ_TOPIC = b"feed_update"

# List of servers to connect to (used by subscriber)
# Format: ["tcp://server1:5556", "tcp://server2:5556"]
# Note: Do not include the current server, as it will receive its own messages
ZMQ_SERVERS = []

_context = None
_publisher = None
_subscriber = None
_listener_thread = None

def init_zmq():
    """Initialize ZMQ context if enabled"""
    global _context
    if not ZMQ_AVAILABLE:
        return False
        
    if ZMQ_ENABLED and _context is None:
        _context = zmq.Context.instance()
        return True
    return False

# --- Publisher ---
def get_publisher():
    """Get or create ZMQ publisher socket"""
    global _publisher
    if not ZMQ_AVAILABLE or not ZMQ_ENABLED or _context is None:
        return None
        
    if _publisher is None:
        try:
            _publisher = _context.socket(zmq.PUB)
            _publisher.setsockopt(zmq.LINGER, 0)  # Don't wait for messages to be sent
            _publisher.setsockopt(zmq.SNDHWM, 1000)  # High water mark to prevent memory bloat
            _publisher.bind(ZMQ_FEED_ADDR)
            print(f"ZMQ publisher bound to {ZMQ_FEED_ADDR}")
        except Exception as e:
            print(f"Error creating ZMQ publisher: {e}")
            return None
    return _publisher

def publish_feed_update(url, feed_data=None):
    """Publish feed update notification to other servers
    
    Args:
        url: The feed URL that was updated
        feed_data: Optional additional data about the update (timestamp, etc.)
                  Set to None to just send notification without data
    """
    if not ZMQ_AVAILABLE or not ZMQ_ENABLED:
        return
        
    pub = get_publisher()
    if pub is None:
        return
        
    data = {
        "url": url,
        "feed_data": feed_data,
        "server_id": os.getenv("SERVER_ID", "unknown"),
        "timestamp": time.time()
    }
    
    try:
        msg = json.dumps(data)
        pub.send_multipart([ZMQ_TOPIC, msg.encode("utf-8")], zmq.NOBLOCK)
    except Exception as e:
        print(f"ZMQ publishing error for {url}: {e}")

# --- Subscriber ---
_feed_update_callbacks = []

def register_feed_update_callback(cb):
    """Register a callback function to be called when feed updates are received
    
    Args:
        cb: Callback function that takes (url, feed_data) parameters
    """
    if cb not in _feed_update_callbacks:
        _feed_update_callbacks.append(cb)

def get_subscriber():
    """Get or create ZMQ subscriber socket"""
    global _subscriber
    if not ZMQ_AVAILABLE or not ZMQ_ENABLED or _context is None:
        return None
        
    if _subscriber is None:
        try:
            _subscriber = _context.socket(zmq.SUB)
            _subscriber.setsockopt(zmq.LINGER, 0)
            _subscriber.setsockopt(zmq.RCVHWM, 1000)
            _subscriber.setsockopt(zmq.SUBSCRIBE, ZMQ_TOPIC)
            
            # Connect to all configured server addresses
            if ZMQ_SERVERS:
                for server in ZMQ_SERVERS:
                    current_host = urlparse(ZMQ_FEED_ADDR).netloc.split(':')[0]
                    server_host = urlparse(server).netloc.split(':')[0]
                    
                    # Don't connect to self (avoid duplicate messages)
                    if server_host != current_host and server_host != "*":
                        _subscriber.connect(server)
                        print(f"ZMQ subscriber connected to {server}")
            else:
                # Default to localhost if no servers specified
                _subscriber.connect("tcp://localhost:5556")
                print("ZMQ subscriber connected to localhost")
                
        except Exception as e:
            print(f"Error creating ZMQ subscriber: {e}")
            return None
    return _subscriber

def feed_update_listener():
    """Background thread function to listen for feed updates"""
    if not ZMQ_AVAILABLE or not ZMQ_ENABLED:
        return
        
    sub = get_subscriber()
    if sub is None:
        return
        
    print("ZMQ feed update listener thread started")
    while ZMQ_ENABLED:
        try:
            # Set a timeout for receiving so we can check if ZMQ_ENABLED changed
            if hasattr(sub, "poll") and sub.poll(1000):  # Poll with 1 second timeout
                topic, msg = sub.recv_multipart()
                data = json.loads(msg.decode("utf-8"))
                
                # Skip messages from self
                if data.get("server_id") == os.getenv("SERVER_ID", "unknown"):
                    continue
                    
                print(f"ZMQ: Received feed update for {data['url']} from {data.get('server_id', 'unknown')}")
                for cb in _feed_update_callbacks:
                    try:
                        cb(data["url"], data.get("feed_data"))
                    except Exception as e:
                        print(f"Error in feed update callback: {e}")
        except zmq.error.Again:
            # Timeout on receive, just continue
            pass
        except Exception as e:
            print(f"ZeroMQ feed update listener error: {e}")
            time.sleep(1)

def start_feed_update_listener():
    """Start the background thread for listening to feed updates"""
    global _listener_thread
    if not ZMQ_AVAILABLE or not ZMQ_ENABLED:
        return False
        
    if _listener_thread is not None and _listener_thread.is_alive():
        return True  # Already running
        
    if init_zmq():
        _listener_thread = threading.Thread(target=feed_update_listener, daemon=True)
        _listener_thread.start()
        return True
    return False

def configure_zmq(enabled=False, servers=None, port=None):
    """Configure ZMQ settings
    
    Args:
        enabled: Whether to enable ZMQ functionality
        servers: List of server addresses to connect to
        port: Port to use for ZMQ communication
    """
    global ZMQ_ENABLED, ZMQ_SERVERS, ZMQ_FEED_PORT, ZMQ_FEED_ADDR
    
    # If ZMQ is not available, always force disabled
    if not ZMQ_AVAILABLE:
        ZMQ_ENABLED = False
        if enabled:
            print("Warning: ZeroMQ is not available (pyzmq not installed). Feed synchronization remains disabled.")
        return False
    
    ZMQ_ENABLED = enabled
    
    if servers is not None:
        ZMQ_SERVERS = servers
        
    if port is not None:
        ZMQ_FEED_PORT = port
        ZMQ_FEED_ADDR = f"tcp://*:{port}"
    
    if ZMQ_ENABLED:
        if init_zmq():
            return start_feed_update_listener()
    return False
