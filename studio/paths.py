"""Per-user application data locations on supported desktop platforms."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DP104Studio"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DP104Studio"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "DP104Studio"
