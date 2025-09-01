"""Image download & ratio utilities."""
from __future__ import annotations

import math
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


__all__ = ["fetch_image_dimensions", "simplify_ratio", "ensure_dependencies"]
