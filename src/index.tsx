import { staticClasses, TextField } from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, CSSProperties, KeyboardEvent } from "react";
import QRCode from "qrcode";
import {
  FaArrowUp,
  FaCheck,
  FaCog,
  FaPlus,
  FaQrcode,
  FaRobot,
  FaSave,
  FaTrash,
  FaWifi,
} from "react-icons/fa";

type Role = "assistant" | "user";
type Provider = "mock" | "openai" | "langchain" | "ragflow";

type ChatMessage = {
  id: string;
  role: Role;
  text: string;
  error?: boolean;
};

type ChatRequest = {
  prompt: string;
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
  metadata?: Record<string, unknown>;
};

type BackendConfig = {
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

const askAi = callable<[request: ChatRequest], ChatResponse>("ask_ai");
const getConfig = callable<[], BackendConfig>("get_config");
const saveConfig = callable<[updates: Record<string, unknown>], BackendConfig>(
  "save_config",
);
const checkBackend = callable<
  [updates: Record<string, unknown>],
  BackendStatus
>("check_backend");
const getPairingInfo = callable<[], PairingInfo>("get_pairing_info");

const initialMessages: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    text: "Ready. Ask for game tips, settings advice, build notes, or anything else.",
  },
];

const quickPrompts = [
  "Suggest Steam Deck settings for the current game.",
  "Summarize a spoiler-free beginner strategy.",
  "Help me debug why this game stutters.",
];

const styles: Record<string, CSSProperties> = {
  shell: {
    display: "flex",
    flexDirection: "column",
    height: "calc(100vh - 92px)",
    minHeight: "520px",
    margin: "-10px -8px 0",
    background: "#151515",
    color: "#f4f4f4",
  },
  topBar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "8px",
    padding: "10px 12px",
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
    fontSize: "15px",
    fontWeight: 700,
  },
  modelStatus: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    fontSize: "12px",
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
    width: "34px",
    height: "34px",
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
    gap: "15px",
    overflowY: "auto",
    padding: "18px 12px 16px",
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
  typing: {
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    color: "rgba(244, 244, 244, 0.64)",
  },
  composerWrap: {
    padding: "10px 10px 12px",
    borderTop: "1px solid rgba(255, 255, 255, 0.08)",
    background: "rgba(21, 21, 21, 0.98)",
  },
  composer: {
    display: "flex",
    alignItems: "flex-end",
    gap: "8px",
    borderRadius: "22px",
    border: "1px solid rgba(255, 255, 255, 0.12)",
    background: "#242424",
    padding: "7px",
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
  },
  compactTextField: {
    minHeight: "32px",
    padding: 0,
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
    width: "32px",
    height: "32px",
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
  composerHint: {
    marginTop: "6px",
    textAlign: "center",
    fontSize: "11px",
    color: "rgba(244, 244, 244, 0.42)",
  },
};

