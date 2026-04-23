from dataclasses import asdict
import os
import time
import argparse
import copy
from datetime import datetime, timedelta
import threading
import pystray
from PIL import Image, ImageDraw
import ctypes
from ctypes import wintypes
import json

from monitors import gather_monitors, MonitorInfo
from wallpaper_scraper import get_wallpapers_after_shuffle, get_unique_wallpapers
from image_utils import ensure_dependencies, download_image, crop_image_to_aspect, set_wallpaper, stitch_images_for_monitors, is_image_too_bright, build_image_request_headers
from download_history import load_history, append_history

# Load configuration
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")
DEFAULT_CONFIG = {
    "destination_folder": "C:\\media\\wallpapers",
    "verbose_logging": True,
    "headless_mode": True,
    "interval_seconds": 600,
    "aspect_ratio": {"width": 16, "height": 9},
    "temp_dir_prefix": "uww_dl_",
    "history_file": "download_history.txt",
    "brightness_threshold": 200.0,
    "replacement_attempts": 3,
    "wallpaper_source": {
        "url": "https://ultrawidewallpapers.net/gallery?lang=en",
        "max_shuffles": 25,
        "webdriver_timeout": 10,
        "shuffle_timeout": 5,
        "window_size": "1920,1080",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    },
    "storage": {
        "parent_folder": "C:\\media\\wallpapers",
        "originals_subfolder": "originals",
        "cropped_subfolder": "cropped",
        "stitched_subfolder": "stitched",
        "max_originals": 50,
        "max_cropped": 50,
        "max_stitched": 1
    },
    "stitch_wallpapers": False,
    "stitched_wallpaper_filename": "stitched_wallpaper.jpg"
}
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"Config file not found at {config_path}. Using default values.")
    config = copy.deepcopy(DEFAULT_CONFIG)
except json.JSONDecodeError as e:
    print(f"Error parsing config file: {e}. Using default values.")
    config = copy.deepcopy(DEFAULT_CONFIG)

# Windows API constants and functions for console manipulation
SW_HIDE = 0
SW_SHOW = 5
CTRL_CLOSE_EVENT = 2
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

# Console event handler
HandlerRoutine = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
SetConsoleCtrlHandler = kernel32.SetConsoleCtrlHandler
SetConsoleCtrlHandler.argtypes = [HandlerRoutine, wintypes.BOOL]
SetConsoleCtrlHandler.restype = wintypes.BOOL

# Global flag to control the wallpaper loop
running = True

# Global flag for console visibility
console_visible = False

# Global flag for verbose logging
verbose_logging = config["verbose_logging"]
config.setdefault("destination_folder", DEFAULT_CONFIG["destination_folder"])
config.setdefault("headless_mode", True)
config.setdefault("replacement_attempts", DEFAULT_CONFIG["replacement_attempts"])
config.setdefault("wallpaper_source", {})
config["wallpaper_source"].setdefault(
    "user_agent",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)
config["wallpaper_source"].setdefault("url", DEFAULT_CONFIG["wallpaper_source"]["url"])
config["wallpaper_source"].setdefault("max_shuffles", DEFAULT_CONFIG["wallpaper_source"]["max_shuffles"])
config["wallpaper_source"].setdefault("webdriver_timeout", DEFAULT_CONFIG["wallpaper_source"]["webdriver_timeout"])
config["wallpaper_source"].setdefault("shuffle_timeout", DEFAULT_CONFIG["wallpaper_source"]["shuffle_timeout"])
config["wallpaper_source"].setdefault("window_size", DEFAULT_CONFIG["wallpaper_source"]["window_size"])
config.setdefault("storage", {})
config["storage"].setdefault("parent_folder", config.get("destination_folder", DEFAULT_CONFIG["storage"]["parent_folder"]))
config["storage"].setdefault("originals_subfolder", DEFAULT_CONFIG["storage"]["originals_subfolder"])
config["storage"].setdefault("cropped_subfolder", DEFAULT_CONFIG["storage"]["cropped_subfolder"])
config["storage"].setdefault("stitched_subfolder", DEFAULT_CONFIG["storage"]["stitched_subfolder"])
config["storage"].setdefault("max_originals", DEFAULT_CONFIG["storage"]["max_originals"])
config["storage"].setdefault("max_cropped", DEFAULT_CONFIG["storage"]["max_cropped"])
config["storage"].setdefault("max_stitched", DEFAULT_CONFIG["storage"]["max_stitched"])


def save_config() -> bool:
    """Persist the current configuration to disk."""
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        if verbose_logging:
            print(f"Failed to save configuration: {e}")
        return False


def log_print(*args, **kwargs):
    """Print function that respects the verbose_logging flag."""
    if verbose_logging:
        print(*args, **kwargs)


