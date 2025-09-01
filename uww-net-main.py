from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import math
import sys
from dataclasses import dataclass, asdict

try:
    # Optional dependency for easy multi-monitor enumeration (pip install screeninfo)
    from screeninfo import get_monitors as _screeninfo_get_monitors  # type: ignore
except ImportError:  # pragma: no cover - optional
    _screeninfo_get_monitors = None
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

@dataclass
class MonitorInfo:
    index: int
    name: str
    width: int
    height: int
    x: int
    y: int
    is_primary: bool

    @property
    def aspect_ratio(self):  # string like 16:9
        return _simplify_ratio(self.width, self.height)

    @property
    def aspect_ratio_float(self):  # numeric like 1.7778
        try:
            return round(self.width / self.height, 4)
        except Exception:
            return None

def _gather_monitors_screeninfo():
    monitors = []
    try:
        if not _screeninfo_get_monitors:
            return None
        for idx, m in enumerate(_screeninfo_get_monitors()):
            monitors.append(
                MonitorInfo(
                    index=idx,
                    name=getattr(m, 'name', f'Monitor {idx+1}') or f'Monitor {idx+1}',
                    width=m.width,
                    height=m.height,
                    x=getattr(m, 'x', 0),
                    y=getattr(m, 'y', 0),
                    is_primary=bool(getattr(m, 'is_primary', idx == 0)),
                )
            )
        return monitors
    except Exception as e:  # pragma: no cover
        print(f"screeninfo monitor enumeration failed: {e}")
        return None

def _gather_monitors_windows_ctypes():
    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()  # attempt to get true pixel sizes

        MONITORINFOF_PRIMARY = 0x00000001

        class MONITORINFOEX(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), ctypes.c_double)

        monitors: list[MonitorInfo] = []

        def _callback(hMonitor, hdcMonitor, lprcMonitor, dwData):  # noqa: N802
            mi = MONITORINFOEX()
            mi.cbSize = ctypes.sizeof(MONITORINFOEX)
            user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi))
            rect = mi.rcMonitor
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            monitors.append(
                MonitorInfo(
                    index=len(monitors),
                    name=mi.szDevice,
                    width=width,
                    height=height,
                    x=rect.left,
                    y=rect.top,
                    is_primary=bool(mi.dwFlags & MONITORINFOF_PRIMARY),
                )
            )
            return 1

        user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_callback), 0)
        return monitors
    except Exception as e:  # pragma: no cover
        print(f"ctypes monitor enumeration failed: {e}")
        return None

def _gather_monitors_tkinter_primary_only():  # fallback single monitor
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        root.destroy()
        return [
            MonitorInfo(
                index=0,
                name="Primary",
                width=w,
                height=h,
                x=0,
                y=0,
                is_primary=True,
            )
        ]
    except Exception:
        return None

def gather_monitors():
    """Collect monitor information.

    Tries (in order): screeninfo, Windows ctypes API, Tkinter primary fallback.
    Returns list[MonitorInfo].
    """
    for strat in (_gather_monitors_screeninfo, _gather_monitors_windows_ctypes, _gather_monitors_tkinter_primary_only):
        result = strat()
        if result:
            return result
    return []

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
    # 0. Monitor information at startup
    monitors = gather_monitors()
    if monitors:
        print("Detected monitors (startup):")
        for m in monitors:
            d = asdict(m)
            d["aspect_ratio"] = m.aspect_ratio
            d["aspect_ratio_float"] = m.aspect_ratio_float
            print(" - ", d)
    else:
        print("No monitor information could be gathered.")

    wallpaper_data = get_one_wallpaper_after_shuffle()
    if wallpaper_data:
        print("\nSuccessfully extracted data for one wallpaper after shuffle:")
        print(wallpaper_data)
    else:
        print("\nFailed to extract wallpaper data.")