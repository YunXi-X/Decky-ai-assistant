from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from py_modules.decky_ai_chat import claude_code
from py_modules.decky_ai_chat.claude_code import ClaudeCodeBackend


TEST_STEAM_ID = "TEST_STEAM_ID"


class _FakeStdout:
    def __init__(self, lines: list[str]):
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)


class _FakePopen:
    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.stdout = _FakeStdout(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {"type": "text", "text": "我先联网查询。"},
                                {"type": "tool_use", "name": "WebSearch", "input": {"query": "Steam Deck game stutter"}},
                            ]
                        },
                    }
                )
                + "\n",
                json.dumps({"type": "result", "result": "结论：需要检查 Proton 和帧率限制。"}) + "\n",
            ]
        )
        self.stderr = _FakeStdout([])
        self.returncode = 0

    def wait(self, timeout=None):
        self.returncode = 0
        return 0


def test_check_reports_missing_claude_binary(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: None)
    backend = ClaudeCodeBackend(plugin_root=tmp_path)

    result = backend.check({})

    assert result["ok"] is False
    assert "Claude Code CLI" in result["message"]


def test_check_reports_auth_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: "/usr/bin/claude")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="not logged in")

    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    backend = ClaudeCodeBackend(plugin_root=tmp_path)

    result = backend.check({})

    assert result["ok"] is False
    assert "auth" in result["message"].lower() or "登录" in result["message"]


def test_check_accepts_deepseek_api_key_without_claude_login(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: "/usr/bin/claude")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="2.1.185 (Claude Code)", stderr="")

    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    backend = ClaudeCodeBackend(plugin_root=tmp_path)

    result = backend.check(
        {
            "endpoint": "https://api.deepseek.com",
            "api_key": "sk-test",
            "model": "deepseek-v4-pro",
        }
    )

    assert result["ok"] is True
    assert captured["command"] == ["/usr/bin/claude", "--version"]
    assert captured["kwargs"]["env"]["ANTHROPIC_AUTH_TOKEN"] == "sk-test"
    assert "DeepSeek" in result["message"]


def test_uses_bundled_claude_before_path_binary(tmp_path: Path, monkeypatch):
    bundled = tmp_path / "bin" / "claude" / "claude"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("#!/bin/sh\n", encoding="utf-8")
    bundled.chmod(0o755)
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: "/usr/bin/claude")
    backend = ClaudeCodeBackend(plugin_root=tmp_path)

    assert backend._claude_executable({}) == str(bundled)


def test_configured_claude_path_still_overrides_bundled_binary(tmp_path: Path, monkeypatch):
    bundled = tmp_path / "bin" / "claude" / "claude"
    configured = tmp_path / "custom" / "claude"
    bundled.parent.mkdir(parents=True)
    configured.parent.mkdir(parents=True)
    bundled.write_text("#!/bin/sh\n", encoding="utf-8")
    configured.write_text("#!/bin/sh\n", encoding="utf-8")
    bundled.chmod(0o755)
    configured.chmod(0o755)
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: "/usr/bin/claude")
    backend = ClaudeCodeBackend(plugin_root=tmp_path)

    assert backend._claude_executable({"claude_code_path": str(configured)}) == str(configured)


def test_ask_invokes_claude_with_home_access_and_permission_mode(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(claude_code, "DEFAULT_HOME_CANDIDATES", (tmp_path / "home" / "deck",))
    (tmp_path / "home" / "deck").mkdir(parents=True)

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"type": "result", "result": "完成"}) + "\n",
            stderr="",
        )

    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    backend = ClaudeCodeBackend(plugin_root=tmp_path / "plugin")

    result = backend.ask_sync(
        {"prompt": "帮我查询当前游戏为什么卡顿"},
        {"claude_permission_mode": "plan", "max_history": 4},
    )

    assert result["ok"] is True
    assert result["message"] == "完成"
    assert "--add-dir" in captured["command"]
    assert str((tmp_path / "home" / "deck").resolve()) in captured["command"]
    assert captured["command"][captured["command"].index("--permission-mode") + 1] == "plan"
    assert captured["kwargs"]["cwd"] == str((tmp_path / "home" / "deck").resolve())
    assert captured["kwargs"]["env"]["DISABLE_AUTOUPDATER"] == "1"


