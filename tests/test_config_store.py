from __future__ import annotations

from pathlib import Path

from py_modules.decky_ai_chat.config import ConfigStore


class FakeDecky:
    def __init__(self, settings_dir: Path):
        self.DECKY_PLUGIN_SETTINGS_DIR = str(settings_dir)


def test_config_store_saves_public_claude_code_settings(tmp_path: Path):
    store = ConfigStore(FakeDecky(tmp_path))

    public = store.save(
        {
            "agent_backend": "legacy-agent",
            "provider": "claude-code-cli",
            "claude_code_path": "/usr/bin/claude",
            "claude_permission_mode": "auto",
            "claude_timeout_seconds": "1200",
            "claude_bare_mode": "true",
        }
    )

    assert public["agent_backend"] == "claude-code-cli"
    assert public["provider"] == "claude-code-cli"
    assert public["claude_code_path"] == "/usr/bin/claude"
    assert public["claude_permission_mode"] == "auto"
    assert public["claude_timeout_seconds"] == 1200
    assert public["claude_bare_mode"] is True


def test_config_store_keeps_existing_steam_api_key_when_requested(tmp_path: Path):
    store = ConfigStore(FakeDecky(tmp_path))
    store.save({"steam_api_key": "STEAM-SECRET-KEY"})

    public = store.save({"steam_api_key": "__KEEP__"})

    assert public["has_steam_api_key"] is True
    assert store.load()["steam_api_key"] == "STEAM-SECRET-KEY"
