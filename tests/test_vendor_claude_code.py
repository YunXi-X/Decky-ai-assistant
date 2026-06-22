from pathlib import Path

from scripts import vendor_claude_code


def test_find_claude_executable_prefers_native_binary(tmp_path: Path):
    candidate = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code-linux-x64" / "vendor" / "claude"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("#!/bin/sh\n", encoding="utf-8")
    candidate.chmod(0o755)

    assert vendor_claude_code.find_claude_executable(tmp_path) == candidate


def test_copy_claude_binary_writes_manifest(tmp_path: Path):
    source = tmp_path / "build" / "claude"
    target = tmp_path / "plugin" / "bin" / "claude"
    source.parent.mkdir(parents=True)
    source.write_text("#!/bin/sh\n", encoding="utf-8")
    source.chmod(0o755)

    manifest = vendor_claude_code.copy_claude_binary(source, target, package="@anthropic-ai/claude-code", version="latest")

    bundled = target / "claude"
    assert bundled.exists()
    assert bundled.stat().st_mode & 0o111
    assert (target / "VENDOR-MANIFEST.json").exists()
    assert manifest["package"] == "@anthropic-ai/claude-code"
    assert manifest["version"] == "latest"
    assert manifest["binary"] == "claude"
