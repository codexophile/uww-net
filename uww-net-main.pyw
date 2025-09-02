from dataclasses import asdict
import os
import time
import argparse
from datetime import datetime
import threading
import pystray
from PIL import Image, ImageDraw

from monitors import gather_monitors
from wallpaper_scraper import get_wallpapers_after_shuffle
from image_utils import ensure_dependencies, download_image, crop_image_to_aspect

# Global flag to control the wallpaper loop
running = True

destinationFolder = "C:\\media\\wallpapers"


def create_icon():
    """Create a simple tray icon."""
    # Create a 64x64 icon
    img = Image.new('RGB', (64, 64), color='blue')
    draw = ImageDraw.Draw(img)
    # Draw a simple wallpaper-like pattern (stripes)
    for i in range(0, 64, 8):
        draw.rectangle([i, 0, i+4, 64], fill='white')
    return img


def run_once() -> bool:
    """Run a single wallpaper fetch / download cycle.

    Returns True if at least one image processed successfully, else False.
    """
    monitors_list = gather_monitors()
    monitor_count = len(monitors_list)
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Detected {monitor_count} monitor(s).")
    wallpapers = get_wallpapers_after_shuffle(monitor_count)
    if wallpapers and len(wallpapers) == monitor_count:
        print(f"Successfully extracted {len(wallpapers)} wallpapers (one per monitor).")
    elif wallpapers:
        print(f"Extracted {len(wallpapers)} wallpapers (requested {monitor_count}).")
    else:
        print("Failed to extract any wallpaper data.")
    for idx, wp in enumerate(wallpapers, start=1):
        print(f"Wallpaper {idx}: {wp}")

    if not wallpapers:
        return False

    try:
        ensure_dependencies()
    except RuntimeError as dep_err:
        print(f"Cannot download images (missing deps): {dep_err}")
        return False

    import tempfile, shutil
    tmp_dir = tempfile.mkdtemp(prefix="uww_dl_")
    print(f"Downloading {len(wallpapers)} image(s) to temporary folder {tmp_dir} ...")
    tmp_files: list[str] = []
    for idx, wp in enumerate(wallpapers, start=1):
        url = wp.get("image_url")
        if not url:
            print(f"Wallpaper {idx} missing image_url, skipping.")
            continue
        saved_path = download_image(url, tmp_dir)
        if saved_path:
            print(f"Downloaded wallpaper {idx} -> {saved_path}")
            tmp_files.append(saved_path)
        else:
            print(f"Failed to download wallpaper {idx}")

    cropped_files: list[str] = []
    for path in tmp_files:
        cropped = crop_image_to_aspect(path, 16, 9, inplace=True)
        if cropped:
            cropped_files.append(cropped)
        else:
            print(f"Skipping move for image that failed to crop: {path}")

    os.makedirs(destinationFolder, exist_ok=True)
    final_files: list[str] = []
    for src in cropped_files:
        try:
            fname = os.path.basename(src)
            dest_path = os.path.join(destinationFolder, fname)
            # Overwrite if exists; we prune anyway
            import shutil
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            shutil.move(src, dest_path)
            final_files.append(os.path.abspath(dest_path))
        except Exception as e:
            print(f"Failed to move {src} into destination: {e}")

    # Clean up temporary directory (ignore errors)
    try:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass

    # Prune destination folder to only keep final_files
    if final_files:
        keep_set = {os.path.normcase(p) for p in final_files}
        removed = 0
        for entry in os.scandir(destinationFolder):
            if entry.is_file():
                ap = os.path.normcase(os.path.abspath(entry.path))
                if ap not in keep_set:
                    try:
                        os.remove(entry.path)
                        removed += 1
                    except Exception as e:
                        print(f"Could not remove stale file '{entry.name}': {e}")
        if removed:
            print(f"Pruned {removed} old file(s) from destination folder.")
        else:
            print("No old files to prune in destination folder.")
    else:
        print("No images successfully processed; destination unchanged.")

    return bool(final_files)


def run_once_wrapper(args):
    """Wrapper to run once with proper output handling."""
    if os.name == "nt" and not args.no_clear:
        os.system("cls")
    elif not args.no_clear:
        os.system("clear")
    print("===== Manual Run =====")
    start = time.time()
    success = run_once()
    duration = time.time() - start
    print(f"Manual run {'succeeded' if success else 'completed'} in {duration:.1f}s")


def wallpaper_loop(args):
    """Main wallpaper fetching loop."""
    global running
    run_number = 0
    while running:
        run_number += 1
        if os.name == "nt" and not args.no_clear:
            os.system("cls")
        elif not args.no_clear:
            os.system("clear")
        print(f"===== Run #{run_number} =====")
        start = time.time()
        success = run_once()
        duration = time.time() - start
        print(f"Run #{run_number} {'succeeded' if success else 'completed'} in {duration:.1f}s")
        if not running:
            break
        sleep_for = max(0, args.interval - duration)
        print(f"Sleeping {sleep_for:.1f}s (next run approx at {datetime.now() + timedelta(seconds=sleep_for):%H:%M:%S})")
        try:
            time.sleep(sleep_for)
        except KeyboardInterrupt:
            print("Interrupted. Exiting loop.")
            break


def main():
    parser = argparse.ArgumentParser(description="UltraWideWallpapers fetcher loop")
    parser.add_argument("--interval", type=int, default=600, help="Interval between runs in seconds (default 600)")
    parser.add_argument("--once", action="store_true", help="Run only once then exit")
    parser.add_argument("--no-clear", action="store_true", help="Do not clear the console at start of each run")
    args = parser.parse_args()

    # Global flag to control the loop
    global running
    running = True

    def run_now(icon, item):
        """Run wallpaper fetch immediately."""
        threading.Thread(target=run_once_wrapper, args=(args,), daemon=True).start()

    def exit_app(icon, item):
        """Exit the application."""
        global running
        running = False
        icon.stop()

    # Create tray icon
    icon = pystray.Icon("uww-net", create_icon(), "UltraWideWallpapers")
    icon.menu = pystray.Menu(
        pystray.MenuItem("Run Now", run_now),
        pystray.MenuItem("Exit", exit_app)
    )

    # Start the wallpaper loop in a separate thread
    if not args.once:
        loop_thread = threading.Thread(target=wallpaper_loop, args=(args,), daemon=True)
        loop_thread.start()

    # Run tray icon (this will block until exit)
    icon.run()

    # If once mode, run once before starting tray
    if args.once:
        run_once_wrapper(args)


if __name__ == "__main__":
    from datetime import timedelta  # local import for clarity
    main()