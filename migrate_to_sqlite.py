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
        sqlite_only=True
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
        for key in old_cache:
            try:
                # Get data from both caches with all metadata
                old_data = old_cache.get(key, read=False, expire_time=True, tag=True)
                new_data = new_cache.get(key, read=False, expire_time=True, tag=True)
                
                if old_data == diskcache.core.ENOVAL or new_data == diskcache.core.ENOVAL:
                    print(f"Error: Key '{key}' missing in one of the caches")
                    return False
                
                old_value, old_expire, old_tag = old_data
                new_value, new_expire, new_tag = new_data
                
                # Verify value, expiration, and tag
                if old_value != new_value:
                    print(f"Error: Value mismatch for key {key}")
                    return False
                if old_expire != new_expire:
                    print(f"Error: Expiration time mismatch for key {key}")
                    return False
                if old_tag != new_tag:
                    print(f"Error: Tag mismatch for key {key}")
                    return False
                    
                print(f"Verified key: {key}")
                
            except Exception as e:
                print(f"Verification error for key {key}: {e}")
                return False
        
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
        print("You can now update your DiskCache configuration to use sqlite_only=True")
    else:
        print("Migration failed! Please check the errors above and try again.") 