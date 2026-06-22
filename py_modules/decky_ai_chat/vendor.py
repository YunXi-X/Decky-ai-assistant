from __future__ import annotations

import sys
from pathlib import Path
from typing import MutableSequence


def configure_vendor_path(
    plugin_root: str | Path,
    path_entries: MutableSequence[str] | None = None,
) -> None:
    """Put bundled third-party dependencies before local plugin modules."""
    entries = path_entries if path_entries is not None else sys.path
    root = Path(plugin_root).resolve()
    vendor_dir = str(root / "py_modules" / "vendor")
    py_modules_dir = str(root / "py_modules")

    for item in (vendor_dir, py_modules_dir):
        while item in entries:
            entries.remove(item)

    entries.insert(0, py_modules_dir)
    entries.insert(0, vendor_dir)
