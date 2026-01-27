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


def fetch_image_dimensions(image_url: str, verbose: bool = True) -> tuple[int | None, int | None]:
    try:
        ensure_dependencies()
        resp = requests.get(image_url, timeout=15)  # type: ignore
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))  # type: ignore
        width, height = img.size
        return width, height
    except Exception as e:  # pragma: no cover
        if verbose:
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


def download_image(image_url: str, destination_folder: str, filename: str | None = None, verbose: bool = True) -> str | None:
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
            if verbose:
                print(f"Skipped non-image url: {image_url} -> {content_type}")
            return None
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        return dest_path
    except Exception as e:  # pragma: no cover
        if verbose:
            print(f"Failed to download image {image_url}: {e}")
        return None


def crop_image_to_aspect(
    image_path: str,
    aspect_w: int = 16,
    aspect_h: int = 9,
    inplace: bool = True,
    output_path: str | None = None,
    verbose: bool = True,
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
        if verbose:
            print(f"Failed to crop image '{image_path}' to {aspect_w}:{aspect_h}: {e}")
        return None


def set_wallpaper(image_path: str, verbose: bool = True) -> bool:
    """Set the system wallpaper to the specified image.

    Parameters:
        image_path: path to the image file to set as wallpaper.
        verbose: if True, print status messages.

    Returns:
        True if successful, False otherwise.
    """
    try:
        if os.name != "nt":
            if verbose:
                print("Wallpaper setting is only supported on Windows.")
            return False

        import ctypes
        from ctypes import wintypes

        # Windows API constants
        SPI_SETDESKWALLPAPER = 0x0014
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDWININICHANGE = 0x02

        # Convert path to absolute and ensure it exists
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            if verbose:
                print(f"Wallpaper image does not exist: {abs_path}")
            return False

        # Set wallpaper using Windows API
        user32 = ctypes.windll.user32
        result = user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            abs_path,
            SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE
        )

        if result:
            if verbose:
                print(f"Successfully set wallpaper to: {abs_path}")
            return True
        else:
            if verbose:
                print(f"Failed to set wallpaper: SystemParametersInfoW returned {result}")
            return False

    except Exception as e:
        if verbose:
            print(f"Failed to set wallpaper: {e}")
        return False


def is_image_too_bright(
    image_path: str,
    brightness_threshold: float = 200.0,
    sample_size: int = 10000,
    verbose: bool = True,
) -> bool:
    """Check if an image is too bright based on average luminance.

    Parameters:
        image_path: path to the image file to check.
        brightness_threshold: maximum average brightness (0-255). Images with
                             average brightness >= threshold are considered too bright.
        sample_size: number of pixels to sample. If 0, samples all pixels (slower).
        verbose: if True, print diagnostic messages.

    Returns:
        True if the image is too bright, False otherwise.
    """
    try:
        ensure_dependencies()
        with Image.open(image_path) as img:  # type: ignore
            # Convert to grayscale for brightness calculation
            if img.mode != 'L':
                gray_img = img.convert('L')  # type: ignore
            else:
                gray_img = img
            
            # Get pixel data
            pixels = list(gray_img.getdata())  # type: ignore
            
            # Sample pixels if requested
            if sample_size > 0 and len(pixels) > sample_size:
                import random
                pixels = random.sample(pixels, sample_size)
            
            # Calculate average brightness
            avg_brightness = sum(pixels) / len(pixels) if pixels else 0
            
            is_too_bright = avg_brightness >= brightness_threshold
            if verbose:
                print(f"Image brightness check: {avg_brightness:.1f} (threshold: {brightness_threshold}) - {'TOO BRIGHT' if is_too_bright else 'OK'}")
            
            return is_too_bright
    except Exception as e:
        if verbose:
            print(f"Failed to check image brightness: {e}")
        # If we can't check, assume it's okay
        return False


def stitch_images_for_monitors(image_paths: list[str], monitors: list, output_path: str, verbose: bool = True) -> str | None:
    """Stitch multiple images into a single image based on monitor layout.

    Parameters:
        image_paths: list of paths to images to stitch (one per monitor).
        monitors: list of MonitorInfo objects describing monitor layout.
        output_path: path where to save the stitched image.
        verbose: if True, print status messages.

    Returns:
        Path to the stitched image or None on failure.
    """
    try:
        ensure_dependencies()
        if len(image_paths) != len(monitors):
            if verbose:
                print(f"Number of images ({len(image_paths)}) must match number of monitors ({len(monitors)})")
            return None

        if not image_paths:
            if verbose:
                print("No images provided for stitching")
            return None

        # Calculate total desktop dimensions
        min_x = min(m.x for m in monitors)
        min_y = min(m.y for m in monitors)
        max_x = max(m.x + m.width for m in monitors)
        max_y = max(m.y + m.height for m in monitors)

        total_width = max_x - min_x
        total_height = max_y - min_y

        if verbose:
            print(f"Creating stitched image of size {total_width}x{total_height}")

        # Create new image with total desktop size
        stitched_image = Image.new('RGB', (total_width, total_height), (0, 0, 0))

        # Paste each monitor's image at its position
        for i, (image_path, monitor) in enumerate(zip(image_paths, monitors)):
            try:
                with Image.open(image_path) as img:
                    # Resize image to fit monitor dimensions if needed
                    if img.size != (monitor.width, monitor.height):
                        img = img.resize((monitor.width, monitor.height), Image.Resampling.LANCZOS)

                    # Calculate position relative to total desktop
                    x_pos = monitor.x - min_x
                    y_pos = monitor.y - min_y

                    stitched_image.paste(img, (x_pos, y_pos))

                    if verbose:
                        print(f"Added monitor {i+1} ({monitor.name}) at position ({x_pos}, {y_pos})")

            except Exception as e:
                if verbose:
                    print(f"Failed to process image for monitor {i+1}: {e}")
                return None

        # Save the stitched image
        stitched_image.save(output_path, 'JPEG', quality=95)
        if verbose:
            print(f"Successfully created stitched wallpaper: {output_path}")

        return output_path

    except Exception as e:
        if verbose:
            print(f"Failed to stitch images: {e}")
        return None


__all__ = [
    "fetch_image_dimensions",
    "simplify_ratio",
    "ensure_dependencies",
    "download_image",
    "crop_image_to_aspect",
    "set_wallpaper",
    "stitch_images_for_monitors",
    "is_image_too_bright",
]
