from pathlib import Path

from py_modules.decky_ai_chat.conversation import ConversationStore


def test_active_conversation_uses_running_game_and_stable_claude_session(tmp_path: Path):
    store = ConversationStore(tmp_path)
    game = {"ok": True, "appid": 620, "name": "Portal 2"}

    first = store.active_conversation(game)
    second = store.active_conversation(game)

    assert first["conversation_id"] == "steam:620"
    assert first["title"] == "Portal 2"
    assert first["game"]["appid"] == 620
    assert first["claude_session_id"] == second["claude_session_id"]
    assert first["claude_session_resume"] is False
    assert first["messages"] == []


def test_append_and_reload_messages_for_game_conversation(tmp_path: Path):
    store = ConversationStore(tmp_path)
    game = {"ok": True, "appid": 620, "name": "Portal 2"}
    conversation = store.active_conversation(game)

    store.append_exchange(
        conversation["conversation_id"],
        {"role": "user", "text": "这款游戏为什么卡顿？"},
        {"role": "assistant", "text": "先检查 Proton 和日志。"},
    )
    reloaded = ConversationStore(tmp_path).active_conversation(game)

    assert [message["role"] for message in reloaded["messages"]] == ["user", "assistant"]
    assert reloaded["claude_session_resume"] is True
    assert reloaded["messages"][0]["text"] == "这款游戏为什么卡顿？"
    assert reloaded["messages"][1]["text"] == "先检查 Proton 和日志。"


def test_clear_only_removes_selected_conversation(tmp_path: Path):
    store = ConversationStore(tmp_path)
    portal = store.active_conversation({"ok": True, "appid": 620, "name": "Portal 2"})
    hades = store.active_conversation({"ok": True, "appid": 1145360, "name": "Hades"})
    store.append_exchange(portal["conversation_id"], {"role": "user", "text": "a"}, {"role": "assistant", "text": "b"})
    store.append_exchange(hades["conversation_id"], {"role": "user", "text": "c"}, {"role": "assistant", "text": "d"})

    cleared = store.clear(portal["conversation_id"])

    assert cleared["conversation_id"] == "steam:620"
    assert cleared["messages"] == []
    assert cleared["claude_session_resume"] is False
    assert store.active_conversation({"ok": True, "appid": 1145360, "name": "Hades"})["messages"][0]["text"] == "c"


def test_clear_resets_claude_session_id(tmp_path: Path):
    store = ConversationStore(tmp_path)
    conversation = store.active_conversation({"ok": True, "appid": 620, "name": "Portal 2"})
    store.append_exchange(conversation["conversation_id"], {"role": "user", "text": "a"}, {"role": "assistant", "text": "b"})
    before_clear = store.active_conversation({"ok": True, "appid": 620, "name": "Portal 2"})

    cleared = store.clear(conversation["conversation_id"])

    assert before_clear["claude_session_id"] != cleared["claude_session_id"]
    assert cleared["claude_session_resume"] is False
