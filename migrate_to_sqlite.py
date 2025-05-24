#!/usr/bin/env python3
import os
import logging
import diskcache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def migrate_to_sqlite(cache_dir):
    """
    Migrate DiskCache from file-based storage to SQLite-only storage.
    Uses DiskCache's own API to handle all data properly and preserves expiration times and tags.
    """
    logging.info(f"Starting migration of cache at {cache_dir}")
    
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
                    logging.warning(f"Key '{key}' not found in source cache. Skipping.")
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
                logging.info(f"Migrated key {migrated_count}/{keys_to_migrate}: {key}")
                
            except Exception as e:
                error_count += 1
                logging.error(f"Error migrating key '{key}': {e}", exc_info=True)
                return False
        
        # Verify the migration
        logging.info("\nVerifying migration...")
        for key in old_cache:
            try:
                # Get data from both caches with all metadata
                old_data = old_cache.get(key, read=False, expire_time=True, tag=True)
                new_data = new_cache.get(key, read=False, expire_time=True, tag=True)
                
                if old_data == diskcache.core.ENOVAL or new_data == diskcache.core.ENOVAL:
                    logging.error(f"Key '{key}' missing in one of the caches")
                    return False
                
                old_value, old_expire, old_tag = old_data
                new_value, new_expire, new_tag = new_data
                
                # Verify value, expiration, and tag
                if old_value != new_value:
                    logging.error(f"Value mismatch for key {key}")
                    return False
                if old_expire != new_expire:
                    logging.error(f"Expiration time mismatch for key {key}")
                    return False
                if old_tag != new_tag:
                    logging.error(f"Tag mismatch for key {key}")
                    return False
                    
                logging.info(f"Verified key: {key}")
                
            except Exception as e:
                logging.error(f"Verification error for key {key}: {e}", exc_info=True)
                return False
        
        logging.info("\nVerification successful!")
        
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        return False
        
    finally:
        # Close both caches
        old_cache.close()
        new_cache.close()
        
        # Log summary
        logging.info("--- Migration Summary ---")
        logging.info(f"Total keys encountered: {keys_to_migrate}")
        logging.info(f"Successfully migrated items: {migrated_count}")
        logging.info(f"Items failed to migrate: {error_count}")
    
    return True

if __name__ == "__main__":
    # Use current directory by default
    CACHE_DIR = os.getcwd()
    
    logging.info("Starting migration to SQLite-only storage...")
    if migrate_to_sqlite(CACHE_DIR):
        logging.info("Migration completed successfully!")
        logging.info(f"New SQLite-only cache is in: {os.path.join(CACHE_DIR, 'migrated')}")
        logging.info("You can now update your DiskCache configuration to use sqlite_only=True")
    else:
        logging.error("Migration failed! Please check the errors above and try again.") 