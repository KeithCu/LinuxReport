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
converted_files = []

# Quality setting for WebP conversion
quality = 85

print(f"Found {len(png_files)} PNG files to analyze...")

# Process each PNG file
for png_file in png_files:
    try:
        basename = os.path.basename(png_file)
        print(f"Processing {basename}...")
        
        # Open the image
        img = Image.open(png_file)
        
        # Get original file size
        orig_size = os.path.getsize(png_file)
        
        # Check if image has alpha channel (transparency)
        has_alpha = img.mode == 'RGBA'
        
        # Create WebP filename (final version)
        webp_file = os.path.splitext(png_file)[0] + ".webp"
        
        # Save as WebP
        img.save(webp_file, "WEBP", quality=quality, lossless=has_alpha)
        
        # Get WebP file size
        webp_size = os.path.getsize(webp_file)
        
        # Calculate size reduction
        size_reduction = (orig_size - webp_size) / orig_size * 100
        
        # Determine if conversion is worth it (>20% reduction)
        worth_converting = size_reduction > 20
        
        # Add to results
        results.append([
            basename,
            f"{orig_size / 1024:.1f} KB",
            f"{webp_size / 1024:.1f} KB",
            f"{size_reduction:.1f}%",
            "Yes" if has_alpha else "No",
            "YES" if worth_converting else "No"
        ])
        
        if worth_converting:
            converted_files.append(basename)
        else:
            # Remove WebP file if not worth converting
            os.remove(webp_file)
            print(f"  Not worth converting, removed WebP version")
        
    except Exception as e:
        print(f"  Error processing {basename}: {str(e)}")
        results.append([basename, "Error", str(e), "", "", ""])

# Sort results by size reduction (largest first)
results.sort(key=lambda x: float(x[3].replace("%", "")) if x[3] else 0, reverse=True)

# Print results as table
headers = ["PNG File", "Original Size", "WebP Size", "Reduction", "Has Alpha", "Worth Converting"]
print("\nConversion Results:")
print(tabulate.tabulate(results, headers=headers, tablefmt="grid"))

print(f"\nConverted {len(converted_files)} PNG files to WebP format:")
for file in converted_files:
    print(f"- {file}")

print(f"\nWebP Quality setting: {quality}%")
print("WebP files with alpha channels were saved in lossless mode to preserve transparency.")
print("\nTo use the WebP versions in your code, update image references from .png to .webp") 