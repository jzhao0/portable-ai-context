from __future__ import annotations

import json
import urllib.error
import urllib.request

from portable_ai_context.errors import CompilerError


class OpenAICompatibleBackend:
    def __init__(self, *, api_base: str, api_key: str, timeout: int = 300) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, *, model: str, system: str, user: str, stage: str) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
        }
        req = urllib.request.Request(
            self.api_base + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise CompilerError(f"compiler backend HTTP status {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CompilerError("compiler backend transport failed") from exc
        except Exception as exc:
            raise CompilerError("compiler backend request failed") from exc

        try:
            data = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CompilerError("compiler backend returned invalid JSON") from exc

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise CompilerError("unexpected OpenAI-compatible response shape") from exc
        if not isinstance(text, str) or not text.strip():
            raise CompilerError("compiler returned empty content")
        return text.strip()