function id(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function Content() {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [prompt, setPrompt] = useState("");
  const [provider, setProvider] = useState<Provider>("mock");
  const [model, setModel] = useState("decky-local");
  const [endpoint, setEndpoint] = useState("mock://decky-backend");
  const [apiKey, setApiKey] = useState("");
  const [hasApiKey, setHasApiKey] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a concise, helpful assistant running inside Steam Deck game mode.",
  );
  const [temperature, setTemperature] = useState(0.7);
  const [maxHistory, setMaxHistory] = useState(16);
  const [verifySsl, setVerifySsl] = useState(true);
  const [ragflowChatId, setRagflowChatId] = useState("");
  const [ragflowSessionId, setRagflowSessionId] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showPairing, setShowPairing] = useState(false);
  const [pairingInfo, setPairingInfo] = useState<PairingInfo | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [pairingError, setPairingError] = useState("");
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  const canSend = useMemo(
    () => prompt.trim().length > 0 && !isSending,
    [isSending, prompt],
  );

  const hasConversation = messages.length > 1;

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [isSending, messages]);

  useEffect(() => {
    void loadConfig();
  }, []);

  useEffect(() => {
    if (!showPairing) {
      return;
    }
    void loadPairingInfo();
  }, [showPairing]);

  const applyConfig = (config: BackendConfig) => {
    setProvider(config.provider || "mock");
    setEndpoint(config.endpoint || "mock://decky-backend");
    setModel(config.model || "decky-local");
    setSystemPrompt(config.system_prompt || "");
    setTemperature(Number(config.temperature ?? 0.7));
    setMaxHistory(Number(config.max_history ?? 16));
    setVerifySsl(Boolean(config.verify_ssl ?? true));
    setRagflowChatId(config.ragflow_chat_id || "");
    setRagflowSessionId(config.ragflow_session_id || "");
    setHasApiKey(Boolean(config.has_api_key));
    setApiKey("");
  };

  const loadConfig = async () => {
    try {
      applyConfig(await getConfig());
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to load backend config";
      toaster.toast({ title: "AI Chat config failed", body: message });
    }
  };

  const configPayload = (includeApiKey: boolean) => ({
    provider,
    endpoint,
    model,
    api_key: includeApiKey ? apiKey : "__KEEP__",
    system_prompt: systemPrompt,
    temperature,
    max_history: maxHistory,
    verify_ssl: verifySsl,
    ragflow_chat_id: ragflowChatId,
    ragflow_session_id: ragflowSessionId,
  });

  const saveSettings = async () => {
    setIsSaving(true);
    try {
      applyConfig(await saveConfig(configPayload(apiKey.length > 0)));
      toaster.toast({ title: "AI Chat settings saved", body: "Configuration updated." });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to save settings";
      toaster.toast({ title: "AI Chat save failed", body: message });
    } finally {
      setIsSaving(false);
    }
  };

  const testBackend = async () => {
    try {
      const status = await checkBackend(configPayload(apiKey.length > 0));
      toaster.toast({
        title: status.ok ? "Backend ready" : "Backend not ready",
        body: status.message,
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to check backend";
      toaster.toast({ title: "AI Chat test failed", body: message });
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
          error instanceof Error ? error.message : "QR generation failed";
        setPairingError(`QR generation failed: ${message}`);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to open phone setup";
      setPairingError(message);
      toaster.toast({ title: "Phone setup failed", body: message });
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
    setMessages((current) => [...current, userMessage]);

    try {
      const history = [...messages, userMessage].map(({ role, text }) => ({
        role,
        text,
      }));
      const response = await askAi({
        prompt: cleanPrompt,
        history,
      });

      const assistantMessage: ChatMessage = {
        id: id(response.ok ? "assistant" : "error"),
        role: "assistant",
        text: response.message,
        error: !response.ok,
      };
      setMessages((current) => [...current, assistantMessage]);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown backend error";

      setMessages((current) => [
        ...current,
        {
          id: id("error"),
          role: "assistant",
          text: `Backend call failed: ${message}`,
          error: true,
        },
      ]);
      toaster.toast({
        title: "AI Chat request failed",
        body: message,
      });
    } finally {
      setIsSending(false);
    }
  };

  const onPromptFieldChange = (event: ChangeEvent<HTMLInputElement>) => {
    setPrompt(event.target.value);
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
    <div style={styles.shell}>
      <header style={styles.topBar}>
        <div style={styles.modelBlock}>
          <div style={styles.modelTitle}>AI Chat</div>
          <div style={styles.modelStatus}>
            <FaWifi />
            <span>
              {model} · {provider}
            </span>
          </div>
        </div>
        <div style={styles.topActions}>
          <button
            aria-label="New chat"
            style={styles.iconButton}
            type="button"
            onClick={() => setMessages(initialMessages)}
          >
            <FaPlus />
          </button>
          <button
            aria-label="Phone setup"
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
            aria-label="Connection settings"
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
          <h2 style={styles.pairingTitle}>Phone Setup</h2>
          <p style={styles.pairingText}>
            用手机扫描二维码，在同一个 Wi-Fi 下填写 DeepSeek、Kimi 或自定义
            OpenAI-compatible 配置。
          </p>
          <div style={styles.qrBox}>
            {qrDataUrl ? (
              <img alt="Phone setup QR code" src={qrDataUrl} style={styles.qrImage} />
            ) : (
              <span style={{ color: "#151515", textAlign: "center" }}>
                {pairingError ? "QR unavailable" : "Loading"}
              </span>
            )}
          </div>
          {pairingError ? (
            <div style={{ ...styles.errorMessage, ...styles.bubble, maxWidth: "100%" }}>
              {pairingError}
            </div>
          ) : null}
          <div style={styles.pairingUrl}>
            {pairingInfo?.url || "Starting phone setup server..."}
          </div>
          <button
            style={styles.actionButton}
            type="button"
            onClick={() => void loadPairingInfo()}
          >
            Refresh
          </button>
          <button
            style={styles.actionButton}
            type="button"
            onClick={() => {
              void loadConfig();
              toaster.toast({
                title: "AI Chat config reloaded",
                body: "Settings refreshed from backend config.",
              });
            }}
          >
            Reload Config
          </button>
          <p style={styles.settingsNote}>
            此页面带随机 token，只适合在可信局域网内使用。保存后可关闭手机页面。
          </p>
        </section>
      ) : null}

      {showSettings ? (
        <section style={styles.settingsPanel}>
          <label style={styles.field}>
            <span style={styles.label}>Provider</span>
            <select
              style={styles.select}
              value={provider}
              onChange={(event) => setProvider(event.target.value as Provider)}
            >
              <option value="mock">Mock</option>
              <option value="openai">OpenAI-compatible HTTP</option>
              <option value="langchain">LangChain ChatOpenAI</option>
              <option value="ragflow">RAGFlow chat</option>
            </select>
          </label>
          <label style={styles.field}>
            <span style={styles.label}>Endpoint / Base URL</span>
            <input
              style={styles.input}
              value={endpoint}
              onChange={(event) => setEndpoint(event.target.value)}
              placeholder="https://api.openai.com/v1 or http://deck-ip:11434/v1"
            />
          </label>
          <label style={styles.field}>
            <span style={styles.label}>Model</span>
            <input
              style={styles.input}
              value={model}
              onChange={(event) => setModel(event.target.value)}
            />
          </label>
          <label style={styles.field}>
            <span style={styles.label}>
              API Key {hasApiKey ? "(saved)" : ""}
            </span>
            <input
              style={styles.input}
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={hasApiKey ? "Leave blank to keep saved key" : "Bearer token"}
            />
          </label>
          <label style={styles.field}>
            <span style={styles.label}>System Prompt</span>
            <textarea
              style={{ ...styles.input, minHeight: "54px", resize: "vertical" }}
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
            />
          </label>
          <label style={styles.field}>
            <span style={styles.label}>Temperature</span>
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
            <span style={styles.label}>Max History Messages</span>
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
            <span style={styles.label}>Verify TLS certificate</span>
          </label>
          {provider === "ragflow" ? (
            <>
              <label style={styles.field}>
                <span style={styles.label}>RAGFlow Chat ID</span>
                <input
                  style={styles.input}
                  value={ragflowChatId}
                  onChange={(event) => setRagflowChatId(event.target.value)}
                />
              </label>
              <label style={styles.field}>
                <span style={styles.label}>RAGFlow Session ID</span>
                <input
                  style={styles.input}
                  value={ragflowSessionId}
                  onChange={(event) => setRagflowSessionId(event.target.value)}
                />
              </label>
            </>
          ) : null}
          <div style={styles.settingsActions}>
            <button
              style={styles.actionButton}
              type="button"
              onClick={() => void saveSettings()}
            >
              <FaSave /> {isSaving ? "Saving" : "Save"}
            </button>
            <button
              style={styles.actionButton}
              type="button"
              onClick={() => void testBackend()}
            >
              <FaCheck /> Test
            </button>
          </div>
          <p style={styles.settingsNote}>
            OpenAI-compatible expects a `/chat/completions` API. RAGFlow expects
            a base URL plus chat/session ids. LangChain requires Python package
            installation on the Deck.
          </p>
        </section>
      ) : null}

      <main ref={transcriptRef} style={styles.transcript}>
        {!hasConversation ? (
          <div style={styles.emptyState}>
            <div style={styles.hero}>
              <div style={styles.heroMark}>
                <FaRobot />
              </div>
              <h2 style={styles.heroTitle}>How can I help?</h2>
              <p style={styles.heroText}>
                Ask for game settings, walkthrough hints, launch options, or
                anything you need while staying in game mode.
              </p>
            </div>
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
          </div>
        ) : (
          messages.map((message) => {
            const isUser = message.role === "user";
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
                <div style={bubbleStyle}>{message.text}</div>
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
              <span style={styles.typing}>Thinking...</span>
            </div>
          </div>
        ) : null}
      </main>

      <footer style={styles.composerWrap}>
        <div style={styles.composer}>
          <button
            aria-label="Clear conversation"
            style={styles.iconButton}
            type="button"
            onClick={() => setMessages(initialMessages)}
          >
            <FaTrash />
          </button>
          <div style={styles.textFieldWrap}>
            <TextField
              aria-label="Chat prompt"
              style={styles.compactTextField}
              value={prompt}
              onChange={onPromptFieldChange}
              onKeyDown={onPromptKeyDown}
              bShowClearAction
            />
          </div>
          <button
            aria-label="Send message"
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
        <div style={styles.composerHint}>Press Enter or the arrow button to send</div>
      </footer>
    </div>
  );
}

export default definePlugin(() => {
  console.log("AI Chat plugin initializing");

  return {
    name: "AI Chat",
    titleView: <div className={staticClasses.Title}>AI Chat</div>,
    content: <Content />,
    icon: <FaRobot />,
    onDismount() {
      console.log("AI Chat plugin unloading");
    },
  };
});
