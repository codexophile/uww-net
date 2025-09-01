from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import math
from io import BytesIO

try:
    import requests
    from PIL import Image
except ImportError:
    # Lazy import guard: user may not have dependencies yet.
    requests = None
    Image = None

def _ensure_deps():
    if requests is None or Image is None:
        raise RuntimeError("Missing dependencies. Install with: pip install requests Pillow")

def _fetch_image_dimensions(image_url: str):
    """Download the image (stream) and return (width, height).

    Falls back to (None, None) on failure.
    """
    try:
        _ensure_deps()
        resp = requests.get(image_url, timeout=15)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        width, height = img.size
        return width, height
    except Exception as e:
        print(f"Failed to obtain image dimensions: {e}")
        return None, None

def _simplify_ratio(width: int, height: int):
    if not width or not height:
        return None
    g = math.gcd(width, height)
    return f"{width // g}:{height // g}"

def get_one_wallpaper_after_shuffle():
    # Initialize the WebDriver (e.g., Chrome)
    # Ensure ChromeDriver is set up correctly (see previous instructions).
    driver = webdriver.Chrome()
    # For headless mode (no browser window visible):
    # from selenium.webdriver.chrome.options import Options
    # options = Options()
    # options.add_argument('--headless')
    # driver = webdriver.Chrome(options=options)


    try:
        # 1. Navigate to the gallery page
        driver.get("https://ultrawidewallpapers.net/gallery")
        print("Navigated to gallery page.")

        # 2. Locate and click the "Shuffle" button
        try:
            shuffle_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#shuffleButton"))
            )
            shuffle_button.click()

            time.sleep(2) 
            print("Content likely reloaded after shuffle.")

        except Exception as e:
            print(f"Could not find or click the shuffle button: {e}")
            return None # Exit if shuffle fails

        # 3. Extract data from the first newly loaded wallpaper
        try:
            # Find all wallpaper elements
            wallpaper_elements = driver.find_elements(By.CSS_SELECTOR, "#galleryContainer .image-link")

            if not wallpaper_elements:
                print("No wallpapers found after shuffle.")
                return None

            # Get the first wallpaper element
            first_wallpaper_element = wallpaper_elements[0]
            print("Found the first wallpaper element.")

            # Extract details from the first wallpaper
            image_url = first_wallpaper_element.get_attribute("href")

            width, height = _fetch_image_dimensions(image_url)
            aspect_ratio = _simplify_ratio(width, height) if width and height else None

            wallpaper_info = {
                "image_url": image_url,
                "width": width,
                "height": height,
                "aspect_ratio": aspect_ratio,
                "aspect_ratio_float": round(width / height, 4) if width and height else None,
            }

            return wallpaper_info

        except Exception as e:
            print(f"Error extracting data from the first wallpaper: {e}")
            return None

    finally:
        driver.quit() # Close the browser

# To run the program:
if __name__ == "__main__":
    wallpaper_data = get_one_wallpaper_after_shuffle()
    if wallpaper_data:
        print("\nSuccessfully extracted data for one wallpaper after shuffle:")
        print(wallpaper_data)
    else:
        print("\nFailed to extract wallpaper data.")