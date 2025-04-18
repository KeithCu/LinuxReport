"""
zmq_feed_sync.py

ZeroMQ-based publisher/subscriber for feed updates. Used to synchronize feed updates across multiple servers.
"""
import threading
import time
import zmq
import json

# ZeroMQ configuration
ZMQ_FEED_ADDR = "tcp://*:5556"  # Publisher binds here
ZMQ_FEED_SUB_ADDR = "tcp://localhost:5556"  # Subscriber connects here (change as needed)
ZMQ_TOPIC = b"feed_update"

_context = zmq.Context.instance()
_publisher = None
_subscriber = None

# --- Publisher ---
def get_publisher():
    global _publisher
    if _publisher is None:
        _publisher = _context.socket(zmq.PUB)
        _publisher.bind(ZMQ_FEED_ADDR)
    return _publisher

def publish_feed_update(url, feed_data):
    pub = get_publisher()
    msg = json.dumps({"url": url, "feed_data": feed_data})
    pub.send_multipart([ZMQ_TOPIC, msg.encode("utf-8")])

# --- Subscriber ---
_feed_update_callbacks = []

def register_feed_update_callback(cb):
    _feed_update_callbacks.append(cb)

def get_subscriber():
    global _subscriber
    if _subscriber is None:
        _subscriber = _context.socket(zmq.SUB)
        _subscriber.connect(ZMQ_FEED_SUB_ADDR)
        _subscriber.setsockopt(zmq.SUBSCRIBE, ZMQ_TOPIC)
    return _subscriber

def feed_update_listener():
    sub = get_subscriber()
    while True:
        try:
            topic, msg = sub.recv_multipart()
            data = json.loads(msg.decode("utf-8"))
            for cb in _feed_update_callbacks:
                cb(data["url"], data["feed_data"])
        except Exception as e:
            print(f"ZeroMQ feed update listener error: {e}")
            time.sleep(1)

def start_feed_update_listener_thread():
    t = threading.Thread(target=feed_update_listener, daemon=True)
    t.start()