def get_storage_paths() -> dict[str, str]:
    """Resolve configured image storage directories."""
    storage_cfg = config.get("storage", {})
    parent = storage_cfg.get("parent_folder") or config.get("destination_folder", DEFAULT_CONFIG["destination_folder"])
    originals = os.path.join(parent, storage_cfg.get("originals_subfolder", "originals"))
    cropped = os.path.join(parent, storage_cfg.get("cropped_subfolder", "cropped"))
    stitched = os.path.join(parent, storage_cfg.get("stitched_subfolder", "stitched"))
    return {
        "parent": parent,
        "originals": originals,
        "cropped": cropped,
        "stitched": stitched,
    }


def prune_folder_to_limit(folder_path: str, max_files: int, protected_paths: set[str] | None = None) -> int:
    """Keep only the newest ``max_files`` files in ``folder_path``."""
    try:
        max_allowed = max(0, int(max_files))
    except Exception:
        max_allowed = 0

    protected_paths = {os.path.normcase(os.path.abspath(p)) for p in (protected_paths or set())}
    file_entries: list[tuple[float, str]] = []
    for entry in os.scandir(folder_path):
        if not entry.is_file():
            continue
        abs_path = os.path.normcase(os.path.abspath(entry.path))
        if abs_path in protected_paths:
            continue
        try:
            mtime = entry.stat().st_mtime
        except Exception:
            mtime = 0.0
        file_entries.append((mtime, entry.path))

    if len(file_entries) <= max_allowed:
        return 0

    file_entries.sort(key=lambda item: item[0], reverse=True)
    to_delete = file_entries[max_allowed:]
    removed = 0
    for _, path in to_delete:
        try:
            os.remove(path)
            removed += 1
        except Exception as e:
            log_print(f"Could not remove stale file '{os.path.basename(path)}': {e}")
    return removed


def create_icon():
    """Create a simple tray icon."""
    # Create a 64x64 icon
    img = Image.new('RGB', (64, 64), color='blue')
    draw = ImageDraw.Draw(img)
    # Draw a simple wallpaper-like pattern (stripes)
    for i in range(0, 64, 8):
        draw.rectangle([i, 0, i+4, 64], fill='white')
    return img


def console_ctrl_handler(ctrl_type):
    """Handle console control events (like clicking the X button)."""
    global console_visible
    if ctrl_type == CTRL_CLOSE_EVENT:
        # Instead of allowing the console to close (which would kill the process),
        # just hide it
        hwnd = GetConsoleWindow()
        if hwnd:
            ShowWindow(hwnd, SW_HIDE)
            console_visible = False
        # Return True to indicate we handled the event (prevents process termination)
        return True
    # Return False for other events to use default handling
    return False


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


def toggle_headless_mode(icon, item):
    """Toggle headless browser mode on/off."""
    global config
    current_state = config.get("headless_mode", True)
    config["headless_mode"] = not current_state
    status = "enabled" if config["headless_mode"] else "disabled"
    if verbose_logging:
        print(f"Headless mode {status}")
    save_config()


def toggle_wallpaper_stitching(icon, item):
    """Toggle wallpaper stitching on/off."""
    global config
    current_state = config.get("stitch_wallpapers", False)
    config["stitch_wallpapers"] = not current_state
    status = "enabled" if config["stitch_wallpapers"] else "disabled"
    if verbose_logging:
        print(f"Wallpaper stitching {status}")
    if save_config() and verbose_logging:
        print("Configuration saved.")


