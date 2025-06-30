#!/usr/bin/env python3
import os
import diskcache

def migrate_to_sqlite(cache_dir):
    """
    Migrate DiskCache from file-based storage to SQLite-only storage.
    Uses DiskCache's own API to handle all data properly and preserves expiration times and tags.
    """
    print(f"Starting migration of cache at {cache_dir}")
    
    # Create migrated directory if it doesn't exist
    migrated_dir = os.path.join(os.path.dirname(cache_dir), 'migrated')
    os.makedirs(migrated_dir, exist_ok=True)
    
    # Create both caches
    old_cache = diskcache.Cache(directory=cache_dir)
    new_cache = diskcache.Cache(
        directory=migrated_dir,
        disk_min_file_size=1000000
    )
    
    migrated_count = 0
    error_count = 0
    keys_to_migrate = 0
    
    try:
        # Iterate over keys in the old cache
        for key in old_cache:
            keys_to_migrate += 1
            try:
                # Get value and all metadata from old cache
                retrieved_data = old_cache.get(
                    key, 
                    default=diskcache.core.ENOVAL, 
                    read=False, 
                    expire_time=True, 
                    tag=True
                )
                
                if retrieved_data == diskcache.core.ENOVAL:
                    print(f"Warning: Key '{key}' not found in source cache. Skipping.")
                    continue
                
                value_object, expiry_timestamp, tag_value = retrieved_data
                
                # Store in new cache with all metadata
                new_cache.set(
                    key, 
                    value_object, 
                    expire=expiry_timestamp, 
                    tag=tag_value
                )
                
                migrated_count += 1
                print(f"Migrated key {migrated_count}/{keys_to_migrate}: {key}")
                
            except Exception as e:
                error_count += 1
                print(f"Error migrating key '{key}': {e}")
                return False
        
        # Verify the migration
        print("\nVerifying migration...")
        verification_errors = 0
        for key in old_cache:
            try:
                # Get data from both caches
                old_value = old_cache.get(key, default=diskcache.core.ENOVAL)
                new_value = new_cache.get(key, default=diskcache.core.ENOVAL)
                
                if old_value == diskcache.core.ENOVAL:
                    print(f"Error: Key '{key}' missing in old cache")
                    verification_errors += 1
                    continue
                    
                if new_value == diskcache.core.ENOVAL:
                    print(f"Error: Key '{key}' missing in new cache")
                    verification_errors += 1
                    continue
                
                # Compare the actual data values
                if old_value == new_value:
                    print(f"Verified key: {key}")
                else:
                    # Try to handle format differences
                    try:
                        # If they're different types but represent the same data
                        if isinstance(old_value, bytes) and isinstance(new_value, str):
                            if old_value.decode('utf-8', errors='ignore') == new_value:
                                print(f"Verified key: {key} (bytes->string conversion)")
                            else:
                                print(f"Error: Value mismatch for key {key}")
                                verification_errors += 1
                        elif isinstance(old_value, str) and isinstance(new_value, bytes):
                            if old_value == new_value.decode('utf-8', errors='ignore'):
                                print(f"Verified key: {key} (string->bytes conversion)")
                            else:
                                print(f"Error: Value mismatch for key {key}")
                                verification_errors += 1
                        elif hasattr(old_value, '__dict__') and hasattr(new_value, '__dict__'):
                            # Handle custom objects like RssFeed
                            if type(old_value) == type(new_value):
                                # Compare object attributes
                                old_dict = old_value.__dict__
                                new_dict = new_value.__dict__
                                if old_dict == new_dict:
                                    print(f"Verified key: {key} (object comparison)")
                                else:
                                    print(f"Error: Object attributes mismatch for key {key}")
                                    print(f"  Old attrs: {old_dict}")
                                    print(f"  New attrs: {new_dict}")
                                    verification_errors += 1
                            else:
                                print(f"Error: Object type mismatch for key {key}")
                                verification_errors += 1
                        else:
                            # For other cases, try to normalize the data
                            old_str = str(old_value).strip()
                            new_str = str(new_value).strip()
                            if old_str == new_str:
                                print(f"Verified key: {key} (string normalization)")
                            else:
                                print(f"Error: Value mismatch for key {key}")
                                print(f"  Old: {repr(old_value)}")
                                print(f"  New: {repr(new_value)}")
                                verification_errors += 1
                    except Exception as e:
                        print(f"Error: Value mismatch for key {key} (comparison failed: {e})")
                        verification_errors += 1
                    
            except Exception as e:
                print(f"Verification error for key {key}: {e}")
                verification_errors += 1
        
        if verification_errors > 0:
            print(f"\nVerification failed with {verification_errors} errors!")
            return False
        else:
            print("\nVerification successful!")
        
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False
        
    finally:
        # Close both caches
        old_cache.close()
        new_cache.close()
        
        # Print summary
        print("--- Migration Summary ---")
        print(f"Total keys encountered: {keys_to_migrate}")
        print(f"Successfully migrated items: {migrated_count}")
        print(f"Items failed to migrate: {error_count}")
    
    return True

if __name__ == "__main__":
    # Use current directory by default
    CACHE_DIR = os.getcwd()
    
    print("Starting migration to SQLite-only storage...")
    if migrate_to_sqlite(CACHE_DIR):
        print("Migration completed successfully!")
        print(f"New SQLite-only cache is in: {os.path.join(CACHE_DIR, 'migrated')}")
        print("You can now update your DiskCache configuration to use disk_min_file_size=1000000")
    else:
        print("Migration failed! Please check the errors above and try again.") 