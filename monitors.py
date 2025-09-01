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


def _gather_monitors_screeninfo():  # pragma: no cover - external dep variability
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
        print(f"screeninfo monitor enumeration failed: {e}")
        return None


def _gather_monitors_windows_ctypes():  # pragma: no cover - platform specific
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
        print(f"ctypes monitor enumeration failed: {e}")
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


def gather_monitors() -> list[MonitorInfo]:
    for strat in (
        _gather_monitors_screeninfo,
        _gather_monitors_windows_ctypes,
        _gather_monitors_tkinter_primary_only,
    ):
        result = strat()
        if result:
            return result
    return []


__all__ = ["MonitorInfo", "gather_monitors"]
