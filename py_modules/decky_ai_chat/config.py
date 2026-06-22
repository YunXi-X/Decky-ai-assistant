import json
import os
from pathlib import Path
from typing import Any


OLD_DEFAULT_SYSTEM_PROMPT = "You are a concise, helpful assistant running inside Steam Deck game mode."
DEFAULT_SYSTEM_PROMPT = (
    "你是运行在 Steam Deck 游戏模式中的中文 AI 助手。"
    "请默认使用简体中文回答，除非用户明确要求其他语言。"
    "回答应简洁、具体、可执行。"
)


DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "agent",
    "provider": "openai",
    "endpoint": "https://api.deepseek.com",
    "model": "deepseek-v4-flash",
    "api_key": "",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "temperature": 0.7,
    "max_history": 16,
    "verify_ssl": True,
    "ragflow_chat_id": "",
    "ragflow_session_id": "",
    "steam_id": "",
    "steam_api_key": "",
    "steam_include_free_games": True,
    "steam_cache_seconds": 1800,
    "steam_api_timeout_seconds": 5,
    "agent_backend": "claude-code-cli",
    "claude_code_path": "",
    "claude_permission_mode": "plan",
    "claude_timeout_seconds": 600,
    "claude_bare_mode": False,
}


PUBLIC_KEYS = {
    "mode",
    "provider",
    "endpoint",
    "model",
    "system_prompt",
    "temperature",
    "max_history",
    "verify_ssl",
    "ragflow_chat_id",
    "ragflow_session_id",
    "steam_id",
    "steam_include_free_games",
    "steam_cache_seconds",
    "steam_api_timeout_seconds",
    "agent_backend",
    "claude_code_path",
    "claude_permission_mode",
    "claude_timeout_seconds",
    "claude_bare_mode",
}


class ConfigStore:
    def __init__(self, decky_module):
        settings_dir = getattr(decky_module, "DECKY_PLUGIN_SETTINGS_DIR", None)
        if not settings_dir:
            settings_dir = os.environ.get(
                "DECKY_PLUGIN_SETTINGS_DIR",
                "/home/deck/homebrew/settings/AI Chat",
            )
        self.path = Path(settings_dir) / "config.json"

    def load(self) -> dict[str, Any]:
        config = dict(DEFAULT_CONFIG)
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    config.update(data)
        except Exception:
            return config
        if config.get("system_prompt") == OLD_DEFAULT_SYSTEM_PROMPT:
            config["system_prompt"] = DEFAULT_SYSTEM_PROMPT
        if config.get("mode") != "agent":
            config["mode"] = "agent"
        if config.get("provider") not in ("openai", "claude-code-cli"):
            config["provider"] = DEFAULT_CONFIG["provider"]
        if config.get("agent_backend") != "claude-code-cli":
            config["agent_backend"] = "claude-code-cli"
        if config.get("endpoint") == "mock://decky-backend":
            config["endpoint"] = DEFAULT_CONFIG["endpoint"]
        if config.get("model") == "decky-local":
            config["model"] = DEFAULT_CONFIG["model"]
        return config

    def public_config(self) -> dict[str, Any]:
        config = self.load()
        public = {key: config.get(key, DEFAULT_CONFIG.get(key)) for key in PUBLIC_KEYS}
        public["has_api_key"] = bool(str(config.get("api_key", "")).strip())
        public["has_steam_api_key"] = bool(str(config.get("steam_api_key", "")).strip())
        public["config_path"] = str(self.path)
        return public

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        config = self.load()
        allowed = set(DEFAULT_CONFIG.keys())
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key in {"api_key", "steam_api_key"} and value == "__KEEP__":
                continue
            config[key] = self._clean_value(key, value)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=True, indent=2)

        return self.public_config()

    def _clean_value(self, key: str, value: Any) -> Any:
        if key == "temperature":
            try:
                return max(0.0, min(float(value), 2.0))
            except (TypeError, ValueError):
                return DEFAULT_CONFIG[key]
        if key == "max_history":
            try:
                return max(2, min(int(value), 40))
            except (TypeError, ValueError):
                return DEFAULT_CONFIG[key]
        if key == "verify_ssl":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "on")
        if key == "steam_include_free_games":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "on")
        if key == "steam_cache_seconds":
            try:
                return max(60, min(int(value), 86400))
            except (TypeError, ValueError):
                return DEFAULT_CONFIG[key]
        if key == "steam_api_timeout_seconds":
            try:
                return max(2, min(int(value), 20))
            except (TypeError, ValueError):
                return DEFAULT_CONFIG[key]
        if key == "claude_timeout_seconds":
            try:
                return max(30, min(int(value), 1800))
            except (TypeError, ValueError):
                return DEFAULT_CONFIG[key]
        if key == "claude_permission_mode":
            mode = str(value).strip()
            return mode if mode in {"default", "acceptEdits", "plan", "auto", "dontAsk"} else DEFAULT_CONFIG[key]
        if key == "claude_bare_mode":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "on")
        if key == "agent_backend":
            return "claude-code-cli"
        if key == "mode":
            return "agent"
        if key == "provider":
            provider = str(value).strip().lower()
            return provider if provider in ("openai", "claude-code-cli") else DEFAULT_CONFIG[key]
        if value is None:
            return ""
        return str(value).strip()
