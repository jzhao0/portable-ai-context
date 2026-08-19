from __future__ import annotations

import json
import urllib.error
import urllib.request

from portable_ai_context.errors import CompilerError


ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_API_BASE = "https://api.anthropic.com"
DEFAULT_ANTHROPIC_MAX_TOKENS = 4096

_SUCCESS_STOP_REASONS = frozenset({"end_turn", "stop_sequence"})
_INCOMPLETE_STOP_ERRORS = {
    "max_tokens": "anthropic backend output reached max_tokens",
    "refusal": "anthropic backend returned a refusal",
    "model_context_window_exceeded": "anthropic backend exceeded the model context window",
    "tool_use": "anthropic backend returned an unexpected tool-use result",
    "pause_turn": "anthropic backend returned an incomplete paused result",
}


class AnthropicBackend:
    """Minimal non-streaming Anthropic Messages API compiler backend."""

    def __init__(
        self,
        *,
        api_key: str,
        api_base: str = DEFAULT_ANTHROPIC_API_BASE,
        max_tokens: int = DEFAULT_ANTHROPIC_MAX_TOKENS,
        timeout: int = 300,
        api_version: str = ANTHROPIC_API_VERSION,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.api_version = api_version

    def _messages_url(self) -> str:
        if self.api_base.endswith("/v1"):
            return self.api_base + "/messages"
        return self.api_base + "/v1/messages"

    def complete(self, *, model: str, system: str, user: str, stage: str) -> str:
        payload = {
            "model": model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "stream": False,
            "temperature": 0.1,
        }
        request = urllib.request.Request(
            self._messages_url(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": self.api_key,
                "anthropic-version": self.api_version,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise CompilerError(f"anthropic backend HTTP status {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CompilerError("anthropic backend transport failed") from exc
        except Exception as exc:
            raise CompilerError("anthropic backend request failed") from exc

        try:
            data = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CompilerError("anthropic backend returned invalid JSON") from exc

        if not isinstance(data, dict):
            raise CompilerError("unexpected Anthropic response shape")
        stop_reason = data.get("stop_reason")
        content = data.get("content")
        if not isinstance(stop_reason, str) or not isinstance(content, list):
            raise CompilerError("unexpected Anthropic response shape")

        stop_error = _INCOMPLETE_STOP_ERRORS.get(stop_reason)
        if stop_error is not None:
            raise CompilerError(stop_error)
        if stop_reason not in _SUCCESS_STOP_REASONS:
            raise CompilerError("anthropic backend returned an unsupported stop reason")

        text_blocks: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                raise CompilerError("unexpected Anthropic response shape")
            if block.get("type") != "text":
                continue
            text = block.get("text")
            if not isinstance(text, str):
                raise CompilerError("unexpected Anthropic response shape")
            if text:
                text_blocks.append(text)

        text = "\n".join(text_blocks).strip()
        if not text:
            raise CompilerError("anthropic backend returned no text content")
        return text
