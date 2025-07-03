
"""
Module: image_candidate_processor.py

This module contains the logic for processing a list of candidate images
and selecting the best one based on a scoring system.
"""

from image_utils import get_actual_image_dimensions, debug_print

def process_candidate_images(candidate_images):
    """
    Process a list of candidate images and return the best one based on a simplified scoring logic.
    
    This function takes a list of (url, metadata) tuples, fetches the actual dimensions for the top
    candidates if they are missing, and then selects the best image based on its area.
    """
    if not candidate_images:
        debug_print("No candidate images available for processing.")
        return None

    # 1. Prioritize meta images if they exist
    meta_images = [(url, meta) for url, meta in candidate_images if meta.get('meta')]
    if meta_images:
        candidate_images = meta_images

    # 2. For each candidate, fetch dimensions if missing (for top 5 only)
    # Sort by the initial score to determine the top candidates
    top_candidates = sorted(candidate_images, key=lambda item: item[1].get('score', 0), reverse=True)[:5]

    for i, (url, meta) in enumerate(top_candidates):
        width = meta.get('width', 0)
        height = meta.get('height', 0)
        
        # Fetch dimensions only if they are unknown
        if width == 0 or height == 0:
            actual_width, actual_height = get_actual_image_dimensions(url)
            if actual_width > 0 and actual_height > 0:
                meta['width'] = actual_width
                meta['height'] = actual_height
                # Update the score based on the actual dimensions
                meta['score'] = actual_width * actual_height
                top_candidates[i] = (url, meta)

    # 3. Re-sort the candidates by the final score (which is now based on area)
    top_candidates.sort(key=lambda item: item[1].get('score', 0), reverse=True)

    if not top_candidates:
        debug_print("No suitable candidates remain after processing.")
        return None

    # 4. Select the best image and perform a final size check
    best_url, best_meta = top_candidates[0]
    best_width = best_meta.get('width', 0)
    best_height = best_meta.get('height', 0)
    min_size = 100  # Minimum width and height for a valid image

    if best_width < min_size or best_height < min_size:
        debug_print(f"No suitable images found (best image {best_url} is too small: {best_width}x{best_height}).")
        return None
        
    debug_print(f"Best image found: {best_url} (score: {best_meta.get('score')}, size: {best_width}x{best_height})")
    return best_url
