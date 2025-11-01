#!/usr/bin/env python3
"""
Process robotreportlogoinitial.png:
1. Crop excess white space
2. Make white background transparent
3. Convert to WebP with quality 85
"""

from PIL import Image
import numpy as np

# Open the image
img = Image.open('robotreportlogoinitial.png')
print(f"Original size: {img.size}, Mode: {img.mode}")

# Convert to RGBA if not already
if img.mode != 'RGBA':
    img = img.convert('RGBA')

# Convert to numpy array for easier processing
img_array = np.array(img)

# Find bounding box of non-white pixels
# Consider pixels transparent if they are very close to white (all channels > 240)
mask = ~((img_array[:, :, 0] > 240) & (img_array[:, :, 1] > 240) & (img_array[:, :, 2] > 240))
coords = np.column_stack(np.where(mask))

if len(coords) > 0:
    # Get bounding box
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)
    
    # Add small padding
    padding = 10
    y_min = max(0, y_min - padding)
    x_min = max(0, x_min - padding)
    y_max = min(img_array.shape[0], y_max + padding + 1)
    x_max = min(img_array.shape[1], x_max + padding + 1)
    
    # Crop the image
    img_cropped = img.crop((x_min, y_min, x_max, y_max))
    print(f"Cropped size: {img_cropped.size}")
else:
    img_cropped = img
    print("No cropping needed")

# Convert white pixels to transparent
img_array_cropped = np.array(img_cropped)
r, g, b, a = img_array_cropped[:, :, 0], img_array_cropped[:, :, 1], img_array_cropped[:, :, 2], img_array_cropped[:, :, 3]

# Create mask for white pixels (with tolerance)
# A pixel is considered white if R, G, B are all > 240
white_mask = (r > 240) & (g > 240) & (b > 240)

# Set alpha channel to 0 for white pixels
img_array_cropped[:, :, 3] = np.where(white_mask, 0, a)

# Convert back to PIL Image
img_final = Image.fromarray(img_array_cropped, 'RGBA')

# Save as WebP with quality 85
output_filename = 'robotreportlogoinitial.webp'
img_final.save(output_filename, 'WEBP', quality=85, lossless=False)

print(f"Saved as {output_filename} with quality 85")
print(f"Final size: {img_final.size}")

