from dataclasses import asdict
import os
import time
import argparse
from datetime import datetime, timedelta
import threading
import pystray
from PIL import Image, ImageDraw
import ctypes
from ctypes import wintypes
import json

from monitors import gather_monitors, MonitorInfo
from wallpaper_scraper import get_wallpapers_after_shuffle, get_unique_wallpapers
from image_utils import ensure_dependencies, download_image, crop_image_to_aspect, set_wallpaper, stitch_images_for_monitors, is_image_too_bright
from download_history import load_history, append_history

# Load configuration
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"Config file not found at {config_path}. Using default values.")
    config = {
        "destination_folder": "C:\\media\\wallpapers",
        "verbose_logging": True,
        "interval_seconds": 600,
        "aspect_ratio": {"width": 16, "height": 9},
        "temp_dir_prefix": "uww_dl_",
        "history_file": "download_history.txt",
        "brightness_threshold": 200.0,
        "wallpaper_source": {
            "url": "https://ultrawidewallpapers.net/gallery",
            "max_shuffles": 25,
            "webdriver_timeout": 10,
            "shuffle_timeout": 5,
            "window_size": "1920,1080"
        },
        "stitch_wallpapers": False,
        "stitched_wallpaper_filename": "stitched_wallpaper.jpg"
    }
except json.JSONDecodeError as e:
    print(f"Error parsing config file: {e}. Using default values.")
    config = {
        "destination_folder": "C:\\media\\wallpapers",
        "verbose_logging": True,
        "interval_seconds": 600,
        "aspect_ratio": {"width": 16, "height": 9},
        "temp_dir_prefix": "uww_dl_",
        "history_file": "download_history.txt",
        "brightness_threshold": 200.0,
        "wallpaper_source": {
            "url": "https://ultrawidewallpapers.net/gallery",
            "max_shuffles": 25,
            "webdriver_timeout": 10,
            "shuffle_timeout": 5,
            "window_size": "1920,1080"
        },
        "stitch_wallpapers": False,
        "stitched_wallpaper_filename": "stitched_wallpaper.jpg"
    }

# Windows API constants and functions for console manipulation
SW_HIDE = 0
SW_SHOW = 5
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
user32 = ctypes.WinDLL('user32', use_last_error=True)
GetConsoleWindow = kernel32.GetConsoleWindow
GetConsoleWindow.restype = wintypes.HWND
ShowWindow = user32.ShowWindow
ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
AllocConsole = kernel32.AllocConsole
AllocConsole.restype = wintypes.BOOL
SetStdHandle = kernel32.SetStdHandle
SetStdHandle.argtypes = [ctypes.c_int, wintypes.HANDLE]
STD_OUTPUT_HANDLE = -11
STD_ERROR_HANDLE = -12

# Global flag to control the wallpaper loop
running = True

# Global flag for console visibility
console_visible = False

# Global flag for verbose logging
verbose_logging = config["verbose_logging"]

destinationFolder = config["destination_folder"]


def log_print(*args, **kwargs):
    """Print function that respects the verbose_logging flag."""
    if verbose_logging:
        print(*args, **kwargs)


def create_icon():
    """Create a simple tray icon."""
    # Create a 64x64 icon
    img = Image.new('RGB', (64, 64), color='blue')
    draw = ImageDraw.Draw(img)
    # Draw a simple wallpaper-like pattern (stripes)
    for i in range(0, 64, 8):
        draw.rectangle([i, 0, i+4, 64], fill='white')
    return img


def toggle_console(icon, item):
    """Toggle the visibility of the console window."""
    global console_visible
    hwnd = GetConsoleWindow()
    if hwnd:
        if console_visible:
            ShowWindow(hwnd, SW_HIDE)
            console_visible = False
        else:
            ShowWindow(hwnd, SW_SHOW)
            console_visible = True


def toggle_verbose_logging(icon, item):
    """Toggle verbose logging on/off."""
    global verbose_logging
    verbose_logging = not verbose_logging
    status = "enabled" if verbose_logging else "disabled"
    if verbose_logging:
        print(f"Verbose logging {status}")  # Always print this status change


def toggle_wallpaper_stitching(icon, item):
    """Toggle wallpaper stitching on/off."""
    global config
    current_state = config.get("stitch_wallpapers", False)
    config["stitch_wallpapers"] = not current_state
    status = "enabled" if config["stitch_wallpapers"] else "disabled"
    if verbose_logging:
        print(f"Wallpaper stitching {status}")
    # Save the updated config to file
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        if verbose_logging:
            print("Configuration saved.")
    except Exception as e:
        if verbose_logging:
            print(f"Failed to save configuration: {e}")


