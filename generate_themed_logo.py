#!/usr/bin/env python3
"""
Generate themed logos using OpenRouter API with Grok image generation.

This script uploads a default logo, applies holiday/thematic modifications using Grok,
downloads the generated image, and updates the logo URL in the report settings file.

Setup:
    1. Get an OpenRouter API key from https://openrouter.ai/keys
    2. Set environment variable: export OPENROUTER_API_KEY="your-key-here"
       OR pass it via --api-key argument

Usage:
    # Just pass the theme string - the prompt is formatted automatically
    python generate_themed_logo.py --theme "Halloween" --report linux
    python generate_themed_logo.py --theme "Christmas" --report ai
    python generate_themed_logo.py --theme "cyberpunk style" --report linux
    python generate_themed_logo.py --theme "space theme with stars" --report space
    
Note:
    Images are generated at 1920x1080 (1080p) resolution. The API will automatically
    maintain the aspect ratio based on the size parameter.

Note:
    If Grok doesn't support image generation, you may need to use a different model.
    Check OpenRouter's available models at https://openrouter.ai/models
    and use --model flag to specify an alternative (e.g., "black-forest-labs/flux-dev").
"""

import os
import sys
import base64
import argparse
import requests
from pathlib import Path

# Configuration
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
STATIC_IMAGES_DIR = "static/images"

# Default logo mappings by report type
DEFAULT_LOGOS = {
    "linux": "linuxreportfancy.webp",
    "ai": "aireportfancy.webp",
    "covid": "covidreportfancy.webp",
    "techno": "TechnoReport.webp",
    "space": "SpaceReport.webp",
    "trump": "TrumpReport.webp",
    "pv": "pvreport.webp",
    "robot": "RobotReport.webp",
}


def encode_image_to_base64(image_path: str) -> str:
    """Encode image file to base64 string."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def generate_themed_image(
    api_key: str,
    base64_image: str,
    prompt_text: str,
    model: str = "x-ai/grok-2-vision-1212"
) -> dict:
    """
    Generate themed image using OpenRouter API.
    
    Args:
        api_key: OpenRouter API key
        base64_image: Base64-encoded image data
        prompt_text: Prompt text describing how to alter the image
        model: Model to use (default: Grok vision model)
    
    Returns:
        API response JSON
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/keithcu/LinuxReport",  # Optional: for OpenRouter analytics
        "X-Title": "LinuxReport Logo Generator",  # Optional: for OpenRouter analytics
    }
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_text
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "modalities": ["image", "text"],
        "image_config": {
            "size": "1920x1080"  # Fixed to 1080p resolution
        }
    }
    
    print(f"Sending request to OpenRouter API...")
    print(f"Model: {model}")
    print(f"Size: 1920x1080 (1080p)")
    print(f"Prompt: {prompt_text[:100]}...")
    
    response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload)
    response.raise_for_status()
    
    return response.json()


def extract_image_url(response_json: dict) -> str:
    """Extract image URL or base64 data from API response."""
    try:
        choices = response_json.get('choices', [])
        if not choices:
            raise ValueError("No choices in API response")
        
        message = choices[0].get('message', {})
        content = message.get('content', [])
        
        # Handle different response formats
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    # Handle Gemini format: {'type': 'image', 'image': 'data:image/png;base64,...'}
                    if item.get('type') == 'image' and 'image' in item:
                        image_data = item['image']
                        if isinstance(image_data, str):
                            if image_data.startswith('data:'):
                                return image_data
                            elif image_data.startswith('http'):
                                return image_data
                            else:
                                # Assume base64
                                return f"data:image/png;base64,{image_data}"
                    
                    # Check for image_url structure
                    if 'image_url' in item:
                        url = item['image_url'].get('url', '')
                        if url:
                            return url
                    # Check for direct url
                    elif 'url' in item:
                        url = item['url']
                        if url:
                            return url
                    # Check for base64 image data
                    elif 'b64_json' in item:
                        # Return base64 data URI format
                        b64_data = item['b64_json']
                        return f"data:image/png;base64,{b64_data}"
        
        # Check for images array (Gemini format)
        if 'images' in message:
            images = message['images']
            if isinstance(images, list) and len(images) > 0:
                first_image = images[0]
                if isinstance(first_image, dict):
                    if 'image_url' in first_image:
                        url = first_image['image_url'].get('url', '')
                        if url:
                            return url
                    elif 'url' in first_image:
                        return first_image['url']
        
        # Try alternative paths
        if 'image_url' in message:
            url = message['image_url'].get('url', '')
            if url:
                return url
        
        # Check for error in response
        if 'error' in response_json:
            error_msg = response_json['error'].get('message', 'Unknown error')
            raise ValueError(f"API error: {error_msg}")
        
        raise ValueError("Could not find image URL or data in response")
    except (KeyError, IndexError, TypeError) as e:
        print(f"Response structure: {response_json}")
        raise ValueError(f"Failed to extract image from response: {e}")


