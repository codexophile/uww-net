from dataclasses import asdict
import os

from monitors import gather_monitors
from wallpaper_scraper import get_one_wallpaper_after_shuffle

# To run the program:
if __name__ == "__main__":
    # 0. Monitor information at startup
    # clean terminal
    os.system("cls" if os.name == "nt" else "clear")
    monitors_list = gather_monitors()
    data = get_one_wallpaper_after_shuffle()
    if data:
        print("\nSuccessfully extracted data for one wallpaper after shuffle:")
        print(data)
    else:
        print("\nFailed to extract wallpaper data.")