def test_command_allows_web_tools_and_partial_stream(tmp_path: Path):
    backend = ClaudeCodeBackend(plugin_root=tmp_path)

    command = backend._command("/usr/bin/claude", "查询最新补丁", {"claude_permission_mode": "plan"})

    assert "--tools" in command
    tools_index = command.index("--tools")
    enabled_tools = command[tools_index + 1 : command.index("--allowedTools")]
    assert "WebSearch" in enabled_tools
    assert "WebFetch" in enabled_tools
    assert "--allowedTools" in command
    allowed_index = command.index("--allowedTools")
    allowed_tools = command[allowed_index + 1 : command.index("--permission-mode")]
    assert "WebSearch" in allowed_tools
    assert "WebFetch" in allowed_tools
    assert "WebFetch(domain:*)" in allowed_tools
    assert "--include-partial-messages" in command


def test_command_uses_explicit_claude_session_id(tmp_path: Path):
    backend = ClaudeCodeBackend(plugin_root=tmp_path)

    command = backend._command(
        "/usr/bin/claude",
        "继续分析当前游戏",
        {
            "claude_permission_mode": "plan",
            "claude_session_id": "11111111-1111-4111-8111-111111111111",
        },
    )

    assert "--session-id" in command
    assert command[command.index("--session-id") + 1] == "11111111-1111-4111-8111-111111111111"
    assert "--resume" not in command


def test_command_resumes_existing_claude_session_instead_of_recreating(tmp_path: Path):
    backend = ClaudeCodeBackend(plugin_root=tmp_path)

    command = backend._command(
        "/usr/bin/claude",
        "继续分析当前游戏",
        {
            "claude_permission_mode": "plan",
            "claude_session_id": "11111111-1111-4111-8111-111111111111",
            "claude_session_resume": True,
        },
    )

    assert "--resume" in command
    assert command[command.index("--resume") + 1] == "11111111-1111-4111-8111-111111111111"
    assert "--session-id" not in command


def test_compose_prompt_includes_current_game_and_steam_library_context(tmp_path: Path, monkeypatch):
    class FakeSteamClient:
        def __init__(self, config):
            self.config = config

        def status(self):
            return {
                "ok": True,
                "steam_id": TEST_STEAM_ID,
                "has_api_key": False,
                "local_library_count": 2,
                "running_game": {"ok": True, "appid": 368340, "name": "CrossCode"},
            }

        def local_installed_games(self):
            return {
                "ok": True,
                "games": [
                    {"appid": 368340, "name": "CrossCode", "library_path": "/home/deck/.local/share/Steam/steamapps"},
                    {"appid": 620, "name": "Portal 2", "library_path": "/home/deck/.local/share/Steam/steamapps"},
                ],
            }

    monkeypatch.setattr(claude_code, "SteamClient", FakeSteamClient)
    backend = ClaudeCodeBackend(plugin_root=tmp_path)

    prompt = backend._compose_prompt(
        "帮我查询这款游戏为什么会卡顿",
        {"game": {"appid": 368340, "name": "CrossCode"}},
        {"steam_id": "", "steam_api_key": ""},
    )

    assert "Steam 事实上下文" in prompt
    assert "当前运行游戏: CrossCode (appid 368340)" in prompt
    assert f"SteamID64: {TEST_STEAM_ID}" in prompt
    assert "Steam Web API Key: 未配置" in prompt
    assert "本机已安装游戏数量: 2" in prompt
    assert "CrossCode" in prompt
    assert "Portal 2" in prompt


