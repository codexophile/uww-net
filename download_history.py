"""Persistent download history utilities.

Stores previously downloaded image URLs in a simple newline-delimited text file
so we can avoid downloading the same image more than once across runs.
"""
from __future__ import annotations

from typing import Iterable, Set
import os

__all__ = ["load_history", "append_history"]


def load_history(path: str) -> Set[str]:
    """Load previously recorded image URLs from ``path``.

    Returns an empty set if the file does not exist or can't be read.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except Exception:
        return set()


def append_history(path: str, urls: Iterable[str]) -> None:
    """Append new image URLs to the history file at ``path``.

    Creates parent directory / file if needed.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            for u in urls:
                f.write(u + "\n")
    except Exception:
        # Non-fatal; silently ignore so main flow continues.
        pass
