#!/usr/bin/env python3
import argparse
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "release"
STAGING_DIR = RELEASE_DIR / ".staging"

RUNTIME_PATHS = [
    "plugin.json",
    "main.py",
    "package.json",
    "README.md",
    "LICENSE",
    "bin",
    "dist",
    "py_modules",
]
CLAUDE_BINARY = ROOT / "bin" / "claude" / "claude"
CLAUDE_MANIFEST = ROOT / "bin" / "claude" / "VENDOR-MANIFEST.json"

EXCLUDED_DIRS = {"__pycache__", "test", "tests", "vendor"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_FILENAMES = {"INSTALLER", "RECORD", "REQUESTED", "direct_url.json"}


def load_version() -> str:
    with (ROOT / "package.json").open("r", encoding="utf-8") as handle:
        package = json.load(handle)
    return str(package["version"])


def clean_path(path: Path) -> None:
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def should_include(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    if parts & EXCLUDED_DIRS:
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if path.name in EXCLUDED_FILENAMES:
        return False
    return True


def copy_runtime_files(destination: Path) -> None:
    clean_path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    missing = []
    for relative in RUNTIME_PATHS:
        source = ROOT / relative
        if not source.exists():
            missing.append(relative)
            continue

        target = destination / relative
        if source.is_dir():
            shutil.copytree(
                source,
                target,
                ignore=lambda directory, names: [
                    name
                    for name in names
                    if not should_include(Path(directory, name).relative_to(source.parent))
                ],
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    if missing:
        raise SystemExit(f"Missing required release files: {', '.join(missing)}")


def assert_claude_ready() -> None:
    def display(path: Path) -> str:
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return str(path)

    missing = [display(path) for path in (CLAUDE_BINARY, CLAUDE_MANIFEST) if not path.exists()]
    if missing:
        raise SystemExit(
            "Bundled Claude Code CLI is missing. "
            "Run `pnpm run vendor:claude` before packaging a release. "
            f"Missing: {', '.join(missing)}"
        )


def write_zip(source_dir: Path, zip_path: Path, include_folder: bool) -> None:
    clean_path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file() or not should_include(path.relative_to(source_dir)):
                continue
            if include_folder:
                archive_name = Path(source_dir.name) / path.relative_to(source_dir)
            else:
                archive_name = path.relative_to(source_dir)
            archive.write(path, archive_name.as_posix())


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Decky AI Chat release zip.")
    parser.add_argument(
        "--folder-wrapper",
        action="store_true",
        help="Put files under a decky-ai-chat/ folder inside the zip.",
    )
    parser.add_argument(
        "--allow-missing-claude",
        action="store_true",
        help="Package without bin/claude; intended only for development.",
    )
    args = parser.parse_args()
    if not args.allow_missing_claude:
        assert_claude_ready()

    version = load_version()
    package_name = f"decky-ai-chat-v{version}"
    staging_name = "folder" if args.folder_wrapper else "root"
    staging_plugin = STAGING_DIR / staging_name / "decky-ai-chat"
    zip_path = RELEASE_DIR / f"{package_name}.zip"
    if args.folder_wrapper:
        zip_path = RELEASE_DIR / f"{package_name}-folder.zip"

    copy_runtime_files(staging_plugin)
    write_zip(staging_plugin, zip_path, include_folder=args.folder_wrapper)
    print(zip_path)


if __name__ == "__main__":
    main()
