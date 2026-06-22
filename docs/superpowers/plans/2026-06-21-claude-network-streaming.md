# Claude Network and Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grant Claude Code WebSearch/WebFetch permission and show observable tool progress in the chat UI while a request is running.

**Architecture:** Keep the existing one-shot `ask_ai` method for compatibility, and add a stream-session API on the same Python backend. The backend starts a `claude -p --output-format stream-json` subprocess in a daemon thread, stores parsed public events in memory, and the frontend polls for new events until the final response is ready.

**Tech Stack:** Python threads and subprocess streaming, Decky callable methods, React polling with existing message/tool trace rendering.

---

### Task 1: Claude Code Network Permission

**Files:**
- Modify: `py_modules/decky_ai_chat/claude_code.py`
- Test: `tests/test_claude_code_backend.py`

- [ ] Add a failing test that `_command()` includes `--allowedTools WebSearch WebFetch` and `--include-partial-messages`.
- [ ] Implement the command flags.
- [ ] Update the system prompt to tell Claude to use WebSearch/WebFetch for current facts.

### Task 2: Backend Stream Sessions

**Files:**
- Modify: `py_modules/decky_ai_chat/claude_code.py`
- Modify: `main.py`
- Test: `tests/test_claude_code_backend.py`

- [ ] Add failing tests for `start_stream()` and `poll_stream()` using a fake `subprocess.Popen`.
- [ ] Implement an in-memory session map keyed by UUID.
- [ ] Parse visible text and tool events from stream-json lines as public events.
- [ ] Return a final `ChatResponse` in `poll_stream()` when the subprocess exits.

### Task 3: Frontend Polling UI

**Files:**
- Modify: `src/index.tsx`

- [ ] Add Decky callables `start_ai_stream` and `poll_ai_stream`.
- [ ] Replace `sendPrompt()` one-shot call with start/poll flow.
- [ ] Show live tool events in the temporary assistant message.
- [ ] Keep fallback to `ask_ai` unnecessary unless stream startup fails.

### Task 4: Verification and Deploy

**Files:**
- Runtime checks only.

- [ ] Run `python3 -m pytest tests -q`.
- [ ] Run `pnpm run typecheck`.
- [ ] Run `pnpm run build`.
- [ ] Deploy to Deck with rsync.
- [ ] Restart plugin loader manually on Deck if needed.
