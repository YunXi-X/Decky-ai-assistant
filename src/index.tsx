import { staticClasses, TextField } from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, CSSProperties, KeyboardEvent, ReactNode } from "react";
import katex from "katex";
import QRCode from "qrcode";
import { isTableStart, splitTableRow, tableAlignments } from "./markdown_table";
import {
  FaArrowDown,
  FaArrowUp,
  FaCheck,
  FaCog,
  FaQrcode,
  FaRobot,
  FaSave,
  FaTrash,
  FaWifi,
} from "react-icons/fa";

type Role = "assistant" | "user";
type Provider = "openai" | "claude-code-cli";
type ChatMode = "chat" | "agent";

type ToolEvent = {
  name: string;
  status: string;
  detail: string;
  action_id?: string;
};

type ChatMessage = {
  id: string;
  role: Role;
  text: string;
  error?: boolean;
  toolEvents?: ToolEvent[];
  suggestions?: string[];
};

type ChatRequest = {
  prompt: string;
  conversation_id?: string;
  claude_session_id?: string;
  game?: {
    appid?: number;
    name?: string;
  };
  skip_conversation_save?: boolean;
  override_config?: boolean;
  provider?: Provider;
  model?: string;
  endpoint?: string;
  system_prompt?: string;
  temperature?: number;
  max_history?: number;
  ragflow_chat_id?: string;
  ragflow_session_id?: string;
  history: Array<Pick<ChatMessage, "role" | "text">>;
};

type ChatResponse = {
  ok: boolean;
  message: string;
  provider: Provider;
  model: string;
  endpoint: string;
  metadata?: {
    tool_events?: ToolEvent[];
    [key: string]: unknown;
  };
};

type StreamStartResponse = {
  ok: boolean;
  stream_id?: string;
  message?: string;
};

type StreamPollResponse = {
  ok: boolean;
  stream_id?: string;
  events: ToolEvent[];
  cursor: number;
  done: boolean;
  response?: ChatResponse | null;
  message?: string;
};

type BackendConfig = {
  mode: ChatMode;
  provider: Provider;
  endpoint: string;
  model: string;
  system_prompt: string;
  temperature: number;
  max_history: number;
  verify_ssl: boolean;
  ragflow_chat_id: string;
  ragflow_session_id: string;
  has_api_key: boolean;
  steam_id: string;
  steam_include_free_games: boolean;
  steam_cache_seconds: number;
  has_steam_api_key: boolean;
  agent_backend: string;
  claude_code_path: string;
  claude_permission_mode: string;
  claude_timeout_seconds: number;
  claude_bare_mode: boolean;
};

type BackendStatus = {
  ok: boolean;
  message: string;
  provider: Provider;
};

type PairingInfo = {
  ok: boolean;
  url: string;
  host: string;
  port: number;
  token: string;
  message?: string;
};

type SteamStatus = {
  ok: boolean;
  steam_id: string;
  has_api_key: boolean;
  local_library_count: number;
  saved_steam_id?: boolean;
  detected?: {
    ok?: boolean;
    steam_id?: string;
    account_name?: string;
    persona_name?: string;
    source?: string;
    message?: string;
  };
  message?: string;
};

type ActiveConversation = {
  conversation_id: string;
  claude_session_id: string;
  title: string;
  game?: {
    appid?: number;
    name?: string;
  };
  running_game?: {
    ok?: boolean;
    appid?: number;
    name?: string;
    message?: string;
  };
  messages: Array<Pick<ChatMessage, "role" | "text">>;
};

const startAiStream = callable<[request: ChatRequest], StreamStartResponse>(
  "start_ai_stream",
);
const pollAiStream = callable<
  [streamId: string, cursor: number],
  StreamPollResponse
>("poll_ai_stream");
const getConfig = callable<[], BackendConfig>("get_config");
const saveConfig = callable<[updates: Record<string, unknown>], BackendConfig>(
  "save_config",
);
const checkBackend = callable<
  [updates: Record<string, unknown>],
  BackendStatus
>("check_backend");
const getPairingInfo = callable<[], PairingInfo>("get_pairing_info");
const detectSteamStatus = callable<[], SteamStatus>("detect_steam_status");
const getActiveConversation = callable<[], ActiveConversation>(
  "get_active_conversation",
);
const clearActiveConversation = callable<
  [conversationId?: string],
  ActiveConversation
>("clear_active_conversation");

const initialMessages: ChatMessage[] = [];

const quickPrompts = [
  "帮我推荐当前游戏的 Steam Deck 画面和功耗设置。",
  "给我一份无剧透的新手入门策略。",
  "帮我排查这个游戏为什么会卡顿。",
];

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const inputCss = `
.decky-ai-chat-input,
.decky-ai-chat-input * {
  background: transparent !important;
}
.decky-ai-chat-input input,
.decky-ai-chat-input textarea {
  background: transparent !important;
  color: #f4f4f4 !important;
  box-shadow: none !important;
  border-color: transparent !important;
}
.decky-ai-chat-input input::placeholder,
.decky-ai-chat-input textarea::placeholder {
  color: rgba(244, 244, 244, 0.42) !important;
}
.decky-ai-chat-shell {
  position: relative;
}
@keyframes decky-ai-thinking-dot {
  0%, 80%, 100% {
    opacity: 0.28;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
    transform: translateY(-3px);
  }
}
.decky-ai-thinking-dot {
  display: inline-block;
  animation: decky-ai-thinking-dot 1.2s infinite ease-in-out;
}
.decky-ai-thinking-dot:nth-child(2) {
  animation-delay: 0.16s;
}
.decky-ai-thinking-dot:nth-child(3) {
  animation-delay: 0.32s;
}
`;

