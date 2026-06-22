# Decky AI 助手

Decky AI 助手是一个面向 Steam Deck 游戏模式的 Decky Loader 插件。它把侧边栏聊天界面、Claude Code CLI Bridge、Steam 游戏上下文和手机扫码配置整合到一起，让玩家可以在游戏中直接询问卡顿原因、设置建议、攻略思路、成就信息和本机文件相关问题。

当前后端以 Claude Code CLI Bridge 为核心，可通过 DeepSeek 的 Anthropic 兼容接口驱动。项目默认使用中文界面和中文回答。

## 功能

- Decky 侧边栏中文聊天界面，输入框固定在底部，支持一键滚动到底部。
- 默认 Agent 模式，通过 Claude Code CLI Bridge 调用成熟的工具执行能力。
- 支持 DeepSeek Anthropic 兼容接口，也可按配置接入其他兼容服务。
- 流式显示思考和工具调用摘要，回答结束后自动折叠过程。
- 支持 Markdown、表格、分割线和 KaTeX 数学公式渲染。
- 支持按当前运行的 Steam 游戏建立会话记忆，重新打开同一游戏时自动恢复上下文。
- 自动检测 SteamID、当前运行游戏、本机已安装 Steam 游戏清单。
- 配置 Steam Web API Key 后，可向 Agent 注入云端游戏库、游玩时长、最近游玩和成就摘要。
- 支持手机扫码配置模型 API Key、Steam Web API Key、模型、超时和 TLS 选项。
- Steam Web API 不可用时会回退到本机安装清单，不伪造云端时长和成就。

## 目录结构

- `src/index.tsx`: Decky 前端界面。
- `src/markdown_table.ts`: Markdown 表格解析 helper。
- `main.py`: Decky RPC 入口，负责配置、会话、Steam 状态和 Claude Code Bridge 调用。
- `py_modules/decky_ai_chat/claude_code.py`: Claude Code CLI Bridge。
- `py_modules/decky_ai_chat/config.py`: 持久化配置。
- `py_modules/decky_ai_chat/config_server.py`: 手机扫码配置页。
- `py_modules/decky_ai_chat/conversation.py`: 按游戏关联的会话记忆。
- `py_modules/decky_ai_chat/steam.py`: SteamID、运行游戏、本机库和 Steam Web API 数据读取。
- `scripts/vendor_claude_code.py`: 将 Claude Code CLI 打包进 `bin/claude/`。
- `scripts/package_release.py`: 生成 Decky 可导入 release zip。

## 本地开发

```bash
pnpm install
pnpm run typecheck
pnpm run build
python3 -m pytest tests -q
```

## 打包

首次打包前先准备内置 Claude Code CLI：

```bash
pnpm run vendor:claude
```

生成可通过 Decky 导入的 zip：

```bash
pnpm run package:release
```

输出文件示例：

```text
release/decky-ai-chat-v0.1.0.zip
```

如果需要手动解压到 Decky 插件目录，可以生成带顶层目录的 zip：

```bash
pnpm run package:release-folder
```

输出文件示例：

```text
release/decky-ai-chat-v0.1.0-folder.zip
```

## 部署到 Steam Deck

推荐使用 zip 包部署，不需要把开发机目录直接同步到 Steam Deck。

1. 在开发机运行：

```bash
pnpm run vendor:claude
pnpm run package:release
```

2. 将 `release/decky-ai-chat-v0.1.0.zip` 复制到 Steam Deck。

3. 在 Steam Deck 游戏模式打开 Decky Loader。

4. 进入 Decky 设置或插件管理页面，选择从 zip 文件安装插件。

5. 选择刚复制到 Steam Deck 的 release zip。

6. 安装完成后重启 Decky Loader 或重启 Steam。

如果使用 SSH 复制 zip，可以执行：

```bash
scp release/decky-ai-chat-v0.1.0.zip deck@STEAM_DECK_IP:~/Downloads/
```

然后在 Decky 的插件安装界面选择该 zip。

## 手机扫码配置

1. 部署插件并重启 Decky Loader。
2. 在 Decky 中打开 `AI 助手`。
3. 点击顶部二维码按钮。
4. 用同一 Wi-Fi 下的手机扫码。
5. 填写模型 API Key、模型、Steam Web API Key 等信息并保存。

手机配置服务默认从 `28888` 端口开始尝试。URL 带一次随机 token，只建议在可信局域网内使用。

## Steam 数据说明

- 不配置 Steam Web API Key 时，插件只能可靠读取 SteamID、当前运行游戏和本机已安装游戏清单。
- 配置 Steam Web API Key 后，才能读取完整云端库、总游玩时长、最近游玩和个人成就。
- Steam API 超时或证书异常时，插件会回退到本机安装清单。
- SteamID 和 API Key 保存在 Steam Deck 本机 Decky settings 目录，不应该提交到仓库。

## 敏感信息

提交到公开仓库前请确认不要包含以下内容：

- 模型 API Key，例如 DeepSeek、Kimi、OpenAI 或 Anthropic key。
- Steam Web API Key。
- 真实 SteamID64。
- 本机绝对路径、用户名、SSH 配置或 token。
- `release/`、`bin/claude/`、`node_modules/`、`dist/` 等构建产物。

项目中的测试会检查常见 API Key 和真实形态 SteamID64，提交前建议运行：

```bash
python3 -m pytest tests -q
```

也可以手动搜索：

```bash
rg -n --hidden --glob '!.git/**' 'sk-[A-Za-z0-9_-]{12,}|7656119[0-9]{10}|/home/[^/]+'
```

## 远程调试

在 Steam Deck 上启用 SSH：

```bash
passwd
sudo systemctl enable --now sshd
```

在游戏模式启用 CEF Remote Debugging：

```text
Steam 按钮 -> 设置 -> 系统 -> 启用开发者模式
Steam 按钮 -> 设置 -> 开发者 -> Enable CEF Remote Debugging
```

重启 Steam 后，在开发机开隧道：

```bash
ssh -L 8080:127.0.0.1:8080 deck@STEAM_DECK_IP
```

浏览器打开：

```text
http://localhost:8080
```

后端日志：

```bash
journalctl -u plugin_loader -f
```
