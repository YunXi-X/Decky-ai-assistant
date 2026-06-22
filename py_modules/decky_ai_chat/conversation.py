from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


CLAUDE_SESSION_NAMESPACE = uuid.UUID("f4c5996a-e862-4c18-9f95-92985f0c5f1d")
MAX_STORED_MESSAGES = 80


class ConversationStore:
    def __init__(self, settings_dir: str | Path):
        self.path = Path(settings_dir) / "conversations.json"

    def active_conversation(self, game: dict[str, Any] | None = None) -> dict[str, Any]:
        conversation_id, title, normalized_game = self._conversation_identity(game or {})
        data = self._load()
        conversations = data.setdefault("conversations", {})
        record = conversations.setdefault(
            conversation_id,
            {
                "conversation_id": conversation_id,
                "title": title,
                "game": normalized_game,
                "messages": [],
            },
        )
        record["title"] = title
        record["game"] = normalized_game
        record["messages"] = self._clean_messages(record.get("messages", []))
        self._ensure_claude_session(record, conversation_id)
        self._save(data)
        return dict(record)

    def conversation(self, conversation_id: str) -> dict[str, Any]:
        data = self._load()
        record = data.setdefault("conversations", {}).setdefault(
            conversation_id,
            {
                "conversation_id": conversation_id,
                "title": "通用对话",
                "game": {},
                "messages": [],
            },
        )
        record["messages"] = self._clean_messages(record.get("messages", []))
        self._ensure_claude_session(record, conversation_id)
        self._save(data)
        return dict(record)

    def append_exchange(
        self,
        conversation_id: str,
        user_message: dict[str, Any],
        assistant_message: dict[str, Any],
        claude_session_ready: bool = True,
    ) -> dict[str, Any]:
        data = self._load()
        conversations = data.setdefault("conversations", {})
        record = conversations.setdefault(
            conversation_id,
            {
                "conversation_id": conversation_id,
                "title": "通用对话",
                "game": {},
                "messages": [],
            },
        )
        messages = self._clean_messages(record.get("messages", []))
        for message in (user_message, assistant_message):
            cleaned = self._clean_message(message)
            if cleaned:
                messages.append(cleaned)
        record["messages"] = messages[-MAX_STORED_MESSAGES:]
        self._ensure_claude_session(record, conversation_id)
        if claude_session_ready:
            record["claude_session_ready"] = True
            record["claude_session_resume"] = True
        elif "claude_session_ready" not in record:
            record["claude_session_ready"] = False
            record["claude_session_resume"] = False
        self._save(data)
        return dict(record)

    def clear(self, conversation_id: str) -> dict[str, Any]:
        data = self._load()
        conversations = data.setdefault("conversations", {})
        record = conversations.setdefault(
            conversation_id,
            {
                "conversation_id": conversation_id,
                "title": "通用对话",
                "game": {},
                "messages": [],
            },
        )
        record["messages"] = []
        record["claude_session_id"] = str(uuid.uuid4())
        record["claude_session_ready"] = False
        record["claude_session_resume"] = False
        self._save(data)
        return dict(record)

    def claude_session_id(self, conversation_id: str) -> str:
        return str(uuid.uuid5(CLAUDE_SESSION_NAMESPACE, conversation_id))

    def _conversation_identity(self, game: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        appid = _to_int(game.get("appid"))
        if appid:
            name = str(game.get("name", "")).strip() or f"Steam 游戏 {appid}"
            return f"steam:{appid}", name, {"appid": appid, "name": name}
        return "global", "通用对话", {}

    def _load(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    data.setdefault("conversations", {})
                    return data
        except Exception:
            pass
        return {"conversations": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=True, indent=2)

    def _clean_messages(self, messages: Any) -> list[dict[str, str]]:
        if not isinstance(messages, list):
            return []
        cleaned = [message for message in (self._clean_message(item) for item in messages) if message]
        return cleaned[-MAX_STORED_MESSAGES:]

    def _clean_message(self, message: Any) -> dict[str, str] | None:
        if not isinstance(message, dict):
            return None
        role = str(message.get("role", "")).strip()
        text = str(message.get("text", message.get("content", ""))).strip()
        if role not in {"user", "assistant"} or not text:
            return None
        return {"role": role, "text": text}

    def _ensure_claude_session(self, record: dict[str, Any], conversation_id: str) -> None:
        session_id = str(record.get("claude_session_id", "")).strip()
        if not _is_uuid(session_id):
            record["claude_session_id"] = self.claude_session_id(conversation_id)
        ready_value = record.get("claude_session_ready")
        if isinstance(ready_value, bool):
            ready = ready_value
        else:
            ready = bool(record.get("messages"))
            record["claude_session_ready"] = ready
        record["claude_session_resume"] = ready


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (TypeError, ValueError):
        return False
    return True
