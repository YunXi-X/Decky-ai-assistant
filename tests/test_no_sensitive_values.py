from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", "node_modules", "dist", "release", "__pycache__", ".pytest_cache"}


def _repo_text_files():
    for path in ROOT.rglob("*"):
        if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        yield path, text


def test_repository_does_not_contain_real_shaped_steam_ids_or_api_keys():
    steam_id_pattern = re.compile("7656119" + r"\d{10}")
    api_key_pattern = re.compile("sk-" + r"[A-Za-z0-9_-]{12,}")
    matches = []

    for path, text in _repo_text_files():
        for pattern in (steam_id_pattern, api_key_pattern):
            for match in pattern.finditer(text):
                matches.append(f"{path.relative_to(ROOT)}:{match.start()}: {match.group(0)}")

    assert matches == []
