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


def crop_image_to_aspect(
    image_path: str,
    aspect_w: int = 16,
    aspect_h: int = 9,
    inplace: bool = True,
    output_path: str | None = None,
) -> str | None:
    """Crop an image file to the target aspect ratio (default 16:9) centered.

    Parameters:
        image_path: path to the source image.
        aspect_w, aspect_h: integers describing desired aspect ratio.
        inplace: if True, overwrite the original file; otherwise write to ``output_path``.
        output_path: required if ``inplace`` is False; if omitted while ``inplace`` False, a new path with suffix is created.

    Returns the path of the cropped image (original or new) or ``None`` on failure.
    """
    try:
        ensure_dependencies()
        if aspect_w <= 0 or aspect_h <= 0:
            raise ValueError("Aspect components must be positive integers")
        with Image.open(image_path) as img:  # type: ignore
            w, h = img.size
            target_ratio = aspect_w / aspect_h
            current_ratio = w / h if h else 0
            if current_ratio == 0:
                return None
            if abs(current_ratio - target_ratio) < 1e-4:
                # Already close enough; just optionally copy
                dest = image_path if inplace else (output_path or image_path)
                if not inplace and output_path:
                    img.save(dest)
                return dest
            if current_ratio > target_ratio:
                # Too wide: reduce width
                new_w = int(round(h * target_ratio))
                new_h = h
                left = (w - new_w) // 2
                top = 0
            else:
                # Too tall: reduce height
                new_w = w
                new_h = int(round(w / target_ratio))
                left = 0
                top = (h - new_h) // 2
            right = left + new_w
            bottom = top + new_h
            cropped = img.crop((left, top, right, bottom))
            if inplace:
                dest_path = image_path
            else:
                if not output_path:
                    base, ext = os.path.splitext(image_path)
                    output_path = f"{base}_cropped{ext or '.jpg'}"
                dest_path = output_path
            # Preserve original format if possible
            save_kwargs = {}
            if getattr(img, "format", None):
                save_kwargs["format"] = img.format  # type: ignore
            cropped.save(dest_path, **save_kwargs)
            return dest_path
    except Exception as e:  # pragma: no cover
        print(f"Failed to crop image '{image_path}' to {aspect_w}:{aspect_h}: {e}")
        return None


__all__ = [
    "fetch_image_dimensions",
    "simplify_ratio",
    "ensure_dependencies",
    "download_image",
    "crop_image_to_aspect",
]
