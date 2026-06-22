from pathlib import Path

from py_modules.decky_ai_chat import steam
from py_modules.decky_ai_chat.steam import SteamClient, detect_running_game, detect_steam_id, parse_library_folders


TEST_STEAM_ID = "TEST_STEAM_ID"
TEST_LOGIN_STEAM_ID_CURRENT = "00000000000000002"


def test_detect_steam_id_reads_most_recent_loginusers_entry(tmp_path: Path):
    steam_root = tmp_path / ".local" / "share" / "Steam"
    config_dir = steam_root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "loginusers.vdf").write_text(
        """
        "users"
        {
          "00000000000000001"
          {
            "AccountName" "old"
            "MostRecent" "0"
          }
          "00000000000000002"
          {
            "AccountName" "current"
            "MostRecent" "1"
          }
        }
        """,
        encoding="utf-8",
    )

    result = detect_steam_id([steam_root])

    assert result["steam_id"] == TEST_LOGIN_STEAM_ID_CURRENT
    assert result["source"].endswith("loginusers.vdf")


def test_parse_library_folders_reads_steamapps_paths(tmp_path: Path):
    root = tmp_path / "Steam"
    extra = tmp_path / "Games"
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "libraryfolders.vdf").write_text(
        f'''
        "libraryfolders"
        {{
          "0"
          {{
            "path" "{root}"
          }}
          "1"
          {{
            "path" "{extra}"
          }}
        }}
        ''',
        encoding="utf-8",
    )

    paths = parse_library_folders(root)

    assert root / "steamapps" in paths
    assert extra / "steamapps" in paths


def test_local_installed_games_parse_appmanifest(tmp_path: Path):
    steam_root = tmp_path / "Steam"
    steamapps = steam_root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_123.acf").write_text(
        '''
        "AppState"
        {
          "appid" "123"
          "name" "Portal 2"
          "installdir" "Portal 2"
          "SizeOnDisk" "1200"
        }
        ''',
        encoding="utf-8",
    )
    client = SteamClient({"steam_id": "", "steam_api_key": ""}, steam_roots=[steam_root])

    games = client.local_installed_games()["games"]

    assert games == [
        {
            "appid": 123,
            "name": "Portal 2",
            "install_dir": "Portal 2",
            "size_on_disk": 1200,
            "library_path": str(steamapps),
        }
    ]


def test_detect_running_game_reads_steam_appid_from_proc_environ(tmp_path: Path):
    steam_root = tmp_path / "Steam"
    steamapps = steam_root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_620.acf").write_text(
        '"AppState"\n{\n"appid" "620"\n"name" "Portal 2"\n"installdir" "Portal 2"\n}\n',
        encoding="utf-8",
    )
    proc_root = tmp_path / "proc"
    (proc_root / "123").mkdir(parents=True)
    (proc_root / "123" / "environ").write_bytes(b"USER=deck\x00SteamAppId=620\x00")
    (proc_root / "123" / "stat").write_text("123 (portal2) S 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 42\n")

    result = detect_running_game(proc_root=proc_root, steam_roots=[steam_root])

    assert result == {
        "ok": True,
        "appid": 620,
        "name": "Portal 2",
        "source": "proc_environ",
        "pid": 123,
    }


def test_owned_games_requires_steam_id_before_request():
    client = SteamClient({"steam_id": "", "steam_api_key": ""}, steam_roots=[])

    result = client.owned_games()

    assert result["ok"] is False
    assert "SteamID64" in result["message"]


def test_search_library_uses_local_and_remote_games(tmp_path: Path, monkeypatch):
    steam_root = tmp_path / "Steam"
    steamapps = steam_root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_123.acf").write_text(
        '"AppState" { "appid" "123" "name" "Portal 2" }',
        encoding="utf-8",
    )
    client = SteamClient({"steam_id": TEST_STEAM_ID, "steam_api_key": ""}, steam_roots=[steam_root])

    monkeypatch.setattr(
        client,
        "owned_games",
        lambda limit=5000: {
            "ok": True,
            "games": [
                {
                    "appid": 456,
                    "name": "Half-Life 2",
                    "playtime_forever_minutes": 90,
                }
            ],
        },
    )

    result = client.search_library("life")

    assert result["ok"] is True
    assert result["results"][0]["name"] == "Half-Life 2"


def test_owned_games_falls_back_to_local_library_when_web_api_times_out(tmp_path: Path, monkeypatch):
    steam_root = tmp_path / "Steam"
    steamapps = steam_root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_123.acf").write_text(
        '"AppState" { "appid" "123" "name" "Portal 2" }',
        encoding="utf-8",
    )
    client = SteamClient({"steam_id": TEST_STEAM_ID}, steam_roots=[steam_root])

    monkeypatch.setattr(
        client,
        "_request_json",
        lambda path, params: (_ for _ in ()).throw(RuntimeError("Steam API 请求失败：timed out")),
    )

    result = client.owned_games()

    assert result["ok"] is True
    assert result["source"] == "local_steam_manifests_fallback"
    assert result["web_api_ok"] is False
    assert result["games"][0]["name"] == "Portal 2"


def test_request_json_uses_short_timeout_from_config(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout, **kwargs):
        captured["timeout"] = timeout
        captured["context"] = kwargs.get("context")
        return FakeResponse()

    monkeypatch.setattr(steam, "urlopen", fake_urlopen)
    client = SteamClient({"steam_api_timeout_seconds": 3}, steam_roots=[])

    client._request_json("/test", {})

    assert captured["timeout"] == 3
    assert captured["context"] is None


def test_request_json_can_disable_ssl_verification(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout, **kwargs):
        captured["context"] = kwargs.get("context")
        return FakeResponse()

    monkeypatch.setattr(steam, "urlopen", fake_urlopen)
    client = SteamClient({"verify_ssl": False}, steam_roots=[])

    client._request_json("/test", {})

    assert captured["context"] is not None
    assert captured["context"].check_hostname is False
    assert captured["context"].verify_mode == steam.ssl.CERT_NONE
