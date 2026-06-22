from __future__ import annotations

import json
import os
import re
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


STEAM_API_BASE = "https://api.steampowered.com"
DEFAULT_CACHE_SECONDS = 1800
DEFAULT_API_TIMEOUT_SECONDS = 5
IGNORED_RUNNING_APPIDS = {
    0,
    769,
}


def default_steam_roots() -> list[Path]:
    home = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
    candidates = [
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        Path("/home/deck/.local/share/Steam"),
        Path("/home/deck/.steam/steam"),
    ]
    deduped: list[Path] = []
    for path in candidates:
        if path not in deduped:
            deduped.append(path)
    return deduped


def detect_steam_id(steam_roots: list[Path] | None = None) -> dict[str, Any]:
    for root in steam_roots or default_steam_roots():
        loginusers = root / "config" / "loginusers.vdf"
        if not loginusers.exists():
            continue
        text = loginusers.read_text(encoding="utf-8", errors="replace")
        users = _parse_loginusers(text)
        if not users:
            continue
        most_recent = next((user for user in users if user.get("most_recent") == "1"), users[0])
        return {
            "ok": True,
            "steam_id": most_recent["steam_id"],
            "account_name": most_recent.get("account_name", ""),
            "persona_name": most_recent.get("persona_name", ""),
            "source": str(loginusers),
        }
    return {
        "ok": False,
        "steam_id": "",
        "message": "未在本机 Steam 配置中检测到 SteamID64。",
    }


def parse_library_folders(steam_root: Path) -> list[Path]:
    steamapps = steam_root / "steamapps"
    libraryfolders = steamapps / "libraryfolders.vdf"
    libraries = [steamapps]
    if not libraryfolders.exists():
        return libraries
    text = libraryfolders.read_text(encoding="utf-8", errors="replace")
    for value in re.findall(r'"path"\s+"([^"]+)"', text):
        path = Path(value.replace("\\\\", "\\")).expanduser() / "steamapps"
        if path not in libraries:
            libraries.append(path)
    return libraries


def detect_running_game(
    proc_root: str | Path = "/proc",
    steam_roots: list[Path] | None = None,
) -> dict[str, Any]:
    manifests = _local_game_names(steam_roots or default_steam_roots())
    candidates: list[dict[str, Any]] = []
    root = Path(proc_root)
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        return {"ok": False, "message": f"无法读取进程列表：{exc}"}
    for entry in entries:
        if not entry.name.isdigit():
            continue
        appid = _appid_from_environ(entry / "environ")
        if not appid or appid in IGNORED_RUNNING_APPIDS:
            continue
        candidates.append(
            {
                "ok": True,
                "appid": appid,
                "name": manifests.get(appid, f"Steam 游戏 {appid}"),
                "source": "proc_environ",
                "pid": int(entry.name),
                "_start_time": _proc_start_time(entry / "stat"),
            }
        )
    if not candidates:
        return {"ok": False, "message": "未检测到正在运行的 Steam 游戏。"}
    candidates.sort(key=lambda item: (int(item.get("_start_time", 0)), int(item.get("pid", 0))), reverse=True)
    selected = dict(candidates[0])
    selected.pop("_start_time", None)
    return selected


