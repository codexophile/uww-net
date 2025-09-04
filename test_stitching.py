#!/usr/bin/env python3
"""Test script for wallpaper stitching functionality."""

import os
import sys
sys.path.append(os.path.dirname(__file__))

from monitors import gather_monitors
from image_utils import stitch_images_for_monitors

def test_stitching():
    """Test the image stitching functionality."""
    print("Testing wallpaper stitching functionality...")

    # Gather monitor information
    monitors = gather_monitors(True)
    if not monitors:
        print("No monitors detected!")
        return False

    print(f"Detected {len(monitors)} monitors:")
    for i, m in enumerate(monitors):
        print(f"  Monitor {i+1}: {m.name} - {m.width}x{m.height} at ({m.x}, {m.y})")

    # Get image paths
    dest_folder = "C:/media/wallpapers"
    image_files = [f for f in os.listdir(dest_folder) if f.endswith(('.jpg', '.png', '.jpeg'))]
    if len(image_files) < len(monitors):
        print(f"Not enough images ({len(image_files)}) for {len(monitors)} monitors")
        return False

    image_paths = [os.path.join(dest_folder, f) for f in image_files[:len(monitors)]]
    print(f"Using images: {image_paths}")

    # Test stitching
    output_path = os.path.join(dest_folder, "test_stitched_wallpaper.jpg")
    result = stitch_images_for_monitors(image_paths, monitors, output_path, True)

    if result:
        print(f"Successfully created stitched wallpaper: {result}")
        return True
    else:
        print("Failed to create stitched wallpaper")
        return False

if __name__ == "__main__":
    success = test_stitching()
    sys.exit(0 if success else 1)
