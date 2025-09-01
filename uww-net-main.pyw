from dataclasses import asdict
import os

from monitors import gather_monitors
from wallpaper_scraper import get_wallpapers_after_shuffle
from image_utils import ensure_dependencies, download_image, crop_image_to_aspect

destinationFolder = "C:\\media\\wallpapers"

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

    # 1. Download wallpapers if we have any
    if wallpapers:
        try:
            ensure_dependencies()
        except RuntimeError as dep_err:
            print(f"Cannot download images (missing deps): {dep_err}")
        else:
            import tempfile, shutil
            tmp_dir = tempfile.mkdtemp(prefix="uww_dl_")
            print(f"\nDownloading {len(wallpapers)} image(s) to temporary folder {tmp_dir} ...")
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

            # Crop each downloaded image to 16:9 (center crop)
            cropped_files: list[str] = []
            for path in tmp_files:
                cropped = crop_image_to_aspect(path, 16, 9, inplace=True)
                if cropped:
                    cropped_files.append(cropped)
                else:
                    print(f"Skipping move for image that failed to crop: {path}")

            # Move cropped images into destination folder
            os.makedirs(destinationFolder, exist_ok=True)
            final_files: list[str] = []
            for src in cropped_files:
                try:
                    fname = os.path.basename(src)
                    dest_path = os.path.join(destinationFolder, fname)
                    # If a file with same name exists, overwrite (we prune anyway)
                    shutil.move(src, dest_path)
                    final_files.append(os.path.abspath(dest_path))
                except Exception as e:
                    print(f"Failed to move {src} into destination: {e}")

            # Clean up temporary directory (ignore errors)
            try:
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