class SteamClient:
    def __init__(
        self,
        config: dict[str, Any],
        steam_roots: list[Path] | None = None,
        cache_seconds: int | None = None,
    ):
        self.config = config
        self.steam_roots = steam_roots or default_steam_roots()
        self.cache_seconds = int(config.get("steam_cache_seconds") or cache_seconds or DEFAULT_CACHE_SECONDS)
        self.api_timeout_seconds = _clamp_int(
            config.get("steam_api_timeout_seconds"),
            DEFAULT_API_TIMEOUT_SECONDS,
            2,
            20,
        )
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def status(self) -> dict[str, Any]:
        steam_id = self._steam_id()
        detected = detect_steam_id(self.steam_roots) if not steam_id else {}
        running_game = detect_running_game(steam_roots=self.steam_roots)
        return {
            "ok": bool(steam_id or detected.get("steam_id")),
            "steam_id": steam_id or detected.get("steam_id", ""),
            "has_api_key": bool(self._api_key()),
            "detected": detected,
            "running_game": running_game if running_game.get("ok") else {},
            "local_library_count": len(self.local_installed_games().get("games", [])),
        }

    def local_installed_games(self) -> dict[str, Any]:
        games: list[dict[str, Any]] = []
        for root in self.steam_roots:
            for steamapps in parse_library_folders(root):
                if not steamapps.exists():
                    continue
                for manifest in sorted(steamapps.glob("appmanifest_*.acf")):
                    parsed = _parse_acf(manifest.read_text(encoding="utf-8", errors="replace"))
                    appid = _to_int(parsed.get("appid"))
                    if not appid:
                        continue
                    games.append(
                        {
                            "appid": appid,
                            "name": parsed.get("name", ""),
                            "install_dir": parsed.get("installdir", ""),
                            "size_on_disk": _to_int(parsed.get("SizeOnDisk")),
                            "library_path": str(steamapps),
                        }
                    )
        return {"ok": True, "games": games, "source": "local_steam_manifests"}

    def owned_games(self, limit: int = 5000) -> dict[str, Any]:
        steam_id = self._steam_id_or_detected()
        if not steam_id:
            return {"ok": False, "message": "缺少 SteamID64，无法获取 Steam 游戏库。"}
        cache_key = f"owned:{steam_id}:{limit}"
        cached = self._cached(cache_key)
        if cached:
            return cached
        params = {
            "steamid": steam_id,
            "format": "json",
            "include_appinfo": 1,
            "include_played_free_games": 1 if self._include_free_games() else 0,
        }
        if self._api_key():
            params["key"] = self._api_key()
        try:
            data = self._request_json("/IPlayerService/GetOwnedGames/v0001/", params)
        except Exception as exc:
            fallback = self.local_installed_games()
            return {
                **fallback,
                "ok": True,
                "steam_id": steam_id,
                "game_count": len(fallback.get("games", [])),
                "source": "local_steam_manifests_fallback",
                "web_api_ok": False,
                "web_api_error": str(exc),
                "message": "Steam Web API 暂时不可用，已回退到本机已安装游戏列表。该列表不包含完整云端库和总游玩时长。",
            }
        games = data.get("response", {}).get("games", [])[: max(1, min(int(limit), 5000))]
        normalized = []
        for game in games:
            normalized.append(
                {
                    "appid": game.get("appid"),
                    "name": game.get("name", ""),
                    "playtime_forever_minutes": game.get("playtime_forever", 0),
                    "playtime_2weeks_minutes": game.get("playtime_2weeks", 0),
                    "img_icon_url": game.get("img_icon_url", ""),
                }
            )
        result = {
            "ok": True,
            "steam_id": steam_id,
            "game_count": data.get("response", {}).get("game_count", len(normalized)),
            "games": normalized,
            "source": "steam_web_api",
            "has_api_key": bool(self._api_key()),
            "web_api_ok": True,
        }
        self._store_cache(cache_key, result)
        return result

    def recently_played(self, limit: int = 10) -> dict[str, Any]:
        steam_id = self._steam_id_or_detected()
        if not steam_id:
            return {"ok": False, "message": "缺少 SteamID64，无法获取最近游玩。"}
        params = {
            "steamid": steam_id,
            "format": "json",
            "count": max(1, min(int(limit), 50)),
        }
        if self._api_key():
            params["key"] = self._api_key()
        data = self._request_json("/IPlayerService/GetRecentlyPlayedGames/v0001/", params)
        return {
            "ok": True,
            "steam_id": steam_id,
            "games": data.get("response", {}).get("games", []),
            "total_count": data.get("response", {}).get("total_count", 0),
            "source": "steam_web_api",
        }

    def achievements(self, appid: int | str) -> dict[str, Any]:
        steam_id = self._steam_id_or_detected()
        if not steam_id:
            return {"ok": False, "message": "缺少 SteamID64，无法获取成就。"}
        appid_int = _to_int(appid)
        if not appid_int:
            return {"ok": False, "message": "appid 无效。"}
        params = {"steamid": steam_id, "appid": appid_int, "format": "json"}
        if self._api_key():
            params["key"] = self._api_key()
        data = self._request_json("/ISteamUserStats/GetPlayerAchievements/v0001/", params)
        playerstats = data.get("playerstats", {})
        achievements = playerstats.get("achievements", [])
        achieved = sum(1 for item in achievements if int(item.get("achieved", 0)) == 1)
        return {
            "ok": bool(playerstats.get("success", True)),
            "steam_id": steam_id,
            "appid": appid_int,
            "game_name": playerstats.get("gameName", ""),
            "achieved": achieved,
            "total": len(achievements),
            "achievements": achievements,
            "source": "steam_web_api",
        }

    def global_achievement_percentages(self, appid: int | str) -> dict[str, Any]:
        appid_int = _to_int(appid)
        if not appid_int:
            return {"ok": False, "message": "appid 无效。"}
        data = self._request_json(
            f"/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v0002/",
            {"gameid": appid_int, "format": "json"},
        )
        return {
            "ok": True,
            "appid": appid_int,
            "achievements": data.get("achievementpercentages", {}).get("achievements", []),
            "source": "steam_web_api",
        }

    def search_library(self, query: str, limit: int = 20) -> dict[str, Any]:
        query_clean = str(query or "").strip().lower()
        if not query_clean:
            return {"ok": False, "message": "搜索关键词不能为空。"}
        results: list[dict[str, Any]] = []
        owned = self.owned_games(limit=5000)
        if owned.get("ok"):
            for game in owned.get("games", []):
                if query_clean in str(game.get("name", "")).lower():
                    results.append({**game, "source": "steam_web_api"})
        for game in self.local_installed_games().get("games", []):
            if query_clean in str(game.get("name", "")).lower() and not any(
                item.get("appid") == game.get("appid") for item in results
            ):
                results.append({**game, "source": "local_steam_manifests"})
        return {"ok": True, "query": query, "results": results[: max(1, min(int(limit), 100))]}

    def _request_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{STEAM_API_BASE}{path}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": "decky-ai-chat/0.1"})
        try:
            kwargs = {}
            if not self._verify_ssl():
                kwargs["context"] = ssl._create_unverified_context()
            with urlopen(request, timeout=self.api_timeout_seconds, **kwargs) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Steam API HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Steam API 请求失败：{exc}") from exc

    def _steam_id(self) -> str:
        return str(self.config.get("steam_id", "")).strip()

    def _steam_id_or_detected(self) -> str:
        return self._steam_id() or str(detect_steam_id(self.steam_roots).get("steam_id", "")).strip()

    def _api_key(self) -> str:
        return str(self.config.get("steam_api_key", "")).strip()

    def _include_free_games(self) -> bool:
        value = self.config.get("steam_include_free_games", True)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _verify_ssl(self) -> bool:
        value = self.config.get("verify_ssl", True)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _cached(self, key: str) -> dict[str, Any] | None:
        cached = self._cache.get(key)
        if not cached:
            return None
        created, value = cached
        if time.time() - created > self.cache_seconds:
            self._cache.pop(key, None)
            return None
        return value

    def _store_cache(self, key: str, value: dict[str, Any]) -> None:
        self._cache[key] = (time.time(), value)


