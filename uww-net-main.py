from dataclasses import asdict
import os

from monitors import gather_monitors
from wallpaper_scraper import get_wallpapers_after_shuffle

# To run the program:
if __name__ == "__main__":
    # 0. Monitor information at startup
    # clean terminal
    os.system("cls" if os.name == "nt" else "clear")
    monitors_list = gather_monitors()
    monitor_count = len(monitors_list)
    print(f"Detected {monitor_count} monitor(s).")
    wallpapers = get_wallpapers_after_shuffle(monitor_count)
    if wallpapers and len(wallpapers) == monitor_count:
        print(f"\nSuccessfully extracted {len(wallpapers)} wallpapers (one per monitor):")
    elif wallpapers:
        print(f"\nExtracted {len(wallpapers)} wallpapers (requested {monitor_count}).")
    else:
        print("\nFailed to extract any wallpaper data.")
    for idx, wp in enumerate(wallpapers, start=1):
        print(f"Wallpaper {idx}: {wp}")