"""
Module: image_candidate_selector.py

Contains logic for selecting the best image from a list of candidates.
"""

from image_utils import get_actual_image_dimensions # Removed debug_print

def process_candidate_images(candidate_images):
    """Process a list of candidate images and return the best one based on a simplified scoring logic."""
    if not candidate_images:
        print("No candidate images available for processing.")
        return None

    # 1. Prioritize meta images
    meta_images = [(url, meta) for url, meta in candidate_images if meta.get('meta')]
    if meta_images:
        candidate_images = meta_images

    # 2. For each candidate, fetch dimensions if missing (for top 5 only)
    top_candidates = sorted(candidate_images, key=lambda item: item[1].get('score', 0), reverse=True)[:5]
    for i, (url, meta) in enumerate(top_candidates):
        width = meta.get('width', 0)
        height = meta.get('height', 0)
        if width == 0 or height == 0:
            actual_width, actual_height = get_actual_image_dimensions(url)
            if actual_width > 0 and actual_height > 0:
                meta['width'] = actual_width
                meta['height'] = actual_height
                meta['score'] = actual_width * actual_height
                top_candidates[i] = (url, meta)

    # 3. Resort by area (width*height)
    top_candidates.sort(key=lambda item: item[1].get('width', 0) * item[1].get('height', 0), reverse=True)

    # Ensure we still have candidates after filtering/sorting
    if not top_candidates:
        print("No suitable candidates remain after processing.")
        return None

    # 4. Fallback: if no dimensions, use original score
    best = top_candidates[0]
    best_url = best[0]
    best_width = best[1].get('width', 0)
    best_height = best[1].get('height', 0)
    min_size = 100  # Minimum width and height for a valid image
    if best_width < min_size or best_height < min_size:
        print("No suitable images found (all images too small).")
        return None
    print(f"Best image found: {best_url} (score: {best[1].get('score')}, size: {best_width}x{best_height})")
    return best_url
