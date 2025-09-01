"""Selenium based wallpaper scraping helpers."""
from __future__ import annotations

import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from image_utils import fetch_image_dimensions, simplify_ratio

def get_one_wallpaper_after_shuffle() -> dict | None:
    """Fetch one wallpaper after pressing the shuffle button.

    Verbose Chromium / GCM auth errors (PHONE_REGISTRATION_ERROR, wrong_secret, etc.)
    are suppressed via Chrome options & service log redirection.
    """
    # Suppress noisy Chrome / GCM logs
    import os
    if os.name == "nt":  # Windows null device
        os.environ.setdefault("CHROME_LOG_FILE", "NUL")
    else:
        os.environ.setdefault("CHROME_LOG_FILE", "/dev/null")

    chrome_options = Options()
    # 0=ALL, 1=INFO, 2=WARNING, 3=ERROR (actually FATAL). We choose 3 to hide most stuff.
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-logging")
    # Remove the typical 'enable-logging' switch Selenium injects that causes extra stderr.
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])  # type: ignore[arg-type]
    # (Optional) could further reduce by disabling notifications / GCM, uncomment if needed:
    # chrome_options.add_argument("--disable-notifications")
    # chrome_options.add_argument("--disable-gcm-registration")

    # Direct chromedriver's own logs to null
    service = Service(log_path="NUL" if os.name == "nt" else "/dev/null")

    driver = webdriver.Chrome(options=chrome_options, service=service)
    try:
        driver.get("https://ultrawidewallpapers.net/gallery")
        print("Navigated to gallery page.")
        try:
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "#galleryContainer .image-link"))
            )
            shuffle_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#shuffleButton"))
            )
            shuffle_button.click()
            time.sleep(2)
            print("Content likely reloaded after shuffle.")
        except Exception as e:
            print(f"Could not find or click the shuffle button: {e}")
            return None
        try:
            wallpaper_elements = driver.find_elements(By.CSS_SELECTOR, "#galleryContainer .image-link")
            if not wallpaper_elements:
                print("No wallpapers found after shuffle.")
                return None
            first_wallpaper_element = wallpaper_elements[0]
            print("Found the first wallpaper element.")
            image_url = first_wallpaper_element.get_attribute("href")
            width, height = fetch_image_dimensions(image_url)
            aspect_ratio = simplify_ratio(width, height)
            return {
                "image_url": image_url,
                "width": width,
                "height": height,
                "aspect_ratio": aspect_ratio,
                "aspect_ratio_float": round(width / height, 4) if width and height else None,
            }
        except Exception as e:
            print(f"Error extracting data from the first wallpaper: {e}")
            return None
    finally:
        driver.quit()


__all__ = ["get_one_wallpaper_after_shuffle"]
