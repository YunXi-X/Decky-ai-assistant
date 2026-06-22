from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .steam import SteamClient


DEFAULT_HOME_CANDIDATES = (
    Path("/home/deck"),
)
MAX_CLAUDE_SECONDS = 600
SHELL_ENV_BLOCKLIST = {
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "PYTHONHOME",
    "PYTHONPATH",
}


class ClaudeCodeBackend:
    """Bridge Decky requests to the mature Claude Code CLI agent runtime."""

    def __init__(self, logger: Any | None = None, plugin_root: str | Path | None = None):
        self.logger = logger
        self.plugin_root = Path(plugin_root or Path(__file__).parents[2]).resolve()
        self._streams: dict[str, dict[str, Any]] = {}
        self._streams_lock = threading.Lock()

    async def ask(self, request: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self.ask_sync, request, config)

    def ask_sync(self, request: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        prompt = str(request.get("prompt", "")).strip()
        if not prompt:
            return self._result(False, "请输入内容后再发送。", config)
        runtime_config = self._runtime_config(config, request)

        executable = self._claude_executable(runtime_config)
        if not executable:
            return self._result(
                False,
                "未找到 Claude Code CLI。请先在 Steam Deck 上安装并登录 Claude Code，然后重启插件。",
                runtime_config,
            )

        command = self._command(executable, self._compose_prompt(prompt, request, runtime_config), runtime_config)
        try:
            completed = subprocess.run(
                command,
                cwd=str(self._home_root()),
                env=self._env(os.environ, runtime_config),
                text=True,
                capture_output=True,
                timeout=self._timeout(runtime_config),
            )
        except subprocess.TimeoutExpired as exc:
            return self._result(False, f"Claude Code CLI 超时：{exc}", runtime_config)
        except Exception as exc:
            if self.logger:
                self.logger.exception(f"Claude Code request failed: {exc!r}")
            return self._result(False, f"Claude Code CLI 调用失败：{exc}", runtime_config)

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        message, tool_events = self._parse_stream_json(stdout)
        if completed.returncode != 0:
            detail = stderr.strip() or stdout.strip() or f"退出码 {completed.returncode}"
            return self._result(False, f"Claude Code CLI 请求失败：{detail}", runtime_config, {"tool_events": tool_events})
        return self._result(
            True,
            message or stdout.strip() or "[Claude Code 没有返回文本]",
            runtime_config,
            {
                "raw_provider": "claude-code-cli",
                "tool_events": tool_events,
            },
        )

    def start_stream(self, request: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        prompt = str(request.get("prompt", "")).strip()
        if not prompt:
            return {"ok": False, "message": "请输入内容后再发送。"}
        runtime_config = self._runtime_config(config, request)

        executable = self._claude_executable(runtime_config)
        if not executable:
            return {
                "ok": False,
                "message": "未找到 Claude Code CLI。请先在 Steam Deck 上安装并登录 Claude Code，然后重启插件。",
            }

        stream_id = uuid.uuid4().hex
        command = self._command(executable, self._compose_prompt(prompt, request, runtime_config), runtime_config)
        state: dict[str, Any] = {
            "id": stream_id,
            "events": [],
            "done": False,
            "response": None,
            "created_at": time.time(),
        }
        with self._streams_lock:
            self._streams[stream_id] = state

        thread = threading.Thread(
            target=self._run_stream,
            args=(stream_id, command, runtime_config),
            name=f"decky-ai-chat-stream-{stream_id[:8]}",
            daemon=True,
        )
        thread.start()
        return {"ok": True, "stream_id": stream_id}

    def poll_stream(self, stream_id: str, cursor: int = 0) -> dict[str, Any]:
        with self._streams_lock:
            state = self._streams.get(str(stream_id))
            if not state:
                return {"ok": False, "message": "stream 不存在或已过期。", "done": True, "events": [], "cursor": cursor}
            events = list(state["events"][max(0, int(cursor)) :])
            next_cursor = len(state["events"])
            done = bool(state["done"])
            response = state.get("response")
            if done and time.time() - float(state.get("created_at", 0)) > 300:
                self._streams.pop(str(stream_id), None)
        return {
            "ok": True,
            "stream_id": str(stream_id),
            "events": events,
            "cursor": next_cursor,
            "done": done,
            "response": response,
        }

    def _run_stream(self, stream_id: str, command: list[str], config: dict[str, Any]) -> None:
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        try:
            process = subprocess.Popen(
                command,
                cwd=str(self._home_root()),
                env=self._env(os.environ, config),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if process.stdout:
                for line in process.stdout:
                    stdout_lines.append(line)
                    self._append_stream_events(stream_id, self._public_events_from_line(line))
            if process.stderr:
                stderr_lines = [line for line in process.stderr]
            returncode = process.wait(timeout=5)
        except Exception as exc:
            if self.logger:
                self.logger.exception(f"Claude Code stream failed: {exc!r}")
            self._finish_stream(stream_id, self._result(False, f"Claude Code CLI 流式调用失败：{exc}", config))
            return

        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)
        message, tool_events = self._parse_stream_json(stdout)
        if returncode != 0:
            detail = stderr.strip() or stdout.strip() or f"退出码 {returncode}"
            response = self._result(False, f"Claude Code CLI 请求失败：{detail}", config, {"tool_events": tool_events})
        else:
            response = self._result(
                True,
                message or stdout.strip() or "[Claude Code 没有返回文本]",
                config,
                {
                    "raw_provider": "claude-code-cli",
                    "tool_events": tool_events,
                },
            )
        self._finish_stream(stream_id, response)

    def _append_stream_events(self, stream_id: str, events: list[dict[str, str]]) -> None:
        if not events:
            return
        with self._streams_lock:
            state = self._streams.get(stream_id)
            if state:
                state["events"].extend(events)

    def _finish_stream(self, stream_id: str, response: dict[str, Any]) -> None:
        with self._streams_lock:
            state = self._streams.get(stream_id)
            if state:
                state["response"] = response
                state["done"] = True

    def _public_events_from_line(self, line: str) -> list[dict[str, str]]:
        line = line.strip()
        if not line:
            return []
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return [{"name": "Claude", "status": "text", "detail": line[:800]}]
        public: list[dict[str, str]] = []
        text_parts: list[str] = []
        self._collect_event_text(event, text_parts)
        for text in text_parts:
            clean = text.strip()
            if clean:
                public.append({"name": "Claude", "status": "text", "detail": clean[:800]})
        self._collect_tool_events(event, public)
        return public

    def check(self, config: dict[str, Any]) -> dict[str, Any]:
        executable = self._claude_executable(config)
        if not executable:
            return {
                "ok": False,
                "message": "未找到 Claude Code CLI。请在 Steam Deck 上安装 Claude Code，并确认 `claude` 在 PATH 中。",
                "provider": "claude-code-cli",
            }
        if self._uses_deepseek(config):
            return self._check_deepseek_cli(executable, config)
        try:
            completed = subprocess.run(
                [executable, "auth", "status"],
                cwd=str(self._home_root()),
                env=self._env(os.environ, config),
                text=True,
                capture_output=True,
                timeout=15,
            )
        except Exception as exc:
            return {
                "ok": False,
                "message": f"Claude Code auth 检测失败：{exc}",
                "provider": "claude-code-cli",
            }
        if completed.returncode != 0:
            return {
                "ok": False,
                "message": f"Claude Code CLI 未登录或不可用：{(completed.stderr or completed.stdout).strip()}",
                "provider": "claude-code-cli",
            }
        return {
            "ok": True,
            "message": "Claude Code CLI 可用。",
            "provider": "claude-code-cli",
        }

    def _check_deepseek_cli(self, executable: str, config: dict[str, Any]) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                [executable, "--version"],
                cwd=str(self._home_root()),
                env=self._env(os.environ, config),
                text=True,
                capture_output=True,
                timeout=15,
            )
        except Exception as exc:
            return {
                "ok": False,
                "message": f"Claude Code CLI 检测失败：{exc}",
                "provider": "claude-code-cli",
            }
        if completed.returncode != 0:
            return {
                "ok": False,
                "message": f"Claude Code CLI 不可用：{(completed.stderr or completed.stdout).strip()}",
                "provider": "claude-code-cli",
            }
        version = (completed.stdout or completed.stderr).strip()
        return {
            "ok": True,
            "message": f"Claude Code CLI 可用，已配置 DeepSeek。{version}",
            "provider": "claude-code-cli",
        }

    def _command(self, executable: str, prompt: str, config: dict[str, Any]) -> list[str]:
        command = [
            executable,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--tools",
            "default",
            "WebSearch",
            "WebFetch",
            "--allowedTools",
            "WebSearch",
            "WebFetch",
            "WebFetch(domain:*)",
            "--permission-mode",
            self._permission_mode(config),
            "--add-dir",
            str(self._home_root()),
            "--append-system-prompt",
            self._system_prompt(config),
        ]
        session_id = str(config.get("claude_session_id", "")).strip()
        if self._is_uuid(session_id):
            if self._as_bool(config.get("claude_session_resume", False)):
                command.extend(["--resume", session_id])
            else:
                command.extend(["--session-id", session_id])
        if str(config.get("claude_bare_mode", "")).strip().lower() in ("1", "true", "yes", "on"):
            command.append("--bare")
        return command

    def _compose_prompt(self, prompt: str, request: dict[str, Any], config: dict[str, Any]) -> str:
        sections: list[str] = []
        game = request.get("game") if isinstance(request.get("game"), dict) else {}
        appid = str(game.get("appid", "")).strip() if isinstance(game, dict) else ""
        game_name = str(game.get("name", "")).strip() if isinstance(game, dict) else ""
        if appid:
            sections.extend(
                [
                    "当前 Steam 游戏上下文：",
                    f"- appid: {appid}",
                    f"- name: {game_name or '未知游戏名'}",
                ]
            )
        session_id = str(config.get("claude_session_id", "")).strip()
        if session_id:
            sections.extend(["Claude Code 会话：", f"- session_id: {session_id}"])

        steam_context = self._steam_context(request, config)
        if steam_context:
            sections.extend(["Steam 事实上下文：", steam_context])

        history_lines = []
        try:
            max_history = max(0, min(int(config.get("max_history", 16)), 40))
        except (TypeError, ValueError):
            max_history = 16
        if not session_id:
            for item in request.get("history", [])[-max_history:]:
                role = str(item.get("role", "user"))
                content = str(item.get("text", item.get("content", ""))).strip()
                if content:
                    history_lines.append(f"{role}: {content}")
        if history_lines:
            sections.extend(["下面是当前 Decky 对话上下文：", "\n".join(history_lines)])
        if not sections:
            return prompt
        return "\n\n".join([*sections, "用户最新请求：", prompt])

    def _steam_context(self, request: dict[str, Any], config: dict[str, Any]) -> str:
        try:
            client = SteamClient(config)
            status = client.status()
        except Exception as exc:
            return f"Steam 状态读取失败: {exc}"

        lines: list[str] = []
        game = request.get("game") if isinstance(request.get("game"), dict) else {}
        appid = self._to_int(game.get("appid")) if isinstance(game, dict) else 0
        game_name = str(game.get("name", "")).strip() if isinstance(game, dict) else ""
        running = status.get("running_game") if isinstance(status.get("running_game"), dict) else {}
        if not appid and running:
            appid = self._to_int(running.get("appid"))
            game_name = str(running.get("name", "")).strip()
        if appid or game_name:
            lines.append(f"当前运行游戏: {game_name or '未知游戏名'} (appid {appid or '未知'})")
        elif running:
            lines.append(f"当前运行游戏: {running.get('name', '未知游戏名')} (appid {running.get('appid', '未知')})")
        else:
            lines.append("当前运行游戏: 未检测到")

        steam_id = str(status.get("steam_id", "")).strip()
        lines.append(f"SteamID64: {steam_id or '未检测到'}")
        has_api_key = bool(status.get("has_api_key"))
        lines.append(f"Steam Web API Key: {'已配置' if has_api_key else '未配置'}")
        if not has_api_key:
            lines.append("云端完整游戏库、总游玩时长和个人成就通常需要 Steam Web API Key；未配置时只能可靠读取本机已安装游戏清单。")

        try:
            local = client.local_installed_games()
            local_games = list(local.get("games", [])) if isinstance(local, dict) else []
        except Exception as exc:
            local_games = []
            lines.append(f"本机 Steam 清单读取失败: {exc}")
        lines.append(f"本机已安装游戏数量: {len(local_games)}")
        current = self._find_game(local_games, appid, game_name)
        if current:
            lines.append(
                "当前游戏本机清单: "
                f"{current.get('name', '')} appid={current.get('appid', '')} "
                f"library={current.get('library_path', '')}"
            )
        sample_games = self._prioritized_games(local_games, current, 50)
        if sample_games:
            lines.append("本机已安装游戏样例（可按 appid/name 继续读取 Steam appmanifest 获取完整清单）:")
            for game_item in sample_games:
                lines.append(
                    "- "
                    f"{game_item.get('appid', '')} | {game_item.get('name', '')} | "
                    f"{game_item.get('library_path', '')}"
                )

        if has_api_key:
            try:
                owned = client.owned_games(limit=80)
                if owned.get("ok"):
                    lines.append(
                        f"Steam Web API 游戏库: source={owned.get('source')} count={owned.get('game_count', len(owned.get('games', [])))}"
                    )
                    for game_item in owned.get("games", [])[:30]:
                        lines.append(
                            "- API库 "
                            f"{game_item.get('appid', '')} | {game_item.get('name', '')} | "
                            f"总时长分钟={game_item.get('playtime_forever_minutes', 0)} | "
                            f"两周分钟={game_item.get('playtime_2weeks_minutes', 0)}"
                        )
                else:
                    lines.append(f"Steam Web API 游戏库读取失败: {owned.get('message', '未知错误')}")
            except Exception as exc:
                lines.append(f"Steam Web API 游戏库读取失败: {exc}")

            if appid:
                try:
                    achievements = client.achievements(appid)
                    if achievements.get("ok"):
                        lines.append(
                            "当前游戏个人成就: "
                            f"{achievements.get('achieved', 0)}/{achievements.get('total', 0)} "
                            f"{achievements.get('game_name', '')}"
                        )
                    else:
                        lines.append(f"当前游戏个人成就读取失败: {achievements.get('message', '未知错误')}")
                except Exception as exc:
                    lines.append(f"当前游戏个人成就读取失败: {exc}")

        return "\n".join(lines)

    def _find_game(self, games: list[dict[str, Any]], appid: int, name: str) -> dict[str, Any] | None:
        if appid:
            for game in games:
                if self._to_int(game.get("appid")) == appid:
                    return game
        name_clean = name.strip().lower()
        if name_clean:
            for game in games:
                if str(game.get("name", "")).strip().lower() == name_clean:
                    return game
        return None

    def _prioritized_games(
        self,
        games: list[dict[str, Any]],
        current: dict[str, Any] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen: set[int] = set()
        if current:
            selected.append(current)
            appid = self._to_int(current.get("appid"))
            if appid:
                seen.add(appid)
        for game in games:
            appid = self._to_int(game.get("appid"))
            if appid and appid in seen:
                continue
            selected.append(game)
            if appid:
                seen.add(appid)
            if len(selected) >= limit:
                break
        return selected

    def _to_int(self, value: Any) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return 0

    def _runtime_config(self, config: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        runtime = dict(config)
        session_id = str(request.get("claude_session_id", "")).strip()
        if self._is_uuid(session_id):
            runtime["claude_session_id"] = session_id
        if "claude_session_resume" in request:
            runtime["claude_session_resume"] = self._as_bool(request.get("claude_session_resume"))
        return runtime

    def _is_uuid(self, value: str) -> bool:
        try:
            uuid.UUID(value)
        except (TypeError, ValueError):
            return False
        return True

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _system_prompt(self, config: dict[str, Any]) -> str:
        base = str(config.get("system_prompt", "")).strip()
        bridge = (
            "你运行在 Steam Deck 的 Decky 插件中。默认使用简体中文回答。"
            "你是 Claude Code CLI agent，可以主动读取 /home/deck 下的文件、检查 Steam 日志、提出或执行诊断命令。"
            "当用户提到“这款游戏”“当前游戏”“卡顿”“掉帧”“崩溃”时，必须先尝试确认正在运行的 Steam 游戏；"
            "不要从最近游玩记录或游戏库猜测当前游戏。"
            "如果没有检测到正在运行的游戏，要明确说明并要求用户先启动游戏或提供游戏名。"
            "优先基于事实、日志和命令输出分析，不要编造游戏名、路径或诊断结果。"
            "当问题涉及最新补丁、兼容性、性能问题、攻略、报错信息或外部资料时，优先使用 WebSearch 和 WebFetch 查询联网资料。"
            "可访问目录至少包括 /home/deck；敏感凭据、token、密码、SSH 私钥不要读取或输出。"
        )
        return f"{base}\n\n{bridge}" if base else bridge

    def _parse_stream_json(self, output: str) -> tuple[str, list[dict[str, str]]]:
        text_parts: list[str] = []
        result_text = ""
        tool_events: list[dict[str, str]] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                text_parts.append(line)
                continue
            event_type = str(event.get("type", ""))
            if event_type == "result":
                result_text = str(event.get("result") or event.get("text") or event.get("message") or "")
            self._collect_event_text(event, text_parts)
            self._collect_tool_events(event, tool_events)
        message = result_text.strip() or "\n".join(part for part in text_parts if part).strip()
        return message, tool_events

    def _collect_event_text(self, event: Any, parts: list[str]) -> None:
        if isinstance(event, dict):
            if event.get("type") == "text" and event.get("text"):
                parts.append(str(event["text"]))
                return
            for key in ("content", "message"):
                self._collect_event_text(event.get(key), parts)
        elif isinstance(event, list):
            for item in event:
                self._collect_event_text(item, parts)

    def _collect_tool_events(self, event: Any, events: list[dict[str, str]]) -> None:
        if isinstance(event, dict):
            if event.get("type") in ("tool_use", "tool_result"):
                name = str(event.get("name") or event.get("tool_name") or event.get("type"))
                detail = self._tool_event_detail(name, str(event.get("type")), event)
                events.append({"name": name, "status": str(event.get("type")), "detail": detail})
            for value in event.values():
                self._collect_tool_events(value, events)
        elif isinstance(event, list):
            for item in event:
                self._collect_tool_events(item, events)

    def _tool_event_detail(self, name: str, event_type: str, event: dict[str, Any]) -> str:
        if event_type == "tool_result":
            return "工具已返回结果"
        payload = event.get("input")
        if not isinstance(payload, dict):
            return "已调用工具"
        lower_name = name.lower()
        if lower_name == "bash" and payload.get("command"):
            return self._compact_text(str(payload["command"]), 80)
        if lower_name == "websearch" and payload.get("query"):
            return self._compact_text(f"搜索：{payload['query']}", 80)
        if lower_name == "webfetch" and payload.get("url"):
            return self._compact_text(f"抓取：{payload['url']}", 80)
        for key in ("path", "file_path", "pattern"):
            if payload.get(key):
                return self._compact_text(f"{key}: {payload[key]}", 80)
        return "已调用工具"

    def _compact_text(self, value: str, limit: int) -> str:
        text = " ".join(value.split())
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    def _claude_executable(self, config: dict[str, Any]) -> str:
        configured = str(config.get("claude_code_path", "")).strip()
        if configured:
            path = Path(configured).expanduser()
            if path.exists() and os.access(path, os.X_OK):
                return str(path)
        bundled = self._bundled_claude_executable()
        if bundled:
            return bundled
        return shutil.which("claude") or ""

    def _bundled_claude_executable(self) -> str:
        path = self.plugin_root / "bin" / "claude" / "claude"
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
        return ""

    def _permission_mode(self, config: dict[str, Any]) -> str:
        value = str(config.get("claude_permission_mode", "plan")).strip()
        return value if value in {"default", "acceptEdits", "plan", "auto", "dontAsk"} else "plan"

    def _timeout(self, config: dict[str, Any]) -> int:
        try:
            return max(30, min(int(config.get("claude_timeout_seconds", MAX_CLAUDE_SECONDS)), 1800))
        except (TypeError, ValueError):
            return MAX_CLAUDE_SECONDS

    def _home_root(self) -> Path:
        for value in (os.environ.get("HOME"), Path.home(), *DEFAULT_HOME_CANDIDATES):
            try:
                path = Path(str(value)).expanduser().resolve()
            except Exception:
                continue
            if path.exists() and path.is_dir() and path.name == "deck":
                return path
        return Path.home().resolve()

    def _env(self, source: dict[str, str] | os._Environ[str], config: dict[str, Any] | None = None) -> dict[str, str]:
        env = {key: str(value) for key, value in dict(source).items()}
        for key in SHELL_ENV_BLOCKLIST:
            env.pop(key, None)
        env.setdefault("HOME", str(self._home_root()))
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        env.setdefault("LANG", "C.UTF-8")
        env["DISABLE_AUTOUPDATER"] = "1"
        self._apply_model_provider_env(env, config or {})
        return env

    def _apply_model_provider_env(self, env: dict[str, str], config: dict[str, Any]) -> None:
        api_key = str(config.get("api_key", "")).strip()
        endpoint = str(config.get("endpoint", "")).strip().rstrip("/")
        model = self._deepseek_model(config)
        if not api_key or not self._is_deepseek_endpoint(endpoint):
            return

        if endpoint.endswith("/anthropic"):
            base_url = endpoint
        else:
            base_url = f"{endpoint}/anthropic"

        env["ANTHROPIC_BASE_URL"] = base_url
        env["ANTHROPIC_AUTH_TOKEN"] = api_key
        env["ANTHROPIC_MODEL"] = model
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = "deepseek-v4-flash"
        env["CLAUDE_CODE_SUBAGENT_MODEL"] = "deepseek-v4-flash"
        env["CLAUDE_CODE_EFFORT_LEVEL"] = "max"

    def _uses_deepseek(self, config: dict[str, Any]) -> bool:
        return bool(str(config.get("api_key", "")).strip()) and self._is_deepseek_endpoint(
            str(config.get("endpoint", "")).strip()
        )

    def _is_deepseek_endpoint(self, endpoint: str) -> bool:
        return "deepseek.com" in endpoint.lower()

    def _deepseek_model(self, config: dict[str, Any]) -> str:
        model = str(config.get("model", "deepseek-v4-pro")).strip() or "deepseek-v4-pro"
        if model in {"deepseek-chat", "deepseek-reasoner"}:
            model = "deepseek-v4-flash"
        if model == "deepseek-v4-pro":
            return "deepseek-v4-pro[1m]"
        return model

    def _result(
        self,
        ok: bool,
        message: str,
        config: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "message": message,
            "provider": "claude-code-cli",
            "model": str(config.get("claude_model", "claude-code")).strip() or "claude-code",
            "endpoint": "claude-code-cli",
            "metadata": metadata or {},
        }