const styles: Record<string, CSSProperties> = {
  shell: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    minHeight: 0,
    boxSizing: "border-box",
    margin: "-10px -8px 0",
    background: "#151515",
    color: "#f4f4f4",
    overflow: "hidden",
  },
  topBar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "8px",
    flex: "0 0 auto",
    padding: "7px 10px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
    background: "rgba(21, 21, 21, 0.96)",
  },
  modelBlock: {
    display: "flex",
    minWidth: 0,
    flexDirection: "column",
    gap: "2px",
  },
  modelTitle: {
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    fontSize: "14px",
    fontWeight: 700,
  },
  modelStatus: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    fontSize: "11px",
    color: "rgba(244, 244, 244, 0.62)",
  },
  topActions: {
    display: "flex",
    alignItems: "center",
    gap: "7px",
  },
  iconButton: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "30px",
    height: "30px",
    borderRadius: "999px",
    border: "1px solid rgba(255, 255, 255, 0.12)",
    background: "rgba(255, 255, 255, 0.07)",
    color: "#f4f4f4",
    font: "inherit",
  },
  settingsPanel: {
    display: "flex",
    flexDirection: "column",
    gap: "9px",
    padding: "10px 12px 12px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
    background: "#1f1f1f",
  },
  pairingPanel: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "13px",
    padding: "18px 14px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
    background: "#1f1f1f",
  },
  pairingTitle: {
    margin: 0,
    fontSize: "17px",
    fontWeight: 750,
  },
  pairingText: {
    margin: 0,
    maxWidth: "300px",
    textAlign: "center",
    color: "rgba(244, 244, 244, 0.66)",
    fontSize: "12px",
    lineHeight: 1.4,
  },
  qrBox: {
    display: "grid",
    placeItems: "center",
    width: "210px",
    height: "210px",
    borderRadius: "18px",
    background: "#fff",
    padding: "10px",
  },
  qrImage: {
    width: "190px",
    height: "190px",
  },
  pairingUrl: {
    maxWidth: "100%",
    boxSizing: "border-box",
    borderRadius: "12px",
    background: "#151515",
    border: "1px solid rgba(255, 255, 255, 0.10)",
    padding: "9px",
    color: "rgba(244, 244, 244, 0.74)",
    fontSize: "11px",
    overflowWrap: "anywhere",
    textAlign: "center",
  },
  transcript: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    minHeight: 0,
    gap: "15px",
    overflowY: "auto",
    padding: "12px 10px 10px",
    overscrollBehavior: "contain",
    background: "#151515",
  },
  scrollToBottomButton: {
    position: "absolute",
    right: "18px",
    bottom: "62px",
    zIndex: 2,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "34px",
    height: "34px",
    borderRadius: "999px",
    border: "1px solid rgba(255, 255, 255, 0.14)",
    background: "#2b2b2b",
    color: "#f4f4f4",
    boxShadow: "0 8px 20px rgba(0, 0, 0, 0.35)",
    font: "inherit",
  },
  emptyState: {
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    minHeight: "100%",
    gap: "18px",
    padding: "8px 0 22px",
  },
  hero: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "10px",
    textAlign: "center",
  },
  heroMark: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "42px",
    height: "42px",
    borderRadius: "999px",
    background: "#f4f4f4",
    color: "#151515",
    fontSize: "20px",
  },
  heroTitle: {
    margin: 0,
    fontSize: "20px",
    fontWeight: 750,
  },
  heroText: {
    margin: 0,
    maxWidth: "260px",
    color: "rgba(244, 244, 244, 0.62)",
    fontSize: "13px",
    lineHeight: 1.35,
  },
  suggestionGrid: {
    display: "grid",
    gridTemplateColumns: "1fr",
    gap: "8px",
  },
  suggestionButton: {
    width: "100%",
    borderRadius: "14px",
    border: "1px solid rgba(255, 255, 255, 0.10)",
    background: "#222",
    color: "#f4f4f4",
    padding: "12px",
    textAlign: "left",
    font: "inherit",
    fontSize: "13px",
    lineHeight: 1.3,
  },
  messageRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: "9px",
  },
  userRow: {
    justifyContent: "flex-end",
  },
  assistantAvatar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flex: "0 0 auto",
    width: "25px",
    height: "25px",
    marginTop: "3px",
    borderRadius: "999px",
    background: "#f4f4f4",
    color: "#151515",
    fontSize: "13px",
  },
  bubble: {
    maxWidth: "82%",
    padding: "10px 12px",
    lineHeight: 1.42,
    fontSize: "14px",
    overflowWrap: "anywhere",
  },
  assistantMessage: {
    maxWidth: "calc(100% - 36px)",
    paddingLeft: 0,
    color: "#f4f4f4",
  },
  markdown: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  markdownParagraph: {
    margin: 0,
    whiteSpace: "pre-wrap",
  },
  markdownHeading: {
    margin: "2px 0 0",
    fontSize: "15px",
    fontWeight: 750,
  },
  markdownList: {
    margin: 0,
    paddingLeft: "18px",
  },
  markdownCodeBlock: {
    margin: 0,
    maxHeight: "220px",
    overflow: "auto",
    whiteSpace: "pre-wrap",
    borderRadius: "8px",
    background: "#101010",
    border: "1px solid rgba(255, 255, 255, 0.09)",
    padding: "9px",
    fontSize: "11px",
    lineHeight: 1.4,
  },
  markdownInlineCode: {
    borderRadius: "5px",
    background: "rgba(255, 255, 255, 0.09)",
    padding: "1px 4px",
    fontSize: "0.92em",
  },
  markdownLink: {
    color: "#8cc8ff",
    textDecoration: "underline",
  },
  markdownRule: {
    width: "100%",
    border: 0,
    borderTop: "1px solid rgba(255, 255, 255, 0.16)",
    margin: "4px 0",
  },
  markdownQuote: {
    margin: 0,
    borderLeft: "3px solid rgba(255, 255, 255, 0.18)",
    paddingLeft: "10px",
    color: "rgba(244, 244, 244, 0.72)",
  },
  markdownTableWrap: {
    maxWidth: "100%",
    overflowX: "auto",
    borderRadius: "8px",
    border: "1px solid rgba(255, 255, 255, 0.10)",
  },
  markdownTable: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "12px",
  },
  markdownTh: {
    borderBottom: "1px solid rgba(255, 255, 255, 0.14)",
    background: "rgba(255, 255, 255, 0.07)",
    padding: "6px 8px",
    textAlign: "left",
    fontWeight: 750,
  },
  markdownTd: {
    borderTop: "1px solid rgba(255, 255, 255, 0.08)",
    padding: "6px 8px",
    verticalAlign: "top",
  },
  markdownMathBlock: {
    maxWidth: "100%",
    overflowX: "auto",
    borderRadius: "8px",
    background: "rgba(255, 255, 255, 0.06)",
    padding: "9px",
    textAlign: "center",
  },
  markdownMathInline: {
    display: "inline-block",
    maxWidth: "100%",
    overflowX: "auto",
    verticalAlign: "middle",
  },
  userMessage: {
    borderRadius: "18px",
    background: "#303030",
    color: "#f4f4f4",
  },
  errorMessage: {
    borderRadius: "14px",
    background: "rgba(255, 82, 82, 0.12)",
    color: "#ffb7b7",
  },
  toolTrace: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    marginTop: "10px",
    borderTop: "1px solid rgba(255, 255, 255, 0.10)",
    paddingTop: "8px",
  },
  toolEvent: {
    borderRadius: "8px",
    background: "rgba(255, 255, 255, 0.07)",
    padding: "7px 8px",
    fontSize: "11px",
    color: "rgba(244, 244, 244, 0.76)",
  },
  toolTraceToggle: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "8px",
    width: "100%",
    marginTop: "10px",
    border: "1px solid rgba(255, 255, 255, 0.10)",
    borderRadius: "9px",
    background: "rgba(255, 255, 255, 0.06)",
    color: "rgba(244, 244, 244, 0.76)",
    padding: "7px 8px",
    font: "inherit",
    fontSize: "11px",
    textAlign: "left",
  },
  suggestionRow: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    marginTop: "12px",
    borderTop: "1px solid rgba(255, 255, 255, 0.10)",
    paddingTop: "9px",
  },
  suggestionTitle: {
    color: "rgba(244, 244, 244, 0.52)",
    fontSize: "11px",
  },
  followupButton: {
    width: "100%",
    borderRadius: "10px",
    border: "1px solid rgba(255, 255, 255, 0.10)",
    background: "rgba(255, 255, 255, 0.06)",
    color: "#f4f4f4",
    padding: "8px 9px",
    font: "inherit",
    fontSize: "12px",
    lineHeight: 1.3,
    textAlign: "left",
  },
  toolResult: {
    display: "flex",
    flexDirection: "column",
    gap: "7px",
    marginTop: "10px",
    borderRadius: "10px",
    border: "1px solid rgba(140, 200, 255, 0.22)",
    background: "rgba(140, 200, 255, 0.08)",
    padding: "9px",
    fontSize: "12px",
  },
  toolResultTitle: {
    fontWeight: 750,
    color: "#8cc8ff",
  },
  typing: {
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    color: "rgba(244, 244, 244, 0.64)",
  },
  thinkingDots: {
    display: "inline-flex",
    width: "18px",
    justifyContent: "space-between",
    marginLeft: "2px",
  },
  composerWrap: {
    position: "relative",
    zIndex: 1,
    flex: "0 0 auto",
    padding: "6px 8px 8px",
    borderTop: "1px solid rgba(255, 255, 255, 0.08)",
    background: "#151515",
  },
  composer: {
    display: "flex",
    alignItems: "flex-end",
    gap: "8px",
    borderRadius: "22px",
    border: "1px solid rgba(255, 255, 255, 0.12)",
    background: "#242424",
    padding: "5px",
  },
  textarea: {
    flex: 1,
    minWidth: 0,
    minHeight: "22px",
    maxHeight: "110px",
    boxSizing: "border-box",
    resize: "vertical",
    border: 0,
    background: "transparent",
    color: "#f4f4f4",
    padding: "7px 3px 6px",
    font: "inherit",
    fontSize: "14px",
    lineHeight: 1.35,
    outline: "none",
  },
  textFieldWrap: {
    flex: 1,
    minWidth: 0,
    margin: "-6px 0",
    borderRadius: "18px",
    background: "transparent",
    overflow: "hidden",
  },
  compactTextField: {
    minHeight: "32px",
    padding: 0,
    background: "transparent",
    color: "#f4f4f4",
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: "5px",
    fontSize: "12px",
  },
  label: {
    color: "rgba(244, 244, 244, 0.62)",
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    borderRadius: "12px",
    border: "1px solid rgba(255, 255, 255, 0.12)",
    background: "#151515",
    color: "#f4f4f4",
    padding: "8px 9px",
    font: "inherit",
    outline: "none",
  },
  select: {
    width: "100%",
    boxSizing: "border-box",
    borderRadius: "12px",
    border: "1px solid rgba(255, 255, 255, 0.12)",
    background: "#151515",
    color: "#f4f4f4",
    padding: "8px 9px",
    font: "inherit",
    outline: "none",
  },
  settingsActions: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "8px",
  },
  actionButton: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "7px",
    borderRadius: "12px",
    border: "1px solid rgba(255, 255, 255, 0.12)",
    background: "#2b2b2b",
    color: "#f4f4f4",
    padding: "9px",
    font: "inherit",
    fontSize: "13px",
  },
  settingsNote: {
    margin: 0,
    color: "rgba(244, 244, 244, 0.54)",
    fontSize: "11px",
    lineHeight: 1.35,
  },
  sendButton: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "30px",
    height: "30px",
    flex: "0 0 auto",
    borderRadius: "999px",
    border: 0,
    background: "#f4f4f4",
    color: "#151515",
    font: "inherit",
  },
  disabledSend: {
    background: "rgba(244, 244, 244, 0.22)",
    color: "rgba(21, 21, 21, 0.45)",
  },
};

