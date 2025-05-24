import os
import os.path
import hashlib

from app import load_config

# Object Storage configuration
STORAGE_ENABLED = False
STORAGE_PROVIDER = "linode"  # options: "s3", "linode", "local"
STORAGE_REGION = "us-ord-1"
STORAGE_BUCKET_NAME = "linuxreportupdates"
STORAGE_ACCESS_KEY = ""  # Loaded from config.yaml
STORAGE_SECRET_KEY = ""  # Loaded from config.yaml
STORAGE_HOST = "us-ord-1.linodeobjects.com"
STORAGE_SYNC_PATH = "feeds/"


# Common constants for all object storage modules
DEFAULT_RETRY_INTERVAL = 1.0  # Base interval for lock acquisition retries
MIN_RETRY_INTERVAL = 1.0      # Minimum retry interval in seconds
MAX_RETRY_INTERVAL = 10.0     # Maximum retry interval in seconds
MAX_RETRY_ATTEMPTS = 3        # Maximum number of retry attempts for S3 operations
RETRY_MULTIPLIER = 1.0        # Multiplier for exponential backoff


# Sync configuration
SERVER_ID = hashlib.md5(os.uname().nodename.encode()).hexdigest()[:8] if hasattr(os, 'uname') else "default_server_id"


# Libcloud imports for availability check and init_storage
try:
    from libcloud.storage.types import ContainerDoesNotExistError
    from libcloud.storage.providers import get_driver
    from libcloud.common.types import LibcloudError
    LIBCLOUD_AVAILABLE = True
except ImportError:
    LIBCLOUD_AVAILABLE = False
    # Forward declarations for type hints if LIBCLOUD_AVAILABLE is False
    class Provider: pass
    class ContainerDoesNotExistError(Exception): pass
    class ObjectDoesNotExistError(Exception): pass
    class Object: pass
    class LibcloudError(Exception): pass

# Custom exceptions
class StorageError(Exception):
    """Base exception for storage-related errors"""
    pass

class ConfigurationError(StorageError):
    """Raised when there are issues with configuration"""
    pass

class StorageConnectionError(StorageError):
    """Raised when there are issues connecting to storage"""
    pass

class StorageOperationError(StorageError):
    """Raised when storage operations fail"""
    pass

# Internal state
_storage_driver = None
_storage_container = None
_secrets_loaded = False

def load_storage_secrets():
    """Load storage secrets from config.yaml"""
    global STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY, _secrets_loaded
    try:
        config = load_config()
        storage_config = config.get('storage')
        
        if not storage_config:
            raise ConfigurationError("Missing 'storage' section in config.yaml")
            
        # Only load secrets
        STORAGE_ACCESS_KEY = storage_config.get('access_key', '')
        STORAGE_SECRET_KEY = storage_config.get('secret_key', '')
        _secrets_loaded = True
        
        if STORAGE_ENABLED and (not STORAGE_ACCESS_KEY or not STORAGE_SECRET_KEY):
            print("Storage is enabled but access key or secret key might be missing after loading.")
            
    except FileNotFoundError as e: # Specific exception
        _secrets_loaded = False
        print(f"Configuration file not found: {e}")
        raise ConfigurationError(f"Configuration file not found: {e}")
    except KeyError as e: # Specific exception for missing keys in config
        _secrets_loaded = False
        print(f"Missing key in configuration data: {e}")
        raise ConfigurationError(f"Missing key in configuration data: {e}")
    except Exception as e: # Fallback for other load_config or parsing issues
        _secrets_loaded = False
        print(f"Error loading storage secrets: {e}")
        raise ConfigurationError(f"Error loading storage secrets: {e}") # Wrap in custom error

def init_storage() -> bool:
    """Initialize storage driver if enabled.
    
    Returns:
        bool: True if initialization was successful
        
    Raises:
        StorageConnectionError: If there are issues connecting to storage
        ConfigurationError: If configuration is invalid
    """
    global _storage_driver, _storage_container
    
    if not LIBCLOUD_AVAILABLE:
        print("Libcloud not available. Storage functionality disabled.")
        return False
        
    if not STORAGE_ENABLED:
        print("Storage is not enabled in configuration.")
        return False
    
    if _storage_driver is None:
        try:
            # Validate configuration
            if not STORAGE_ACCESS_KEY or not STORAGE_SECRET_KEY:
                raise ConfigurationError("Storage access key and secret key must be provided")
                
            # Get driver class
            cls = get_driver(STORAGE_PROVIDER)
            
            # Initialize driver with connection pooling
            _storage_driver = cls(
                STORAGE_ACCESS_KEY, 
                STORAGE_SECRET_KEY,
                region=STORAGE_REGION,
                host=STORAGE_HOST,
                secure=True  # Always use SSL
            )
            print(f"Storage driver initialized for provider {STORAGE_PROVIDER}")
            
            # Create or get container
            try:
                _storage_container = _storage_driver.get_container(container_name=STORAGE_BUCKET_NAME)
                print(f"Using existing storage container: {STORAGE_BUCKET_NAME}")
            except ContainerDoesNotExistError:
                _storage_container = _storage_driver.create_container(container_name=STORAGE_BUCKET_NAME)
                print(f"Created new storage container: {STORAGE_BUCKET_NAME}")
                                
            return True
        except LibcloudError as e: # Catch specific libcloud errors during driver init/container ops
            _storage_driver = None
            _storage_container = None
            raise StorageConnectionError(f"Libcloud error initializing storage driver: {e}")
        except Exception as e: # General fallback for other init issues
            _storage_driver = None
            _storage_container = None
            raise StorageConnectionError(f"Error initializing storage driver: {e}")
    
    return True

def generate_object_name(key: str, prefix: str = "") -> str:
    """Generate a unique object name for storage.
    
    Args:
        key: Base identifier for the object
        prefix: Optional prefix to add to the path (e.g., 'cache/', 'lock/')
        
    Returns:
        str: Unique object name with server ID and hash
    """
    if not key:
        raise ValueError("Key cannot be empty")
        
    # Generate hash of the key
    key_hash = hashlib.md5(key.encode()).hexdigest()
    
    # Build the full path
    path_parts = [STORAGE_SYNC_PATH]
    if prefix:
        path_parts.append(prefix)
    path_parts.extend([SERVER_ID, key_hash])
    
    return "/".join(path_parts)


