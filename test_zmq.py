import importlib.util

zmq_spec = importlib.util.find_spec('zmq')
print(f'ZMQ library is: {"installed" if zmq_spec is not None else "not installed"}')

if zmq_spec is not None:
    try:
        import zmq
        print(f"Successfully imported ZMQ")
        print(f"ZMQ version: {zmq.__version__}")
        
        # Test ZMQ_ENABLED access
        try:
            print(f"ZMQ_ENABLED from zmq_feed_sync: {zmq.ZMQ_ENABLED}")
        except AttributeError:
            print("ZMQ_ENABLED not found as direct attribute on zmq module")
            
            try:
                # Try importing from zmq_feed_sync
                from zmq_feed_sync import ZMQ_ENABLED
                print(f"ZMQ_ENABLED from import: {ZMQ_ENABLED}")
            except ImportError:
                print("Could not import ZMQ_ENABLED from zmq_feed_sync")
            except Exception as e:
                print(f"Other error accessing ZMQ_ENABLED: {e}")
    except ImportError as e:
        print(f"Error importing ZMQ: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}") 