def run_once() -> bool:
    """Run a single wallpaper fetch / download cycle.

    Returns True if at least one image processed successfully, else False.
    """
    monitors_list = gather_monitors(verbose_logging)
    monitor_count = len(monitors_list)
    log_print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Detected {monitor_count} monitor(s).")
    # Load history early so we can request unique wallpapers
    os.makedirs(destinationFolder, exist_ok=True)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    history_file = os.path.join(script_dir, config["history_file"])
    downloaded_history = load_history(history_file)

    if downloaded_history:
        log_print(f"Loaded download history with {len(downloaded_history)} entries.")
    else:
        log_print("No prior download history (starting fresh).")

    # Attempt to get unique wallpapers (fallback to basic shuffle if zero returned)
    wallpapers = get_unique_wallpapers(
        monitor_count, 
        skip_urls=downloaded_history, 
        verbose=verbose_logging, 
        max_shuffles=config["wallpaper_source"]["max_shuffles"],
        url=config["wallpaper_source"]["url"],
        webdriver_timeout=config["wallpaper_source"]["webdriver_timeout"],
        window_size=config["wallpaper_source"]["window_size"],
        shuffle_timeout=config["wallpaper_source"]["shuffle_timeout"]
    )
    if not wallpapers:
        wallpapers = get_wallpapers_after_shuffle(
            monitor_count, 
            verbose_logging,
            config["wallpaper_source"]["url"],
            config["wallpaper_source"]["webdriver_timeout"],
            config["wallpaper_source"]["window_size"]
        )
    if wallpapers and len(wallpapers) == monitor_count:
        log_print(f"Successfully extracted {len(wallpapers)} wallpapers (one per monitor).")
    elif wallpapers:
        log_print(f"Extracted {len(wallpapers)} wallpapers (requested {monitor_count}).")
    else:
        log_print("Failed to extract any wallpaper data.")
    for idx, wp in enumerate(wallpapers, start=1):
        log_print(f"Wallpaper {idx}: {wp}")

    if not wallpapers:
        return False

    try:
        ensure_dependencies()
    except RuntimeError as dep_err:
        log_print(f"Cannot download images (missing deps): {dep_err}")
        return False

    import tempfile, shutil
    # Load persistent history of previously downloaded image URLs
    # downloaded_history already loaded above
    tmp_dir = tempfile.mkdtemp(prefix=config["temp_dir_prefix"])
    log_print(f"Downloading {len(wallpapers)} image(s) to temporary folder {tmp_dir} ...")
    tmp_files: list[str] = []
    url_for_file: dict[str, str] = {}
    for idx, wp in enumerate(wallpapers, start=1):
        url = wp.get("image_url")
        if not url:
            log_print(f"Wallpaper {idx} missing image_url, skipping.")
            continue
        if url in downloaded_history:
            log_print(f"Skipping already-downloaded image (#{idx}): {url}")
            continue
        saved_path = download_image(url, tmp_dir, verbose=verbose_logging)
        if saved_path:
            log_print(f"Downloaded wallpaper {idx} -> {saved_path}")
            tmp_files.append(saved_path)
            url_for_file[saved_path] = url
        else:
            log_print(f"Failed to download wallpaper {idx}")

    cropped_files: list[str] = []
    for path in tmp_files:
        cropped = crop_image_to_aspect(path, config["aspect_ratio"]["width"], config["aspect_ratio"]["height"], inplace=True, verbose=verbose_logging)
        if cropped:
            cropped_files.append(cropped)
        else:
            log_print(f"Skipping move for image that failed to crop: {path}")

    # Filter out too-bright images
    brightness_threshold = config.get("brightness_threshold", 200.0)
    filtered_files: list[str] = []
    for path in cropped_files:
        if is_image_too_bright(path, brightness_threshold=brightness_threshold, verbose=verbose_logging):
            log_print(f"Skipping bright image: {os.path.basename(path)}")
            try:
                os.remove(path)
            except Exception:
                pass
        else:
            filtered_files.append(path)

    if not filtered_files:
        log_print("All images were too bright; skipping wallpaper update.")
        # Clean up temporary directory (ignore errors)
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        return False


    os.makedirs(destinationFolder, exist_ok=True)
    final_files: list[str] = []
    newly_downloaded_urls: list[str] = []
    for src in filtered_files:
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
            # Map back to URL and add to history list if we have one
            original_url = url_for_file.get(src)
            if original_url:
                newly_downloaded_urls.append(original_url)
        except Exception as e:
            log_print(f"Failed to move {src} into destination: {e}")

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
                        log_print(f"Could not remove stale file '{entry.name}': {e}")
        if removed:
            log_print(f"Pruned {removed} old file(s) from destination folder.")
        else:
            log_print("No old files to prune in destination folder.")
    else:
        log_print("No images successfully processed; destination unchanged.")

    # Persist history updates (only after successful processing)
    if newly_downloaded_urls:
        append_history(history_file, newly_downloaded_urls)
        log_print(f"Recorded {len(newly_downloaded_urls)} new image URL(s) to history.")
    else:
        log_print("No new images were added to history this run.")

    # Set wallpaper if we have successfully processed images
    if final_files:
        if config.get("stitch_wallpapers", False):
            # Stitch images into a single wallpaper
            stitched_path = os.path.join(destinationFolder, config.get("stitched_wallpaper_filename", "stitched_wallpaper.jpg"))
            stitched_result = stitch_images_for_monitors(final_files, monitors_list, stitched_path, verbose_logging)
            if stitched_result:
                wallpaper_set = set_wallpaper(stitched_result, verbose_logging)
                if wallpaper_set:
                    log_print("Successfully set stitched wallpaper as system wallpaper.")
                else:
                    log_print("Failed to set stitched wallpaper as system wallpaper.")
            else:
                log_print("Failed to create stitched wallpaper.")
        else:
            # Original behavior: set the first image as wallpaper (or could implement per-monitor setting)
            if final_files:
                wallpaper_set = set_wallpaper(final_files[0], verbose_logging)
                if wallpaper_set:
                    log_print(f"Successfully set wallpaper to: {os.path.basename(final_files[0])}")
                else:
                    log_print("Failed to set wallpaper.")

    return bool(final_files)


