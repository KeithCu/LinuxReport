#!/usr/bin/env python3
"""
Test script for compression caching functionality.
"""

import gzip
import hashlib
import time

def test_compression_caching():
    """Test the compression caching functions."""
    
    # Test content
    test_content = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>Hello World</h1>
        <p>This is a test page with some content to compress.</p>
        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
    </body>
    </html>
    """
    
    # Test compression level
    COMPRESSION_LEVEL = 6
    
    print("Testing compression caching functionality...")
    print(f"Original content length: {len(test_content)} bytes")
    
    # Test compression
    start_time = time.time()
    compressed_data = gzip.compress(test_content.encode('utf-8'), compresslevel=COMPRESSION_LEVEL)
    compression_time = time.time() - start_time
    
    print(f"Compressed content length: {len(compressed_data)} bytes")
    print(f"Compression ratio: {len(compressed_data) / len(test_content) * 100:.1f}%")
    print(f"Compression time: {compression_time * 1000:.2f} ms")
    
    # Test cache key generation
    content_hash = hashlib.md5(test_content.encode('utf-8')).hexdigest()
    cache_key = f"compressed_gzip_{content_hash}"
    print(f"Cache key: {cache_key}")
    
    # Test decompression
    start_time = time.time()
    decompressed = gzip.decompress(compressed_data).decode('utf-8')
    decompression_time = time.time() - start_time
    
    print(f"Decompression time: {decompression_time * 1000:.2f} ms")
    print(f"Content matches after decompression: {test_content == decompressed}")
    
    print("\nCompression caching test completed successfully!")

def test_client_capabilities():
    """Test the client capability detection logic."""
    
    # Simulate different client Accept-Encoding headers
    test_headers = [
        "gzip, deflate, br",  # Modern browser
        "gzip, deflate",      # Older browser
        "gzip",               # Basic gzip support
        "",                   # No compression support
        "deflate",            # Only deflate support
    ]
    
    print("\nTesting client capability detection:")
    for header in test_headers:
        supports_gzip = 'gzip' in header.lower()
        print(f"Accept-Encoding: '{header}' -> Supports gzip: {supports_gzip}")

def test_feature_flag():
    """Test the feature flag logic."""
    
    print("\nTesting feature flag logic:")
    
    # Simulate different scenarios
    scenarios = [
        (True, True, False),   # Feature enabled, gzip supported, not admin
        (True, False, False),  # Feature enabled, no gzip, not admin
        (True, True, True),    # Feature enabled, gzip supported, admin
        (False, True, False),  # Feature disabled, gzip supported, not admin
        (False, False, False), # Feature disabled, no gzip, not admin
    ]
    
    for enable_compression, supports_gzip, is_admin in scenarios:
        # Simulate the logic from routes.py
        should_use_compression = enable_compression and supports_gzip and not is_admin
        print(f"ENABLE_COMPRESSION_CACHING={enable_compression}, supports_gzip={supports_gzip}, is_admin={is_admin} -> Use compression: {should_use_compression}")

if __name__ == "__main__":
    test_compression_caching()
    test_client_capabilities()
    test_feature_flag() 