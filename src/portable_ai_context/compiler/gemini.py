from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from portable_ai_context.errors import CompilerError


DEFAULT_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MAX_OUTPUT_TOKENS = 4096
_MODEL_LEAF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_BLOCKED_FINISH_REASONS = frozenset(
    {
        "SAFETY",
        "RECITATION",
        "LANGUAGE",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "IMAGE_SAFETY",
        "IMAGE_PROHIBITED_CONTENT",
        "IMAGE_OTHER",
        "NO_IMAGE",
        "IMAGE_RECITATION",
        "ESCALATION",
    }
)
_NON_TEXT_OR_INCOMPLETE_FINISH_REASONS = frozenset(
    {
        "MALFORMED_FUNCTION_CALL",
        "UNEXPECTED_TOOL_CALL",
        "TOO_MANY_TOOL_CALLS",
        "MISSING_THOUGHT_SIGNATURE",
        "MALFORMED_RESPONSE",
    }
)


class GeminiBackend:
    """Minimal non-streaming Gemini generateContent compiler backend."""

    def __init__(
        self,
        *,
        api_key: str,
        api_base: str = DEFAULT_GEMINI_API_BASE,
        max_output_tokens: int = DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
        timeout: int = 300,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout

    @staticmethod
    def _normalize_model_path(model: str) -> str:
        if not isinstance(model, str):
            raise CompilerError("gemini backend model identifier is invalid")
        leaf = model[7:] if model.startswith("models/") else model
        if not _MODEL_LEAF_RE.fullmatch(leaf):
            raise CompilerError("gemini backend model identifier is invalid")
        return "models/" + leaf

    def _generate_url(self, model: str) -> str:
        model_path = self._normalize_model_path(model)
        return f"{self.api_base}/{model_path}:generateContent"

    def complete(self, *, model: str, system: str, user: str, stage: str) -> str:
        payload = {
            "system_instruction": {
                "parts": [{"text": system}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user}],
                }
            ],
            "generationConfig": {
                "candidateCount": 1,
                "maxOutputTokens": self.max_output_tokens,
                "temperature": 0.1,
                "responseMimeType": "text/plain",
            },
        }
        request = urllib.request.Request(
            self._generate_url(model),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise CompilerError(f"gemini backend HTTP status {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CompilerError("gemini backend transport failed") from exc
        except Exception as exc:
            raise CompilerError("gemini backend request failed") from exc

        try:
            data = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CompilerError("gemini backend returned invalid JSON") from exc

        if not isinstance(data, dict):
            raise CompilerError("unexpected Gemini response shape")

        candidates = data.get("candidates")
        if candidates == [] or candidates is None:
            prompt_feedback = data.get("promptFeedback")
            if isinstance(prompt_feedback, dict) and prompt_feedback.get("blockReason"):
                raise CompilerError("gemini backend prompt was blocked")
            raise CompilerError("gemini backend returned no candidate")
        if not isinstance(candidates, list) or len(candidates) != 1:
            raise CompilerError("unexpected Gemini response shape")

        candidate = candidates[0]
        if not isinstance(candidate, dict):
            raise CompilerError("unexpected Gemini response shape")
        finish_reason = candidate.get("finishReason")
        if not isinstance(finish_reason, str):
            raise CompilerError("unexpected Gemini response shape")
        if finish_reason == "MAX_TOKENS":
            raise CompilerError("gemini backend output reached maxOutputTokens")
        if finish_reason in _BLOCKED_FINISH_REASONS:
            raise CompilerError("gemini backend candidate was blocked")
        if finish_reason in _NON_TEXT_OR_INCOMPLETE_FINISH_REASONS:
            raise CompilerError("gemini backend returned a non-text or incomplete result")
        if finish_reason != "STOP":
            raise CompilerError("gemini backend returned an unsupported finish reason")

        content = candidate.get("content")
        if not isinstance(content, dict):
            raise CompilerError("unexpected Gemini response shape")
        parts = content.get("parts")
        if not isinstance(parts, list):
            raise CompilerError("unexpected Gemini response shape")

        text_parts: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                raise CompilerError("unexpected Gemini response shape")
            if "thought" in part and not isinstance(part["thought"], bool):
                raise CompilerError("unexpected Gemini response shape")
            if part.get("thought") is True:
                continue
            if "text" not in part:
                continue
            text = part.get("text")
            if not isinstance(text, str):
                raise CompilerError("unexpected Gemini response shape")
            if text:
                text_parts.append(text)

        text = "\n".join(text_parts).strip()
        if not text:
            raise CompilerError("gemini backend returned no text content")
        return text
