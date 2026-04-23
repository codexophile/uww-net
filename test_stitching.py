#!/usr/bin/env python3
"""Test script for wallpaper stitching functionality."""

import os
import sys
import json
sys.path.append(os.path.dirname(__file__))

from monitors import gather_monitors
from image_utils import stitch_images_for_monitors


def _get_cropped_folder() -> str:
    """Resolve cropped image folder from config with safe fallbacks."""
    script_dir = os.path.dirname(__file__)
    config_path = os.path.join(script_dir, "config.json")
    parent = "C:/media/wallpapers"
    cropped_subfolder = "cropped"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        storage = cfg.get("storage", {})
        parent = storage.get("parent_folder") or cfg.get("destination_folder", parent)
        cropped_subfolder = storage.get("cropped_subfolder", cropped_subfolder)
    except Exception:
        pass
    return os.path.join(parent, cropped_subfolder)

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
    dest_folder = _get_cropped_folder()
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
