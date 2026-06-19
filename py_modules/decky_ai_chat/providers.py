import asyncio
import json
import ssl
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class ProviderResult:
    ok: bool
    message: str
    provider: str
    model: str
    endpoint: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "provider": self.provider,
            "model": self.model,
            "endpoint": self.endpoint,
            "metadata": self.metadata or {},
        }


class ProviderRouter:
    def __init__(self, logger):
        self.logger = logger

    async def ask(self, request: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        merged = dict(config)
        if request.get("override_config") is True:
            for key in (
                "provider",
                "endpoint",
                "model",
                "system_prompt",
                "temperature",
                "max_history",
                "ragflow_chat_id",
                "ragflow_session_id",
            ):
                if request.get(key) not in (None, ""):
                    merged[key] = request[key]

        prompt = str(request.get("prompt", "")).strip()
        if not prompt:
            return ProviderResult(
                False,
                "Please enter a prompt before sending.",
                self._provider(merged),
                self._model(merged),
                self._endpoint(merged),
            ).to_dict()

        provider = self._provider(merged)
        self.logger.info(
            "AI Chat provider request: "
            f"provider={provider} "
            f"endpoint={self._endpoint(merged)} "
            f"model={self._model(merged)} "
            f"has_api_key={bool(str(merged.get('api_key', '')).strip())}"
        )
        try:
            if provider == "mock":
                result = await self._ask_mock(prompt, request, merged)
            elif provider == "openai":
                result = await asyncio.to_thread(
                    self._ask_openai_compatible,
                    prompt,
                    request,
                    merged,
                )
            elif provider == "langchain":
                result = await asyncio.to_thread(self._ask_langchain, prompt, request, merged)
            elif provider == "ragflow":
                result = await asyncio.to_thread(self._ask_ragflow, prompt, merged)
            else:
                result = ProviderResult(
                    False,
                    f"Unknown provider: {provider}",
                    provider,
                    self._model(merged),
                    self._endpoint(merged),
                )
        except Exception as exc:
            self.logger.exception(f"AI provider request failed: {exc!r}")
            result = ProviderResult(
                False,
                f"{provider} request failed: {exc}",
                provider,
                self._model(merged),
                self._endpoint(merged),
            )
        return result.to_dict()

    async def check(self, config: dict[str, Any]) -> dict[str, Any]:
        provider = self._provider(config)
        endpoint = self._endpoint(config)
        if provider == "mock":
            return {"ok": True, "message": "Mock backend is available.", "provider": provider}
        if provider == "langchain":
            try:
                import langchain_openai  # noqa: F401
            except Exception as exc:
                return {
                    "ok": False,
                    "message": f"langchain-openai is not installed: {exc}",
                    "provider": provider,
                }
            return {"ok": True, "message": "LangChain package is available.", "provider": provider}
        if provider == "ragflow":
            if not str(config.get("api_key", "")).strip():
                return {"ok": False, "message": "RAGFlow API key is missing.", "provider": provider}
            if not str(config.get("ragflow_chat_id", "")).strip():
                return {"ok": False, "message": "RAGFlow chat id is missing.", "provider": provider}
            return {
                "ok": True,
                "message": "RAGFlow config looks complete. Send a message to verify the chat session.",
                "provider": provider,
            }
        if provider == "openai":
            if not endpoint.startswith(("http://", "https://")):
                return {"ok": False, "message": "Endpoint must start with http:// or https://.", "provider": provider}
            return {"ok": True, "message": "OpenAI-compatible config looks valid.", "provider": provider}
        return {"ok": False, "message": f"Unknown provider: {provider}", "provider": provider}

    async def _ask_mock(
        self,
        prompt: str,
        request: dict[str, Any],
        config: dict[str, Any],
    ) -> ProviderResult:
        await asyncio.sleep(0.2)
        history_count = len(request.get("history", []))
        return ProviderResult(
            True,
            (
                "Mock reply from Decky backend. "
                f"Provider routing is working, history messages: {history_count}. "
                f"You asked: {prompt}"
            ),
            self._provider(config),
            self._model(config),
            self._endpoint(config),
        )

    def _ask_openai_compatible(
        self,
        prompt: str,
        request: dict[str, Any],
        config: dict[str, Any],
    ) -> ProviderResult:
        messages = self._build_messages(prompt, request.get("history", []), config)
        body = {
            "model": self._model(config),
            "messages": messages,
            "temperature": self._temperature(config),
            "stream": False,
        }
        data = self._post_json(
            self._chat_completions_url(self._endpoint(config)),
            body,
            self._headers(config),
        )
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not content:
            content = json.dumps(data, ensure_ascii=False)
        return ProviderResult(
            True,
            content,
            self._provider(config),
            self._model(config),
            self._endpoint(config),
            {"raw_provider": "openai-compatible"},
        )

    def _ask_langchain(
        self,
        prompt: str,
        request: dict[str, Any],
        config: dict[str, Any],
    ) -> ProviderResult:
        try:
            from langchain_openai import ChatOpenAI
        except Exception as exc:
            raise RuntimeError(
                "LangChain support requires `pip install langchain-openai` in the Decky Python environment"
            ) from exc

        kwargs: dict[str, Any] = {
            "model": self._model(config),
            "temperature": self._temperature(config),
        }
        api_key = str(config.get("api_key", "")).strip()
        endpoint = self._endpoint(config)
        if api_key:
            kwargs["api_key"] = api_key
        if endpoint and endpoint != "mock://decky-backend":
            kwargs["base_url"] = endpoint

        llm = ChatOpenAI(**kwargs)
        response = llm.invoke(self._build_messages(prompt, request.get("history", []), config))
        content = getattr(response, "content", None) or getattr(response, "text", "")
        return ProviderResult(
            True,
            str(content),
            self._provider(config),
            self._model(config),
            self._endpoint(config),
            {"raw_provider": "langchain-openai"},
        )

    def _ask_ragflow(self, prompt: str, config: dict[str, Any]) -> ProviderResult:
        chat_id = str(config.get("ragflow_chat_id", "")).strip()
        session_id = str(config.get("ragflow_session_id", "")).strip()
        if not chat_id:
            raise ValueError("RAGFlow chat id is required.")
        if not session_id:
            raise ValueError("RAGFlow session id is required. Create one in RAGFlow first.")

        base_url = self._endpoint(config).rstrip("/")
        if not base_url.endswith("/api/v1"):
            base_url = f"{base_url}/api/v1"

        data = self._post_json(
            f"{base_url}/chats/{chat_id}/completions",
            {
                "question": prompt,
                "stream": False,
                "session_id": session_id,
            },
            self._headers(config),
        )
        payload = data.get("data", data)
        message = payload.get("answer") or payload.get("content") or json.dumps(payload, ensure_ascii=False)
        return ProviderResult(
            True,
            message,
            self._provider(config),
            self._model(config),
            self._endpoint(config),
            {
                "raw_provider": "ragflow",
                "reference": payload.get("reference", {}),
            },
        )

    def _build_messages(
        self,
        prompt: str,
        history: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        system_prompt = str(config.get("system_prompt", "")).strip()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        trimmed = history[-self._max_history(config) :]
        for item in trimmed:
            role = str(item.get("role", "user"))
            if role not in ("user", "assistant", "system"):
                role = "user"
            content = str(item.get("text", item.get("content", ""))).strip()
            if content:
                messages.append({"role": role, "content": content})

        if not messages or messages[-1].get("content") != prompt:
            messages.append({"role": "user", "content": prompt})
        return messages

    def _post_json(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        context = self._ssl_context(headers)
        request = Request(url, data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=60, context=context) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc
        if not raw:
            return {}
        return json.loads(raw)

    def _ssl_context(self, headers: dict[str, str]) -> ssl.SSLContext | None:
        verify_ssl = headers.pop("X-Decky-AI-Verify-SSL", "true") == "true"
        if verify_ssl:
            return None
        return ssl._create_unverified_context()

    def _headers(self, config: dict[str, Any]) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        headers["X-Decky-AI-Verify-SSL"] = "true" if self._verify_ssl(config) else "false"
        api_key = str(config.get("api_key", "")).strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _chat_completions_url(self, endpoint: str) -> str:
        endpoint = endpoint.rstrip("/")
        if endpoint.endswith("/chat/completions"):
            return endpoint
        return f"{endpoint}/chat/completions"

    def _provider(self, config: dict[str, Any]) -> str:
        return str(config.get("provider", "mock")).strip().lower() or "mock"

    def _endpoint(self, config: dict[str, Any]) -> str:
        return str(config.get("endpoint", "mock://decky-backend")).strip()

    def _model(self, config: dict[str, Any]) -> str:
        return str(config.get("model", "decky-local")).strip() or "decky-local"

    def _temperature(self, config: dict[str, Any]) -> float:
        try:
            return float(config.get("temperature", 0.7))
        except (TypeError, ValueError):
            return 0.7

    def _max_history(self, config: dict[str, Any]) -> int:
        try:
            return max(2, min(int(config.get("max_history", 16)), 40))
        except (TypeError, ValueError):
            return 16

    def _verify_ssl(self, config: dict[str, Any]) -> bool:
        value = config.get("verify_ssl", True)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
