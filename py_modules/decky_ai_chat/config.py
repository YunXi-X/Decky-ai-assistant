import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "mock",
    "endpoint": "mock://decky-backend",
    "model": "decky-local",
    "api_key": "",
    "system_prompt": "You are a concise, helpful assistant running inside Steam Deck game mode.",
    "temperature": 0.7,
    "max_history": 16,
    "verify_ssl": True,
    "ragflow_chat_id": "",
    "ragflow_session_id": "",
}


PUBLIC_KEYS = {
    "provider",
    "endpoint",
    "model",
    "system_prompt",
    "temperature",
    "max_history",
    "verify_ssl",
    "ragflow_chat_id",
    "ragflow_session_id",
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
        return config

    def public_config(self) -> dict[str, Any]:
        config = self.load()
        public = {key: config.get(key, DEFAULT_CONFIG.get(key)) for key in PUBLIC_KEYS}
        public["has_api_key"] = bool(str(config.get("api_key", "")).strip())
        public["config_path"] = str(self.path)
        return public

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        config = self.load()
        allowed = set(DEFAULT_CONFIG.keys())
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "api_key" and value == "__KEEP__":
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
        if value is None:
            return ""
        return str(value).strip()