function id(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function isSafeUrl(value: string): boolean {
  return /^(https?:|mailto:)/i.test(value);
}

function renderMath(formula: string, displayMode: boolean, key: string): ReactNode {
  try {
    return (
      <span
        key={key}
        style={displayMode ? styles.markdownMathBlock : styles.markdownMathInline}
        dangerouslySetInnerHTML={{
          __html: katex.renderToString(formula, {
            displayMode,
            output: "mathml",
            throwOnError: false,
            trust: false,
          }),
        }}
      />
    );
  } catch {
    return (
      <code key={key} style={styles.markdownInlineCode}>
        {displayMode ? `$$${formula}$$` : `$${formula}$`}
      </code>
    );
  }
}

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(`[^`]+`|\$[^$\n]+\$|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    if (token.startsWith("`")) {
      nodes.push(
        <code key={key} style={styles.markdownInlineCode}>
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("$")) {
      nodes.push(renderMath(token.slice(1, -1), false, key));
    } else if (token.startsWith("**")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (link && isSafeUrl(link[2])) {
        nodes.push(
          <a key={key} href={link[2]} rel="noreferrer" style={styles.markdownLink}>
            {link[1]}
          </a>,
        );
      } else {
        nodes.push(token);
      }
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function isHorizontalRule(line: string): boolean {
  return /^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(line);
}

function stripBlockquoteMarker(line: string): string {
  return line.replace(/^\s*(?:>\s*)+/, "");
}

function cleanHeadingText(text: string): string {
  return stripBlockquoteMarker(text).replace(/^\s*(?:>\s*)+/, "").trim();
}

function renderTable(
  headerLine: string,
  separatorLine: string,
  rowLines: string[],
  keyPrefix: string,
): ReactNode {
  const headers = splitTableRow(headerLine);
  const alignments = tableAlignments(separatorLine);
  const rows = rowLines.map(splitTableRow);

  return (
    <div key={`${keyPrefix}-table`} style={styles.markdownTableWrap}>
      <table style={styles.markdownTable}>
        <thead>
          <tr>
            {headers.map((header, index) => (
              <th
                key={`${keyPrefix}-th-${index}`}
                style={{
                  ...styles.markdownTh,
                  textAlign: alignments[index] || "left",
                }}
              >
                {renderInlineMarkdown(header, `${keyPrefix}-th-${index}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${keyPrefix}-tr-${rowIndex}`}>
              {headers.map((_, cellIndex) => (
                <td
                  key={`${keyPrefix}-td-${rowIndex}-${cellIndex}`}
                  style={{
                    ...styles.markdownTd,
                    textAlign: alignments[cellIndex] || "left",
                  }}
                >
                  {renderInlineMarkdown(
                    row[cellIndex] || "",
                    `${keyPrefix}-td-${rowIndex}-${cellIndex}`,
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderMarkdownBlocks(lines: string[], keyPrefix: string): ReactNode[] {
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = stripBlockquoteMarker(lines[index]);
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (isHorizontalRule(line)) {
      blocks.push(<hr key={`${keyPrefix}-hr-${index}`} style={styles.markdownRule} />);
      index += 1;
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      blocks.push(
        <div key={`${keyPrefix}-h-${index}`} style={styles.markdownHeading}>
          {renderInlineMarkdown(cleanHeadingText(heading[2]), `${keyPrefix}-h-${index}`)}
        </div>,
      );
      index += 1;
      continue;
    }

    if (isTableStart(lines, index)) {
      const headerLine = lines[index];
      const separatorLine = lines[index + 1];
      const rowLines: string[] = [];
      index += 2;
      while (
        index < lines.length &&
        stripBlockquoteMarker(lines[index]).includes("|") &&
        stripBlockquoteMarker(lines[index]).trim()
      ) {
        rowLines.push(lines[index]);
        index += 1;
      }
      blocks.push(renderTable(headerLine, separatorLine, rowLines, `${keyPrefix}-table-${index}`));
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(stripBlockquoteMarker(lines[index]))) {
        const item = stripBlockquoteMarker(lines[index]).replace(/^\s*[-*]\s+/, "");
        items.push(
          <li key={`${keyPrefix}-ul-${index}`}>
            {renderInlineMarkdown(item, `${keyPrefix}-ul-${index}`)}
          </li>,
        );
        index += 1;
      }
      blocks.push(
        <ul key={`${keyPrefix}-ul-block-${index}`} style={styles.markdownList}>
          {items}
        </ul>,
      );
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(stripBlockquoteMarker(lines[index]))) {
        const item = stripBlockquoteMarker(lines[index]).replace(/^\s*\d+\.\s+/, "");
        items.push(
          <li key={`${keyPrefix}-ol-${index}`}>
            {renderInlineMarkdown(item, `${keyPrefix}-ol-${index}`)}
          </li>,
        );
        index += 1;
      }
      blocks.push(
        <ol key={`${keyPrefix}-ol-block-${index}`} style={styles.markdownList}>
          {items}
        </ol>,
      );
      continue;
    }

    const paragraph: string[] = [];
    while (
      index < lines.length &&
      stripBlockquoteMarker(lines[index]).trim() &&
      !/^(#{1,3})\s+/.test(stripBlockquoteMarker(lines[index])) &&
      !isHorizontalRule(stripBlockquoteMarker(lines[index])) &&
      !isTableStart(lines, index) &&
      !/^\s*[-*]\s+/.test(stripBlockquoteMarker(lines[index])) &&
      !/^\s*\d+\.\s+/.test(stripBlockquoteMarker(lines[index]))
    ) {
      paragraph.push(stripBlockquoteMarker(lines[index]));
      index += 1;
    }
    blocks.push(
      <p key={`${keyPrefix}-p-${index}`} style={styles.markdownParagraph}>
        {renderInlineMarkdown(paragraph.join("\n"), `${keyPrefix}-p-${index}`)}
      </p>,
    );
  }

  return blocks;
}

function renderMarkdown(text: string, keyPrefix: string): ReactNode {
  const blocks: ReactNode[] = [];
  const lines = text.split(/\r?\n/);
  let plainLines: string[] = [];
  let codeLines: string[] = [];
  let mathLines: string[] = [];
  let inCode = false;
  let inMath = false;

  const flushPlain = (index: number) => {
    if (plainLines.length) {
      blocks.push(...renderMarkdownBlocks(plainLines, `${keyPrefix}-plain-${index}`));
      plainLines = [];
    }
  };

  lines.forEach((line, index) => {
    if (line.trim().startsWith("```")) {
      if (inMath) {
        mathLines.push(line);
        return;
      }
      if (inCode) {
        blocks.push(
          <pre key={`${keyPrefix}-code-${index}`} style={styles.markdownCodeBlock}>
            {codeLines.join("\n")}
          </pre>,
        );
        codeLines = [];
        inCode = false;
      } else {
        flushPlain(index);
        inCode = true;
      }
      return;
    }

    if (line.trim().startsWith("$$")) {
      if (inCode) {
        codeLines.push(line);
        return;
      }
      const trimmed = line.trim();
      if (!inMath && trimmed.length > 4 && trimmed.endsWith("$$")) {
        flushPlain(index);
        blocks.push(renderMath(trimmed.slice(2, -2).trim(), true, `${keyPrefix}-math-${index}`));
        return;
      }
      if (inMath) {
        blocks.push(
          renderMath(mathLines.join("\n").trim(), true, `${keyPrefix}-math-${index}`),
        );
        mathLines = [];
        inMath = false;
      } else {
        flushPlain(index);
        inMath = true;
        const rest = trimmed.slice(2).trim();
        if (rest) {
          mathLines.push(rest);
        }
      }
      return;
    }

    if (inCode) {
      codeLines.push(line);
    } else if (inMath) {
      mathLines.push(line);
    } else {
      plainLines.push(line);
    }
  });

  flushPlain(lines.length);
  if (codeLines.length) {
    blocks.push(
      <pre key={`${keyPrefix}-code-tail`} style={styles.markdownCodeBlock}>
        {codeLines.join("\n")}
      </pre>,
    );
  }
  if (mathLines.length) {
    blocks.push(renderMath(mathLines.join("\n").trim(), true, `${keyPrefix}-math-tail`));
  }

  return <div style={styles.markdown}>{blocks}</div>;
}

function ThinkingDots() {
  return (
    <span aria-label="思考中" style={styles.thinkingDots}>
      <span className="decky-ai-thinking-dot">.</span>
      <span className="decky-ai-thinking-dot">.</span>
      <span className="decky-ai-thinking-dot">.</span>
    </span>
  );
}

function compactTraceDetail(value: string, limit = 90): string {
  const clean = value.replace(/\s+/g, " ").trim();
  if (clean.length <= limit) {
    return clean;
  }
  return `${clean.slice(0, limit - 1).trim()}…`;
}

function recommendedQuestions(answer: string, gameName?: string): string[] {
  const text = answer.toLowerCase();
  const target = gameName ? `这款游戏（${gameName}）` : "这款游戏";
  if (/卡顿|掉帧|帧率|性能|stutter|fps|proton|兼容/.test(answer) || /stutter|fps/.test(text)) {
    return [
      `继续帮我排查${target}卡顿的最可能原因`,
      `帮我推荐${target}的 Steam Deck 画面和功耗设置`,
      `帮我查看${target}相关日志里有没有异常`,
    ];
  }
  if (/成就|游戏库|时长|steam api|appid|游玩/.test(answer) || /achievement|playtime|library/.test(text)) {
    return [
      "帮我查询这款游戏的成就进度",
      "帮我总结我在 Steam 库里的相关游玩数据",
      "帮我根据游玩时长推荐下一步要玩的游戏",
    ];
  }
  if (/报错|错误|崩溃|crash|error|日志|log/.test(answer) || /crash|error|log/.test(text)) {
    return [
      `继续分析${target}的报错日志`,
      "给我一份下一步排查清单",
      "帮我生成可以安全执行的诊断命令",
    ];
  }
  return [
    "把刚才的结论整理成可执行步骤",
    "继续深入分析最可能的问题",
    "还有哪些信息需要我补充？",
  ];
}

function Content() {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("decky-local");
  const [endpoint, setEndpoint] = useState("https://api.deepseek.com");
  const [apiKey, setApiKey] = useState("");
  const [hasApiKey, setHasApiKey] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState(
    "你是运行在 Steam Deck 游戏模式中的中文 AI 助手。请默认使用简体中文回答，除非用户明确要求其他语言。回答应简洁、具体、可执行。",
  );
  const [temperature, setTemperature] = useState(0.7);
  const [maxHistory, setMaxHistory] = useState(16);
  const [verifySsl, setVerifySsl] = useState(true);
  const [ragflowChatId, setRagflowChatId] = useState("");
  const [ragflowSessionId, setRagflowSessionId] = useState("");
  const [steamId, setSteamId] = useState("");
  const [steamApiKey, setSteamApiKey] = useState("");
  const [hasSteamApiKey, setHasSteamApiKey] = useState(false);
  const [steamIncludeFreeGames, setSteamIncludeFreeGames] = useState(true);
  const [steamCacheSeconds, setSteamCacheSeconds] = useState(1800);
  const [steamStatus, setSteamStatus] = useState<SteamStatus | null>(null);
  const [activeConversation, setActiveConversation] = useState<ActiveConversation | null>(null);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [isDetectingSteam, setIsDetectingSteam] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showPairing, setShowPairing] = useState(false);
  const [pairingInfo, setPairingInfo] = useState<PairingInfo | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [pairingError, setPairingError] = useState("");
  const [expandedTraceIds, setExpandedTraceIds] = useState<Set<string>>(() => new Set());
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const messagesRef = useRef<ChatMessage[]>(initialMessages);

  const canSend = useMemo(
    () => prompt.trim().length > 0 && !isSending,
    [isSending, prompt],
  );

  const hasConversation = messages.length > 0;

  const updateScrollButton = () => {
    const transcript = transcriptRef.current;
    if (!transcript) {
      return;
    }
    const distanceFromBottom =
      transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight;
    setShowScrollToBottom(distanceFromBottom > 120);
  };

  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    const transcript = transcriptRef.current;
    if (!transcript) {
      return;
    }
    transcript.scrollTo({
      top: transcript.scrollHeight,
      behavior,
    });
    setShowScrollToBottom(false);
  };

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (!transcript) {
      messagesRef.current = messages;
      return;
    }

    const distanceFromBottom =
      transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight;
    if (isSending || distanceFromBottom < 160) {
      scrollToBottom("smooth");
    } else {
      updateScrollButton();
    }
    messagesRef.current = messages;
  }, [isSending, messages]);

  useEffect(() => {
    void loadConfig();
    void loadActiveConversation();
  }, []);

  useEffect(() => {
    if (!showPairing) {
      return;
    }
    void loadPairingInfo();
  }, [showPairing]);

  const applyConfig = (config: BackendConfig) => {
    setEndpoint(config.endpoint || "https://api.deepseek.com");
    setModel(config.model || "decky-local");
    setSystemPrompt(config.system_prompt || "");
    setTemperature(Number(config.temperature ?? 0.7));
    setMaxHistory(Number(config.max_history ?? 16));
    setVerifySsl(Boolean(config.verify_ssl ?? true));
    setRagflowChatId(config.ragflow_chat_id || "");
    setRagflowSessionId(config.ragflow_session_id || "");
    setHasApiKey(Boolean(config.has_api_key));
    setSteamId(config.steam_id || "");
    setSteamIncludeFreeGames(Boolean(config.steam_include_free_games ?? true));
    setSteamCacheSeconds(Number(config.steam_cache_seconds ?? 1800));
    setHasSteamApiKey(Boolean(config.has_steam_api_key));
    setSteamApiKey("");
    setApiKey("");
  };

  const loadConfig = async () => {
    try {
      applyConfig(await getConfig());
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "后端配置加载失败";
      toaster.toast({ title: "配置加载失败", body: message });
    }
  };

  const loadActiveConversation = async () => {
    setIsLoadingConversation(true);
    try {
      const conversation = await getActiveConversation();
      setActiveConversation(conversation);
      const restoredMessages = conversation.messages.map((message, index) => ({
        id: id(`restored-${message.role}-${index}`),
        role: message.role,
        text: message.text,
      }));
      setMessages(restoredMessages);
      messagesRef.current = restoredMessages;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "会话加载失败";
      toaster.toast({ title: "会话加载失败", body: message });
    } finally {
      setIsLoadingConversation(false);
    }
  };

  const configPayload = (includeApiKey: boolean) => ({
    mode: "agent",
    provider: "claude-code-cli",
    endpoint,
    model,
    api_key: includeApiKey ? apiKey : "__KEEP__",
    system_prompt: systemPrompt,
    temperature,
    max_history: maxHistory,
    verify_ssl: verifySsl,
    ragflow_chat_id: ragflowChatId,
    ragflow_session_id: ragflowSessionId,
    steam_id: steamId,
    steam_api_key: steamApiKey.length > 0 ? steamApiKey : "__KEEP__",
    steam_include_free_games: steamIncludeFreeGames,
    steam_cache_seconds: steamCacheSeconds,
  });

  const saveSettings = async () => {
    setIsSaving(true);
    try {
      applyConfig(await saveConfig(configPayload(apiKey.length > 0)));
      toaster.toast({ title: "设置已保存", body: "已更新后端配置。" });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "设置保存失败";
      toaster.toast({ title: "设置保存失败", body: message });
    } finally {
      setIsSaving(false);
    }
  };

  const testBackend = async () => {
    try {
      const status = await checkBackend(configPayload(apiKey.length > 0));
      toaster.toast({
        title: status.ok ? "后端配置可用" : "后端配置不可用",
        body: status.message,
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "后端检查失败";
      toaster.toast({ title: "后端测试失败", body: message });
    }
  };

  const connectSteam = async () => {
    setIsDetectingSteam(true);
    try {
      const status = await detectSteamStatus();
      setSteamStatus(status);
      if (status.steam_id) {
        setSteamId(status.steam_id);
        setHasSteamApiKey(Boolean(status.has_api_key));
        toaster.toast({
          title: "Steam 已连接",
          body: `检测到 SteamID64：${status.steam_id}`,
        });
      } else {
        toaster.toast({
          title: "未检测到 Steam 账号",
          body: status.message || status.detected?.message || "请确认 Steam 已在此 Deck 登录过。",
        });
      }
      await loadConfig();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Steam 连接失败";
      toaster.toast({ title: "Steam 连接失败", body: message });
    } finally {
      setIsDetectingSteam(false);
    }
  };

  const loadPairingInfo = async () => {
    setPairingError("");
    setQrDataUrl("");
    try {
      const info = await getPairingInfo();
      setPairingInfo(info);
      if (!info.ok || !info.url) {
        setPairingError(info.message || "Phone setup server did not return a URL.");
        return;
      }
      try {
        setQrDataUrl(await QRCode.toDataURL(info.url, {
          width: 190,
          margin: 1,
          color: {
            dark: "#151515",
            light: "#ffffff",
          },
        }));
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "二维码生成失败";
        setPairingError(`二维码生成失败：${message}`);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "无法打开手机配置页";
      setPairingError(message);
      toaster.toast({ title: "手机配置页打开失败", body: message });
    }
  };

  const sendPrompt = async (value = prompt) => {
    const cleanPrompt = value.trim();
    if (!cleanPrompt || isSending) {
      return;
    }

    const userMessage: ChatMessage = {
      id: id("user"),
      role: "user",
      text: cleanPrompt,
    };

    setPrompt("");
    setIsSending(true);
    const assistantId = id("assistant-stream");
    const streamingMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      text: "正在启动 Claude Code...",
      toolEvents: [
        {
          name: "Claude Code",
          status: "start",
          detail: "正在启动内置 Claude Code CLI，并准备联网查询权限。",
        },
      ],
    };
    setMessages((current) => [...current, userMessage, streamingMessage]);

    try {
      const history = [...messages, userMessage].map(({ role, text }) => ({
        role,
        text,
      }));
      const start = await startAiStream({
        prompt: cleanPrompt,
        conversation_id: activeConversation?.conversation_id,
        claude_session_id: activeConversation?.claude_session_id,
        game: activeConversation?.game,
        history,
      });
      if (!start.ok || !start.stream_id) {
        throw new Error(start.message || "无法启动 Claude Code 流式会话");
      }

      let cursor = 0;
      const allEvents: ToolEvent[] = [...(streamingMessage.toolEvents || [])];
      for (;;) {
        await sleep(500);
        const poll = await pollAiStream(start.stream_id, cursor);
        if (!poll.ok) {
          throw new Error(poll.message || "Claude Code 流式会话读取失败");
        }
        cursor = poll.cursor;
        if (poll.events?.length) {
          allEvents.push(...poll.events);
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    text: "正在处理，请稍候...",
                    toolEvents: [...allEvents],
                  }
                : message,
            ),
          );
        }
        if (poll.done) {
          const response = poll.response;
          if (!response) {
            throw new Error("Claude Code 流式会话结束但没有返回最终结果");
          }
          const finalEvents = allEvents.length
            ? allEvents
            : response.metadata?.tool_events;
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    id: id(response.ok ? "assistant" : "error"),
                    text: response.message,
                    error: !response.ok,
                    toolEvents: finalEvents,
                    suggestions: response.ok
                      ? recommendedQuestions(response.message, activeConversation?.game?.name)
                      : undefined,
                  }
                : message,
            ),
          );
          break;
        }
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown backend error";

      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId
            ? {
                ...item,
                id: id("error"),
                text: `后端调用失败：${message}`,
                error: true,
              }
            : item,
        ),
      );
      toaster.toast({
        title: "请求失败",
        body: message,
      });
    } finally {
      setIsSending(false);
    }
  };

  const onPromptFieldChange = (event: ChangeEvent<HTMLInputElement>) => {
    setPrompt(event.target.value);
  };

  const toggleTrace = (messageId: string) => {
    setExpandedTraceIds((current) => {
      const next = new Set(current);
      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }
      return next;
    });
  };

  const onPromptKeyDown = (
    event: KeyboardEvent<HTMLTextAreaElement | HTMLInputElement>,
  ) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey || !event.shiftKey)) {
      event.preventDefault();
      void sendPrompt();
    }
  };

  return (
    <div className="decky-ai-chat-shell" style={styles.shell}>
      <style>{inputCss}</style>
      <header style={styles.topBar}>
        <div style={styles.modelBlock}>
          <div style={styles.modelTitle}>AI 助手</div>
          <div style={styles.modelStatus}>
            <FaWifi />
            <span>
              {activeConversation?.game?.name
                ? `当前游戏：${activeConversation.game.name}`
                : activeConversation?.title || `Claude Code CLI · ${model}`}
            </span>
          </div>
        </div>
        <div style={styles.topActions}>
          <button
            aria-label="手机扫码配置"
            style={styles.iconButton}
            type="button"
            onClick={() => {
              setShowPairing((current) => !current);
              setShowSettings(false);
            }}
          >
            <FaQrcode />
          </button>
          <button
            aria-label="连接设置"
            style={styles.iconButton}
            type="button"
            onClick={() => {
              setShowSettings((current) => {
                const next = !current;
                if (next) {
                  void loadConfig();
                }
                return next;
              });
              setShowPairing(false);
            }}
          >
            <FaCog />
          </button>
        </div>
      </header>

      {showPairing ? (
        <section style={styles.pairingPanel}>
          <h2 style={styles.pairingTitle}>手机配置</h2>
          <p style={styles.pairingText}>
            用手机扫描二维码，在同一个 Wi-Fi 下填写 DeepSeek、Kimi 或自定义
            OpenAI 兼容接口配置，也可以填写 Steam Web API Key。
          </p>
          <div style={styles.qrBox}>
            {qrDataUrl ? (
              <img alt="Phone setup QR code" src={qrDataUrl} style={styles.qrImage} />
            ) : (
              <span style={{ color: "#151515", textAlign: "center" }}>
                {pairingError ? "二维码不可用" : "加载中"}
              </span>
            )}
          </div>
          {pairingError ? (
            <div style={{ ...styles.errorMessage, ...styles.bubble, maxWidth: "100%" }}>
              {pairingError}
            </div>
          ) : null}
          <div style={styles.pairingUrl}>
            {pairingInfo?.url || "正在启动手机配置服务..."}
          </div>
          <button
            style={styles.actionButton}
            type="button"
            onClick={() => void loadPairingInfo()}
          >
            刷新二维码
          </button>
          <button
            style={styles.actionButton}
            type="button"
            onClick={() => {
              void loadConfig();
              toaster.toast({
                title: "配置已刷新",
                body: "已从后端配置重新同步。",
              });
            }}
          >
            重新同步配置
          </button>
          <p style={styles.settingsNote}>
            此页面带随机 token，只适合在可信局域网内使用。保存后可关闭手机页面。
          </p>
        </section>
      ) : null}

      {showSettings ? (
        <section style={styles.settingsPanel}>
          <p style={styles.settingsNote}>
            当前固定为 Agent 工具模式。写文件和 shell 命令会先生成待确认动作，不会自动执行。
          </p>
          <div style={styles.toolResult}>
            <div style={styles.toolResultTitle}>Steam 账号连接</div>
            <p style={styles.settingsNote}>
              优先自动读取这台 Steam Deck 上已登录的 SteamID64。完整游戏库、时长和成就可能需要公开资料或可选 Web API Key。
            </p>
            <div style={styles.settingsNote}>
              状态：
              {steamId ? ` 已连接 ${steamId}` : " 未连接"}
              {hasSteamApiKey ? " · API Key 已保存" : ""}
              {steamStatus ? ` · 本机已安装 ${steamStatus.local_library_count} 个游戏` : ""}
            </div>
            <button
              style={styles.actionButton}
              type="button"
              onClick={() => void connectSteam()}
            >
              <FaCheck /> {isDetectingSteam ? "检测中" : "连接 Steam（自动检测）"}
            </button>
            <label style={styles.field}>
              <span style={styles.label}>SteamID64</span>
              <input
                style={styles.input}
                value={steamId}
                onChange={(event) => setSteamId(event.target.value)}
                placeholder="自动检测后会填入，也可以手动修正"
              />
            </label>
            <label style={styles.field}>
              <span style={styles.label}>
                Steam Web API Key {hasSteamApiKey ? "（已保存，可选）" : "（可选）"}
              </span>
              <input
                style={styles.input}
                type="password"
                value={steamApiKey}
                onChange={(event) => setSteamApiKey(event.target.value)}
                placeholder={hasSteamApiKey ? "留空则保留已保存的 key" : "需要私有库/成就时再填写"}
              />
            </label>
            <label style={{ ...styles.field, flexDirection: "row", alignItems: "center" }}>
              <input
                checked={steamIncludeFreeGames}
                type="checkbox"
                onChange={(event) => setSteamIncludeFreeGames(event.target.checked)}
              />
              <span style={styles.label}>Steam 库包含免费游戏</span>
            </label>
            <label style={styles.field}>
              <span style={styles.label}>Steam 数据缓存秒数</span>
              <input
                style={styles.input}
                type="number"
                min={60}
                max={86400}
                step={60}
                value={steamCacheSeconds}
                onChange={(event) => setSteamCacheSeconds(Number(event.target.value))}
              />
            </label>
          </div>
          <div style={styles.toolResult}>
            <div style={styles.toolResultTitle}>Agent 后端</div>
            <p style={styles.settingsNote}>
              当前后端固定为 Claude Code CLI。请先在 Steam Deck 上安装并登录
              Claude Code；插件会从 Decky 后端调用 `claude -p`，并授予
              `/home/deck` 访问目录。
            </p>
          </div>
          <label style={styles.field}>
            <span style={styles.label}>接口地址 / Base URL</span>
            <input
              style={styles.input}
              value={endpoint}
              onChange={(event) => setEndpoint(event.target.value)}
              placeholder="https://api.openai.com/v1 or http://deck-ip:11434/v1"
            />
          </label>
          <label style={styles.field}>
            <span style={styles.label}>模型</span>
            <input
              style={styles.input}
              value={model}
              onChange={(event) => setModel(event.target.value)}
            />
          </label>
          <label style={styles.field}>
            <span style={styles.label}>
              API Key {hasApiKey ? "（已保存）" : ""}
            </span>
            <input
              style={styles.input}
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={hasApiKey ? "留空则保留已保存的 key" : "Bearer token"}
            />
          </label>
          <label style={styles.field}>
            <span style={styles.label}>系统提示词</span>
            <textarea
              style={{ ...styles.input, minHeight: "54px", resize: "vertical" }}
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
            />
          </label>
          <label style={styles.field}>
            <span style={styles.label}>温度</span>
            <input
              style={styles.input}
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={temperature}
              onChange={(event) => setTemperature(Number(event.target.value))}
            />
          </label>
          <label style={styles.field}>
            <span style={styles.label}>最大历史消息数</span>
            <input
              style={styles.input}
              type="number"
              min={2}
              max={40}
              step={1}
              value={maxHistory}
              onChange={(event) => setMaxHistory(Number(event.target.value))}
            />
          </label>
          <label style={{ ...styles.field, flexDirection: "row", alignItems: "center" }}>
            <input
              checked={verifySsl}
              type="checkbox"
              onChange={(event) => setVerifySsl(event.target.checked)}
            />
            <span style={styles.label}>校验 TLS 证书</span>
          </label>
          <div style={styles.settingsActions}>
            <button
              style={styles.actionButton}
              type="button"
              onClick={() => void saveSettings()}
            >
              <FaSave /> {isSaving ? "保存中" : "保存"}
            </button>
            <button
              style={styles.actionButton}
              type="button"
              onClick={() => void testBackend()}
            >
              <FaCheck /> 测试
            </button>
          </div>
          <p style={styles.settingsNote}>
            当前所有请求都会进入 Claude Code CLI Bridge。上面的模型服务字段仅保留为旧配置和系统提示词入口，不再驱动主 Agent。
          </p>
        </section>
      ) : null}

      <main ref={transcriptRef} style={styles.transcript} onScroll={updateScrollButton}>
        {!hasConversation ? (
          <div style={styles.emptyState}>
            {isLoadingConversation ? (
              <div style={{ ...styles.bubble, ...styles.assistantMessage }}>
                正在加载当前游戏会话
                <ThinkingDots />
              </div>
            ) : (
              <div style={styles.suggestionGrid}>
                {quickPrompts.map((quickPrompt) => (
                  <button
                    key={quickPrompt}
                    style={styles.suggestionButton}
                    type="button"
                    onClick={() => {
                      setPrompt(quickPrompt);
                      void sendPrompt(quickPrompt);
                    }}
                  >
                    {quickPrompt}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          messages.map((message) => {
            const isUser = message.role === "user";
            const isStreamingMessage = message.id.startsWith("assistant-stream");
            const traceExpanded = isStreamingMessage || expandedTraceIds.has(message.id);
            const rowStyle = {
              ...styles.messageRow,
              ...(isUser ? styles.userRow : {}),
            };
            const bubbleStyle = {
              ...styles.bubble,
              ...(isUser ? styles.userMessage : styles.assistantMessage),
              ...(message.error ? styles.errorMessage : {}),
            };

            return (
              <div key={message.id} style={rowStyle}>
                {!isUser ? (
                  <div style={styles.assistantAvatar}>
                    <FaRobot />
                  </div>
                ) : null}
                <div style={bubbleStyle}>
                  {isUser ? (
                    <div style={{ whiteSpace: "pre-wrap" }}>{message.text}</div>
                  ) : (
                    renderMarkdown(message.text, message.id)
                  )}
                  {!isUser && message.toolEvents?.length ? (
                    <>
                      {!isStreamingMessage ? (
                        <button
                          style={styles.toolTraceToggle}
                          type="button"
                          onClick={() => toggleTrace(message.id)}
                        >
                          <span>
                            思考过程 · {message.toolEvents.length} 个步骤
                          </span>
                          <span>{traceExpanded ? "收起" : "展开"}</span>
                        </button>
                      ) : null}
                      {traceExpanded ? (
                        <div style={styles.toolTrace}>
                          {message.toolEvents.map((event, index) => (
                            <div key={`${message.id}-tool-${index}`} style={styles.toolEvent}>
                              <strong>{event.name}</strong> · {event.status}
                              <br />
                              {compactTraceDetail(event.detail)}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </>
                  ) : null}
                  {!isUser && message.suggestions?.length ? (
                    <div style={styles.suggestionRow}>
                      <div style={styles.suggestionTitle}>可以继续问：</div>
                      {message.suggestions.map((question) => (
                        <button
                          key={`${message.id}-suggestion-${question}`}
                          style={styles.followupButton}
                          type="button"
                          onClick={() => setPrompt(question)}
                        >
                          {question}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })
        )}

        {isSending ? (
          <div style={styles.messageRow}>
            <div style={styles.assistantAvatar}>
              <FaRobot />
            </div>
            <div style={{ ...styles.bubble, ...styles.assistantMessage }}>
              <span style={styles.typing}>
                思考中
                <ThinkingDots />
              </span>
            </div>
          </div>
        ) : null}
      </main>

      {showScrollToBottom ? (
        <button
          aria-label="跳转到最新消息"
          style={styles.scrollToBottomButton}
          type="button"
          onClick={() => scrollToBottom("smooth")}
        >
          <FaArrowDown />
        </button>
      ) : null}

      <footer style={styles.composerWrap}>
        <div style={styles.composer}>
          <button
            aria-label="清空对话"
            style={styles.iconButton}
            type="button"
            onClick={async () => {
              const cleared = await clearActiveConversation(activeConversation?.conversation_id);
              setActiveConversation(cleared);
              setMessages([]);
              messagesRef.current = [];
              setExpandedTraceIds(new Set());
            }}
          >
            <FaTrash />
          </button>
          <div className="decky-ai-chat-input" style={styles.textFieldWrap}>
            <TextField
              aria-label="聊天输入"
              style={styles.compactTextField}
              value={prompt}
              onChange={onPromptFieldChange}
              onKeyDown={onPromptKeyDown}
              bShowClearAction
            />
          </div>
          <button
            aria-label="发送消息"
            disabled={!canSend}
            style={{
              ...styles.sendButton,
              ...(!canSend ? styles.disabledSend : {}),
            }}
            type="button"
            onClick={() => void sendPrompt()}
          >
            <FaArrowUp />
          </button>
        </div>
      </footer>
    </div>
  );
}

export default definePlugin(() => {
  console.log("AI Chat plugin initializing");

  return {
    name: "AI 助手",
    titleView: <div className={staticClasses.Title}>AI 助手</div>,
    content: <Content />,
    icon: <FaRobot />,
    onDismount() {
      console.log("AI Chat plugin unloading");
    },
  };
});
