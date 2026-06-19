# Decky AI Chat

Decky Loader plugin frontend for an AI chat panel in Steam Deck game mode.

## Develop

```bash
pnpm i
pnpm run build
```

The frontend entry point is `src/index.tsx`. The Python backend mock is `main.py`, where `Plugin.ask_ai` can be replaced with a call to OpenAI-compatible HTTP APIs, Ollama, llama.cpp server, or another local service.

## Backend Providers

The backend is split into a small Decky RPC layer and provider modules:

- `main.py`: Decky RPC methods.
- `py_modules/decky_ai_chat/config.py`: persistent settings.
- `py_modules/decky_ai_chat/providers.py`: model and RAG provider routing.

Supported providers:

- `mock`: no network or API key required.
- `openai`: OpenAI-compatible `/chat/completions` HTTP API. Works with OpenAI-compatible servers such as Ollama, llama.cpp server, vLLM, LiteLLM, and hosted OpenAI-compatible endpoints.
- `langchain`: optional `langchain-openai` integration. Install `requirements-langchain.txt` in the Decky Python environment before using it.
- `ragflow`: calls RAGFlow chat completions through its HTTP API. Requires base URL, API key, chat id, and session id.

OpenAI-compatible local example:

```text
Provider: openai
Endpoint: http://127.0.0.1:11434/v1
Model: qwen2.5:7b
API Key: empty or your server token
```

RAGFlow example:

```text
Provider: ragflow
Endpoint: http://RAGFLOW_HOST
API Key: your RAGFlow API key
RAGFlow Chat ID: chat id from RAGFlow
RAGFlow Session ID: session id from RAGFlow
```

LangChain setup on Steam Deck:

```bash
cd /home/deck/homebrew/plugins/decky-ai-chat
python3 -m pip install -r requirements-langchain.txt
sudo systemctl restart plugin_loader
```

## Configure API Keys From Your PC

If typing API keys in Steam Deck game mode is inconvenient, configure the plugin
over SSH from your development machine. The helper prompts for the API key
without putting it in shell history, then writes Decky's settings file.

DeepSeek:

```bash
python3 scripts/configure_remote.py deck@STEAM_DECK_IP --preset deepseek
```

DeepSeek Pro:

```bash
python3 scripts/configure_remote.py deck@STEAM_DECK_IP --preset deepseek-pro
```

Kimi:

```bash
python3 scripts/configure_remote.py deck@STEAM_DECK_IP --preset kimi
```

Kimi code model:

```bash
python3 scripts/configure_remote.py deck@STEAM_DECK_IP --preset kimi-code
```

Custom OpenAI-compatible endpoint:

```bash
python3 scripts/configure_remote.py deck@STEAM_DECK_IP --preset custom
```

The config is written to:

```text
/home/deck/homebrew/settings/AI Chat/config.json
```

## Configure From Phone

The plugin also exposes a local phone setup page:

1. Deploy and restart the plugin.
2. Open AI Chat in Decky.
3. Press the QR-code button in the top bar.
4. Scan the QR code with a phone on the same Wi-Fi network.
5. Choose DeepSeek, Kimi, or a custom OpenAI-compatible endpoint and save.

The phone setup server listens on the Steam Deck LAN address, starting at port
`28888` and trying later ports if needed. The URL contains a random token and is
intended only for trusted local networks.

## Install on Steam Deck

Build the plugin, then copy this folder to:

```bash
~/homebrew/plugins/decky-ai-chat
```

Restart Decky Loader or Steam, then open the Quick Access Menu in game mode.

Recommended deploy command from your development machine.

Important: keep the remote target as `plugins/decky-ai-chat/`, not just
`plugins/`. With `--delete`, targeting `plugins/` will try to delete other
installed Decky plugins.

```bash
ssh deck@STEAM_DECK_IP 'mkdir -p /home/deck/homebrew/plugins/decky-ai-chat'
rsync -av --delete --exclude node_modules --exclude __pycache__ decky-ai-chat/ deck@STEAM_DECK_IP:/home/deck/homebrew/plugins/decky-ai-chat/
ssh deck@STEAM_DECK_IP 'sudo systemctl restart plugin_loader'
```

If `/home/deck/homebrew/plugins` is owned by root on your Deck, use:

```bash
rsync -av --delete --exclude node_modules --exclude __pycache__ --rsync-path='sudo rsync' decky-ai-chat/ deck@STEAM_DECK_IP:/home/deck/homebrew/plugins/decky-ai-chat/
ssh deck@STEAM_DECK_IP 'sudo systemctl restart plugin_loader'
```

## Remote Debugging

1. On Steam Deck, switch to Desktop Mode and set a password if SSH is not ready:

   ```bash
   passwd
   sudo systemctl enable --now sshd
   ip addr
   ```

2. In Gaming Mode, enable Steam developer options:

   - Steam button
   - Settings
   - System
   - Enable Developer Mode
   - Developer
   - Enable CEF Remote Debugging

   Restart Steam after toggling CEF debugging.

3. From your development machine, open a tunnel:

   ```bash
   ssh -L 8080:127.0.0.1:8080 deck@STEAM_DECK_IP
   ```

4. Open Chrome or Edge on the development machine and visit:

   ```text
   http://localhost:8080
   ```

   Choose the Steam page that contains the Quick Access Menu, open DevTools, then filter sources or console logs for `AI Chat`.

5. For backend logs:

   ```bash
   ssh deck@STEAM_DECK_IP
   journalctl -u plugin_loader -f
   ls ~/homebrew/logs
   ```
