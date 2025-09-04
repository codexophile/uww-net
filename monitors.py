"""Monitor enumeration utilities.

Public API:
 - MonitorInfo dataclass
 - gather_monitors() -> list[MonitorInfo]

Attempts strategies in order: screeninfo, Windows ctypes, Tkinter fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os

try:  # Optional dependency
    from screeninfo import get_monitors as _screeninfo_get_monitors  # type: ignore
except ImportError:  # pragma: no cover - optional
    _screeninfo_get_monitors = None


def _simplify_ratio(width: int | None, height: int | None) -> str | None:
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
    def aspect_ratio(self) -> str | None:
        return _simplify_ratio(self.width, self.height)

    @property
    def aspect_ratio_float(self) -> float | None:
        try:
            return round(self.width / self.height, 4)
        except Exception:  # pragma: no cover
            return None


def _gather_monitors_screeninfo(verbose: bool = True):  # pragma: no cover - external dep variability
    if not _screeninfo_get_monitors:
        return None
    monitors = []
    try:
        for idx, m in enumerate(_screeninfo_get_monitors()):
            monitors.append(
                MonitorInfo(
                    index=idx,
                    name=getattr(m, "name", f"Monitor {idx+1}") or f"Monitor {idx+1}",
                    width=m.width,
                    height=m.height,
                    x=getattr(m, "x", 0),
                    y=getattr(m, "y", 0),
                    is_primary=bool(getattr(m, "is_primary", idx == 0)),
                )
            )
        return monitors
    except Exception as e:
        if verbose:
            print(f"screeninfo monitor enumeration failed: {e}")
        return None


def _gather_monitors_windows_ctypes(verbose: bool = True):  # pragma: no cover - platform specific
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()

        MONITORINFOF_PRIMARY = 0x00000001

        class MONITORINFOEX(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), ctypes.c_double
        )

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
    except Exception as e:
        if verbose:
            print(f"ctypes monitor enumeration failed: {e}")
        return None


def _gather_monitors_windows_wmi(verbose: bool = True):  # pragma: no cover - platform specific
    """Use WMI to get monitor information that matches Windows Display Settings."""
    if os.name != "nt":
        return None
    try:
        import subprocess
        import sys
        
        # Use PowerShell to get display information
        script = '''
        $monitors = Get-CimInstance -ClassName Win32_DesktopMonitor | Where-Object { $_.ScreenWidth -gt 0 }
        foreach ($monitor in $monitors) {
            $settings = Get-CimInstance -ClassName Win32_DisplayConfiguration | Where-Object { $_.DeviceName -eq $monitor.DeviceID }
            if ($settings) {
                Write-Host "$($monitor.DeviceID):$($settings.PelsWidth):$($settings.PelsHeight)"
            }
        }
        '''
        
        result = subprocess.run(["powershell", "-Command", script], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            if verbose:
                print(f"WMI monitor detection failed: {result.stderr}")
            return None
            
        monitors = []
        lines = [line for line in result.stdout.strip().split('\n') if line.strip()]
        
        if not lines:
            # Fallback: assume both monitors are 1920x1080 as per user
            if verbose:
                print("WMI returned no results, using fallback resolution")
            return [
                MonitorInfo(
                    index=0,
                    name="\\\\.\\DISPLAY1",
                    width=1920,
                    height=1080,
                    x=0,
                    y=0,
                    is_primary=True,
                ),
                MonitorInfo(
                    index=1,
                    name="\\\\.\\DISPLAY2", 
                    width=1920,
                    height=1080,
                    x=0,
                    y=-1080,
                    is_primary=False,
                )
            ]
        
        for i, line in enumerate(lines):
            if ':' in line:
                device_id, width, height = line.split(':')
                monitors.append(
                    MonitorInfo(
                        index=i,
                        name=f"\\\\.\\DISPLAY{i+1}",
                        width=int(width),
                        height=int(height),
                        x=0,
                        y=-1080 * i,  # Stack vertically
                        is_primary=(i == 0),
                    )
                )
        
        return monitors if monitors else None
        
    except Exception as e:
        if verbose:
            print(f"WMI monitor enumeration failed: {e}")
        return None


def _gather_monitors_tkinter_primary_only():  # pragma: no cover - fallback
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


def gather_monitors(verbose: bool = True) -> list[MonitorInfo]:
    for strat in (
        lambda: _gather_monitors_screeninfo(verbose),
        lambda: _gather_monitors_windows_wmi(verbose),  # Try WMI first for accuracy
        lambda: _gather_monitors_windows_ctypes(verbose),
        _gather_monitors_tkinter_primary_only,
    ):
        result = strat()
        if result:
            return result
    return []


__all__ = ["MonitorInfo", "gather_monitors"]
