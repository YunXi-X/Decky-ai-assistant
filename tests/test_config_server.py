from __future__ import annotations

from urllib.parse import parse_qs, urlencode

from py_modules.decky_ai_chat.config_server import PhoneConfigServer


TEST_STEAM_ID = "TEST_STEAM_ID"
TEST_PHONE_STEAM_ID = "TEST_PHONE_STEAM_ID"


class FakeConfigStore:
    def __init__(self):
        self.saved_updates = None

    def public_config(self):
        return {
            "endpoint": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "system_prompt": "中文回答",
            "temperature": 0.7,
            "max_history": 16,
            "verify_ssl": False,
            "has_api_key": True,
            "steam_id": TEST_STEAM_ID,
            "has_steam_api_key": True,
            "steam_include_free_games": True,
            "steam_cache_seconds": 1800,
            "steam_api_timeout_seconds": 5,
            "config_path": "/tmp/config.json",
        }

    def save(self, updates):
        self.saved_updates = updates
        return {
            **self.public_config(),
            "has_api_key": updates.get("api_key") not in ("", "__KEEP__"),
            "has_steam_api_key": updates.get("steam_api_key") not in ("", "__KEEP__"),
            "steam_id": updates.get("steam_id", ""),
        }


class FakeLogger:
    def info(self, *_args, **_kwargs):
        pass

    def exception(self, *_args, **_kwargs):
        pass


def test_phone_config_page_includes_steam_web_api_fields():
    server = PhoneConfigServer(FakeConfigStore(), FakeLogger(), port=0)

    page = server._page()

    assert "Steam Web API" in page
    assert 'name="steam_id"' in page
    assert 'name="steam_api_key"' in page
    assert 'name="steam_include_free_games"' in page
    assert 'name="steam_cache_seconds"' in page
    assert 'name="steam_api_timeout_seconds"' in page
    assert "https://steamcommunity.com/dev/apikey" in page


def test_phone_config_save_updates_steam_web_api_fields():
    store = FakeConfigStore()
    server = PhoneConfigServer(store, FakeLogger(), port=0)
    form = parse_qs(
        urlencode(
            {
                "endpoint": "https://api.moonshot.cn/v1",
                "model": "kimi-k2.6",
                "api_key": "",
                "system_prompt": "默认中文",
                "temperature": "0.5",
                "max_history": "12",
                "steam_id": TEST_PHONE_STEAM_ID,
                "steam_api_key": "STEAMKEY",
                "steam_include_free_games": "on",
                "steam_cache_seconds": "3600",
                "steam_api_timeout_seconds": "10",
            }
        ),
        keep_blank_values=True,
    )

    updates = server._updates_from_form(form)

    assert updates["api_key"] == "__KEEP__"
    assert updates["steam_id"] == TEST_PHONE_STEAM_ID
    assert updates["steam_api_key"] == "STEAMKEY"
    assert updates["steam_include_free_games"] is True
    assert updates["steam_cache_seconds"] == "3600"
    assert updates["steam_api_timeout_seconds"] == "10"