def run_once_wrapper(args):
    """Wrapper to run once with proper output handling."""
    if os.name == "nt" and not args.no_clear:
        os.system("cls")
    elif not args.no_clear:
        os.system("clear")
    log_print("===== Manual Run =====")
    start = time.time()
    success = run_once()
    duration = time.time() - start
    log_print(f"Manual run {'succeeded' if success else 'completed'} in {duration:.1f}s")


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
        log_print(f"===== Run #{run_number} =====")
        start = time.time()
        try:
            success = run_once()
            duration = time.time() - start
            log_print(f"Run #{run_number} {'succeeded' if success else 'completed'} in {duration:.1f}s")
        except TimeoutError as e:
            duration = time.time() - start
            log_print(f"Run #{run_number} timed out after {duration:.1f}s: {e}")
            log_print("Will retry on next cycle.")
        except Exception as e:
            duration = time.time() - start
            log_print(f"Run #{run_number} encountered an error after {duration:.1f}s: {type(e).__name__}: {e}")
            log_print("Will retry on next cycle.")
        
        if not running:
            break
        sleep_for = max(0, args.interval - duration)
        log_print(f"Sleeping {sleep_for:.1f}s (next run approx at {datetime.now() + timedelta(seconds=sleep_for):%H:%M:%S})")
        try:
            time.sleep(sleep_for)
        except KeyboardInterrupt:
            log_print("Interrupted. Exiting loop.")
            break


def main():
    # Allocate console for Windows
    if os.name == "nt":
        import sys
        import subprocess
        
        # Allocate a new console
        kernel32.AllocConsole()
        
        # Get the console handle
        hwnd = GetConsoleWindow()
        
        # Redirect stdout and stderr to the console using a more reliable method
        try:
            # Use subprocess to handle the redirection properly
            import io
            
            # Create console output streams
            console_out = io.TextIOWrapper(
                open('CONOUT$', 'wb', buffering=0), 
                encoding='utf-8', 
                write_through=True,
                line_buffering=True
            )
            console_err = io.TextIOWrapper(
                open('CONOUT$', 'wb', buffering=0), 
                encoding='utf-8', 
                write_through=True,
                line_buffering=True
            )
            
            # Replace stdout and stderr
            sys.stdout = console_out
            sys.stderr = console_err
            
        except Exception as e:
            # If redirection fails, try a simpler approach
            try:
                sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
                sys.stderr = open('CONOUT$', 'w', encoding='utf-8')
            except:
                pass
        
        # Initially hide the console
        if hwnd:
            ShowWindow(hwnd, SW_HIDE)
    
    parser = argparse.ArgumentParser(description="UltraWideWallpapers fetcher loop")
    parser.add_argument("--interval", type=int, default=config["interval_seconds"], help=f"Interval between runs in seconds (default {config['interval_seconds']})")
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

    def restart_app(icon, item):
        """Restart the whole script with original arguments."""
        import sys, subprocess
        global running
        running = False
        # Build command: current interpreter + current script + original args (excluding any leading path modifications)
        script_path = os.path.abspath(__file__)
        cmd = [sys.executable, script_path] + sys.argv[1:]
        try:
            subprocess.Popen(cmd, close_fds=False)
        except Exception as e:
            print(f"Failed to restart: {e}")
            return
        # Stop tray icon then terminate current process
        icon.stop()
        os._exit(0)

    # Create tray icon
    icon = pystray.Icon("uww-net", create_icon(), "UltraWideWallpapers")
    icon.menu = pystray.Menu(
        pystray.MenuItem("Run Now", run_now),
        pystray.MenuItem("Toggle Console", toggle_console),
        pystray.MenuItem("Toggle Logging", toggle_verbose_logging),
        pystray.MenuItem("Toggle Wallpaper Stitching", toggle_wallpaper_stitching),
        pystray.MenuItem("Restart", restart_app),
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