def _parse_loginusers(text: str) -> list[dict[str, str]]:
    users: list[dict[str, str]] = []
    for match in re.finditer(r'"(\d{17})"\s*\{(.*?)\n\s*\}', text, re.S):
        body = match.group(2)
        users.append(
            {
                "steam_id": match.group(1),
                "account_name": _vdf_value(body, "AccountName"),
                "persona_name": _vdf_value(body, "PersonaName"),
                "most_recent": _vdf_value(body, "MostRecent"),
            }
        )
    return users


def _parse_acf(text: str) -> dict[str, str]:
    return {key: value for key, value in re.findall(r'"([^"]+)"\s+"([^"]*)"', text)}


def _local_game_names(steam_roots: list[Path]) -> dict[int, str]:
    games: dict[int, str] = {}
    for root in steam_roots:
        for steamapps in parse_library_folders(root):
            if not steamapps.exists():
                continue
            for manifest in sorted(steamapps.glob("appmanifest_*.acf")):
                try:
                    parsed = _parse_acf(manifest.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
                appid = _to_int(parsed.get("appid"))
                name = str(parsed.get("name", "")).strip()
                if appid and name:
                    games[appid] = name
    return games


def _appid_from_environ(path: Path) -> int:
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    values: dict[str, str] = {}
    for chunk in data.split(b"\0"):
        if b"=" not in chunk:
            continue
        key, value = chunk.split(b"=", 1)
        try:
            values[key.decode("utf-8", errors="replace")] = value.decode("utf-8", errors="replace")
        except Exception:
            continue
    return _to_int(values.get("SteamAppId")) or _to_int(values.get("SteamGameId"))


def _proc_start_time(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    tail = text.rsplit(")", 1)[-1].split()
    if len(tail) >= 20:
        return _to_int(tail[19])
    return 0


def _vdf_value(text: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s+"([^"]*)"', text)
    return match.group(1) if match else ""


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default
