from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from portable_ai_context.errors import CompilerError


DEFAULT_OLLAMA_API_BASE = "http://localhost:11434"
DEFAULT_OLLAMA_NUM_PREDICT = 4096
_MAX_MODEL_NAME_CHARS = 256


def _validate_model_name(model: str) -> str:
    if not isinstance(model, str):
        raise CompilerError("ollama backend model identifier is invalid")
    if not model or len(model) > _MAX_MODEL_NAME_CHARS or model != model.strip():
        raise CompilerError("ollama backend model identifier is invalid")
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in model):
        raise CompilerError("ollama backend model identifier is invalid")
    return model


def _normalize_api_base(api_base: str) -> tuple[str, str]:
    if not isinstance(api_base, str) or not api_base or api_base != api_base.strip():
        raise CompilerError("ollama backend API base is invalid")
    try:
        parsed = urllib.parse.urlsplit(api_base)
    except ValueError as exc:
        raise CompilerError("ollama backend API base is invalid") from exc

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CompilerError("ollama backend API base is invalid")
    if parsed.username is not None or parsed.password is not None:
        raise CompilerError("ollama backend API base is invalid")
    if parsed.query or parsed.fragment:
        raise CompilerError("ollama backend API base is invalid")

    decoded_path = urllib.parse.unquote(parsed.path)
    if "\\" in decoded_path:
        raise CompilerError("ollama backend API base is invalid")
    path_parts = [part for part in decoded_path.split("/") if part]
    if any(part in {".", ".."} for part in path_parts):
        raise CompilerError("ollama backend API base is invalid")

    path = parsed.path.rstrip("/")
    if path.endswith("/api"):
        endpoint_path = path + "/chat"
    else:
        endpoint_path = path + "/api/chat"
    endpoint = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, endpoint_path, "", "")
    )
    normalized_base = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, "", "")
    )
    return normalized_base, endpoint


class OllamaBackend:
    """Minimal non-streaming native Ollama `/api/chat` compiler backend."""

    def __init__(
        self,
        *,
        api_base: str = DEFAULT_OLLAMA_API_BASE,
        api_key: str | None = None,
        num_predict: int = DEFAULT_OLLAMA_NUM_PREDICT,
        timeout: int = 300,
    ) -> None:
        normalized_base, chat_url = _normalize_api_base(api_base)
        self.api_base = normalized_base
        self.chat_url = chat_url
        self.api_key = api_key
        self.num_predict = num_predict
        self.timeout = timeout

    def complete(self, *, model: str, system: str, user: str, stage: str) -> str:
        safe_model = _validate_model_name(model)
        payload = {
            "model": safe_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": False,
            "options": {
                "num_predict": self.num_predict,
                "temperature": 0.1,
            },
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key is not None:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            self.chat_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise CompilerError(f"ollama backend HTTP status {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CompilerError("ollama backend transport failed") from exc
        except Exception as exc:
            raise CompilerError("ollama backend request failed") from exc

        try:
            data = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CompilerError("ollama backend returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise CompilerError("unexpected Ollama response shape")

        done = data.get("done")
        if done is not True:
            raise CompilerError("ollama backend returned an incomplete response")

        done_reason = data.get("done_reason")
        if done_reason is not None and not isinstance(done_reason, str):
            raise CompilerError("unexpected Ollama response shape")
        if done_reason == "length":
            raise CompilerError("ollama backend output reached num_predict")
        if done_reason not in {None, "", "stop"}:
            raise CompilerError("ollama backend returned an unsupported done reason")

        message = data.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise CompilerError("unexpected Ollama response shape")

        thinking = message.get("thinking")
        if thinking is not None and not isinstance(thinking, str):
            raise CompilerError("unexpected Ollama response shape")

        tool_calls = message.get("tool_calls")
        if tool_calls is not None:
            if not isinstance(tool_calls, list):
                raise CompilerError("unexpected Ollama response shape")
            if tool_calls:
                raise CompilerError("ollama backend returned an unexpected tool-use result")

        content = message.get("content")
        if not isinstance(content, str):
            raise CompilerError("unexpected Ollama response shape")
        text = content.strip()
        if not text:
            raise CompilerError("ollama backend returned no text content")
        return text
