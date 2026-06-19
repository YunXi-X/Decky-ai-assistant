import os
import sys

import decky

PLUGIN_DIR = os.path.dirname(os.path.realpath(__file__))
PY_MODULES_DIR = os.path.join(PLUGIN_DIR, "py_modules")
if PY_MODULES_DIR not in sys.path:
    sys.path.insert(0, PY_MODULES_DIR)

from decky_ai_chat.config import ConfigStore
from decky_ai_chat.config_server import PhoneConfigServer
from decky_ai_chat.providers import ProviderRouter


class Plugin:
    async def _main(self):
        self.config_store = ConfigStore(decky)
        self.router = ProviderRouter(decky.logger)
        self.phone_config_server = PhoneConfigServer(self.config_store, decky.logger)
        decky.logger.info("AI Chat plugin loaded")

    async def ask_ai(self, request: dict) -> dict:
        config = self.config_store.load()
        return await self.router.ask(request, config)

    async def get_config(self) -> dict:
        return self.config_store.public_config()

    async def save_config(self, updates: dict) -> dict:
        return self.config_store.save(updates)

    async def check_backend(self, updates: dict | None = None) -> dict:
        config = self.config_store.load()
        if updates:
            config.update(updates)
        return await self.router.check(config)

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
