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

def get_unique_wallpapers(
    count: int,
    skip_urls: set[str] | None = None,
    verbose: bool = True,
    max_shuffles: int = 25,
) -> list[dict]:
    """Fetch up to ``count`` wallpapers whose URLs are not in ``skip_urls``.

    This function keeps a single Selenium session open and presses the shuffle
    button repeatedly (up to ``max_shuffles``) until it accumulates the desired
    number of new / unseen wallpapers or exhausts attempts.

    Returns a (possibly smaller) list of wallpaper dicts with the same schema as
    ``get_wallpapers_after_shuffle``.
    """
    if count <= 0:
        return []
    skip_urls = skip_urls or set()
    driver = _init_driver()
    collected: list[dict] = []
    try:
        driver.get("https://ultrawidewallpapers.net/gallery")
        if verbose:
            print("Navigated to gallery page (unique mode).")
        try:
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "#galleryContainer .image-link"))
            )
        except Exception as e:
            if verbose:
                print(f"Initial gallery load failed: {e}")
            return []

        attempts = 0
        while len(collected) < count and attempts < max_shuffles:
            # Always click shuffle (including first attempt) to ensure fresh set
            try:
                shuffle_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#shuffleButton"))
                )
                shuffle_button.click()
                time.sleep(2)
            except Exception as e:
                if verbose:
                    print(f"Shuffle attempt {attempts+1} failed: {e}")
                break
            attempts += 1
            try:
                wallpaper_elements = driver.find_elements(By.CSS_SELECTOR, "#galleryContainer .image-link")
            except Exception as e:
                if verbose:
                    print(f"Failed to enumerate wallpaper elements: {e}")
                break
            for el in wallpaper_elements:
                if len(collected) >= count:
                    break
                try:
                    image_url = el.get_attribute("href")
                    if not image_url or image_url in skip_urls or any(r.get("image_url") == image_url for r in collected):
                        continue
                    width, height = fetch_image_dimensions(image_url, verbose)
                    aspect_ratio = simplify_ratio(width, height)
                    collected.append(
                        {
                            "image_url": image_url,
                            "width": width,
                            "height": height,
                            "aspect_ratio": aspect_ratio,
                            "aspect_ratio_float": round(width / height, 4) if width and height else None,
                        }
                    )
                    if verbose:
                        print(f"Collected unique wallpaper {len(collected)}/{count}")
                except Exception as inner_e:
                    if verbose:
                        print(f"Failed extracting a wallpaper element: {inner_e}")
            # If we didn't gain any new images this attempt, continue to next shuffle
        if verbose and len(collected) < count:
            print(f"Only gathered {len(collected)}/{count} unique wallpapers after {attempts} attempt(s).")
        return collected
    finally:
        driver.quit()

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
    try:
        chrome_options.add_argument("--headless=new")
    except:
        # Fallback to old headless mode if new one fails
        chrome_options.add_argument("--headless")
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
    # Essential option to disable DevTools remote debugging
    chrome_options.add_argument("--remote-debugging-port=0")  # Disable remote debugging

    # Direct chromedriver's own logs to null
    service = Service(log_path=os.devnull if hasattr(os, 'devnull') else ("NUL" if os.name == "nt" else "/dev/null"))
    
    # Try to suppress any remaining output
    import sys
    from contextlib import redirect_stderr, redirect_stdout
    
    try:
        with redirect_stdout(open(os.devnull, 'w')), redirect_stderr(open(os.devnull, 'w')):
            driver = webdriver.Chrome(options=chrome_options, service=service)
            return driver
    except Exception as e:
        # If redirection fails, try without it
        try:
            driver = webdriver.Chrome(options=chrome_options, service=service)
            return driver
        except Exception as e2:
            # If that also fails, provide a helpful error message
            raise RuntimeError(f"Failed to create Chrome WebDriver. Please ensure Chrome is installed and up to date. Error: {e2}") from e2


def get_wallpapers_after_shuffle(count: int, verbose: bool = True) -> list[dict]:
    """Fetch up to `count` wallpapers after pressing shuffle once.

    Returns a list with length 0..count. Each entry is same schema as
    ``get_one_wallpaper_after_shuffle``.
    """
    if count <= 0:
        return []
    driver = _init_driver()
    try:
        driver.get("https://ultrawidewallpapers.net/gallery")
        if verbose:
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
            if verbose:
                print("Content likely reloaded after shuffle.")
        except Exception as e:
            if verbose:
                print(f"Could not find or click the shuffle button: {e}")
            return []

        try:
            wallpaper_elements = driver.find_elements(By.CSS_SELECTOR, "#galleryContainer .image-link")
            if not wallpaper_elements:
                if verbose:
                    print("No wallpapers found after shuffle.")
                return []
            selected = wallpaper_elements[:count]
            results: list[dict] = []
            for idx, el in enumerate(selected, start=1):
                try:
                    image_url = el.get_attribute("href")
                    width, height = fetch_image_dimensions(image_url, verbose)
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
                    if verbose:
                        print(f"Collected wallpaper {idx}/{len(selected)}")
                except Exception as inner_e:  # continue gathering others
                    if verbose:
                        print(f"Failed to extract one wallpaper element: {inner_e}")
            return results
        except Exception as e:
            if verbose:
                print(f"Error extracting wallpapers: {e}")
            return []
    finally:
        driver.quit()

__all__ = ["get_wallpapers_after_shuffle", "get_unique_wallpapers"]
