"""Image download & ratio utilities."""
from __future__ import annotations

import math
import os
import re
from io import BytesIO

try:
    import requests  # type: ignore
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore
    Image = None  # type: ignore


def ensure_dependencies():
    if requests is None or Image is None:  # type: ignore
        raise RuntimeError("Missing dependencies. Install with: pip install requests Pillow")


def fetch_image_dimensions(image_url: str) -> tuple[int | None, int | None]:
    try:
        ensure_dependencies()
        resp = requests.get(image_url, timeout=15)  # type: ignore
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))  # type: ignore
        width, height = img.size
        return width, height
    except Exception as e:  # pragma: no cover
        print(f"Failed to obtain image dimensions: {e}")
        return None, None


def simplify_ratio(width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    g = math.gcd(width, height)
    return f"{width // g}:{height // g}"


def _sanitize_filename(name: str) -> str:
    # Remove query params and unsafe chars
    name = name.split("?")[0]
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name or "image.jpg"


def download_image(image_url: str, destination_folder: str, filename: str | None = None) -> str | None:
    """Download an image to ``destination_folder``.

    Returns the absolute path of the saved file or ``None`` on failure.
    """
    try:
        ensure_dependencies()
        os.makedirs(destination_folder, exist_ok=True)
        if not filename:
            # derive from URL
            filename = _sanitize_filename(image_url.rsplit("/", 1)[-1] or "wallpaper.jpg")
            if "." not in filename:
                filename += ".jpg"
        dest_path = os.path.join(destination_folder, filename)
        base, ext = os.path.splitext(dest_path)
        # Avoid overwriting existing files; append counter if needed.
        counter = 1
        while os.path.exists(dest_path):
            dest_path = f"{base}_{counter}{ext}"
            counter += 1
        resp = requests.get(image_url, timeout=30)  # type: ignore
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").lower()
        if "image" not in content_type:
            print(f"Skipped non-image url: {image_url} -> {content_type}")
            return None
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        return dest_path
    except Exception as e:  # pragma: no cover
        print(f"Failed to download image {image_url}: {e}")
        return None


__all__ = [
    "fetch_image_dimensions",
    "simplify_ratio",
    "ensure_dependencies",
    "download_image",
]
