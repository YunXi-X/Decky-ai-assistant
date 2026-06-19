import html
import json
import os
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


class PhoneConfigServer:
    def __init__(self, config_store, logger, port: int = 28888):
        self.config_store = config_store
        self.logger = logger
        self.port = port
        self.token = secrets.token_urlsafe(18)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server:
            return

        handler = self._handler()
        server = None
        last_error: OSError | None = None
        for port in range(self.port, self.port + 20):
            try:
                server = ThreadingHTTPServer(("0.0.0.0", port), handler)
                break
            except OSError as exc:
                last_error = exc
        if server is None:
            raise RuntimeError(f"Could not start phone config server: {last_error}")

        self.port = int(server.server_port)
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        self.logger.info(f"AI Chat phone config server listening on {self.port}")

    def stop(self) -> None:
        if not self._server:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None

    def info(self) -> dict[str, Any]:
        self.start()
        host = os.environ.get("DECKY_AI_CHAT_HOST", "").strip() or self._lan_ip()
        return {
            "ok": True,
            "url": f"http://{host}:{self.port}/?token={self.token}",
            "host": host,
            "port": self.port,
            "token": self.token,
        }

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._json({"ok": True})
                    return
                if not self._authorized(parsed):
                    self._text("Invalid or expired token.", 403)
                    return
                self._html(outer._page())

            def do_POST(self):
                try:
                    parsed = urlparse(self.path)
                    if parsed.path != "/save":
                        self._text("Not found.", 404)
                        return
                    if not self._authorized(parsed):
                        self._text("Invalid or expired token.", 403)
                        return

                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length).decode("utf-8")
                    form = parse_qs(raw, keep_blank_values=True)
                    updates = {
                        "provider": "openai",
                        "endpoint": self._one(form, "endpoint"),
                        "model": self._one(form, "model"),
                        "system_prompt": self._one(form, "system_prompt"),
                        "temperature": self._one(form, "temperature"),
                        "max_history": self._one(form, "max_history"),
                        "verify_ssl": "verify_ssl" in form,
                    }
                    api_key = self._one(form, "api_key")
                    updates["api_key"] = api_key if api_key else "__KEEP__"
                    public_config = outer.config_store.save(updates)
                    outer.logger.info(
                        "AI Chat phone config saved: "
                        f"provider={public_config.get('provider')} "
                        f"endpoint={public_config.get('endpoint')} "
                        f"model={public_config.get('model')} "
                        f"has_api_key={public_config.get('has_api_key')} "
                        f"path={public_config.get('config_path')}"
                    )
                    self._html(outer._saved_page(public_config))
                except Exception as exc:
                    outer.logger.exception("AI Chat phone config save failed")
                    self._text(f"Save failed: {exc}", 500)

            def log_message(self, fmt, *args):
                outer.logger.info("phone-config " + fmt % args)

            def _authorized(self, parsed) -> bool:
                params = parse_qs(parsed.query)
                return params.get("token", [""])[0] == outer.token

            def _one(self, form, key: str) -> str:
                return form.get(key, [""])[0].strip()

            def _html(self, body: str, status: int = 200) -> None:
                payload = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _json(self, data: dict[str, Any]) -> None:
                payload = json.dumps(data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _text(self, body: str, status: int) -> None:
                payload = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Handler

    def _page(self) -> str:
        config = self.config_store.public_config()
        endpoint = html.escape(str(config.get("endpoint", "")), quote=True)
        model = html.escape(str(config.get("model", "")), quote=True)
        system_prompt = html.escape(str(config.get("system_prompt", "")), quote=False)
        temperature = html.escape(str(config.get("temperature", "0.7")), quote=True)
        max_history = html.escape(str(config.get("max_history", "16")), quote=True)
        verify_ssl_checked = "checked" if config.get("verify_ssl", True) else ""
        has_key = "saved" if config.get("has_api_key") else "not saved"
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Chat Setup</title>
  <style>
    body {{ margin: 0; background: #151515; color: #f4f4f4; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 560px; margin: 0 auto; padding: 24px 16px 40px; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; }}
    p {{ color: rgba(244,244,244,.68); line-height: 1.45; }}
    label {{ display: block; margin-top: 16px; font-size: 13px; color: rgba(244,244,244,.72); }}
    input, select, textarea {{ width: 100%; box-sizing: border-box; margin-top: 6px; border: 1px solid rgba(255,255,255,.14); border-radius: 14px; padding: 12px; background: #222; color: #fff; font: inherit; }}
    textarea {{ min-height: 90px; resize: vertical; }}
    button {{ width: 100%; margin-top: 22px; border: 0; border-radius: 18px; padding: 14px; background: #f4f4f4; color: #151515; font: inherit; font-weight: 700; }}
    .card {{ border: 1px solid rgba(255,255,255,.10); border-radius: 18px; padding: 16px; background: #1f1f1f; }}
    .hint {{ font-size: 12px; }}
  </style>
</head>
<body>
  <main>
    <h1>AI Chat Setup</h1>
    <p>在手机上填写模型服务信息，保存后 Steam Deck 插件会直接读取配置。API Key 当前状态：{has_key}。</p>
    <form method="post" action="/save?token={self.token}" class="card">
      <label>Preset
        <select id="preset">
          <option value="deepseek">DeepSeek Flash</option>
          <option value="deepseek-pro">DeepSeek Pro</option>
          <option value="kimi">Kimi</option>
          <option value="kimi-code">Kimi Code</option>
          <option value="custom">Custom OpenAI-compatible</option>
        </select>
      </label>
      <label>Endpoint / Base URL
        <input id="endpoint" name="endpoint" value="{endpoint}">
      </label>
      <label>Model
        <input id="model" name="model" value="{model}">
      </label>
      <label>API Key
        <input name="api_key" type="password" placeholder="留空则保留已保存的 key">
      </label>
      <label>System Prompt
        <textarea name="system_prompt">{system_prompt}</textarea>
      </label>
      <label>Temperature
        <input name="temperature" type="number" min="0" max="2" step="0.1" value="{temperature}">
      </label>
      <label>Max History
        <input name="max_history" type="number" min="2" max="40" step="1" value="{max_history}">
      </label>
      <label>
        <input name="verify_ssl" type="checkbox" {verify_ssl_checked} style="width: auto; margin-right: 8px;">
        Verify TLS certificate
      </label>
      <p class="hint">如果 Steam Deck 的代理或网关使用自签证书导致 CERTIFICATE_VERIFY_FAILED，可以临时取消勾选。只建议在可信网络中这样做。</p>
      <button type="submit">Save to Steam Deck</button>
    </form>
    <p class="hint">建议只在你的家庭局域网使用。此页面 URL 带一次随机 token，不要发给别人。</p>
  </main>
  <script>
    const presets = {{
      "deepseek": ["https://api.deepseek.com", "deepseek-v4-flash"],
      "deepseek-pro": ["https://api.deepseek.com", "deepseek-v4-pro"],
      "kimi": ["https://api.moonshot.cn/v1", "kimi-k2.6"],
      "kimi-code": ["https://api.moonshot.cn/v1", "kimi-k2.7-code"],
    }};
    document.getElementById("preset").addEventListener("change", (event) => {{
      const value = event.target.value;
      if (!presets[value]) return;
      document.getElementById("endpoint").value = presets[value][0];
      document.getElementById("model").value = presets[value][1];
    }});
  </script>
</body>
</html>"""

    def _saved_page(self, config: dict[str, Any]) -> str:
        endpoint = html.escape(str(config.get("endpoint", "")))
        model = html.escape(str(config.get("model", "")))
        path = html.escape(str(config.get("config_path", "")))
        has_key = "yes" if config.get("has_api_key") else "no"
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Saved</title>
  <style>
    body {{ margin: 0; background: #151515; color: #f4f4f4; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 560px; margin: 0 auto; padding: 32px 16px; text-align: center; }}
    .mark {{ width: 54px; height: 54px; margin: 0 auto 18px; border-radius: 999px; background: #f4f4f4; color: #151515; display: grid; place-items: center; font-size: 28px; }}
    p {{ color: rgba(244,244,244,.68); }}
    dl {{ text-align: left; border: 1px solid rgba(255,255,255,.10); border-radius: 18px; padding: 14px; background: #1f1f1f; }}
    dt {{ margin-top: 10px; color: rgba(244,244,244,.56); font-size: 12px; }}
    dd {{ margin: 4px 0 0; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <main>
    <div class="mark">✓</div>
    <h1>已保存</h1>
    <p>回到 Steam Deck 插件，重新打开设置或直接开始对话即可。</p>
    <dl>
      <dt>API Key saved</dt>
      <dd>{has_key}</dd>
      <dt>Endpoint</dt>
      <dd>{endpoint}</dd>
      <dt>Model</dt>
      <dd>{model}</dd>
      <dt>Config path</dt>
      <dd>{path}</dd>
    </dl>
  </main>
</body>
</html>"""

    def _lan_ip(self) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        except OSError:
            return socket.gethostbyname(socket.gethostname())
        finally:
            sock.close()
