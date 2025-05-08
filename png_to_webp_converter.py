import os
import glob
from PIL import Image
import sys

# Ensure we have the tabulate package
try:
    import tabulate
except ImportError:
    print("Installing tabulate package...")
    os.system(f"{sys.executable} -m pip install tabulate")
    import tabulate

# Directory containing images
image_dir = "static/images"

# Find all PNG files
png_files = glob.glob(os.path.join(image_dir, "*.png"))

# Results table
results = []

# Quality setting for WebP conversion
quality = 85

# Process each PNG file
for png_file in png_files:
    try:
        # Open the image
        img = Image.open(png_file)
        
        # Get original file size
        orig_size = os.path.getsize(png_file)
        
        # Check if image has alpha channel (transparency)
        has_alpha = img.mode == 'RGBA'
        
        # Create WebP filename
        webp_file = os.path.splitext(png_file)[0] + "_test.webp"
        
        # Save as WebP
        img.save(webp_file, "WEBP", quality=quality, lossless=has_alpha)
        
        # Get WebP file size
        webp_size = os.path.getsize(webp_file)
        
        # Calculate size reduction
        size_reduction = (orig_size - webp_size) / orig_size * 100
        
        # Determine if conversion is worth it (>20% reduction and alpha preserved)
        worth_converting = size_reduction > 20
        
        # Add to results
        results.append([
            os.path.basename(png_file),
            f"{orig_size / 1024:.1f} KB",
            f"{webp_size / 1024:.1f} KB",
            f"{size_reduction:.1f}%",
            "Yes" if has_alpha else "No",
            "YES" if worth_converting else "No"
        ])
        
    except Exception as e:
        results.append([os.path.basename(png_file), "Error", str(e), "", "", ""])

# Sort results by size reduction (largest first)
results.sort(key=lambda x: float(x[3].replace("%", "")) if x[3] else 0, reverse=True)

# Print results as table
headers = ["PNG File", "Original Size", "WebP Size", "Reduction", "Has Alpha", "Worth Converting"]
print(tabulate.tabulate(results, headers=headers, tablefmt="grid"))

print("\nNote: Test WebP files have been created with '_test' suffix.")
print(f"WebP Quality setting: {quality}%")
print("WebP files with alpha channels were saved in lossless mode to preserve transparency.") 