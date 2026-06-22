import os
import sys

import decky

PLUGIN_DIR = os.path.dirname(os.path.realpath(__file__))
PY_MODULES_DIR = os.path.join(PLUGIN_DIR, "py_modules")
if PY_MODULES_DIR not in sys.path:
    sys.path.insert(0, PY_MODULES_DIR)

from decky_ai_chat.vendor import configure_vendor_path

configure_vendor_path(PLUGIN_DIR)

from decky_ai_chat.config import ConfigStore
from decky_ai_chat.config_server import PhoneConfigServer
from decky_ai_chat.conversation import ConversationStore
from decky_ai_chat.claude_code import ClaudeCodeBackend
from decky_ai_chat.steam import SteamClient, detect_running_game


class Plugin:
    async def _main(self):
        self.config_store = ConfigStore(decky)
        self.conversation_store = ConversationStore(self.config_store.path.parent)
        self.claude_backend = ClaudeCodeBackend(decky.logger, PLUGIN_DIR)
        self.phone_config_server = PhoneConfigServer(self.config_store, decky.logger)
        self._pending_stream_requests = {}
        decky.logger.info("AI Chat plugin loaded")

    async def ask_ai(self, request: dict) -> dict:
        config = self.config_store.load()
        prepared = self._prepare_conversation_request(request)
        response = await self.claude_backend.ask(prepared, config)
        self._save_exchange(prepared, response)
        return response

    async def start_ai_stream(self, request: dict) -> dict:
        config = self.config_store.load()
        prepared = self._prepare_conversation_request(request)
        started = self.claude_backend.start_stream(prepared, config)
        if started.get("ok") and started.get("stream_id"):
            started["conversation_id"] = prepared.get("conversation_id")
            started["claude_session_id"] = prepared.get("claude_session_id")
            started["claude_session_resume"] = prepared.get("claude_session_resume")
            self._pending_stream_requests[started["stream_id"]] = prepared
        return started

    async def poll_ai_stream(self, stream_id: str, cursor: int = 0) -> dict:
        polled = self.claude_backend.poll_stream(stream_id, cursor)
        if polled.get("done") and polled.get("response") and not polled.get("_conversation_saved"):
            prepared = self._pending_stream_requests.pop(str(stream_id), None)
            if prepared:
                self._save_exchange(prepared, polled["response"])
                polled["_conversation_saved"] = True
        return polled

    async def get_config(self) -> dict:
        return self.config_store.public_config()

    async def save_config(self, updates: dict) -> dict:
        return self.config_store.save(updates)

    async def check_backend(self, updates: dict | None = None) -> dict:
        config = self.config_store.load()
        if updates:
            config.update(updates)
        return self.claude_backend.check(config)

    async def detect_steam_status(self) -> dict:
        config = self.config_store.load()
        client = SteamClient(config)
        status = client.status()
        if status.get("steam_id") and not str(config.get("steam_id", "")).strip():
            self.config_store.save({"steam_id": status["steam_id"]})
            status["saved_steam_id"] = True
        return status

    async def get_active_conversation(self) -> dict:
        game = detect_running_game()
        conversation = self.conversation_store.active_conversation(game if game.get("ok") else {})
        conversation["running_game"] = game if game.get("ok") else {}
        return conversation

    async def clear_active_conversation(self, conversation_id: str | None = None) -> dict:
        if conversation_id:
            return self.conversation_store.clear(conversation_id)
        game = detect_running_game()
        conversation = self.conversation_store.active_conversation(game if game.get("ok") else {})
        return self.conversation_store.clear(conversation["conversation_id"])

    async def get_pairing_info(self) -> dict:
        try:
            return self.phone_config_server.info()
        except Exception as exc:
            decky.logger.exception("AI Chat phone setup failed")
            return {
                "ok": False,
                "url": "",
                "host": "",
                "port": 0,
                "token": "",
                "message": str(exc),
            }

    async def _unload(self):
        self.phone_config_server.stop()
        decky.logger.info("AI Chat plugin unloaded")

    def _prepare_conversation_request(self, request: dict) -> dict:
        prepared = dict(request or {})
        conversation_id = str(prepared.get("conversation_id", "")).strip()
        if conversation_id:
            conversation = self.conversation_store.conversation(conversation_id)
            prepared["claude_session_id"] = str(conversation.get("claude_session_id", ""))
            prepared["claude_session_resume"] = bool(conversation.get("claude_session_resume"))
            if not prepared.get("game"):
                prepared["game"] = conversation.get("game", {})
            return prepared
        else:
            game = detect_running_game()
            conversation = self.conversation_store.active_conversation(game if game.get("ok") else {})
        prepared["conversation_id"] = conversation["conversation_id"]
        prepared["claude_session_id"] = conversation["claude_session_id"]
        prepared["claude_session_resume"] = conversation.get("claude_session_resume", False)
        if conversation.get("game"):
            prepared["game"] = conversation["game"]
        return prepared

    def _save_exchange(self, request: dict, response: dict) -> None:
        if request.get("skip_conversation_save"):
            return
        conversation_id = str(request.get("conversation_id", "")).strip()
        prompt = str(request.get("prompt", "")).strip()
        message = str(response.get("message", "")).strip()
        if not conversation_id or not prompt or not message:
            return
        self.conversation_store.append_exchange(
            conversation_id,
            {"role": "user", "text": prompt},
            {"role": "assistant", "text": message},
            claude_session_ready=bool(response.get("ok")),
        )
