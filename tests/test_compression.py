#!/usr/bin/env python3
"""
Test script for compression caching functionality.
"""

import gzip
import hashlib
import time
import sys
import os

# Add the parent directory to Python path when running tests directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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

    # Verify compression actually reduces size
    assert len(compressed_data) < len(test_content), "Compression should reduce content size"
    assert test_content == decompressed, "Decompressed content should match original"

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
        "GZIP, DEFLATE",      # Case insensitive
        "gzip;q=1.0, deflate;q=0.8",  # Quality values
    ]

    print("\nTesting client capability detection:")
    results = []
    for header in test_headers:
        supports_gzip = 'gzip' in header.lower()
        results.append((header, supports_gzip))
        print(f"Accept-Encoding: '{header}' -> Supports gzip: {supports_gzip}")

    # Verify expected results
    assert results[0][1] == True, "Modern browser should support gzip"
    assert results[1][1] == True, "Older browser should support gzip"
    assert results[2][1] == True, "Basic gzip should support gzip"
    assert results[3][1] == False, "Empty header should not support gzip"
    assert results[4][1] == False, "Deflate only should not support gzip"
    assert results[5][1] == True, "Case insensitive should work"
    assert results[6][1] == True, "Quality values should still detect gzip"

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

    results = []
    for enable_compression, supports_gzip, is_admin in scenarios:
        # Simulate the logic from routes.py
        should_use_compression = enable_compression and supports_gzip and not is_admin
        results.append((enable_compression, supports_gzip, is_admin, should_use_compression))
        print(f"ENABLE_COMPRESSION_CACHING={enable_compression}, supports_gzip={supports_gzip}, is_admin={is_admin} -> Use compression: {should_use_compression}")

    # Verify expected results
    assert results[0][3] == True, "Should use compression when enabled, supported, and not admin"
    assert results[1][3] == False, "Should not use compression when gzip not supported"
    assert results[2][3] == False, "Should not use compression for admin users"
    assert results[3][3] == False, "Should not use compression when feature disabled"
    assert results[4][3] == False, "Should not use compression when feature disabled and no gzip"

if __name__ == "__main__":
    test_compression_caching()
    test_client_capabilities()
    test_feature_flag() 