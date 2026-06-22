#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "release" / ".claude-code-build"
DEFAULT_TARGET = ROOT / "bin" / "claude"
DEFAULT_PACKAGE = "@anthropic-ai/claude-code-linux-x64"


def clean_path(path: Path) -> None:
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def install_package(build_dir: Path, package: str, version: str) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    package_spec = package if version in ("", "latest") else f"{package}@{version}"
    subprocess.run(
        [
            "npm",
            "install",
            "--prefix",
            str(build_dir),
            "--no-save",
            "--omit=dev",
            package_spec,
        ],
        check=True,
    )


def find_claude_executable(build_dir: Path) -> Path:
    candidates = []
    for path in list(build_dir.rglob("claude")) + list(build_dir.rglob("claude.exe")):
        if not path.is_file():
            continue
        if not os.access(path, os.X_OK):
            continue
        candidates.append(path)
    if not candidates:
        raise SystemExit(f"Could not find an executable `claude` under {build_dir}")

    def score(path: Path) -> tuple[int, int, str]:
        text = path.as_posix()
        native_hint = 0 if any(part in text for part in ("linux-x64", "vendor", "native", "bin")) else 1
        bin_shim = 1 if ".bin" in path.parts else 0
        return (bin_shim, native_hint, text)

    return sorted(candidates, key=score)[0]


def copy_claude_binary(source: Path, target_dir: Path, package: str, version: str) -> dict[str, Any]:
    clean_path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "claude"
    shutil.copy2(source, target)
    target.chmod(0o755)
    manifest = {
        "package": package,
        "version": version or "latest",
        "binary": "claude",
        "source": str(source),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (target_dir / "VENDOR-MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Vendor Claude Code CLI into bin/claude.")
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--version", default="latest")
    parser.add_argument("--build-dir", type=Path, default=BUILD_DIR)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--keep-build", action="store_true")
    args = parser.parse_args()

    if not args.keep_build:
        clean_path(args.build_dir)
    install_package(args.build_dir, args.package, args.version)
    source = find_claude_executable(args.build_dir)
    manifest = copy_claude_binary(source, args.target, args.package, args.version)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
