from dataclasses import asdict

from monitors import gather_monitors
from wallpaper_scraper import get_one_wallpaper_after_shuffle

# To run the program:
if __name__ == "__main__":
    # 0. Monitor information at startup
    monitors_list = gather_monitors()
    if monitors_list:
        print("Detected monitors (startup):")
        for m in monitors_list:
            d = asdict(m)
            d["aspect_ratio"] = m.aspect_ratio
            d["aspect_ratio_float"] = m.aspect_ratio_float
            print(" - ", d)
    else:
        print("No monitor information could be gathered.")

    data = get_one_wallpaper_after_shuffle()
    if data:
        print("\nSuccessfully extracted data for one wallpaper after shuffle:")
        print(data)
    else:
        print("\nFailed to extract wallpaper data.")