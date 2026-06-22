# Bundled Claude Code CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle a Linux x64 Claude Code CLI binary inside the Decky plugin so Steam Deck users do not install `claude` globally.

**Architecture:** Add `bin/claude/claude` as a vendored runtime artifact and make the Python bridge resolve it before falling back to `PATH`. Add a vendor script that installs the official npm package into a temporary build directory, copies the native executable, writes a manifest, and disables CLI auto-updates for plugin-launched sessions.

**Tech Stack:** Python 3 scripts and tests, npm package `@anthropic-ai/claude-code`, existing Decky Python backend, existing release zip script.

---

### Task 1: Prefer Bundled CLI

**Files:**
- Modify: `py_modules/decky_ai_chat/claude_code.py`
- Test: `tests/test_claude_code_backend.py`

- [x] Add a failing test that creates `bin/claude/claude` under a temporary plugin root and asserts `_claude_executable({})` returns that path when no configured path and no `PATH` command exist.
- [x] Implement `_bundled_claude_executable()` and update `_claude_executable()` order: configured path, bundled executable, `shutil.which("claude")`.
- [x] Add `DISABLE_AUTOUPDATER=1` to the Claude subprocess environment so a vendored binary does not self-mutate inside the plugin directory.

### Task 2: Vendor Claude Code Binary

**Files:**
- Create: `scripts/vendor_claude_code.py`
- Modify: `package.json`
- Test: `tests/test_vendor_claude_code.py`

- [x] Add a script that runs `npm install --prefix release/.claude-code-build --no-save --omit=dev @anthropic-ai/claude-code`.
- [x] Locate an executable named `claude` under the temporary install tree.
- [x] Copy it to `bin/claude/claude`, chmod `0755`, and write `bin/claude/VENDOR-MANIFEST.json`.
- [x] Add `pnpm run vendor:claude` script.

### Task 3: Release Packaging

**Files:**
- Modify: `scripts/package_release.py`
- Test: `tests/test_package_release.py`

- [x] Include `bin` in runtime paths.
- [x] Add release-time check that `bin/claude/claude` and `bin/claude/VENDOR-MANIFEST.json` exist unless `--allow-missing-claude` is set.
- [x] Keep existing Python vendor checks unchanged.

### Task 4: Verification and Deploy

**Files:**
- Runtime checks only.

- [x] Run focused failing tests before implementation and focused passing tests after implementation.
- [x] Run `python3 -m pytest tests -q`.
- [x] Run `pnpm run typecheck`.
- [x] Run `pnpm run build`.
- [x] Run `pnpm run vendor:claude` with network access.
- [x] Deploy to `deck@192.168.1.3:/home/deck/homebrew/plugins/decky-ai-chat/`.