def run_once() -> bool:
    """Run a single wallpaper fetch / download cycle.

    Returns True if at least one image processed successfully, else False.
    """
    monitors_list = gather_monitors(verbose_logging)
    monitor_count = len(monitors_list)
    if monitor_count <= 0:
        log_print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] No monitors detected; skipping run.")
        return False
    log_print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Detected {monitor_count} monitor(s).")
    # Load history early so we can request unique wallpapers
    storage_paths = get_storage_paths()
    os.makedirs(storage_paths["parent"], exist_ok=True)
    os.makedirs(storage_paths["originals"], exist_ok=True)
    os.makedirs(storage_paths["cropped"], exist_ok=True)
    os.makedirs(storage_paths["stitched"], exist_ok=True)
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
        shuffle_timeout=config["wallpaper_source"]["shuffle_timeout"],
        headless=config.get("headless_mode", True),
        browser_user_agent=config["wallpaper_source"].get("user_agent"),
    )
    if not wallpapers:
        wallpapers = get_wallpapers_after_shuffle(
            monitor_count, 
            verbose_logging,
            config["wallpaper_source"]["url"],
            config["wallpaper_source"]["webdriver_timeout"],
            config["wallpaper_source"]["window_size"],
            headless=config.get("headless_mode", True),
            browser_user_agent=config["wallpaper_source"].get("user_agent"),
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
    tmp_dir = tempfile.mkdtemp(prefix=config["temp_dir_prefix"])
    log_print(f"Downloading {len(wallpapers)} image(s) to temporary folder {tmp_dir} ...")

    brightness_threshold = config.get("brightness_threshold", 200.0)
    replacement_attempts = max(0, int(config.get("replacement_attempts", 3)))
    accepted_records: list[dict[str, str]] = []
    attempted_urls: set[str] = set(downloaded_history)
    download_failures = 0
    crop_failures = 0
    bright_rejections = 0

    def process_wallpaper_candidate(wp: dict, label: str) -> bool:
        nonlocal download_failures, crop_failures, bright_rejections
        url = wp.get("image_url")
        if not url:
            log_print(f"{label} missing image_url, skipping.")
            return False
        if url in attempted_urls:
            log_print(f"Skipping already-attempted image ({label}): {url}")
            return False

        attempted_urls.add(url)
        request_headers = build_image_request_headers(url)
        saved_path = download_image(url, tmp_dir, verbose=verbose_logging, request_headers=request_headers)
        if not saved_path:
            download_failures += 1
            log_print(f"Failed to download {label}")
            return False

        cropped = crop_image_to_aspect(
            saved_path,
            config["aspect_ratio"]["width"],
            config["aspect_ratio"]["height"],
            inplace=False,
            verbose=verbose_logging,
        )
        if not cropped:
            crop_failures += 1
            log_print(f"Skipping {label}; crop failed: {saved_path}")
            try:
                os.remove(saved_path)
            except Exception:
                pass
            return False

        if is_image_too_bright(cropped, brightness_threshold=brightness_threshold, verbose=verbose_logging):
            bright_rejections += 1
            log_print(f"Skipping bright image: {os.path.basename(cropped)}")
            try:
                os.remove(cropped)
            except Exception:
                pass
            try:
                os.remove(saved_path)
            except Exception:
                pass
            return False

        accepted_records.append({
            "original_tmp": saved_path,
            "cropped_tmp": cropped,
            "url": url,
        })
        log_print(f"Accepted {label} -> {os.path.basename(cropped)} ({len(accepted_records)}/{monitor_count})")
        return True

    for idx, wp in enumerate(wallpapers, start=1):
        process_wallpaper_candidate(wp, f"wallpaper {idx}")

    if len(accepted_records) < monitor_count:
        log_print(
            f"Need {monitor_count - len(accepted_records)} replacement image(s) after rejections. "
            f"Will try up to {replacement_attempts} refill round(s)."
        )

    refill_round = 0
    while len(accepted_records) < monitor_count and refill_round < replacement_attempts:
        refill_round += 1
        needed = monitor_count - len(accepted_records)
        log_print(f"Refill round {refill_round}/{replacement_attempts}: requesting {needed} replacement image(s).")
        extras = get_unique_wallpapers(
            needed,
            skip_urls=attempted_urls,
            verbose=verbose_logging,
            max_shuffles=config["wallpaper_source"]["max_shuffles"],
            url=config["wallpaper_source"]["url"],
            webdriver_timeout=config["wallpaper_source"]["webdriver_timeout"],
            window_size=config["wallpaper_source"]["window_size"],
            shuffle_timeout=config["wallpaper_source"]["shuffle_timeout"],
            headless=config.get("headless_mode", True),
            browser_user_agent=config["wallpaper_source"].get("user_agent"),
        )
        if not extras:
            extras = get_wallpapers_after_shuffle(
                needed,
                verbose_logging,
                config["wallpaper_source"]["url"],
                config["wallpaper_source"]["webdriver_timeout"],
                config["wallpaper_source"]["window_size"],
                headless=config.get("headless_mode", True),
                browser_user_agent=config["wallpaper_source"].get("user_agent"),
            )
        if not extras:
            log_print("No replacement candidates returned this round.")
            continue

        for extra_idx, wp in enumerate(extras, start=1):
            if len(accepted_records) >= monitor_count:
                break
            process_wallpaper_candidate(wp, f"replacement {refill_round}.{extra_idx}")

    if not accepted_records:
        if bright_rejections > 0 and download_failures == 0 and crop_failures == 0:
            log_print("All images were too bright; skipping wallpaper update.")
        else:
            log_print(
                "No images survived processing; "
                f"download failures={download_failures}, crop failures={crop_failures}, bright rejects={bright_rejections}."
            )
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        return False

    if config.get("stitch_wallpapers", False) and len(accepted_records) < monitor_count:
        log_print(
            f"Only {len(accepted_records)}/{monitor_count} image(s) accepted after refill attempts; "
            "cannot build a stitched wallpaper this cycle."
        )

    final_cropped_files: list[str] = []
    newly_downloaded_urls: list[str] = []
    for record in accepted_records:
        try:
            import shutil
            original_src = record["original_tmp"]
            cropped_src = record["cropped_tmp"]
            original_dest = os.path.join(storage_paths["originals"], os.path.basename(original_src))
            cropped_dest = os.path.join(storage_paths["cropped"], os.path.basename(cropped_src))
            if os.path.exists(original_dest):
                try:
                    os.remove(original_dest)
                except Exception:
                    pass
            if os.path.exists(cropped_dest):
                try:
                    os.remove(cropped_dest)
                except Exception:
                    pass
            shutil.move(original_src, original_dest)
            if os.path.normcase(os.path.abspath(cropped_src)) != os.path.normcase(os.path.abspath(original_src)):
                shutil.move(cropped_src, cropped_dest)
            else:
                shutil.copy2(original_dest, cropped_dest)
            final_cropped_files.append(os.path.abspath(cropped_dest))
            original_url = record.get("url")
            if original_url:
                newly_downloaded_urls.append(original_url)
        except Exception as e:
            log_print(f"Failed to move accepted files into storage folders: {e}")

    # Clean up temporary directory (ignore errors)
    try:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass

    # Prune configured image folders to retention limits.
    if final_cropped_files:
        originals_removed = prune_folder_to_limit(storage_paths["originals"], config["storage"].get("max_originals", 50))
        cropped_removed = prune_folder_to_limit(storage_paths["cropped"], config["storage"].get("max_cropped", 50))
        if originals_removed:
            log_print(f"Pruned {originals_removed} old file(s) from originals folder.")
        if cropped_removed:
            log_print(f"Pruned {cropped_removed} old file(s) from cropped folder.")
        if not originals_removed and not cropped_removed:
            log_print("No old files to prune in originals/cropped folders.")
    else:
        log_print("No images successfully processed; storage folders unchanged.")

    # Persist history updates (only after successful processing)
    if newly_downloaded_urls:
        append_history(history_file, newly_downloaded_urls)
        log_print(f"Recorded {len(newly_downloaded_urls)} new image URL(s) to history.")
    else:
        log_print("No new images were added to history this run.")

    run_success = bool(final_cropped_files)
    stitched_path: str | None = None

    # Set wallpaper if we have successfully processed images
    if final_cropped_files:
        if config.get("stitch_wallpapers", False):
            if len(final_cropped_files) != monitor_count:
                log_print(
                    f"Skipping stitched wallpaper set because accepted image count ({len(final_cropped_files)}) "
                    f"does not match monitor count ({monitor_count})."
                )
                run_success = False
            else:
                # Stitch images into a single wallpaper
                stitched_path = os.path.join(storage_paths["stitched"], config.get("stitched_wallpaper_filename", "stitched_wallpaper.jpg"))
                stitched_result = stitch_images_for_monitors(final_cropped_files, monitors_list, stitched_path, verbose_logging)
                if stitched_result:
                    wallpaper_set = set_wallpaper(stitched_result, verbose_logging)
                    if wallpaper_set:
                        log_print("Successfully set stitched wallpaper as system wallpaper.")
                    else:
                        log_print("Failed to set stitched wallpaper as system wallpaper.")
                    run_success = bool(wallpaper_set)
                else:
                    log_print("Failed to create stitched wallpaper.")
                    run_success = False
        else:
            # Original behavior: set the first image as wallpaper (or could implement per-monitor setting)
            if final_cropped_files:
                wallpaper_set = set_wallpaper(final_cropped_files[0], verbose_logging)
                if wallpaper_set:
                    log_print(f"Successfully set wallpaper to: {os.path.basename(final_cropped_files[0])}")
                else:
                    log_print("Failed to set wallpaper.")
                run_success = bool(wallpaper_set)

    protected = {stitched_path} if stitched_path and os.path.exists(stitched_path) else set()
    stitched_removed = prune_folder_to_limit(
        storage_paths["stitched"],
        config["storage"].get("max_stitched", 1),
        protected_paths=protected,
    )
    if stitched_removed:
        log_print(f"Pruned {stitched_removed} old file(s) from stitched folder.")

    return run_success


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
        
        # Register console event handler to prevent closing the console from terminating the app
        handler = HandlerRoutine(console_ctrl_handler)
        SetConsoleCtrlHandler(handler, True)
    
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
        pystray.MenuItem("Headless Mode", toggle_headless_mode, checked=lambda item: config.get("headless_mode", True)),
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