import sys
from pathlib import Path

from py_modules.decky_ai_chat.vendor import configure_vendor_path


def test_configure_vendor_path_inserts_vendor_before_py_modules(tmp_path: Path):
    plugin_root = tmp_path / "decky-ai-chat"
    vendor = plugin_root / "py_modules" / "vendor"
    py_modules = plugin_root / "py_modules"
    vendor.mkdir(parents=True)
    py_modules.mkdir(exist_ok=True)

    fake_path = [str(py_modules), *sys.path]

    configure_vendor_path(plugin_root, fake_path)

    assert fake_path[0] == str(vendor)
    assert fake_path[1] == str(py_modules)


def test_configure_vendor_path_does_not_duplicate_entries(tmp_path: Path):
    plugin_root = tmp_path / "decky-ai-chat"
    vendor = plugin_root / "py_modules" / "vendor"
    py_modules = plugin_root / "py_modules"
    vendor.mkdir(parents=True)
    py_modules.mkdir(exist_ok=True)

    fake_path = [str(vendor), str(py_modules)]

    configure_vendor_path(plugin_root, fake_path)
    configure_vendor_path(plugin_root, fake_path)

    assert fake_path.count(str(vendor)) == 1
    assert fake_path.count(str(py_modules)) == 1
