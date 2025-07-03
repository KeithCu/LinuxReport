import difflib

from shared import g_c

def merge_entries(new_entries, old_entries, title_threshold=0.85):
    """
    Merge two lists of feed entries, preserving order and avoiding duplicates.
    Two entries are considered the same if:
      - They share the same link.
    
    New entries take precedence over cached ones, but original timestamps are preserved
    from cached entries to maintain proper chronological ordering.
    """
    merged = []
    seen_links = set()
    new_titles = []  # to compare against old titles
    
    # Create a mapping of old entries by link for timestamp preservation
    old_entries_by_link = {}
    for entry in old_entries:
        link = entry.get('link')
        if link:
            old_entries_by_link[link] = entry

    # Process new entries first.
    for entry in new_entries:
        # Get unique key and title. (Assumes entries are dicts.)
        key = entry.get('link')
        title = entry.get('title')
        if key:
            seen_links.add(key)
            
            # If we've seen this link before, preserve the original timestamp
            if key in old_entries_by_link:
                old_entry = old_entries_by_link[key]
                # Preserve the original published timestamp
                if 'published' in old_entry:
                    entry['published'] = old_entry['published']
                if 'published_parsed' in old_entry:
                    entry['published_parsed'] = old_entry['published_parsed']
                    
        if title:
            new_titles.append(title)
        merged.append(entry)

    # Append old entries only if they're not already represented.
    for entry in old_entries:
        key = entry.get('link')
        title = entry.get('title')
        # Skip if the link already exists.
        if key and key in seen_links:
            continue

        merged.append(entry)

    return merged