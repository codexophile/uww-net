"""Selenium based wallpaper scraping helpers."""
from __future__ import annotations

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from image_utils import fetch_image_dimensions, simplify_ratio


def get_one_wallpaper_after_shuffle() -> dict | None:
    driver = webdriver.Chrome()
    try:
        driver.get("https://ultrawidewallpapers.net/gallery")
        print("Navigated to gallery page.")
        try:
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