def download_image(image_url_or_data: str, save_path: str) -> None:
    """Download image from URL or save base64 data to file."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    # Handle base64 data URI
    if image_url_or_data.startswith('data:image'):
        print("Extracting image from base64 data...")
        # Extract base64 part after the comma
        if ',' in image_url_or_data:
            base64_data = image_url_or_data.split(',')[1]
            image_data = base64.b64decode(base64_data)
            with open(save_path, 'wb') as f:
                f.write(image_data)
            print(f"Image saved to: {save_path}")
            return
    
    # Handle URL
    print(f"Downloading image from {image_url_or_data}...")
    response = requests.get(image_url_or_data, stream=True)
    response.raise_for_status()
    
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    print(f"Image saved to: {save_path}")


def update_logo_url_in_settings(report_type: str, new_logo_filename: str) -> None:
    """
    Update the LOGO_URL in the report settings file.
    
    Args:
        report_type: Report type (e.g., 'linux', 'ai')
        new_logo_filename: New logo filename (e.g., 'LinuxReportSpooky.webp')
    """
    settings_file = f"{report_type}_report_settings.py"
    
    if not os.path.exists(settings_file):
        print(f"Warning: Settings file not found: {settings_file}")
        return
    
    print(f"Updating {settings_file}...")
    
    with open(settings_file, 'r') as f:
        content = f.read()
    
    # Find and replace LOGO_URL
    import re
    pattern = r'LOGO_URL\s*=\s*["\']([^"\']+)["\']'
    
    def replace_logo(match):
        return f'LOGO_URL="{new_logo_filename}"'
    
    updated_content = re.sub(pattern, replace_logo, content)
    
    if updated_content == content:
        print(f"Warning: Could not find LOGO_URL in {settings_file}")
        print("Please manually update the LOGO_URL setting.")
        return
    
    with open(settings_file, 'w') as f:
        f.write(updated_content)
    
    print(f"Updated LOGO_URL to: {new_logo_filename}")


def generate_logo_filename(report_type: str, theme: str) -> str:
    """Generate filename for themed logo."""
    report_capitalized = report_type.capitalize()
    theme_capitalized = theme.capitalize()
    
    # Handle special cases
    if report_type == "ai":
        report_prefix = "AIReport"
    elif report_type == "pv":
        report_prefix = "PVReport"
    else:
        report_prefix = f"{report_capitalized}Report"
    
    return f"{report_prefix}{theme_capitalized}.webp"


def main():
    parser = argparse.ArgumentParser(
        description="Generate themed logos using OpenRouter API with Grok",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using relaxed prompt (default - works well for most logos)
  python generate_themed_logo.py --theme "Halloween" --report linux
  python generate_themed_logo.py --theme "Christmas" --report ai
  
  # Using strict prompt (preserves logo better - use when logo disappears)
  python generate_themed_logo.py --theme "Fall harvest theme" --report robot --preserve-logo
  
  # Custom themes
  python generate_themed_logo.py --theme "cyberpunk style with neon colors" --report linux
  python generate_themed_logo.py --theme "space theme with stars and planets" --report space
  
Note: Images are generated at 1920x1080 (1080p) resolution.
        """
    )
    parser.add_argument(
        "--theme",
        required=True,
        help='Theme or custom text describing how to alter the image. Can be any string (e.g., "Halloween", "Christmas", "cyberpunk style", etc.). By default uses a relaxed prompt that works well for most logos. Use --preserve-logo for stricter preservation when needed.'
    )
    parser.add_argument(
        "--report",
        required=True,
        choices=list(DEFAULT_LOGOS.keys()),
        help="Report type"
    )
    parser.add_argument(
        "--custom-prompt",
        help='[DEPRECATED] Use --theme instead. Custom text describing how to alter the image.'
    )
    parser.add_argument(
        "--default-logo",
        help="Path to default logo file (defaults to standard logo for report type)"
    )
    parser.add_argument(
        "--api-key",
        help="OpenRouter API key (or set OPENROUTER_API_KEY environment variable)"
    )
    parser.add_argument(
        "--model",
        default="google/gemini-2.5-flash-image",
        help="OpenRouter model to use (default: google/gemini-2.5-flash-image)"
    )
    parser.add_argument(
        "--preserve-logo",
        action="store_true",
        help="Use strict prompt that emphasizes preserving the original logo (recommended for logos that tend to disappear). Default: use relaxed prompt that works well for most logos."
    )
    parser.add_argument(
        "--output-filename",
        help="Custom output filename (defaults to {ReportType}{Theme}.webp)"
    )
    parser.add_argument(
        "--no-update-settings",
        action="store_true",
        help="Don't update the report settings file"
    )
    
    args = parser.parse_args()
    
    # Use custom-prompt if provided (for backward compatibility), otherwise use theme
    theme_input = args.custom_prompt if args.custom_prompt else args.theme
    
    # Get API key
    api_key = args.api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OpenRouter API key required.")
        print("Set OPENROUTER_API_KEY environment variable or use --api-key")
        sys.exit(1)
    
    # Determine default logo path
    if args.default_logo:
        default_logo_path = args.default_logo
    else:
        default_logo_filename = DEFAULT_LOGOS[args.report]
        default_logo_path = os.path.join(STATIC_IMAGES_DIR, default_logo_filename)
    
    if not os.path.exists(default_logo_path):
        print(f"Error: Default logo not found: {default_logo_path}")
        sys.exit(1)
    
    # Format prompt based on preserve-logo flag
    if args.preserve_logo:
        # Strict prompt: emphasizes preserving the original logo
        prompt_text = f'Please take this logo image, and alter it to have a {theme_input} theme while keeping the original logo design and central subject clearly visible and recognizable. Add thematic elements around or integrated with the logo, but maintain the logo itself as the main focus.'
    else:
        # Relaxed prompt: simpler, works well for most logos
        prompt_text = f'Please take this image, and alter it to be more like "{theme_input}".'
    # Sanitize theme name for filename: remove spaces, special chars, capitalize first letter
    theme_name = "".join(c for c in theme_input.title() if c.isalnum())
    if not theme_name:
        theme_name = "Custom"
    
    # Generate output filename
    if args.output_filename:
        output_filename = args.output_filename
    else:
        output_filename = generate_logo_filename(args.report, theme_name)
    
    output_path = os.path.join(STATIC_IMAGES_DIR, output_filename)
    
    try:
        # Step 1: Encode image
        print(f"\nStep 1: Encoding image: {default_logo_path}")
        base64_image = encode_image_to_base64(default_logo_path)
        
        # Step 2: Generate themed image
        print(f"\nStep 2: Generating themed image...")
        response_json = generate_themed_image(
            api_key=api_key,
            base64_image=base64_image,
            prompt_text=prompt_text,
            model=args.model
        )
        
        # Step 3: Extract image URL
        print(f"\nStep 3: Extracting image URL...")
        image_url = extract_image_url(response_json)
        print(f"Image URL: {image_url[:100] if len(image_url) > 100 else image_url}...")
        
        # Step 4: Download image
        print(f"\nStep 4: Downloading image...")
        download_image(image_url, output_path)
        
        # Step 5: Update settings file
        if not args.no_update_settings:
            print(f"\nStep 5: Updating settings file...")
            update_logo_url_in_settings(args.report, output_filename)
        
        print(f"\n✓ Successfully generated themed logo!")
        print(f"  Theme: {theme_input}")
        print(f"  Output: {output_path}")
        print(f"  Filename: {output_filename}")
        
        if args.no_update_settings:
            print(f"\nNote: Settings file was not updated. Please manually update LOGO_URL in {args.report}_report_settings.py")
        
    except requests.exceptions.HTTPError as e:
        print(f"\nError: API request failed")
        print(f"Status: {e.response.status_code}")
        print(f"Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

