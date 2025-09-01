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

def _init_driver():
    """Internal helper to create a quiet Chrome webdriver instance."""
    # Suppress noisy Chrome / GCM logs
    import os
    if os.name == "nt":  # Windows null device
        os.environ.setdefault("CHROME_LOG_FILE", "NUL")
    else:
        os.environ.setdefault("CHROME_LOG_FILE", "/dev/null")

    chrome_options = Options()
    # Run fully headless so no Chrome window appears.
    # Use the modern headless implementation (Chrome 109+) for better compatibility.
    # If an older Chrome version is in use, Selenium/Chrome will gracefully fall back.
    chrome_options.add_argument("--headless=new")
    # Helpful stability flags when headless (esp. on Windows / some GPU drivers):
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--disable-crash-reporter")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-in-process-stack-traces")
    chrome_options.add_argument("--disable-logging")  # keep explicit though we also exclude below
    chrome_options.add_argument("--disable-dev-shm-usage")  # robustness in constrained environments
    chrome_options.add_argument("--window-size=1920,1080")  # consistent layout calculations headless
    # 0=ALL, 1=INFO, 2=WARNING, 3=ERROR (actually FATAL). We choose 3 to hide most stuff.
    chrome_options.add_argument("--log-level=3")
    # Remove the typical 'enable-logging' switch Selenium injects that causes extra stderr.
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])  # type: ignore[arg-type]
    # (Optional) could further reduce by disabling notifications / GCM, uncomment if needed:
    # chrome_options.add_argument("--disable-notifications")
    # chrome_options.add_argument("--disable-gcm-registration")

    # Direct chromedriver's own logs to null
    service = Service(log_path="NUL" if os.name == "nt" else "/dev/null")

    return webdriver.Chrome(options=chrome_options, service=service)


def get_wallpapers_after_shuffle(count: int) -> list[dict]:
    """Fetch up to `count` wallpapers after pressing shuffle once.

    Returns a list with length 0..count. Each entry is same schema as
    ``get_one_wallpaper_after_shuffle``.
    """
    if count <= 0:
        return []
    driver = _init_driver()
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
            return []

        try:
            wallpaper_elements = driver.find_elements(By.CSS_SELECTOR, "#galleryContainer .image-link")
            if not wallpaper_elements:
                print("No wallpapers found after shuffle.")
                return []
            selected = wallpaper_elements[:count]
            results: list[dict] = []
            for idx, el in enumerate(selected, start=1):
                try:
                    image_url = el.get_attribute("href")
                    width, height = fetch_image_dimensions(image_url)
                    aspect_ratio = simplify_ratio(width, height)
                    results.append(
                        {
                            "image_url": image_url,
                            "width": width,
                            "height": height,
                            "aspect_ratio": aspect_ratio,
                            "aspect_ratio_float": round(width / height, 4) if width and height else None,
                        }
                    )
                    print(f"Collected wallpaper {idx}/{len(selected)}")
                except Exception as inner_e:  # continue gathering others
                    print(f"Failed to extract one wallpaper element: {inner_e}")
            return results
        except Exception as e:
            print(f"Error extracting wallpapers: {e}")
            return []
    finally:
        driver.quit()

__all__ = ["get_wallpapers_after_shuffle"]
