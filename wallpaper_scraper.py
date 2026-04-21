"""Selenium based wallpaper scraping helpers."""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from image_utils import fetch_image_dimensions, simplify_ratio, build_image_request_headers

GALLERY_LINK_SELECTORS = (
    "#galleryContainer .image-link",
    "a.image-link[href*='/highres/']",
    "a[href*='/highres/']",
)

SHUFFLE_BUTTON_SELECTORS = (
    "#shuffleButton",
    "button#shuffleButton",
    "button[onclick*='shuffle']",
    "a[onclick*='shuffle']",
    "[data-action='shuffle']",
)

HIGHRES_HREF_REGEX = re.compile(r"href=[\"']([^\"']*/highres/[^\"']+)[\"']", re.IGNORECASE)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
DEFAULT_BROWSER_USER_AGENT = HTTP_HEADERS["User-Agent"]


def _candidate_gallery_urls(url: str) -> list[str]:
    """Build a small set of URL fallbacks to tolerate endpoint drift."""
    primary = (url or "").strip() or "https://ultrawidewallpapers.net/gallery?lang=en"
    variants = [
        primary,
        primary.rstrip("/"),
        "https://ultrawidewallpapers.net/gallery?lang=en",
        "https://www.ultrawidewallpapers.net/gallery?lang=en",
        "https://ultrawidewallpapers.net/gallery",
        "https://www.ultrawidewallpapers.net/gallery",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _find_gallery_links(driver: webdriver.Chrome):
    """Return gallery link elements using fallback selectors."""
    for selector in GALLERY_LINK_SELECTORS:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            continue
        if elements:
            return elements
    return []


def _wait_for_gallery_links(driver: webdriver.Chrome, timeout: int) -> bool:
    """Wait until at least one wallpaper link is present."""
    try:
        WebDriverWait(driver, timeout).until(lambda d: len(_find_gallery_links(d)) > 0)
        return True
    except Exception:
        return False


def _log_page_diagnostics(driver: webdriver.Chrome, verbose: bool, context: str) -> None:
    """Emit compact diagnostics to make Selenium failures actionable."""
    if not verbose:
        return
    try:
        title = driver.title
    except Exception:
        title = "<unavailable>"
    try:
        current_url = driver.current_url
    except Exception:
        current_url = "<unavailable>"
    try:
        ready_state = driver.execute_script("return document.readyState")
    except Exception:
        ready_state = "<unavailable>"
    try:
        highres_count = len(driver.find_elements(By.CSS_SELECTOR, "a[href*='/highres/']"))
    except Exception:
        highres_count = -1
    print(
        f"{context} diagnostics: "
        f"title='{title}', url='{current_url}', readyState='{ready_state}', highresLinks={highres_count}"
    )


def _navigate_gallery_page(driver: webdriver.Chrome, url: str, timeout: int, verbose: bool, mode_label: str) -> bool:
    """Navigate to the gallery using fallback URLs and wait for links to appear."""
    last_error: Exception | None = None
    for candidate in _candidate_gallery_urls(url):
        try:
            driver.get(candidate)
            if verbose:
                print(f"Navigated to gallery candidate ({mode_label}): {candidate}")
            if _wait_for_gallery_links(driver, timeout):
                return True
            if verbose:
                print(f"Gallery links not found on candidate URL: {candidate}")
                _log_page_diagnostics(driver, verbose, "Gallery wait failure")
        except TimeoutError as e:
            last_error = e
            if verbose:
                print(f"Connection timeout while loading gallery candidate '{candidate}': {e}")
        except Exception as e:
            last_error = e
            if verbose:
                print(f"Error loading gallery candidate '{candidate}': {e}")
    if verbose and last_error is not None:
        print(f"Unable to load gallery page after fallbacks: {last_error}")
    return False


def _click_shuffle(driver: webdriver.Chrome, timeout: int, verbose: bool) -> bool:
    """Click shuffle using multiple fallback selectors."""
    for selector in SHUFFLE_BUTTON_SELECTORS:
        try:
            button = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            try:
                button.click()
            except Exception:
                driver.execute_script("arguments[0].click();", button)
            return True
        except Exception:
            continue
    if verbose:
        print("Could not find a clickable shuffle control using fallback selectors.")
        _log_page_diagnostics(driver, verbose, "Shuffle click failure")
    return False


def _extract_highres_urls_from_html(base_url: str, html: str) -> list[str]:
    """Extract absolute highres image links from raw HTML."""
    extracted: list[str] = []
    seen: set[str] = set()
    for raw_href in HIGHRES_HREF_REGEX.findall(html or ""):
        href = raw_href.strip().replace("&amp;", "&")
        full = urljoin(base_url, href)
        lower = full.lower()
        if not lower.endswith(IMAGE_EXTENSIONS):
            continue
        if full not in seen:
            seen.add(full)
            extracted.append(full)
    return extracted


def _candidate_http_urls(url: str) -> list[str]:
    """Build URL candidates for non-browser fallback scraping."""
    parsed = urlparse((url or "").strip())
    netloc = parsed.netloc or "ultrawidewallpapers.net"
    scheme = parsed.scheme or "https"
    origin = f"{scheme}://{netloc}"
    candidates = [
        url,
        f"{origin}/",
        f"{origin}/?lang=en",
        "https://ultrawidewallpapers.net/",
        "https://www.ultrawidewallpapers.net/",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for candidate in candidates:
        value = (candidate or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _http_fallback_links(url: str, limit: int, verbose: bool) -> list[str]:
    """Fetch wallpaper links via HTTP when Selenium is blocked."""
    results: list[str] = []
    seen: set[str] = set()
    for candidate in _candidate_http_urls(url):
        try:
            response = requests.get(candidate, headers=HTTP_HEADERS, timeout=20)
        except Exception as e:
            if verbose:
                print(f"HTTP fallback request failed for '{candidate}': {e}")
            continue

        if response.status_code != 200:
            if verbose:
                print(f"HTTP fallback candidate returned {response.status_code}: {candidate}")
            continue

        urls = _extract_highres_urls_from_html(candidate, response.text)
        if verbose:
            print(f"HTTP fallback candidate '{candidate}' yielded {len(urls)} highres link(s).")
        for image_url in urls:
            if image_url not in seen:
                seen.add(image_url)
                results.append(image_url)
                if len(results) >= limit:
                    return results
    return results


def _build_wallpaper_record(image_url: str, verbose: bool, referer: str | None = None) -> dict:
    """Build one wallpaper metadata record from an image URL."""
    request_headers = build_image_request_headers(image_url, referer=referer)
    width, height = fetch_image_dimensions(image_url, verbose, request_headers=request_headers)
    aspect_ratio = simplify_ratio(width, height)
    return {
        "image_url": image_url,
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "aspect_ratio_float": round(width / height, 4) if width and height else None,
    }


def _collect_via_http_fallback(count: int, skip_urls: set[str], url: str, verbose: bool) -> list[dict]:
    """Collect wallpaper records without Selenium using HTTP/HTML parsing."""
    if count <= 0:
        return []
    candidates = _http_fallback_links(url=url, limit=max(count * 12, 50), verbose=verbose)
    records: list[dict] = []
    for image_url in candidates:
        if image_url in skip_urls or any(r.get("image_url") == image_url for r in records):
            continue
        try:
            records.append(_build_wallpaper_record(image_url, verbose, referer=url))
            if verbose:
                print(f"Collected fallback wallpaper {len(records)}/{count}")
        except Exception as e:
            if verbose:
                print(f"Skipping invalid fallback wallpaper URL '{image_url}': {e}")
        if len(records) >= count:
            break
    return records

def get_unique_wallpapers(
    count: int,
    skip_urls: set[str] | None = None,
    verbose: bool = True,
    max_shuffles: int = 25,
    url: str = "https://ultrawidewallpapers.net/gallery?lang=en",
    webdriver_timeout: int = 10,
    window_size: str = "1920,1080",
    shuffle_timeout: int = 5,
    headless: bool = True,
    browser_user_agent: str | None = None,
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
    driver = _init_driver(window_size, headless=headless, user_agent=browser_user_agent)
    collected: list[dict] = []
    try:
        if not _navigate_gallery_page(driver, url, webdriver_timeout, verbose, "unique mode"):
            if verbose:
                print("Initial gallery load failed across all URL fallbacks.")
            return _collect_via_http_fallback(count=count, skip_urls=skip_urls, url=url, verbose=verbose)

        attempts = 0
        while len(collected) < count and attempts < max_shuffles:
            # Always click shuffle (including first attempt) to ensure fresh set
            if _click_shuffle(driver, shuffle_timeout, verbose):
                time.sleep(2)
            elif attempts > 0:
                break
            elif verbose:
                print("First shuffle click failed; trying current gallery state once.")

            attempts += 1
            try:
                wallpaper_elements = _find_gallery_links(driver)
            except Exception as e:
                if verbose:
                    print(f"Failed to enumerate wallpaper elements: {e}")
                    _log_page_diagnostics(driver, verbose, "Gallery enumeration failure")
                break
            for el in wallpaper_elements:
                if len(collected) >= count:
                    break
                try:
                    image_url = el.get_attribute("href")
                    if not image_url or image_url in skip_urls or any(r.get("image_url") == image_url for r in collected):
                        continue
                    collected.append(_build_wallpaper_record(image_url, verbose, referer=driver.current_url))
                    if verbose:
                        print(f"Collected unique wallpaper {len(collected)}/{count}")
                except Exception as inner_e:
                    if verbose:
                        print(f"Failed extracting a wallpaper element: {inner_e}")
            # If we didn't gain any new images this attempt, continue to next shuffle
        if verbose and len(collected) < count:
            print(f"Only gathered {len(collected)}/{count} unique wallpapers after {attempts} attempt(s).")
        if len(collected) < count:
            # Top up via HTTP fallback for robustness when Selenium yields too few links.
            remaining = count - len(collected)
            fallback_records = _collect_via_http_fallback(
                count=remaining,
                skip_urls=skip_urls.union({r.get("image_url") for r in collected if r.get("image_url")}),
                url=url,
                verbose=verbose,
            )
            collected.extend(fallback_records)
        return collected
    finally:
        driver.quit()

def _init_driver(
    window_size: str = "1920,1080",
    headless: bool = True,
    user_agent: str | None = None,
):
    """Internal helper to create a quiet Chrome webdriver instance."""
    # Suppress noisy Chrome / GCM logs
    import os
    if os.name == "nt":  # Windows null device
        os.environ.setdefault("CHROME_LOG_FILE", "NUL")
    else:
        os.environ.setdefault("CHROME_LOG_FILE", "/dev/null")

    chrome_options = Options()
    effective_user_agent = (user_agent or "").strip() or DEFAULT_BROWSER_USER_AGENT
    chrome_options.add_argument(f"--user-agent={effective_user_agent}")
    if headless:
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
    chrome_options.add_argument(f"--window-size={window_size}")  # consistent layout calculations headless
    # Some sites gate Selenium traffic based on automation-specific browser fingerprints.
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    # 0=ALL, 1=INFO, 2=WARNING, 3=ERROR (actually FATAL). We choose 3 to hide most stuff.
    chrome_options.add_argument("--log-level=3")
    # Remove the typical 'enable-logging' switch Selenium injects that causes extra stderr.
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])  # type: ignore[arg-type]
    chrome_options.add_experimental_option("useAutomationExtension", False)
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
            _apply_anti_detection_profile(driver)
            return driver
    except Exception as e:
        # If redirection fails, try without it
        try:
            driver = webdriver.Chrome(options=chrome_options, service=service)
            _apply_anti_detection_profile(driver)
            return driver
        except Exception as e2:
            # If that also fails, provide a helpful error message
            raise RuntimeError(f"Failed to create Chrome WebDriver. Please ensure Chrome is installed and up to date. Error: {e2}") from e2


def _apply_anti_detection_profile(driver: webdriver.Chrome) -> None:
    """Apply lightweight anti-detection patches to reduce fake 403/404 responses."""
    script = """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script})
    except Exception:
        # Some driver/browser combinations may not expose the CDP endpoint.
        pass
    try:
        driver.execute_script(script)
    except Exception:
        pass


def get_wallpapers_after_shuffle(
    count: int, 
    verbose: bool = True,
    url: str = "https://ultrawidewallpapers.net/gallery?lang=en",
    webdriver_timeout: int = 10,
    window_size: str = "1920,1080",
    headless: bool = True,
    browser_user_agent: str | None = None,
) -> list[dict]:
    """Fetch up to `count` wallpapers after pressing shuffle once.

    Returns a list with length 0..count. Each entry is same schema as
    ``get_one_wallpaper_after_shuffle``.
    """
    if count <= 0:
        return []
    driver = _init_driver(window_size, headless=headless, user_agent=browser_user_agent)
    try:
        if not _navigate_gallery_page(driver, url, webdriver_timeout, verbose, "single shuffle mode"):
            if verbose:
                print("Failed to load gallery page across all URL fallbacks.")
            return _collect_via_http_fallback(count=count, skip_urls=set(), url=url, verbose=verbose)

        if _click_shuffle(driver, webdriver_timeout, verbose):
            time.sleep(2)
            if verbose:
                print("Content likely reloaded after shuffle.")
        elif verbose:
            print("Proceeding without shuffle; using currently visible gallery items.")

        try:
            wallpaper_elements = _find_gallery_links(driver)
            if not wallpaper_elements:
                if verbose:
                    print("No wallpapers found after shuffle.")
                    _log_page_diagnostics(driver, verbose, "No wallpapers found")
                return []
            selected = wallpaper_elements[:count]
            results: list[dict] = []
            for idx, el in enumerate(selected, start=1):
                try:
                    image_url = el.get_attribute("href")
                    results.append(_build_wallpaper_record(image_url, verbose, referer=driver.current_url))
                    if verbose:
                        print(f"Collected wallpaper {idx}/{len(selected)}")
                except Exception as inner_e:  # continue gathering others
                    if verbose:
                        print(f"Failed to extract one wallpaper element: {inner_e}")
            if len(results) < count:
                needed = count - len(results)
                fallback_records = _collect_via_http_fallback(
                    count=needed,
                    skip_urls={r.get("image_url") for r in results if r.get("image_url")},
                    url=url,
                    verbose=verbose,
                )
                results.extend(fallback_records)
            return results
        except Exception as e:
            if verbose:
                print(f"Error extracting wallpapers: {e}")
                _log_page_diagnostics(driver, verbose, "Wallpaper extraction failure")
            return []
    finally:
        driver.quit()

__all__ = ["get_wallpapers_after_shuffle", "get_unique_wallpapers"]