def test_ask_configures_deepseek_anthropic_environment(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(claude_code, "DEFAULT_HOME_CANDIDATES", (tmp_path / "home" / "deck",))
    (tmp_path / "home" / "deck").mkdir(parents=True)

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"type": "result", "result": "完成"}) + "\n",
            stderr="",
        )

    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    backend = ClaudeCodeBackend(plugin_root=tmp_path / "plugin")

    result = backend.ask_sync(
        {"prompt": "检查当前游戏卡顿"},
        {
            "endpoint": "https://api.deepseek.com",
            "api_key": "sk-test",
            "model": "deepseek-v4-pro",
        },
    )

    env = captured["kwargs"]["env"]
    assert result["ok"] is True
    assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-test"
    assert env["ANTHROPIC_MODEL"] == "deepseek-v4-pro[1m]"
    assert env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "deepseek-v4-pro[1m]"
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "deepseek-v4-pro[1m]"
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "deepseek-v4-flash"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "deepseek-v4-flash"
    assert env["CLAUDE_CODE_EFFORT_LEVEL"] == "max"
    assert "sk-test" not in " ".join(captured["command"])


def test_deepseek_anthropic_endpoint_is_not_duplicated(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(claude_code, "DEFAULT_HOME_CANDIDATES", (tmp_path / "home" / "deck",))
    (tmp_path / "home" / "deck").mkdir(parents=True)

    def fake_run(command, **kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"type": "result", "result": "完成"}) + "\n",
            stderr="",
        )

    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    backend = ClaudeCodeBackend(plugin_root=tmp_path / "plugin")

    backend.ask_sync(
        {"prompt": "检查当前游戏卡顿"},
        {
            "endpoint": "https://api.deepseek.com/anthropic",
            "api_key": "sk-test",
            "model": "deepseek-v4-flash",
        },
    )

    env = captured["kwargs"]["env"]
    assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert env["ANTHROPIC_MODEL"] == "deepseek-v4-flash"


def test_stream_json_parser_extracts_text_and_tool_events(tmp_path: Path):
    backend = ClaudeCodeBackend(plugin_root=tmp_path)
    output = "\n".join(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": "先读取当前游戏。"},
                            {"type": "tool_use", "name": "Bash", "input": {"command": "ps aux"}},
                        ]
                    },
                }
            ),
            json.dumps({"type": "result", "result": "结论：当前没有检测到正在运行的游戏。"}),
        ]
    )

    message, events = backend._parse_stream_json(output)

    assert "结论" in message
    assert events[0]["name"] == "Bash"
    assert "ps aux" in events[0]["detail"]


def test_tool_event_summarizes_commands_and_hides_outputs(tmp_path: Path):
    backend = ClaudeCodeBackend(plugin_root=tmp_path)
    long_command = "curl https://example.com/very/long/path " + "x" * 200
    output = "\n".join(
        [
            json.dumps({"type": "tool_use", "name": "Bash", "input": {"command": long_command}}),
            json.dumps({"type": "tool_result", "name": "Bash", "content": "SECRET_OUTPUT" * 30}),
        ]
    )

    _message, events = backend._parse_stream_json(output)

    command_event = events[0]
    result_event = events[1]
    assert command_event["detail"].startswith("curl https://example.com/very/long/path")
    assert len(command_event["detail"]) <= 90
    assert "SECRET_OUTPUT" not in result_event["detail"]
    assert result_event["detail"] == "工具已返回结果"


def test_stream_session_polls_visible_text_and_tool_events(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(claude_code.subprocess, "Popen", _FakePopen)
    backend = ClaudeCodeBackend(plugin_root=tmp_path)

    started = backend.start_stream({"prompt": "帮我查卡顿原因", "history": []}, {})
    assert started["ok"] is True

    deadline = time.time() + 2
    polled = {}
    while time.time() < deadline:
        polled = backend.poll_stream(started["stream_id"], 0)
        if polled.get("done"):
            break
        time.sleep(0.01)

    assert polled["done"] is True
    assert polled["response"]["ok"] is True
    assert "结论" in polled["response"]["message"]
    assert any(event["name"] == "WebSearch" for event in polled["events"])
    assert any("我先联网查询" in event["detail"] for event in polled["events"])
