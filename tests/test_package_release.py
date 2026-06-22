from pathlib import Path

from scripts import package_release
from scripts.package_release import should_include


def test_release_excludes_python_cache_files():
    assert not should_include(Path("py_modules/decky_ai_chat/__pycache__/config.pyc"))
    assert not should_include(Path("py_modules/decky_ai_chat/config.pyo"))


def test_release_excludes_test_directories_and_dist_metadata():
    assert not should_include(Path("py_modules/decky_ai_chat/tests/test_config.py"))
    assert not should_include(Path("py_modules/example-1.0.0.dist-info/RECORD"))


def test_release_excludes_python_vendor_directory():
    assert not should_include(Path("py_modules/vendor/example_package/__init__.py"))


def test_release_keeps_runtime_modules():
    assert should_include(Path("py_modules/decky_ai_chat/claude_code.py"))
    assert should_include(Path("py_modules/decky_ai_chat/steam.py"))


def test_release_runtime_paths_include_bundled_claude_directory():
    assert "bin" in package_release.RUNTIME_PATHS


def test_assert_claude_ready_requires_binary_and_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(package_release, "CLAUDE_BINARY", tmp_path / "bin" / "claude" / "claude")
    monkeypatch.setattr(package_release, "CLAUDE_MANIFEST", tmp_path / "bin" / "claude" / "VENDOR-MANIFEST.json")

    try:
        package_release.assert_claude_ready()
    except SystemExit as exc:
        assert "pnpm run vendor:claude" in str(exc)
    else:
        raise AssertionError("assert_claude_ready should fail when bundled Claude files are missing")

    package_release.CLAUDE_BINARY.parent.mkdir(parents=True)
    package_release.CLAUDE_BINARY.write_text("#!/bin/sh\n", encoding="utf-8")
    package_release.CLAUDE_MANIFEST.write_text("{}", encoding="utf-8")

    package_release.assert_claude_ready()
