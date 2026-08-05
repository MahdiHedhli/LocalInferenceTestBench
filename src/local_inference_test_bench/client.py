"""Minimal OpenAI-compatible client with a local-only endpoint gate."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler,
    OpenerDirector,
    ProxyHandler,
    Request,
    build_opener,
)

from .models import GenerationSettings
from .safety import SafeEndpoint, validate_endpoint


MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class ClientError(RuntimeError):
    """A sanitized client failure with a stable categorical reason."""

    def __init__(self, category: str, message: str = "inference request failed") -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Transient tool-call content. Report writers must never serialize this object."""

    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class Completion:
    """Transient response data used for scoring and immediately minimized."""

    content: str
    finish_reason: str | None
    usage: Usage
    tool_calls: tuple[ToolCall, ...] = ()
    runtime_model: str | None = None
    reasoning_present: bool = False


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):  # noqa: ANN001
        return None


def _default_opener() -> OpenerDirector:
    # Disable environment proxies and redirects so endpoint validation remains meaningful.
    return build_opener(ProxyHandler({}), _NoRedirects())


class OpenAICompatibleClient:
    """A bounded client for ``/v1/models`` and ``/v1/chat/completions`` only."""

    def __init__(
        self,
        endpoint: str,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        opener: OpenerDirector | Any | None = None,
    ) -> None:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise ValueError("timeout_seconds must be numeric")
        if not 0 < float(timeout_seconds) <= 3600:
            raise ValueError("timeout_seconds must be greater than 0 and at most 3600")
        self._endpoint_text = endpoint
        self._safe_endpoint: SafeEndpoint = validate_endpoint(endpoint)
        self._api_key = api_key
        self._timeout_seconds = float(timeout_seconds)
        self._opener = opener or _default_opener()

    def _url(self, path: str) -> str:
        base = self._safe_endpoint.base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}{path}"
        return f"{base}/v1{path}"

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        # Re-resolve immediately before every request to reject a changed DNS answer.
        self._safe_endpoint = validate_endpoint(self._endpoint_text)
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = Request(self._url(path), data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            try:
                category = self._http_error_category(error)
            finally:
                error.close()
            raise ClientError(category) from error
        except (TimeoutError, socket.timeout) as error:
            raise ClientError("timeout") from error
        except (URLError, OSError) as error:
            raise ClientError("network_error") from error
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ClientError("response_too_large")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ClientError("invalid_json") from error
        if not isinstance(decoded, Mapping):
            raise ClientError("protocol_error")
        return decoded

    @staticmethod
    def _http_error_category(error: HTTPError) -> str:
        if error.code in {401, 403}:
            return "authentication"
        if error.code == 429:
            return "rate_limited"
        if error.code >= 500:
            return "server_error"
        raw = b""
        try:
            raw = error.read(64 * 1024)
            decoded = json.loads(raw.decode("utf-8"))
            detail = decoded.get("error", decoded) if isinstance(decoded, Mapping) else {}
            code = str(detail.get("code", "")).lower() if isinstance(detail, Mapping) else ""
            message = (
                str(detail.get("message", "")).lower() if isinstance(detail, Mapping) else ""
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            code = ""
            message = ""
        context_markers = (
            "context_length",
            "context window",
            "maximum context",
            "too many tokens",
        )
        if any(marker in code or marker in message for marker in context_markers):
            return "context_window"
        return "request_rejected" if 400 <= error.code < 500 else "http_error"

    def list_models(self) -> tuple[str, ...]:
        """Return runtime model identifiers transiently; callers should hash or discard them."""

        decoded = self._request_json("GET", "/models")
        data = decoded.get("data")
        if data is None:
            return ()
        if not isinstance(data, list):
            raise ClientError("protocol_error")
        identifiers: list[str] = []
        for item in data:
            if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                identifiers.append(item["id"])
        return tuple(identifiers)

    def chat_completions(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        settings: GenerationSettings,
        tools: Sequence[Mapping[str, Any]] | None = None,
    ) -> Completion:
        """Request one completion. Model-generated tools are returned but never invoked."""

        payload: dict[str, Any] = {
            "model": model,
            "messages": [dict(message) for message in messages],
            **settings.as_api_parameters(),
        }
        if tools:
            payload["tools"] = [dict(tool) for tool in tools]
            payload["tool_choice"] = "auto"
        decoded = self._request_json("POST", "/chat/completions", payload)
        choices = decoded.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ClientError("protocol_error")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, Mapping):
            raise ClientError("protocol_error")
        content_value = message.get("content")
        if content_value is None:
            content = ""
        elif isinstance(content_value, str):
            content = content_value
        else:
            raise ClientError("protocol_error")

        tool_calls: list[ToolCall] = []
        raw_tool_calls = message.get("tool_calls", [])
        if raw_tool_calls is None:
            raw_tool_calls = []
        if not isinstance(raw_tool_calls, list):
            raise ClientError("protocol_error")
        for call in raw_tool_calls:
            function = call.get("function") if isinstance(call, Mapping) else None
            if not isinstance(function, Mapping):
                raise ClientError("protocol_error")
            name = function.get("name")
            arguments = function.get("arguments")
            if not isinstance(name, str) or not isinstance(arguments, str):
                raise ClientError("protocol_error")
            tool_calls.append(ToolCall(name=name, arguments=arguments))

        raw_usage = decoded.get("usage")
        usage = Usage()
        if isinstance(raw_usage, Mapping):
            usage = Usage(
                prompt_tokens=_optional_nonnegative_int(raw_usage.get("prompt_tokens")),
                completion_tokens=_optional_nonnegative_int(raw_usage.get("completion_tokens")),
                total_tokens=_optional_nonnegative_int(raw_usage.get("total_tokens")),
            )
        finish_reason = choice.get("finish_reason")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise ClientError("protocol_error")
        runtime_model = decoded.get("model")
        if runtime_model is not None and not isinstance(runtime_model, str):
            runtime_model = None
        reasoning_present = _has_reasoning(message.get("reasoning_content")) or _has_reasoning(
            message.get("reasoning")
        )
        return Completion(
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            tool_calls=tuple(tool_calls),
            runtime_model=runtime_model,
            reasoning_present=reasoning_present,
        )


def _optional_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _has_reasoning(value: Any) -> bool:
    """Reduce runtime-specific reasoning fields to a transient presence bit."""

    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, Mapping)):
        return bool(value)
    return False
